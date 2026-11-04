# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check fixed clock leaf operations against their complete public fixtures."""

import ctypes
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
MMIO_READ, MMIO_WRITE, NATIVE_READ, NATIVE_WRITE = range(4)
KINDS = {"supplied_mmio_read": MMIO_READ, "mmio_write": MMIO_WRITE,
         "elf_ram_read": NATIVE_READ, "elf_ram_write": NATIVE_WRITE}
SENTINEL = 0xA5A5A5A5
Word, Wide, Byte = ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint8
WordPointer = ctypes.POINTER(Word)
Observe = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, Word, Word)


class Observer(ctypes.Structure):
    _fields_ = [("observe", Observe), ("context", ctypes.c_void_p)]


class Read(ctypes.Structure):
    _fields_ = [("address", Word), ("word", Word)]


class Plan(ctypes.Structure):
    _fields_ = [("reads", ctypes.POINTER(Read)), ("count", ctypes.c_size_t),
                ("observer", Observer)]


class SourceInputs(ctypes.Structure):
    _fields_ = [("handle", Word), ("comparison_handle", Word), ("source", Word),
                ("requested", Wide), ("selection", Word), ("helper_selection", Word),
                ("helper_gate", Word), ("helper_input", Word), ("diagnostic", Byte)]


class SourceState(ctypes.Structure):
    _fields_ = [("marker", Word), ("requested", Wide), ("cached", Wide)]


class WordInputs(ctypes.Structure):
    _fields_ = [(name, Word) for name in ("handle", "comparison_handle", "clock",
                "source", "divider", "factor_bits", "argument5")]
    _fields_ += [("diagnostic", Byte), ("enable", Byte)]


class DividerInputs(ctypes.Structure):
    _fields_ = [(name, Word) for name in
                ("handle", "comparison_handle", "divider", "count", "selection")]


class DividerState(ctypes.Structure):
    _fields_ = [("marker", Word), ("count", Word)]


def guarded(value):
    class Guarded(ctypes.Structure):
        _fields_ = [("before", Wide), ("value", type(value)), ("after", Wide)]
    return Guarded(0x713AC924713AC924, value, 0x57DDEF8357DDEF83)


def value_pointer(storage):
    return ctypes.cast(ctypes.byref(storage, type(storage).value.offset),
                       ctypes.POINTER(type(storage)._fields_[1][1]))


def fixture_bytes(case, phase, address, size):
    for region in case[phase]["memory"]:
        base = int(region["address"], 0)
        raw = (bytes.fromhex(region["hex"]) if "hex" in region
               else bytes.fromhex(region["fill"]) * region["size"])
        if base <= address and address + size <= base + len(raw):
            return raw[address - base:address - base + size]
    raise AssertionError(f"missing fixture bytes {address:#x}+{size}")


def fixture_word(case, phase, address, size=4):
    return int.from_bytes(fixture_bytes(case, phase, address, size), "little")


class Request:
    def __init__(self, operation, case):
        self.operation, self.case = operation, case
        registers = case["setup"]["registers"]
        reg = lambda index: int(registers[f"r{index}"], 0)
        gp = int(registers["gp"], 0)
        get = lambda offset, size=4: fixture_word(case, "setup", gp + offset, size)
        common = [reg(0), get(0x3E494)]
        if operation == "source":
            self.inputs = SourceInputs(*common, reg(1), reg(2) | reg(3) << 32,
                                       get(0x1564), get(0x1568), get(0xCC93C),
                                       get(0xCC940), get(0xCCE48, 1))
            state = SourceState(get(0x3E6AC), get(0x3E6B0, 8), get(0x3E4A8, 8))
        elif operation == "divider":
            self.inputs = DividerInputs(*common, reg(1), reg(2), get(0x1564))
            state = DividerState(get(0x3E72C), get(0x3E730))
        else:
            self.inputs = WordInputs(*common, *(reg(index) for index in range(1, 6)),
                                     get(0xCCE48, 1), get(0x3E518, 1))
            state = Word(fixture_word(case, "setup", 0x0EE056B0))
        self.state_storage, self.raw_storage = guarded(state), guarded(Word(SENTINEL))
        self.state_pointer, self.raw_pointer = (value_pointer(self.state_storage),
                                                value_pointer(self.raw_storage))
        responses = case["execution"]["mmio_responses"]
        self.reads = (Read * len(responses))(*(Read(int(read["address"], 0),
                    int.from_bytes(bytes.fromhex(read["hex"]), "little")) for read in responses))
        self.events, self.snapshots, self.contexts = [], [], []
        self.bookkeeping = Word()
        self.callback = Observe(self.observe)
        self.observer = Observer(self.callback, ctypes.addressof(self.bookkeeping))
        self.plan = Plan(self.reads, len(self.reads), self.observer)

    def observe(self, context, kind, address, word):
        self.events.append((kind, address, word))
        self.snapshots.append((bytes(self.state_pointer.contents), self.raw_pointer[0]))
        self.contexts.append(context)
        self.bookkeeping.value += 1

    def arguments(self):
        return [ctypes.byref(self.inputs), self.state_pointer,
                ctypes.byref(self.observer if self.operation == "word" else self.plan),
                self.raw_pointer]

    def storage(self):
        return tuple(bytes(value) for value in (self.inputs, self.state_storage,
                     self.raw_storage, self.reads, self.plan, self.observer))

    def memory_words(self):
        state, inputs = self.state_pointer.contents, self.inputs
        result = {0xE403E494: (inputs.comparison_handle, 4)}
        if self.operation == "source":
            result.update({0xE403E6AC: (state.marker, 4), 0xE403E6B0: (state.requested, 8),
                           0xE403E4A8: (state.cached, 8), 0xE4001564: (inputs.selection, 4),
                           0xE4001568: (inputs.helper_selection, 4),
                           0xE40CC93C: (inputs.helper_gate, 4),
                           0xE40CC940: (inputs.helper_input, 4),
                           0xE40CCE48: (inputs.diagnostic, 1)})
        elif self.operation == "divider":
            result.update({0xE403E72C: (state.marker, 4), 0xE403E730: (state.count, 4),
                           0xE4001564: (inputs.selection, 4)})
        else:
            result.update({0x0EE056B0: (state.value, 4), 0xE40CCE48: (inputs.diagnostic, 1),
                           0xE403E518: (inputs.enable, 1)})
        return result


class ClockDriverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Clock-driver tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="clock-driver-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "clock_driver.so"
        subprocess.run(compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/clock_driver.c"), "-o", str(library),
        ], check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.functions, cls.cases = {}, {}
        for operation, inputs, state, plan in (
            ("source", SourceInputs, SourceState, Plan),
            ("word", WordInputs, Word, Observer),
            ("divider", DividerInputs, DividerState, Plan),
        ):
            function = getattr(cls.library, f"clock_{operation}_program")
            function.argtypes = [ctypes.POINTER(inputs), ctypes.POINTER(state),
                                 ctypes.POINTER(plan), WordPointer]
            function.restype = ctypes.c_int
            cls.functions[operation] = function
            cls.cases[operation] = json.loads((ROOT / "tests/vectors/start4"
                                             / f"clock-{operation}.json").read_text())["cases"]

    def request(self, operation, index=0):
        return Request(operation, self.cases[operation][index])

    def run_request(self, request, status=OK, arguments=None):
        before = request.storage()
        self.assertEqual(self.functions[request.operation](
            *(request.arguments() if arguments is None else arguments)), status)
        if status != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.events, [])
        else:
            after = request.storage()
            self.assertEqual((after[0], after[3:]), (before[0], before[3:]))
        for storage in (request.state_storage, request.raw_storage):
            self.assertEqual((storage.before, storage.after),
                             (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)]
                         * len(request.events))
        self.assertEqual(request.bookkeeping.value, len(request.events))
        self.assertTrue(all(raw == SENTINEL for _, raw in request.snapshots))

    def test_fixture_identities_and_complete_events(self):
        identities = {
            "source": "dfb8bd8ebe810bb90855dc9a0d701108a88c6215306b9827201bceb6663fac78",
            "word": "d9fb830adc8c889696959227d29eba473013b67acfeafc20cdeef413d4c4c2ae",
            "divider": "d67ac8367485ab008e8880617b9a89ac330ec7be0703207ee6e9a30401eb892f",
        }
        totals = [0] * 4
        for operation, cases in self.cases.items():
            path = ROOT / "tests/vectors/start4" / f"clock-{operation}.json"
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), identities[operation])
            for case in cases:
                with self.subTest(operation=operation, case=case["id"]):
                    request = Request(operation, case)
                    self.run_request(request)
                    expected = [(KINDS[event["kind"]], int(event["address"], 0),
                                 int.from_bytes(bytes.fromhex(event["hex"]), "little"))
                                for event in case["expected"]["events"]]
                    self.assertEqual(request.events, expected)
                    self.assertEqual(request.raw_pointer[0], int(case["expected"]["registers"]["r0"], 0))
                    for kind, _, _ in request.events:
                        totals[kind] += 1
                    for region in case["expected"]["memory"]:
                        address = int(region["address"], 0)
                        expected_bytes = bytes.fromhex(region["hex"])
                        actual = bytearray(fixture_bytes(case, "setup", address, len(expected_bytes)))
                        for field, (word, size) in request.memory_words().items():
                            if address <= field and field + size <= address + len(actual):
                                actual[field - address:field - address + size] = word.to_bytes(size, "little")
                        self.assertEqual(actual, expected_bytes)
        self.assertEqual(totals, [2362, 590, 2015, 6])

    def test_caches_precede_every_mmio_event_and_persist_on_raw_four(self):
        for operation in ("source", "divider"):
            for case in self.cases[operation][:-1]:
                with self.subTest(operation=operation, case=case["id"]):
                    request = Request(operation, case)
                    self.run_request(request)
                    state_type = SourceState if operation == "source" else DividerState
                    for snapshot, _ in request.snapshots:
                        state = state_type.from_buffer_copy(snapshot)
                        self.assertEqual(state.marker, 1)
                        if operation == "source":
                            self.assertEqual((state.requested, state.cached), (1200000000, 1200000000))
                        else:
                            self.assertEqual(state.count, 2)
                    if case["id"] == "lock-count-exhausted":
                        self.assertEqual(request.raw_pointer[0], 4)
                        self.assertEqual(request.events[-1], (MMIO_WRITE, 0x7E101170, 0x5A345678))

    def test_native_cell_order_and_finite_counter(self):
        for index in range(5):
            request = self.request("word", index)
            self.run_request(request)
            for (kind, address, word), (state, _) in zip(request.events, request.snapshots):
                self.assertIn(kind, (NATIVE_READ, NATIVE_WRITE))
                self.assertEqual(address, 0x0EE056B0)
                self.assertEqual(int.from_bytes(state, sys.byteorder), word)
            reads = sum(kind == NATIVE_READ for kind, _, _ in request.events)
            self.assertEqual(reads, 2003 if index == 3 else 3)
            self.assertEqual(request.raw_pointer[0], 0)

    def test_fixed_arithmetic_and_repeated_final_divider_write(self):
        request = self.request("source", 1)
        self.run_request(request)
        quotient = (1200000000 * 2**20 + 27000000) // 54000000
        self.assertIn((MMIO_WRITE, 0x7E1022E0, 0x5A000000 | (quotient & 0xFFFFF)), request.events)
        writes = [word for kind, address, word in request.events if kind == MMIO_WRITE and address == 0x7E1021E0]
        self.assertEqual(writes, [0x5A021015, 0x5A021016])
        request = self.request("divider", 4)
        self.run_request(request)
        writes = [word for kind, address, word in request.events if kind == MMIO_WRITE and address == 0x7E1023E0]
        self.assertEqual(writes, [0x5A000000 | value for value in range(254, 1, -1)] + [0x5A000002])
        commands = [word for kind, address, word in request.events if kind == MMIO_WRITE and address == 0x7E101100]
        self.assertEqual(commands, [0x5A000000 | ((54000000 // 1000000) * 10)] * 253)

    def test_additional_exact_composition_divider_pair(self):
        request = self.request("divider", 3)
        request.reads[-1].word = 0x00345678
        self.run_request(request)
        expected = [(KINDS[event["kind"]], int(event["address"], 0),
                     int.from_bytes(bytes.fromhex(event["hex"]), "little"))
                    for event in request.case["expected"]["events"]]
        expected[-2] = (MMIO_READ, 0x7E101170, 0x00345678)
        self.assertEqual(request.events, expected)
        self.assertEqual(request.raw_pointer[0], 0)
        for index in (0, 1, 2, 4, 5):
            request = self.request("divider", index)
            request.reads[-1].word = 0x00345678
            self.run_request(request, UNSUPPORTED)

    def test_mismatched_profiles_need_no_providers(self):
        for operation in self.cases:
            request = self.request(operation, -1)
            request.observer.observe = Observe()
            request.plan.observer.observe = Observe()
            request.plan.reads = ctypes.POINTER(Read)()
            self.run_request(request)
            self.assertEqual(request.raw_pointer[0], 0xFFFFFFFF)
            self.assertEqual(request.events, [])

    def test_missing_required_objects_and_observers(self):
        for operation in self.cases:
            for index in range(4):
                with self.subTest(operation=operation, argument=index):
                    request = self.request(operation)
                    arguments = request.arguments()
                    arguments[index] = None
                    self.run_request(request, INVALID, arguments)
            request = self.request(operation)
            if operation == "word":
                request.observer.observe = Observe()
            else:
                request.plan.observer.observe = Observe()
            self.run_request(request, INVALID)

    def test_all_typed_object_overlaps(self):
        for operation in self.cases:
            function = self.functions[operation]
            for left in range(4):
                for right in range(left + 1, 4):
                    with self.subTest(operation=operation, pair=(left, right)):
                        request = self.request(operation)
                        arguments = request.arguments()
                        arguments[right] = ctypes.cast(arguments[left], function.argtypes[right])
                        self.run_request(request, OVERLAP, arguments)

    def test_reply_storage_overlap_and_bounds(self):
        maximum = ctypes.c_size_t(-1).value
        for operation in ("source", "divider"):
            for index in range(4):
                request = self.request(operation)
                request.plan.reads = ctypes.cast(request.arguments()[index], ctypes.POINTER(Read))
                self.run_request(request, OVERLAP)
            request = self.request(operation)
            request.plan.reads = ctypes.POINTER(Read)()
            self.run_request(request, INVALID)
            request = self.request(operation)
            request.plan.count = maximum
            self.run_request(request, BOUNDS)
            request = self.request(operation)
            request.plan.reads = ctypes.cast(maximum - 3, ctypes.POINTER(Read))
            self.run_request(request, BOUNDS)
        for operation in self.cases:
            for index in range(4):
                request = self.request(operation)
                arguments = request.arguments()
                arguments[index] = ctypes.cast(maximum - 1, self.functions[operation].argtypes[index])
                self.run_request(request, BOUNDS, arguments)

    def test_every_input_and_initial_cache_is_checked(self):
        for operation in self.cases:
            for field, _ in type(self.request(operation).inputs)._fields_:
                with self.subTest(operation=operation, field=field):
                    request = self.request(operation)
                    setattr(request.inputs, field, getattr(request.inputs, field) ^ 0x40)
                    self.run_request(request, UNSUPPORTED)
            if operation != "word":
                for field, _ in type(self.request(operation).state_pointer.contents)._fields_:
                    request = self.request(operation)
                    setattr(request.state_pointer.contents, field,
                            getattr(request.state_pointer.contents, field) ^ 1)
                    self.run_request(request, UNSUPPORTED)
        request = self.request("word")
        request.state_pointer[0] = 1
        self.run_request(request, UNSUPPORTED)

    def test_each_literal_reply_and_address_is_checked_before_effects(self):
        for operation in ("source", "divider"):
            for case in self.cases[operation][:-1]:
                request = Request(operation, case)
                for index in range(len(request.reads)):
                    for field in ("address", "word"):
                        with self.subTest(operation=operation, case=case["id"], index=index, field=field):
                            original = getattr(request.reads[index], field)
                            setattr(request.reads[index], field, original ^ 0x80000000)
                            self.run_request(request, UNSUPPORTED)
                            setattr(request.reads[index], field, original)

    def test_missing_extra_and_unterminated_plans_have_no_effects(self):
        for operation in ("source", "divider"):
            for case in self.cases[operation][:-1]:
                request = Request(operation, case)
                request.plan.count = 0
                self.run_request(request, BOUNDS)
                request = Request(operation, case)
                request.plan.count -= 1
                before = request.storage()
                self.assertIn(self.functions[operation](*request.arguments()), (BOUNDS, UNSUPPORTED))
                self.assertEqual(request.storage(), before)
                self.assertEqual(request.events, [])
                request = Request(operation, case)
                request.reads = (Read * (len(request.reads) + 1))(*request.reads, Read(0x7E101100, 0))
                request.plan.reads, request.plan.count = request.reads, len(request.reads)
                self.run_request(request, UNSUPPORTED)
            request = self.request(operation, 4 if operation == "source" else 5)
            for read in request.reads:
                if read.address == 0x7E101100 and read.word == 0:
                    read.word = 1
            self.run_request(request, UNSUPPORTED)

    def test_profiles_do_not_form_a_cartesian_product(self):
        request = self.request("source", 6)
        request.reads[0].word = 0x4000
        self.run_request(request, UNSUPPORTED)
        request = self.request("source", 4)
        request.reads[1].word = 0x20014
        self.run_request(request, UNSUPPORTED)
        request = self.request("divider", 5)
        request.reads[0].word = 255
        self.run_request(request, UNSUPPORTED)
        request = self.request("divider", 6)
        request.reads[-1].word = 0x34567A
        self.run_request(request, UNSUPPORTED)
        request = self.request("word", 4)
        request.state_pointer[0] = 0x80
        self.run_request(request, UNSUPPORTED)
        for operation in ("source", "divider"):
            request = self.request(operation)
            request.inputs.handle = request.inputs.comparison_handle = 0
            self.run_request(request, UNSUPPORTED)

    def test_resulting_state_cannot_be_reused_as_an_initial_profile(self):
        for operation in self.cases:
            request = self.request(operation)
            self.run_request(request)
            request.events.clear()
            request.contexts.clear()
            request.snapshots.clear()
            request.bookkeeping.value = 0
            self.run_request(request, UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
