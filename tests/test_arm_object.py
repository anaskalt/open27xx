# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check finite ARM object calls, boundary order and host preflight."""

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
Observer = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, WordPointer,
                           ctypes.c_size_t, Word)
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
SENTINEL = 0xA5A5A5A5
RAW_SENTINEL = 0xD451BE70
RECORD_BASE = 0xE40DA4C4


class Plan(ctypes.Structure):
    _fields_ = [("acquire", Observer), ("diagnostic", Observer),
                ("release", Observer), ("context", ctypes.c_void_p)]


class State(ctypes.Structure):
    _fields_ = [("count", Word), ("object", Word)]


def guarded(value):
    class Guard(ctypes.Structure):
        _fields_ = [("before", ctypes.c_uint64), ("value", type(value)),
                    ("after", ctypes.c_uint64)]
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
    raise AssertionError(f"Unmapped fixture bytes: {address:#x}+{length}")


def fixture_word(case, phase, address):
    return int.from_bytes(fixture_bytes(case, phase, address, 4), "little")


class Request:
    def __init__(self, case, unaligned=0):
        self.case = case
        self.reopen = case["id"] == "repeated-open"
        self.present = case["id"] != "register-null-output"
        self.guards = {"output": guarded(Word(SENTINEL)),
                       "raw": guarded(Word(RAW_SENTINEL)),
                       "state": guarded(State(1, 0x11223344))}
        self.output, self.raw, self.state = (pointer(self.guards[name]) for name in
                                             ("output", "raw", "state"))
        self.offset = 16 + unaligned
        self.buffer = (ctypes.c_uint8 * (self.offset + 912 + 16))()
        self.buffer[:] = b"\x53" * len(self.buffer)
        self.records = ctypes.cast(ctypes.byref(self.buffer, self.offset), BytePointer)
        if self.present and not self.reopen:
            self.buffer[self.offset:self.offset + 896] = fixture_bytes(
                case, "setup", RECORD_BASE, 896)
        self.events, self.snapshots = [], []
        self.bookkeeping = Word(0)
        self.contexts = []

        @Observer
        def observe(context, entry, arguments, count, reply):
            self.events.append((entry, tuple(arguments[:count]), reply))
            self.snapshots.append(self.snapshot())
            self.contexts.append(context)
            self.bookkeeping.value += 1

        self.observe = observe
        self.plan = Plan(observe, observe, observe, ctypes.addressof(self.bookkeeping))

    def arguments(self):
        if self.reopen:
            return [0x400, 2, self.state, self.output, ctypes.byref(self.plan), self.raw]
        return [int(self.present), self.records if self.present else None,
                912 if self.present else 0, self.output if self.present else None,
                ctypes.byref(self.plan) if self.present else None, self.raw]

    def snapshot(self):
        return {"records": bytes(self.buffer[self.offset:self.offset + 896]),
                "output": self.output.contents.value, "raw": self.raw.contents.value,
                "state": bytes(self.state.contents)}

    def storage(self):
        return bytes(self.buffer), bytes(self.plan), tuple(bytes(g) for g in self.guards.values())


class ArmObjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("ARM object tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="arm-object-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "arm_object.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/arm_object.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.register = cls.library.arm_object_register
        cls.register.argtypes = [Word, BytePointer, ctypes.c_size_t, WordPointer,
                                ctypes.POINTER(Plan), WordPointer]
        cls.register.restype = ctypes.c_int
        cls.reopen = cls.library.arm_object_reopen
        cls.reopen.argtypes = [Word, ctypes.c_uint8, ctypes.POINTER(State), WordPointer,
                              ctypes.POINTER(Plan), WordPointer]
        cls.reopen.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/arm-object.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = {case["id"]: case for case in json.loads(path.read_text())["cases"]}

    def request(self, name="register-slot0", unaligned=0):
        return Request(self.cases[name], unaligned)

    def run_request(self, request, expected=OK, arguments=None):
        before = request.storage()
        function = self.reopen if request.reopen else self.register
        self.assertEqual(function(*(request.arguments() if arguments is None else arguments)), expected)
        if expected != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.events, [])
        self.assertEqual(bytes(request.plan), before[1])
        self.assertEqual(bytes(request.buffer[:request.offset]), b"\x53" * request.offset)
        self.assertEqual(bytes(request.buffer[request.offset + 896:]),
                         b"\x53" * (len(request.buffer) - request.offset - 896))
        for guard in request.guards.values():
            self.assertEqual((guard.before, guard.after), (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)] * len(request.events))
        self.assertEqual(request.bookkeeping.value, len(request.events))
        self.assertTrue(all(s["raw"] == RAW_SENTINEL for s in request.snapshots))

    def test_six_complete_fixtures_and_semantic_boundaries(self):
        self.assertEqual(self.fixture_hash,
                         "58d5c7c36b8bda0a402a975900a985f32cc39daad6b8beb0c91541b5c66e6d0b")
        complete = set(self.cases) - {"first-open-before-version"}
        self.assertEqual(len(complete), 6)
        for name in sorted(complete):
            with self.subTest(case=name):
                request = self.request(name)
                case, initial = request.case, request.snapshot()
                self.run_request(request)
                expected_events = []
                for event in case["expected"]["events"]:
                    entry = int(event["entry"], 0)
                    count = 3 if entry == 0x0ED17442 else 1
                    expected_events.append((entry, tuple(int(word, 0) for word in
                                                        event["arguments"][:count]), 0))
                self.assertEqual(request.events, expected_events)
                self.assertEqual(request.raw.contents.value, int(case["expected"]["registers"]["r0"], 0))
                if request.reopen:
                    for field, address in (("count", 0xE403B474), ("object", 0xE403B478)):
                        self.assertEqual(getattr(request.state.contents, field),
                                         fixture_word(case, "expected", address))
                    self.assertEqual(request.output.contents.value, fixture_word(case, "expected", 0x24003000))
                    self.assertEqual(request.snapshots[0], initial)
                    self.assertEqual(State.from_buffer_copy(request.snapshots[1]["state"]).count, 2)
                    self.assertEqual(request.snapshots[1]["output"], SENTINEL)
                    self.assertEqual(request.snapshots[1]["records"], initial["records"])
                elif request.present:
                    final = request.snapshot()
                    self.assertEqual(final["records"], fixture_bytes(case, "expected", RECORD_BASE, 896))
                    self.assertEqual(final["output"], fixture_word(case, "expected", 0xE403B478))
                    self.assertEqual(final["state"], initial["state"])
                    self.assertEqual(request.snapshots[0], dict(initial, output=0))
                    for snapshot in request.snapshots[1:]:
                        self.assertEqual(snapshot, dict(final, raw=RAW_SENTINEL))
                else:
                    self.assertEqual(request.snapshot(), dict(initial, raw=0xFFFFFFFF))

    def test_registration_accepts_unaligned_record_bytes(self):
        for offset in range(1, 8):
            for name in ("register-slot0", "register-slot1", "register-full", "register-stale-fields"):
                request = self.request(name, offset)
                self.run_request(request)
                self.assertEqual(request.snapshot()["records"],
                                 fixture_bytes(request.case, "expected", RECORD_BASE, 896))

    def test_every_profile_byte_is_validated_before_effects(self):
        for name in ("register-slot0", "register-slot1", "register-full", "register-stale-fields"):
            request = self.request(name)
            for index in range(896):
                request.records[index] ^= 0x80
                self.run_request(request, UNSUPPORTED)
                request.records[index] ^= 0x80

    def test_required_objects_and_reachable_observers(self):
        for name, positions in (("register-slot0", (1, 3, 4, 5)), ("repeated-open", (2, 3, 4, 5))):
            for position in positions:
                request = self.request(name)
                arguments = request.arguments()
                arguments[position] = None
                self.run_request(request, INVALID, arguments)
            for boundary in (("acquire", "diagnostic", "release") if name.startswith("register")
                             else ("acquire", "release")):
                request = self.request(name)
                setattr(request.plan, boundary, Observer())
                self.run_request(request, INVALID)
        for name in ("register-full", "repeated-open"):
            request = self.request(name)
            request.plan.diagnostic = Observer()
            self.run_request(request)
        request = self.request("register-null-output")
        arguments = request.arguments()
        arguments[-1] = None
        self.run_request(request, INVALID, arguments)

    def test_vendor_null_ignores_optional_storage_contents(self):
        request = self.request("register-null-output")
        request.plan = Plan()
        request.output.contents.value = 17
        self.run_request(request, arguments=[0, request.records, 912, request.output,
                                            ctypes.byref(request.plan), request.raw])
        self.assertEqual(request.output.contents.value, 17)
        self.assertEqual(request.raw.contents.value, 0xFFFFFFFF)

    def test_every_declared_object_pair_is_disjoint(self):
        for name, positions in (("register-slot0", (1, 3, 4, 5)),
                                ("register-null-output", (1, 3, 4, 5)),
                                ("repeated-open", (2, 3, 4, 5))):
            function = self.reopen if name == "repeated-open" else self.register
            for left, right in itertools.permutations(positions, 2):
                request = self.request(name)
                arguments = request.arguments()
                if not request.present:
                    arguments = [0, request.records, 912, request.output,
                                 ctypes.byref(request.plan), request.raw]
                arguments[right] = ctypes.cast(arguments[left], function.argtypes[right])
                self.run_request(request, OVERLAP, arguments)
        for position in (3, 4, 5):
            request = self.request()
            arguments = request.arguments()
            arguments[position] = ctypes.cast(ctypes.addressof(request.buffer) + request.offset + 896,
                                              self.register.argtypes[position])
            self.run_request(request, OVERLAP, arguments)

    def test_short_null_and_wrapped_extents(self):
        maximum = ctypes.c_size_t(-1).value
        for name, positions in (("register-slot0", (1, 3, 4, 5)), ("repeated-open", (2, 3, 4, 5))):
            function = self.reopen if name == "repeated-open" else self.register
            for position in positions:
                request = self.request(name)
                arguments = request.arguments()
                arguments[position] = ctypes.cast(maximum - 1, function.argtypes[position])
                self.run_request(request, BOUNDS, arguments)
        for length in (0, 895, maximum):
            request = self.request()
            arguments = request.arguments()
            arguments[2] = length
            self.run_request(request, BOUNDS, arguments)
        request = self.request()
        arguments = request.arguments()
        arguments[1:3] = None, 0
        self.run_request(request, INVALID, arguments)
        request = self.request("register-null-output")
        arguments = request.arguments()
        arguments[2] = 1
        self.run_request(request, INVALID, arguments)

    def test_exact_inputs_and_repeated_call_rejection(self):
        for value in (0, 1, 0xFFFFFFFF):
            request = self.request()
            request.output.contents.value = value
            self.run_request(request, UNSUPPORTED)
        request = self.request()
        arguments = request.arguments()
        arguments[0] = 2
        self.run_request(request, UNSUPPORTED, arguments)
        for position, values in ((0, (0, 0x401, 0xFFFFFFFF)), (1, (0, 1, 3, 255))):
            for value in values:
                request = self.request("repeated-open")
                arguments = request.arguments()
                arguments[position] = value
                self.run_request(request, UNSUPPORTED, arguments)
        for field in ("count", "object"):
            for value in (0, 2, 0xFFFFFFFF):
                request = self.request("repeated-open")
                setattr(request.state.contents, field, value)
                self.run_request(request, UNSUPPORTED)
        request = self.request("repeated-open")
        request.output.contents.value = 0
        self.run_request(request, UNSUPPORTED)
        for name in ("register-slot0", "register-slot1", "register-full", "register-stale-fields", "repeated-open"):
            request = self.request(name)
            self.run_request(request)
            request.events.clear()
            request.contexts.clear()
            request.snapshots.clear()
            request.bookkeeping.value = 0
            self.run_request(request, UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
