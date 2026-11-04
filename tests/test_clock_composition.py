# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare the owned first clock operation with complete calls and prefixes."""

import ctypes
import hashlib
import itertools
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import test_clock_driver as driver
from tests import test_clock_request as manager

ROOT = Path(__file__).resolve().parents[1]
Word, Byte = driver.Word, driver.Byte
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4


class Inputs(ctypes.Structure):
    _fields_ = [("request", manager.Inputs), ("helper_selection", Word),
                ("helper_gate", Word), ("helper_input", Word), ("diagnostic", Byte)]


class Plan(ctypes.Structure):
    _fields_ = [("source", driver.Plan), ("word", driver.Observer),
                ("divider", driver.Plan), ("acquire", manager.Provider),
                ("diagnostic", manager.Provider), ("release", manager.Provider),
                ("context", ctypes.c_void_p)]


class Result(ctypes.Structure):
    _fields_ = [(name, Word) for name in
                ("source_raw", "word_raw", "divider_raw", "manager_raw")]


def event_projection(event):
    if event["kind"] != "stub":
        return (driver.KINDS[event["kind"]], int(event["address"], 0),
                int.from_bytes(bytes.fromhex(event["hex"]), "little"))
    identity = int(event["entry"], 0)
    boundary = {0x0ED64D02: manager.ACQUIRE, 0x0ED17442: manager.DIAGNOSTIC,
                0x0ED64D3A: manager.RELEASE}[identity]
    words = tuple(int(word, 0) for word in event["arguments"])
    arguments = words + (0,) if boundary == manager.DIAGNOSTIC else words[:1]
    return ("boundary", boundary, identity, arguments, 0)


class Request:
    def __init__(self, case):
        self.case = case
        gp = int(case["setup"]["registers"]["gp"], 0)
        get = lambda offset, size=4: driver.fixture_word(case, "setup", gp + offset, size)
        request = manager.Inputs(0x30, 600000000, 0, 0, get(0xD33F8), get(0x1564),
                                 get(0x3E494), (Word * 3)(get(0xD1B80), get(0xD1B7C),
                                                        get(0xD1B78)),
                                 get(0x3B938), gp + 0x3E810)
        self.inputs = Inputs(request, get(0x1568), get(0xCC93C), get(0xCC940), get(0xCCE48, 1))
        self.manager_storage = driver.guarded((Byte * 1172)())
        self.manager = self.manager_storage.value
        self.manager[:1156] = driver.fixture_bytes(case, "setup", gp + 0x3E810, 1156)
        self.manager[1156:] = b"\x53" * 16
        self.state_storage = driver.guarded(manager.State(get(0x184C),
            (Byte * 86).from_buffer_copy(driver.fixture_bytes(case, "setup", gp + 0xD1B88, 86)),
            get(0xD1BE4), get(0xD1BE0)))
        self.source_storage = driver.guarded(driver.SourceState(get(0x3E6AC),
                                                get(0x3E6B0, 8), get(0x3E4A8, 8)))
        self.divider_storage = driver.guarded(driver.DividerState(get(0x3E72C), get(0x3E730)))
        self.cell_storage = driver.guarded(Word(driver.fixture_word(case, "setup", 0x0EE056B0)))
        self.output_storage = (Byte * 48).from_buffer_copy(
            driver.fixture_bytes(case, "setup", 0x24020000, 48))
        self.output = ctypes.cast(ctypes.byref(self.output_storage, 16), manager.BytePointer)
        self.result_storage = driver.guarded(Result(*([driver.SENTINEL] * 4)))
        self.state, self.source, self.divider = (self.state_storage.value,
                                                self.source_storage.value,
                                                self.divider_storage.value)
        self.cell, self.result = (driver.value_pointer(self.cell_storage),
                                 driver.value_pointer(self.result_storage))
        responses = case["execution"]["mmio_responses"]
        arrays = []
        for records in (responses[:-5], responses[-5:]):
            arrays.append((driver.Read * len(records))(*(driver.Read(int(read["address"], 0),
                int.from_bytes(bytes.fromhex(read["hex"]), "little")) for read in records)))
        self.source_reads, self.divider_reads = arrays
        self.events, self.snapshots, self.contexts = [], [], []
        self.bookkeeping = Word()
        self.callback = driver.Observe(self.observe)
        self.provider = manager.Provider(self.boundary)
        observer = driver.Observer(self.callback, ctypes.addressof(self.bookkeeping))
        self.plan = Plan(driver.Plan(self.source_reads, len(self.source_reads), observer),
                         observer, driver.Plan(self.divider_reads, len(self.divider_reads), observer),
                         self.provider, self.provider, self.provider, ctypes.addressof(self.bookkeeping))

    def snapshot(self):
        return tuple(bytes(value) for value in (self.manager, self.state, self.source, self.divider,
                     self.cell.contents, self.output_storage, self.result.contents))

    def record(self, context, event):
        self.contexts.append(context)
        self.events.append(event)
        self.snapshots.append(self.snapshot())
        self.bookkeeping.value += 1

    def observe(self, context, kind, address, word):
        self.record(context, (kind, address, word))

    def boundary(self, context, boundary, identity, arguments, count, reply):
        self.record(context, ("boundary", boundary, identity, tuple(arguments[:count]), reply))

    def arguments(self):
        return [ctypes.byref(self.inputs), self.manager, len(self.manager), ctypes.byref(self.state),
                ctypes.byref(self.source), ctypes.byref(self.divider), self.cell, self.output, 32,
                ctypes.byref(self.plan), self.result]

    def storage(self):
        return tuple(bytes(value) for value in (self.inputs, self.manager_storage, self.state_storage,
            self.source_storage, self.divider_storage, self.cell_storage, self.output_storage,
            self.result_storage, self.source_reads, self.divider_reads, self.plan))


class ClockCompositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Clock-composition tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="clock-composition-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "clock_composition.so"
        subprocess.run(compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/clock_composition.c"),
            str(ROOT / "src/start4/clock_driver.c"), "-o", str(library),
        ], check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.clock_composition_execute
        cls.function.argtypes = [ctypes.POINTER(Inputs), manager.BytePointer, ctypes.c_size_t,
            ctypes.POINTER(manager.State), ctypes.POINTER(driver.SourceState),
            ctypes.POINTER(driver.DividerState), driver.WordPointer, manager.BytePointer,
            ctypes.c_size_t, ctypes.POINTER(Plan), ctypes.POINTER(Result)]
        cls.function.restype = ctypes.c_int
        cls.cases = json.loads((ROOT / "tests/vectors/start4/clock-composition.json").read_text())["cases"]

    def request(self, index=0):
        return Request(self.cases[index])

    def run_request(self, request, status=OK, arguments=None):
        before = request.storage()
        actual = self.function(*(request.arguments() if arguments is None else arguments))
        self.assertEqual(actual, status)
        if status != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.events, [])
        else:
            after = request.storage()
            self.assertEqual((after[0], after[8:]), (before[0], before[8:]))
        for storage in (request.manager_storage, request.state_storage, request.source_storage,
                        request.divider_storage, request.cell_storage, request.result_storage):
            self.assertEqual((storage.before, storage.after), (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        self.assertEqual(bytes(request.manager[1156:]), b"\x53" * 16)
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)] * len(request.events))
        self.assertEqual(request.bookkeeping.value, len(request.events))
        self.assertTrue(all(snapshot[-1] == bytes(Result(*([driver.SENTINEL] * 4)))
                            for snapshot in request.snapshots))

    def compare_memory(self, case, snapshot):
        actual_manager, state_bytes, source_bytes, divider_bytes, cell, output, _ = snapshot
        state = manager.State.from_buffer_copy(state_bytes)
        source = driver.SourceState.from_buffer_copy(source_bytes)
        divider = driver.DividerState.from_buffer_copy(divider_bytes)
        patches = {0xE403E810: actual_manager[:1156], 0xE400184C: state.initialized.to_bytes(4, "little"),
                   0xE40D1B88: bytes(state.descriptor_miss),
                   0xE40D1BE4: state.divider_miss.to_bytes(4, "little"),
                   0xE40D1BE0: state.source_miss.to_bytes(4, "little"),
                   0xE403E6AC: source.marker.to_bytes(4, "little"),
                   0xE403E6B0: source.requested.to_bytes(8, "little"),
                   0xE403E4A8: source.cached.to_bytes(8, "little"),
                   0xE403E72C: divider.marker.to_bytes(4, "little"),
                   0xE403E730: divider.count.to_bytes(4, "little"),
                   0x0EE056B0: cell, 0x24020000: output}
        for region in case["expected"]["memory"]:
            address = int(region["address"], 0)
            if address in (0x2400F000, 0x24010000):
                continue
            expected = bytes.fromhex(region["hex"])
            actual = bytearray(driver.fixture_bytes(case, "setup", address, len(expected)))
            for field, value in patches.items():
                if address <= field and field + len(value) <= address + len(actual):
                    actual[field - address:field - address + len(value)] = value
            self.assertEqual(actual, expected, f"{case['id']}: {address:#x}")

    def test_complete_events_state_and_source_return_prefixes(self):
        path = ROOT / "tests/vectors/start4/clock-composition.json"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "392fb2777fd26be429765748d346558cff34e83542ca8c50997fa04d79b00ad4")
        for index, case in enumerate(self.cases[:2]):
            with self.subTest(case=case["id"]):
                request = self.request(index)
                self.run_request(request)
                self.assertEqual(request.events, list(map(event_projection, case["expected"]["events"])))
                self.compare_memory(case, request.snapshot())
                result = request.result.contents
                self.assertEqual((result.source_raw, result.word_raw, result.divider_raw,
                                  result.manager_raw), (4 if index else 0, 0, 0, 0))
                prefix = self.cases[index + 2]
                prefix_events = list(map(event_projection, prefix["expected"]["events"]))
                self.assertEqual(request.events[:len(prefix_events)], prefix_events)
                self.compare_memory(prefix, request.snapshots[len(prefix_events) - 1])
                self.assertEqual(result.source_raw, int(prefix["expected"]["registers"]["r0"], 0))

    def test_observer_visible_transition_order(self):
        for index in range(2):
            request = self.request(index)
            initial = request.snapshot()
            self.run_request(request)
            source_end = len(self.cases[index + 2]["expected"]["events"])
            for position, (event, snapshot) in enumerate(zip(request.events, request.snapshots)):
                memory, misses, source, divider, cell, output, _ = snapshot
                get = lambda offset, size=8, data=memory: int.from_bytes(data[offset:offset + size], "little")
                if position < 2:
                    self.assertEqual(snapshot, initial)
                    continue
                state = manager.State.from_buffer_copy(misses)
                self.assertEqual(bytes(state.descriptor_miss), bytes(0x30) + b"\x01" + bytes(37))
                self.assertEqual((state.divider_miss, state.source_miss), (0x20, 0x80))
                self.assertEqual(get(0x188, 4), 2)
                source_state = driver.SourceState.from_buffer_copy(source)
                self.assertEqual((source_state.marker, source_state.requested, source_state.cached),
                                 (1, 1200000000, 1200000000))
                if position < source_end:
                    self.assertEqual((get(0x44), get(0x11C), get(0x334)), (0, 0, 500000000))
                    self.assertEqual((divider, cell, output), (initial[3], initial[4], initial[5]))
                elif position < len(request.events) - 1:
                    self.assertEqual((get(0x44), get(0x11C), get(0x334)),
                                     (1200000000, 600000000, 500000000))
                    self.assertEqual(output, initial[5])
                    if event[0] in (driver.NATIVE_READ, driver.NATIVE_WRITE):
                        self.assertEqual(int.from_bytes(cell, "little"), event[2])
                        self.assertEqual(divider, initial[3])
                    else:
                        state = driver.DividerState.from_buffer_copy(divider)
                        self.assertEqual((state.marker, state.count), (1, 2))
                        self.assertEqual(int.from_bytes(cell, "little"), 0x5A000000)
                else:
                    self.assertEqual(get(0x334), 600000000)
                    self.assertEqual(int.from_bytes(output[16:24], "little"), 600000000)

    def test_missing_objects_and_every_reachable_observer(self):
        for argument in (0, 1, 3, 4, 5, 6, 7, 9, 10):
            request = self.request()
            arguments = request.arguments()
            arguments[argument] = None
            self.run_request(request, INVALID, arguments)
        for path in ("source", "word", "divider", "acquire", "diagnostic", "release"):
            request = self.request()
            if path in ("source", "divider"):
                getattr(request.plan, path).observer.observe = driver.Observe()
            elif path == "word":
                request.plan.word.observe = driver.Observe()
            else:
                setattr(request.plan, path, manager.Provider())
            self.run_request(request, INVALID)
        for path in ("source", "divider"):
            request = self.request()
            getattr(request.plan, path).reads = ctypes.POINTER(driver.Read)()
            self.run_request(request, INVALID)

    def test_pairwise_object_and_plan_array_overlap(self):
        indices = (0, 1, 3, 4, 5, 6, 7, 9, 10)
        for left, right in itertools.combinations(indices, 2):
            request = self.request()
            arguments = request.arguments()
            arguments[right] = ctypes.cast(arguments[left], self.function.argtypes[right])
            self.run_request(request, OVERLAP, arguments)
        for path in ("source", "divider"):
            for index in indices:
                request = self.request()
                getattr(request.plan, path).reads = ctypes.cast(request.arguments()[index],
                                                                ctypes.POINTER(driver.Read))
                self.run_request(request, OVERLAP)
        request = self.request()
        request.plan.divider.reads = request.plan.source.reads
        self.run_request(request, OVERLAP)

    def test_full_declared_extents_and_address_wrap(self):
        maximum = ctypes.c_size_t(-1).value
        for index in (0, 1, 3, 4, 5, 6, 7, 9, 10):
            request = self.request()
            arguments = request.arguments()
            arguments[index] = ctypes.cast(maximum - 1, self.function.argtypes[index])
            self.run_request(request, BOUNDS, arguments)
        for length_index, length in ((2, 1155), (8, 7), (2, maximum), (8, maximum)):
            request = self.request()
            arguments = request.arguments()
            arguments[length_index] = length
            self.run_request(request, BOUNDS, arguments)
        for path in ("source", "divider"):
            request = self.request()
            getattr(request.plan, path).count = maximum
            self.run_request(request, BOUNDS)
            request = self.request()
            getattr(request.plan, path).reads = ctypes.cast(maximum - 3, ctypes.POINTER(driver.Read))
            self.run_request(request, BOUNDS)
        for span_index, length_index, offset in ((1, 2, 1156), (7, 8, 8)):
            for target in (0, 3, 4, 5, 6, 9, 10, "source", "divider"):
                request = self.request()
                arguments = request.arguments()
                pointer = ctypes.cast(arguments[span_index], ctypes.c_void_p).value + offset
                if isinstance(target, str):
                    getattr(request.plan, target).reads = ctypes.cast(pointer, ctypes.POINTER(driver.Read))
                else:
                    arguments[target] = ctypes.cast(pointer, self.function.argtypes[target])
                self.assertGreater(arguments[length_index], offset)
                self.run_request(request, OVERLAP, arguments)

    def test_every_entry_field_and_manager_byte_is_checked(self):
        for name, _ in manager.Inputs._fields_:
            if name in ("override_heads", "mutex_identity"):
                continue
            request = self.request()
            setattr(request.inputs.request, name, getattr(request.inputs.request, name) ^ 0x40)
            self.run_request(request, UNSUPPORTED)
        for name in ("helper_selection", "helper_gate", "helper_input", "diagnostic"):
            request = self.request()
            setattr(request.inputs, name, getattr(request.inputs, name) ^ 0x40)
            self.run_request(request, UNSUPPORTED)
        for index in range(3):
            request = self.request()
            request.inputs.request.override_heads[index] = 1
            self.run_request(request, UNSUPPORTED)
        request = self.request()
        for index in range(1156):
            request.manager[index] ^= 1
            self.run_request(request, UNSUPPORTED)
            request.manager[index] ^= 1
        for field in ("initialized", "divider_miss", "source_miss"):
            request = self.request()
            setattr(request.state, field, getattr(request.state, field) ^ 1)
            self.run_request(request, UNSUPPORTED)
        request = self.request()
        for index in range(86):
            request.state.descriptor_miss[index] = 1
            self.run_request(request, UNSUPPORTED)
            request.state.descriptor_miss[index] = 0
        for storage_name in ("source", "divider"):
            for field, _ in getattr(self.request(), storage_name)._fields_:
                request = self.request()
                storage = getattr(request, storage_name)
                setattr(storage, field, getattr(storage, field) ^ 1)
                self.run_request(request, UNSUPPORTED)
        for value in (1, 0x10, 0x80, 0x12345678, 0x5A000000):
            request = self.request()
            request.cell[0] = value
            self.run_request(request, UNSUPPORTED)

    def test_complete_later_plans_preflight_before_any_effect(self):
        for case_index in range(2):
            for path in ("source", "divider"):
                request = self.request(case_index)
                reads = getattr(request, f"{path}_reads")
                for index in range(len(reads)):
                    for field in ("address", "word"):
                        original = getattr(reads[index], field)
                        setattr(reads[index], field, original ^ 0x80000000)
                        self.run_request(request, UNSUPPORTED)
                        setattr(reads[index], field, original)
                for count in (0, 1, len(reads) - 1):
                    request = self.request(case_index)
                    getattr(request.plan, path).count = count
                    expected = BOUNDS if count < (7 if path == "source" else 5) else UNSUPPORTED
                    self.run_request(request, expected)
                request = self.request(case_index)
                extra = (driver.Read * (len(reads) + 1))(*reads, driver.Read(0, 0))
                getattr(request.plan, path).reads = extra
                getattr(request.plan, path).count = len(extra)
                self.run_request(request, UNSUPPORTED)
        request = self.request()
        request.divider_reads[-1].word = 0x0034567A
        self.run_request(request, UNSUPPORTED)

    def test_repeated_state_is_unsupported(self):
        request = self.request()
        self.run_request(request)
        request.events.clear()
        request.snapshots.clear()
        request.contexts.clear()
        request.bookkeeping.value = 0
        self.run_request(request, UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
