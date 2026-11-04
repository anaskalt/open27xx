# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare complete resource calls and callback-visible store ordering."""

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

from tests import test_arm_control as arm
from tests import test_clock_composition as clock
from tests import test_clock_driver as driver
from tests import test_clock_request as manager
from tests import test_resource_request as resource

ROOT = Path(__file__).resolve().parents[1]
Word, Byte = driver.Word, driver.Byte
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
Provider = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, driver.WordPointer,
                           ctypes.c_size_t, Word)


class Inputs(ctypes.Structure):
    _fields_ = [("request", resource.Inputs)] + [(name, Word) for name in
        ("table", "selection", "skip", "outer_mutex", "resource_mutex")]
    _fields_ += [("configuration", arm.Configuration), ("clock", clock.Inputs)]


class State(ctypes.Structure):
    _fields_ = [(name, Word) for name in ("held", "aggregate", "prehook")]


class Plan(ctypes.Structure):
    _fields_ = [("clock", clock.Plan), ("control", driver.Plan * 2), ("final", driver.Plan)]
    _fields_ += [(name, Provider) for name in ("diagnostic", "acquire", "release", "service")]
    _fields_ += [("context", ctypes.c_void_p)]


class Result(ctypes.Structure):
    _fields_ = [("first_clock", clock.Result)] + [(name, Word) for name in
        ("repeated_word_raw", "repeated_manager_raw", "resource_raw")]


def event_projection(event):
    if event["kind"] != "stub":
        return (driver.KINDS[event["kind"]], int(event["address"], 0),
                int.from_bytes(bytes.fromhex(event["hex"]), "little"))
    identity = int(event["entry"], 0)
    arguments = tuple(int(word, 0) for word in event["arguments"])
    if identity in (0x0ED64D02, 0x0ED64D3A):
        arguments = arguments[:1]
    elif identity == 0x0ED17442 and arguments[1] == 0x0EC7EF38:
        arguments += (0,)
    return ("boundary", identity, arguments, 0)


class Request:
    def __init__(self, case, *, identity=None, scratch_address=0x2400FF88):
        self.case = case
        gp = int(case["setup"]["registers"]["gp"], 0)
        get = lambda offset, size=4: driver.fixture_word(case, "setup", gp + offset, size)
        request = manager.Inputs(0x30, 600000000, 0, 0, get(0xD33F8), get(0x1564),
            get(0x3E494), (Word * 3)(get(0xD1B80), get(0xD1B7C), get(0xD1B78)),
            get(0x3B938), gp + 0x3E810)
        clock_inputs = clock.Inputs(request, get(0x1568), get(0xCC93C), get(0xCC940), get(0xCCE48, 1))
        resource_inputs = resource.Inputs(1, int(case["setup"]["registers"]["r0"], 0) if identity is None else identity,
            0, 23, 1, 1, get(0xCD4), get(0xDA988), gp + 0xDA4C0)
        self.inputs = Inputs(resource_inputs, get(0xDA984), get(0x1564), get(0xD33F8),
            gp + 0xFD4, gp + 0xD33EC,
            arm.Configuration(*(get(offset) for offset in arm.CONFIGURATION_FIELDS.values())),
            clock_inputs)
        values = {
            "records": (Byte * 912).from_buffer_copy(
                driver.fixture_bytes(case, "setup", gp + 0xDA4C4, 896) + b"\x53" * 16),
            "resource": State(get(0xDA98C), driver.fixture_word(case, "setup", get(0x14B0)), get(0xD33FC)),
            "manager": (Byte * 1172).from_buffer_copy(
                driver.fixture_bytes(case, "setup", gp + 0x3E810, 1156) + b"\x53" * 16),
            "state": manager.State(get(0x184C), (Byte * 86).from_buffer_copy(
                driver.fixture_bytes(case, "setup", gp + 0xD1B88, 86)), get(0xD1BE4), get(0xD1BE0)),
            "source": driver.SourceState(get(0x3E6AC), get(0x3E6B0, 8), get(0x3E4A8, 8)),
            "divider": driver.DividerState(get(0x3E72C), get(0x3E730)),
            "cell": Word(driver.fixture_word(case, "setup", 0x0EE056B0)),
            "scratch": (Byte * 24).from_buffer_copy(
                driver.fixture_bytes(case, "setup", scratch_address, 8) + b"\x53" * 16),
            "result": Result(clock.Result(*([driver.SENTINEL] * 4)), *([driver.SENTINEL] * 3)),
        }
        self.guards = {name: driver.guarded(value) for name, value in values.items()}
        for name, storage in self.guards.items():
            if name in ("cell", "result"):
                setattr(self, name, driver.value_pointer(storage))
            else:
                setattr(self, name, storage.value)
        responses = case["execution"]["mmio_responses"]
        source_count = len(responses) - 58
        lengths = (source_count, 5, 24, 24, 5)
        self.arrays = []
        position = 0
        for length in lengths:
            records = responses[position:position + length]
            self.arrays.append((driver.Read * length)(*(driver.Read(int(read["address"], 0),
                int.from_bytes(bytes.fromhex(read["hex"]), "little")) for read in records)))
            position += length
        self.events, self.snapshots, self.contexts = [], [], []
        self.bookkeeping = Word()
        self.callback = driver.Observe(self.observe)
        self.provider = Provider(self.boundary)
        self.clock_provider = manager.Provider(self.clock_boundary)
        context = ctypes.addressof(self.bookkeeping)
        observer = driver.Observer(self.callback, context)
        plans = [driver.Plan(array, len(array), observer) for array in self.arrays]
        self.plan = Plan(clock.Plan(plans[0], observer, plans[1], self.clock_provider,
            self.clock_provider, self.clock_provider, context), (driver.Plan * 2)(*plans[2:4]),
            plans[4], self.provider, self.provider, self.provider, self.provider, context)

    def snapshot(self):
        return {name: bytes(driver.value_pointer(storage).contents)
                for name, storage in self.guards.items()}

    def record(self, context, event):
        self.contexts.append(context)
        self.events.append(event)
        self.snapshots.append(self.snapshot())
        self.bookkeeping.value += 1

    def observe(self, context, kind, address, word):
        self.record(context, (kind, address, word))

    def boundary(self, context, identity, arguments, count, reply):
        self.record(context, ("boundary", identity, tuple(arguments[:count]), reply))

    def clock_boundary(self, context, boundary, identity, arguments, count, reply):
        self.boundary(context, identity, arguments, count, reply)

    def arguments(self):
        return [ctypes.byref(self.inputs), self.records, len(self.records), ctypes.byref(self.resource),
            self.manager, len(self.manager), ctypes.byref(self.state), ctypes.byref(self.source),
            ctypes.byref(self.divider), self.cell, self.scratch, len(self.scratch),
            ctypes.byref(self.plan), self.result]

    def plans(self):
        return [self.plan.clock.source, self.plan.clock.divider,
                self.plan.control[0], self.plan.control[1], self.plan.final]

    def storage(self):
        return tuple(bytes(value) for value in (self.inputs, self.plan, *self.arrays,
                                               *self.guards.values()))


class ResourceCompositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Resource-composition tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="resource-composition-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "resource_composition.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            *(str(ROOT / "src/start4" / name) for name in
              ("resource_composition.c", "clock_composition.c", "clock_driver.c", "arm_control.c")),
            "-o", str(library)], check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.resource_composition_execute
        cls.function.argtypes = [ctypes.POINTER(Inputs), manager.BytePointer, ctypes.c_size_t,
            ctypes.POINTER(State), manager.BytePointer, ctypes.c_size_t, ctypes.POINTER(manager.State),
            ctypes.POINTER(driver.SourceState), ctypes.POINTER(driver.DividerState), driver.WordPointer,
            manager.BytePointer, ctypes.c_size_t, ctypes.POINTER(Plan), ctypes.POINTER(Result)]
        cls.function.restype = ctypes.c_int
        cls.cases = json.loads((ROOT / "tests/vectors/start4/resource-composition.json").read_text())["cases"]

    def request(self, index=0):
        return Request(self.cases[index])

    def run_request(self, request, status=OK, arguments=None):
        before = request.storage()
        self.assertEqual(self.function(*(request.arguments() if arguments is None else arguments)), status)
        if status != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.events, [])
        else:
            self.assertEqual(request.storage()[:7], before[:7])
        for storage in request.guards.values():
            self.assertEqual((storage.before, storage.after), (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        for name, offset in (("records", 896), ("manager", 1156), ("scratch", 8)):
            self.assertEqual(bytes(getattr(request, name)[offset:]), b"\x53" * 16)
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)] * len(request.events))
        self.assertEqual(request.bookkeeping.value, len(request.events))
        self.assertTrue(all(snapshot["result"] == bytes([0xA5]) * ctypes.sizeof(Result)
                            for snapshot in request.snapshots))

    def compare_memory(self, request):
        case, snapshot = request.case, request.snapshot()
        state, source, divider = request.state, request.source, request.divider
        patches = {0xE40DA4C4: snapshot["records"][:896],
            0xE40DA98C: request.resource.held.to_bytes(4, "little"),
            0x24020010: request.resource.aggregate.to_bytes(4, "little"),
            0xE40D33FC: request.resource.prehook.to_bytes(4, "little"),
            0xE403E810: snapshot["manager"][:1156], 0xE400184C: state.initialized.to_bytes(4, "little"),
            0xE40D1B88: bytes(state.descriptor_miss),
            0xE40D1BE4: state.divider_miss.to_bytes(4, "little"),
            0xE40D1BE0: state.source_miss.to_bytes(4, "little"),
            0xE403E6AC: source.marker.to_bytes(4, "little"),
            0xE403E6B0: source.requested.to_bytes(8, "little"),
            0xE403E4A8: source.cached.to_bytes(8, "little"),
            0xE403E72C: divider.marker.to_bytes(4, "little"),
            0xE403E730: divider.count.to_bytes(4, "little"),
            0x0EE056B0: snapshot["cell"], 0x2400FF88: snapshot["scratch"][:8]}
        for region in case["expected"]["memory"]:
            address = int(region["address"], 0)
            expected = bytes.fromhex(region["hex"])
            actual = bytearray(driver.fixture_bytes(case, "setup", address, len(expected)))
            for field, value in patches.items():
                if address <= field and field + len(value) <= address + len(actual):
                    actual[field - address:field - address + len(value)] = value
            self.assertEqual(actual, expected, f"{case['id']}: {address:#x}")

    def test_complete_fixture_events_and_final_memory(self):
        path = ROOT / "tests/vectors/start4/resource-composition.json"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "1f6df457d17a969dcbd429b08dc1a7cc78ee72a49adc8c1ba3dcae7d5a310c2d")
        for index, case in enumerate(self.cases):
            with self.subTest(case=case["id"]):
                request = self.request(index)
                self.run_request(request)
                self.assertEqual(request.events, list(map(event_projection, case["expected"]["events"])))
                self.compare_memory(request)
                result = request.result.contents
                self.assertEqual(tuple(getattr(result.first_clock, field) for field, _ in clock.Result._fields_),
                                 (4 if index else 0, 0, 0, 0))
                self.assertEqual((result.repeated_word_raw, result.repeated_manager_raw, result.resource_raw),
                                 (0, 0, int(case["expected"]["registers"]["r0"], 0)))
                for kind, count in ((driver.MMIO_READ, 2064 if index else 65), (driver.MMIO_WRITE, 58),
                                    (driver.NATIVE_READ, 6), (driver.NATIVE_WRITE, 2), ("boundary", 23)):
                    self.assertEqual(sum(event[0] == kind for event in request.events), count)

    def test_store_order_and_shared_scratch_visibility(self):
        for case_index in range(2):
            request = self.request(case_index)
            initial = request.snapshot()
            self.run_request(request)
            source_end = 16 + len(request.arrays[0]) + 3
            first_release = source_end + 4 + 13
            second_acquire = first_release + 47
            second_release = second_acquire + 6
            completed = request.snapshots[first_release]
            for index, (event, snapshot) in enumerate(zip(request.events, request.snapshots)):
                state = State.from_buffer_copy(snapshot["resource"])
                word = lambda field, offset=0, size=4, data=snapshot: int.from_bytes(
                    data[field][offset:offset + size], "little")
                self.assertEqual(state.held, 0)
                if index < 2:
                    self.assertEqual(snapshot, initial)
                    continue
                self.assertEqual((word("records", 8), state.aggregate), (0x800000, 0x180))
                self.assertEqual(state.prehook, 0 if index < 4 else 0x80 if index < 8 else 0x180)
                if index < 14:
                    self.assertEqual(snapshot["scratch"], initial["scratch"])
                    self.assertEqual(snapshot["manager"], initial["manager"])
                    continue
                expected_scratch = 0 if index < first_release or second_acquire <= index < second_release else 600000000
                self.assertEqual(word("scratch", size=8), expected_scratch)
                if index < 16:
                    for field in ("manager", "state", "source", "divider", "cell"):
                        self.assertEqual(snapshot[field], initial[field])
                    continue
                misses = manager.State.from_buffer_copy(snapshot["state"])
                self.assertEqual(bytes(misses.descriptor_miss), bytes(0x30) + b"\x01" + bytes(37))
                self.assertEqual((misses.divider_miss, misses.source_miss), (0x20, 0x80))
                self.assertEqual(word("manager", 0x188), 2)
                source = driver.SourceState.from_buffer_copy(snapshot["source"])
                self.assertEqual((source.marker, source.requested, source.cached),
                                 (1, 1200000000, 1200000000))
                if index < source_end:
                    self.assertEqual(tuple(word("manager", offset, 8) for offset in (0x44, 0x11C, 0x334)),
                                     (0, 0, 500000000))
                    self.assertEqual(snapshot["divider"], initial["divider"])
                    self.assertEqual(snapshot["cell"], initial["cell"])
                elif index < first_release:
                    self.assertEqual(tuple(word("manager", offset, 8) for offset in (0x44, 0x11C, 0x334)),
                                     (1200000000, 600000000, 500000000))
                    if index < source_end + 4:
                        self.assertEqual(snapshot["divider"], initial["divider"])
                    else:
                        divider = driver.DividerState.from_buffer_copy(snapshot["divider"])
                        self.assertEqual((divider.marker, divider.count), (1, 2))
                else:
                    for field in ("manager", "state", "source", "divider", "cell"):
                        self.assertEqual(snapshot[field], completed[field])
                if event[0] in (driver.NATIVE_READ, driver.NATIVE_WRITE):
                    self.assertEqual(word("cell"), event[2])

    def test_required_objects_observers_and_read_arrays(self):
        for index in (0, 1, 3, 4, 6, 7, 8, 9, 10, 12, 13):
            request = self.request()
            arguments = request.arguments()
            arguments[index] = None
            self.run_request(request, INVALID, arguments)
        for name in ("diagnostic", "acquire", "release", "service"):
            request = self.request()
            setattr(request.plan, name, Provider())
            self.run_request(request, INVALID)
        for name in ("diagnostic", "acquire", "release"):
            request = self.request()
            setattr(request.plan.clock, name, manager.Provider())
            self.run_request(request, INVALID)
        request = self.request()
        request.plan.clock.word.observe = driver.Observe()
        self.run_request(request, INVALID)
        for index in range(5):
            request = self.request()
            request.plans()[index].observer.observe = driver.Observe()
            self.run_request(request, INVALID)
            request = self.request()
            request.plans()[index].reads = ctypes.POINTER(driver.Read)()
            self.run_request(request, INVALID)

    def test_all_object_and_read_array_pairs_are_disjoint(self):
        indices = (0, 1, 3, 4, 6, 7, 8, 9, 10, 12, 13)
        for left, right in itertools.combinations(indices, 2):
            request = self.request()
            arguments = request.arguments()
            arguments[right] = ctypes.cast(arguments[left], self.function.argtypes[right])
            self.run_request(request, OVERLAP, arguments)
        for plan_index in range(5):
            for object_index in indices:
                request = self.request()
                request.plans()[plan_index].reads = ctypes.cast(request.arguments()[object_index],
                                                               ctypes.POINTER(driver.Read))
                self.run_request(request, OVERLAP)
        for left, right in itertools.combinations(range(5), 2):
            request = self.request()
            request.plans()[right].reads = request.plans()[left].reads
            self.run_request(request, OVERLAP)

    def test_full_span_tails_lengths_and_overflow(self):
        maximum = ctypes.c_size_t(-1).value
        indices = (0, 1, 3, 4, 6, 7, 8, 9, 10, 12, 13)
        for index in indices:
            request = self.request()
            arguments = request.arguments()
            arguments[index] = ctypes.cast(maximum - 1, self.function.argtypes[index])
            self.run_request(request, BOUNDS, arguments)
        for span, length, minimum in ((1, 2, 896), (4, 5, 1156), (10, 11, 8)):
            for size in (0, minimum - 1, maximum):
                request = self.request()
                arguments = request.arguments()
                arguments[length] = size
                self.run_request(request, BOUNDS, arguments)
            for target in [index for index in indices if index != span] + list(range(20, 25)):
                request = self.request()
                arguments = request.arguments()
                pointer = ctypes.cast(arguments[span], ctypes.c_void_p).value + minimum
                if target >= 20:
                    request.plans()[target - 20].reads = ctypes.cast(pointer, ctypes.POINTER(driver.Read))
                else:
                    arguments[target] = ctypes.cast(pointer, self.function.argtypes[target])
                self.run_request(request, OVERLAP, arguments)
        for index in range(5):
            request = self.request()
            request.plans()[index].count = maximum
            self.run_request(request, BOUNDS)
            request = self.request()
            request.plans()[index].reads = ctypes.cast(maximum - 3, ctypes.POINTER(driver.Read))
            self.run_request(request, BOUNDS)

    def test_every_read_is_validated_before_initial_diagnostic(self):
        for case_index in range(2):
            request = self.request(case_index)
            for reads in request.arrays:
                for index in range(len(reads)):
                    for field in ("address", "word"):
                        original = getattr(reads[index], field)
                        setattr(reads[index], field, original ^ 0x80000000)
                        self.run_request(request, UNSUPPORTED)
                        setattr(reads[index], field, original)
            for index in range(5):
                request = self.request(case_index)
                plan = request.plans()[index]
                plan.count = 0
                self.run_request(request, BOUNDS)
                request = self.request(case_index)
                plan = request.plans()[index]
                plan.count -= 1
                self.run_request(request, UNSUPPORTED if index == 0 and case_index else BOUNDS)
                request = self.request(case_index)
                reads = request.arrays[index]
                extra = (driver.Read * (len(reads) + 1))(*reads, driver.Read(0, 0))
                plan = request.plans()[index]
                plan.reads, plan.count = extra, len(extra)
                self.run_request(request, UNSUPPORTED)

    def test_fixed_inputs_records_and_state(self):
        groups = (("request", resource.Inputs, {"mutex_identity"}),
                  ("configuration", arm.Configuration, set()))
        for group, structure, excluded in groups:
            for name, _ in structure._fields_:
                if name in excluded:
                    continue
                request = self.request()
                target = getattr(request.inputs, group)
                setattr(target, name, getattr(target, name) ^ 0x40)
                self.run_request(request, UNSUPPORTED)
        for name in ("table", "selection", "skip"):
            request = self.request()
            setattr(request.inputs, name, getattr(request.inputs, name) ^ 0x40)
            self.run_request(request, UNSUPPORTED)
        request = self.request()
        for index in range(896):
            request.records[index] ^= 1
            self.run_request(request, UNSUPPORTED)
            request.records[index] ^= 1
        for name in ("held", "prehook"):
            request = self.request()
            setattr(request.resource, name, 1)
            self.run_request(request, UNSUPPORTED)
        for left, right in itertools.combinations(range(4), 2):
            request = self.request()
            objects = [(request.inputs.request, "mutex_identity"), (request.inputs, "outer_mutex"),
                       (request.inputs, "resource_mutex"), (request.inputs.clock.request, "mutex_identity")]
            target, name = objects[right]
            setattr(target, name, getattr(*objects[left]))
            self.run_request(request, UNSUPPORTED)
        request = self.request()
        self.run_request(request)
        request.events.clear()
        request.snapshots.clear()
        request.contexts.clear()
        request.bookkeeping.value = 0
        self.run_request(request, UNSUPPORTED)

    def test_entire_first_clock_profile_is_checked_before_resource_effects(self):
        for name, _ in manager.Inputs._fields_:
            if name in ("override_heads", "mutex_identity"):
                continue
            request = self.request()
            target = request.inputs.clock.request
            setattr(target, name, getattr(target, name) ^ 0x40)
            self.run_request(request, UNSUPPORTED)
        for index in range(3):
            request = self.request()
            request.inputs.clock.request.override_heads[index] = 1
            self.run_request(request, UNSUPPORTED)
        for name in ("helper_selection", "helper_gate", "helper_input", "diagnostic"):
            request = self.request()
            setattr(request.inputs.clock, name, getattr(request.inputs.clock, name) ^ 0x40)
            self.run_request(request, UNSUPPORTED)
        request = self.request()
        for index in range(1156):
            request.manager[index] ^= 1
            self.run_request(request, UNSUPPORTED)
            request.manager[index] ^= 1
        for name in ("initialized", "divider_miss", "source_miss"):
            request = self.request()
            setattr(request.state, name, getattr(request.state, name) ^ 1)
            self.run_request(request, UNSUPPORTED)
        request = self.request()
        for index in range(86):
            request.state.descriptor_miss[index] = 1
            self.run_request(request, UNSUPPORTED)
            request.state.descriptor_miss[index] = 0
        for name in ("source", "divider"):
            for field, _ in getattr(request, name)._fields_:
                request = self.request()
                state = getattr(request, name)
                setattr(state, field, getattr(state, field) ^ 1)
                self.run_request(request, UNSUPPORTED)
        for value in (1, 0x10, 0x80, 0x12345678, 0x5A000000):
            request = self.request()
            request.cell[0] = value
            self.run_request(request, UNSUPPORTED)

    def test_incoming_aggregate_and_scratch_are_preserved_until_their_stores(self):
        request = self.request()
        request.resource.aggregate = 0x12345678
        request.scratch[:8] = b"\x32" * 8
        initial = request.snapshot()
        self.run_request(request)
        self.assertEqual(request.snapshots[0], initial)
        self.assertEqual(request.snapshots[1], initial)
        self.assertTrue(all(snapshot["scratch"] == initial["scratch"]
                            for snapshot in request.snapshots[:14]))
        self.assertEqual(request.resource.aggregate, 0x180)
        self.assertEqual(int.from_bytes(request.scratch[:8], "little"), 600000000)


if __name__ == "__main__":
    unittest.main()
