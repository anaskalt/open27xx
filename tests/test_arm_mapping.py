# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check fixed ARM table preparation and carried state against fixtures."""

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

ROOT = Path(__file__).resolve().parents[1]
Word = ctypes.c_uint32
WordPointer = ctypes.POINTER(Word)
BytePointer = ctypes.POINTER(ctypes.c_uint8)
Observer = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, WordPointer, ctypes.c_size_t, Word)
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
SENTINEL = 0xD451BE70
TABLE_ADDRESS = 0xE403B498
STATE_ADDRESSES = (0xE403B494, 0xE403B47C, 0xE403B518, 0xE4001564, 0xE403B48C)
TABLE_CASES = ("fresh-table", "repeat-last-entry", "selection-zero-service-seven",
               "wrapped-index-outside-table")


class Inputs(ctypes.Structure):
    _fields_ = [(name, Word) for name in ("handle", "offset", "base", "length")]


class State(ctypes.Structure):
    _fields_ = [(name, Word) for name in ("active", "capacity", "marker", "selection", "service_index")]


class Plan(ctypes.Structure):
    _fields_ = [("acquire", Observer), ("release", Observer),
                ("service", Observer), ("context", ctypes.c_void_p)]


def guarded(value):
    class Guard(ctypes.Structure):
        _fields_ = [("before", ctypes.c_uint64), ("value", type(value)), ("after", ctypes.c_uint64)]
    return Guard(0x713AC924713AC924, value, 0x57DDEF8357DDEF83)


def pointer(guard):
    return ctypes.cast(ctypes.byref(guard, type(guard).value.offset),
                       ctypes.POINTER(type(guard)._fields_[1][1]))


def fixture_bytes(case, phase, address, length):
    for region in case[phase]["memory"]:
        start = int(region["address"], 0)
        data = (bytes.fromhex(region["hex"]) if "hex" in region else
                bytes.fromhex(region["fill"]) * region["size"])
        if start <= address and address + length <= start + len(data):
            return data[address - start:address - start + length]
    return None


class Request:
    def __init__(self, case, unaligned=0):
        self.case = case
        self.has_table = case["id"] in TABLE_CASES
        self.has_state = case["id"] != "invalid-handle"
        inputs = Inputs(*(int(case["setup"]["registers"][f"r{index}"], 0) for index in range(4)))
        values = [fixture_bytes(case, "setup", address, 4) for address in STATE_ADDRESSES]
        self.used_fields = {field for (field, _), value in zip(State._fields_, values) if value is not None}
        state = State(*(int.from_bytes(value, "little") if value is not None else SENTINEL
                        for value in values))
        self.guards = {"inputs": guarded(inputs), "state": guarded(state), "raw": guarded(Word(SENTINEL))}
        self.inputs, self.state, self.raw = (pointer(self.guards[name]) for name in ("inputs", "state", "raw"))
        self.offset = 16 + unaligned
        self.buffer = (ctypes.c_uint8 * (self.offset + 144 + 16))()
        self.buffer[:] = b"\x53" * len(self.buffer)
        self.table = ctypes.cast(ctypes.byref(self.buffer, self.offset), BytePointer)
        if self.has_table:
            self.buffer[self.offset:self.offset + 128] = fixture_bytes(case, "setup", TABLE_ADDRESS, 128)
        self.events, self.snapshots, self.contexts = [], [], []
        self.bookkeeping = Word(0)

        @Observer
        def observe(context, entry, arguments, count, reply):
            self.events.append((entry, tuple(arguments[:count]), reply))
            self.snapshots.append(self.snapshot())
            self.contexts.append(context)
            self.bookkeeping.value += 1

        self.observe = observe
        self.plan = Plan(observe, observe, observe, ctypes.addressof(self.bookkeeping))

    def arguments(self, all_objects=False):
        return [self.inputs, self.state if self.has_state or all_objects else None,
                self.table if self.has_table or all_objects else None,
                144 if self.has_table or all_objects else 0,
                ctypes.byref(self.plan) if self.has_state or all_objects else None, self.raw]

    def snapshot(self):
        return {"state": bytes(self.state.contents), "table": bytes(self.buffer[self.offset:self.offset + 128]),
                "raw": self.raw.contents.value}

    def storage(self):
        return bytes(self.buffer), bytes(self.plan), tuple(bytes(g) for g in self.guards.values())

    def reset_observations(self):
        self.events.clear()
        self.snapshots.clear()
        self.contexts.clear()
        self.bookkeeping.value = 0


class ArmMappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("ARM mapping tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="arm-mapping-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "arm_mapping.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/arm_mapping.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.arm_mapping_prepare
        cls.function.argtypes = [ctypes.POINTER(Inputs), ctypes.POINTER(State), BytePointer,
                                ctypes.c_size_t, ctypes.POINTER(Plan), WordPointer]
        cls.function.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/arm-mapping.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = {case["id"]: case for case in json.loads(path.read_text())["cases"]}

    def request(self, name="fresh-table", unaligned=0):
        return Request(self.cases[name], unaligned)

    def run_request(self, request, expected=OK, arguments=None):
        before = request.storage()
        self.assertEqual(self.function(*(request.arguments() if arguments is None else arguments)), expected)
        if expected != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.events, [])
        self.assertEqual(bytes(request.plan), before[1])
        self.assertEqual(bytes(request.guards["inputs"]), before[2][0])
        self.assertEqual(bytes(request.buffer[:request.offset]), b"\x53" * request.offset)
        self.assertEqual(bytes(request.buffer[request.offset + 128:]),
                         b"\x53" * (len(request.buffer) - request.offset - 128))
        for guard in request.guards.values():
            self.assertEqual((guard.before, guard.after), (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)] * len(request.events))
        self.assertEqual(request.bookkeeping.value, len(request.events))
        self.assertTrue(all(snapshot["raw"] == SENTINEL for snapshot in request.snapshots))

    def compare_case(self, request, case, initial):
        expected_events = []
        for event in case["expected"]["events"]:
            entry = int(event["entry"], 0)
            service = entry == 0x0ED65284
            expected_events.append((entry, tuple(int(word, 0) for word in event["arguments"][:6 if service else 1]),
                                    7 if service else 0))
        self.assertEqual(request.events, expected_events)
        self.assertEqual(request.raw.contents.value, int(case["expected"]["registers"]["r0"], 0))
        final = request.snapshot()
        original_state = State.from_buffer_copy(initial["state"])
        for (field, _), address in zip(State._fields_, STATE_ADDRESSES):
            expected = fixture_bytes(case, "expected", address, 4)
            expected = int.from_bytes(expected, "little") if expected is not None else getattr(original_state, field)
            self.assertEqual(getattr(request.state.contents, field), expected)
        expected_table = fixture_bytes(case, "expected", TABLE_ADDRESS, 128)
        self.assertEqual(final["table"], initial["table"] if expected_table is None else expected_table)
        if request.events:
            self.assertEqual(request.snapshots[0], initial)
            for snapshot in request.snapshots[1:]:
                self.assertEqual(snapshot, dict(final, raw=SENTINEL))

    def test_all_twelve_complete_profiles_and_boundary_snapshots(self):
        self.assertEqual(self.fixture_hash,
                         "b4d23a356284c0e7f088815079712b7e0d87a3ea1a6358d0e85561aa146866de")
        self.assertEqual(len(self.cases), 12)
        for name in self.cases:
            with self.subTest(case=name):
                request = self.request(name)
                initial = request.snapshot()
                self.run_request(request)
                self.compare_case(request, request.case, initial)

    def test_fresh_output_is_the_repeat_input(self):
        request = self.request()
        self.run_request(request)
        repeat = self.cases["repeat-last-entry"]
        self.assertEqual(request.snapshot()["table"], fixture_bytes(repeat, "setup", TABLE_ADDRESS, 128))
        request.inputs.contents.offset = 0x3F000000
        request.inputs.contents.base = 0x40000000
        request.raw.contents.value = SENTINEL
        request.reset_observations()
        initial = request.snapshot()
        self.run_request(request)
        self.compare_case(request, repeat, initial)
        self.assertEqual(request.snapshot()["table"][:-2], initial["table"][:-2])
        self.assertEqual(request.snapshot()["table"][-2:], b"\x00\x02")

    def test_unaligned_table_bytes_and_retained_wrapped_failure(self):
        for offset in range(1, 8):
            for name in TABLE_CASES:
                request = self.request(name, offset)
                initial = request.snapshot()
                self.run_request(request)
                self.compare_case(request, request.case, initial)
        request = self.request("wrapped-index-outside-table")
        self.run_request(request)
        self.assertEqual(request.raw.contents.value, 0xFFFFFFFC)
        self.assertEqual(request.state.contents.marker, 1)
        self.assertEqual(request.snapshot()["table"], b"\xf0\x03" * 64)

    def test_only_used_state_members_are_numeric_premises(self):
        for name in self.cases:
            for field, _ in State._fields_:
                request = self.request(name)
                if field in request.used_fields:
                    continue
                setattr(request.state.contents, field, 0xFFFFFFFF)
                initial = request.snapshot()
                self.run_request(request, arguments=request.arguments(all_objects=True))
                self.compare_case(request, request.case, initial)
        request = self.request("invalid-handle")
        request.plan = Plan()
        self.run_request(request, arguments=request.arguments(all_objects=True))
        self.assertEqual(request.events, [])

    def test_exact_arguments_state_and_every_table_byte(self):
        for name in self.cases:
            for field, _ in Inputs._fields_:
                request = self.request(name)
                setattr(request.inputs.contents, field, getattr(request.inputs.contents, field) ^ 0x80000000)
                self.run_request(request, UNSUPPORTED)
            for field in self.request(name).used_fields:
                request = self.request(name)
                setattr(request.state.contents, field, getattr(request.state.contents, field) ^ 0x80000000)
                self.run_request(request, UNSUPPORTED)
        for name in TABLE_CASES:
            request = self.request(name)
            for index in range(128):
                request.table[index] ^= 0x80
                self.run_request(request, UNSUPPORTED)
                request.table[index] ^= 0x80
        request = self.request()
        self.run_request(request)
        request.reset_observations()
        self.run_request(request, UNSUPPORTED)

    def test_required_storage_and_only_reachable_observers(self):
        for name in self.cases:
            positions = [0, 5] + ([] if name == "invalid-handle" else [1, 4])
            if name in TABLE_CASES:
                positions.append(2)
            for position in positions:
                request = self.request(name)
                arguments = request.arguments()
                arguments[position] = None
                self.run_request(request, INVALID, arguments)
            if name != "invalid-handle":
                for field in ("acquire", "release"):
                    request = self.request(name)
                    setattr(request.plan, field, Observer())
                    self.run_request(request, INVALID)
            request = self.request(name)
            request.plan.service = Observer()
            self.run_request(request, INVALID if name == "selection-zero-service-seven" else OK)

    def test_all_declared_objects_and_full_tails_are_disjoint(self):
        positions = (0, 1, 2, 4, 5)
        for name in ("invalid-handle", "active", "range-exceeded", "fresh-table"):
            for left, right in itertools.permutations(positions, 2):
                request = self.request(name)
                arguments = request.arguments(all_objects=True)
                arguments[right] = ctypes.cast(arguments[left], self.function.argtypes[right])
                self.run_request(request, OVERLAP, arguments)
            for position in (0, 1, 4, 5):
                request = self.request(name)
                arguments = request.arguments(all_objects=True)
                arguments[position] = ctypes.cast(ctypes.addressof(request.buffer) + request.offset + 128,
                                                  self.function.argtypes[position])
                self.run_request(request, OVERLAP, arguments)
        request = self.request("active")
        arguments = request.arguments()
        arguments[5] = ctypes.cast(ctypes.addressof(request.state.contents) + State.service_index.offset, WordPointer)
        self.run_request(request, OVERLAP, arguments)

    def test_short_optional_and_wrapped_host_extents(self):
        maximum = ctypes.c_size_t(-1).value
        for name in ("invalid-handle", "active", "fresh-table"):
            for position in (0, 1, 2, 4, 5):
                request = self.request(name)
                arguments = request.arguments(all_objects=True)
                arguments[position] = ctypes.cast(maximum - 1, self.function.argtypes[position])
                self.run_request(request, BOUNDS, arguments)
        for name in TABLE_CASES:
            for length in (0, 127, maximum):
                request = self.request(name)
                arguments = request.arguments()
                arguments[3] = length
                self.run_request(request, BOUNDS, arguments)
        for name in ("invalid-handle", "active", "range-exceeded"):
            for length in (0, 1, 127):
                request = self.request(name)
                arguments = request.arguments(all_objects=True)
                arguments[3] = length
                self.run_request(request, arguments=arguments)
        request = self.request("invalid-handle")
        arguments = request.arguments()
        arguments[3] = 1
        self.run_request(request, INVALID, arguments)
        request = self.request()
        arguments = request.arguments()
        arguments[2:4] = None, 0
        self.run_request(request, INVALID, arguments)


if __name__ == "__main__":
    unittest.main()
