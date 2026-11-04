# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check paired ARM configuration calls and ordered semantic observations."""

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
Observer = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, WordPointer, ctypes.c_size_t, Word)
VersionObserver = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, Word, Word)
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
SENTINEL = 0xD451BE70


class Inputs(ctypes.Structure):
    _fields_ = [("handle", Word), ("control", Word)]


class ReplyPlan(ctypes.Structure):
    _fields_ = [("words", WordPointer), ("count", ctypes.c_size_t)]


class Observers(ctypes.Structure):
    _fields_ = [("acquire", Observer), ("version", VersionObserver), ("service", Observer),
                ("release", Observer), ("context", ctypes.c_void_p)]


def guarded(value):
    class Guard(ctypes.Structure):
        _fields_ = [("before", ctypes.c_uint64), ("value", type(value)), ("after", ctypes.c_uint64)]
    return Guard(0x713AC924713AC924, value, 0x57DDEF8357DDEF83)


def pointer(guard):
    return ctypes.cast(ctypes.byref(guard, type(guard).value.offset),
                       ctypes.POINTER(type(guard)._fields_[1][1]))


def fixture_word(case, phase, address):
    for region in case[phase]["memory"]:
        start = int(region["address"], 0)
        data = (bytes.fromhex(region["hex"]) if "hex" in region else
                bytes.fromhex(region["fill"]) * region["size"])
        if start <= address and address + 4 <= start + len(data):
            return int.from_bytes(data[address - start:address - start + 4], "little")
    raise AssertionError(f"Unmapped fixture word: {address:#x}")


class Request:
    def __init__(self, case):
        self.case = case
        cpu = int(case["execution"]["version_input"]["word"], 0)
        self.service = cpu == 0
        self.guards = {
            "inputs": guarded(Inputs(*(int(case["setup"]["registers"][name], 0) for name in ("r0", "r1")))),
            "configuration": guarded(Word(fixture_word(case, "setup", 0xE403B51C))),
            "cpu": guarded(Word(cpu)),
            "index": guarded(Word(fixture_word(case, "setup", 0xE403B490) if self.service else SENTINEL)),
            "raw": guarded(Word(SENTINEL)),
            "replies": guarded((Word * 4)(0, 7 if self.service else 0, 0, SENTINEL)),
        }
        self.inputs, self.configuration, self.cpu, self.index, self.raw = (
            pointer(self.guards[name]) for name in ("inputs", "configuration", "cpu", "index", "raw"))
        self.words = ctypes.cast(pointer(self.guards["replies"]), WordPointer)
        self.plan = ReplyPlan(self.words, 3 if self.service else 2)
        self.events, self.snapshots, self.contexts = [], [], []
        self.bookkeeping = Word(0)

        def record(context, event):
            self.events.append(event)
            self.snapshots.append((self.configuration.contents.value, self.raw.contents.value))
            self.contexts.append(context)
            self.bookkeeping.value += 1

        @Observer
        def observe(context, entry, arguments, count, reply):
            record(context, ("boundary", entry, tuple(arguments[:count]), reply))

        @VersionObserver
        def version(context, site, destination, word):
            record(context, ("version", site, destination, word))

        self.observe, self.version = observe, version
        self.observers = Observers(observe, version, observe, observe, ctypes.addressof(self.bookkeeping))

    def arguments(self, include_index=False):
        return [self.inputs, self.configuration, self.cpu,
                self.index if self.service or include_index else None,
                ctypes.byref(self.plan), ctypes.byref(self.observers), self.raw]

    def storage(self):
        return bytes(self.plan), bytes(self.observers), {name: bytes(value) for name, value in self.guards.items()}

    def reset_observations(self):
        self.events.clear()
        self.snapshots.clear()
        self.contexts.clear()
        self.bookkeeping.value = 0


class ArmConfigurationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("ARM configuration tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="arm-configuration-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "arm_configuration.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/arm_configuration.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.arm_configuration_execute
        cls.function.argtypes = [ctypes.POINTER(Inputs), WordPointer, WordPointer, WordPointer,
                                ctypes.POINTER(ReplyPlan), ctypes.POINTER(Observers), WordPointer]
        cls.function.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/arm-configuration.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = json.loads(path.read_text())["cases"]

    def request(self, index=0):
        return Request(self.cases[index])

    def run_request(self, request, expected=OK, arguments=None):
        before = request.storage()
        incoming_raw = request.raw.contents.value
        self.assertEqual(self.function(*(request.arguments() if arguments is None else arguments)), expected)
        if expected != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.events, [])
        self.assertEqual(request.storage()[:2], before[:2])
        for name in request.guards.keys() - {"configuration", "raw"}:
            self.assertEqual(bytes(request.guards[name]), before[2][name])
        for guard in request.guards.values():
            self.assertEqual((guard.before, guard.after), (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)] * len(request.events))
        self.assertEqual(request.bookkeeping.value, len(request.events))
        self.assertTrue(all(raw == incoming_raw for _, raw in request.snapshots))

    def test_both_complete_fixtures_and_observer_visible_order(self):
        self.assertEqual(self.fixture_hash,
                         "510e76f733805e52eab9343b776531616cac97ba4acedbf93589ce26d0f0cd9c")
        self.assertEqual(len(self.cases), 2)
        for index, case in enumerate(self.cases):
            request = self.request(index)
            self.run_request(request)
            replies = {int(stub["entry"], 0): int(stub["replies"][0]["registers"]["r0"], 0)
                       for stub in case["execution"]["stubs"]}
            events = []
            for event in case["expected"]["events"]:
                if event["kind"] == "version":
                    events.append(("version", int(event["pc"], 0), int(event["destination"][1:]),
                                   int(event["value"], 0)))
                else:
                    entry = int(event["entry"], 0)
                    count = 6 if entry == 0x0ED65284 else 1
                    events.append(("boundary", entry, tuple(int(word, 0) for word in event["arguments"][:count]),
                                   replies[entry]))
            self.assertEqual(request.events, events)
            self.assertEqual(request.configuration.contents.value, fixture_word(case, "expected", 0xE403B51C))
            self.assertEqual(request.raw.contents.value, int(case["expected"]["registers"]["r0"], 0))
            self.assertEqual(request.snapshots[0], (0x1230FC1B, SENTINEL))
            self.assertEqual(request.snapshots[1:], [(0x1230FC5B, SENTINEL)] * (len(events) - 1))

    def test_no_raw_result_premise_and_unused_index_is_preserved(self):
        for index in range(2):
            for raw in (0, 1, 0xFFFFFFFF):
                request = self.request(index)
                request.raw.contents.value = raw
                self.run_request(request)
        for value in (0, 1, 7, 0x80000000, 0xFFFFFFFF):
            request = self.request(1)
            request.index.contents.value = value
            request.observers.service = Observer()
            self.run_request(request, arguments=request.arguments(include_index=True))
            self.assertEqual(request.index.contents.value, value)
            self.assertEqual(len(request.events), 3)

    def test_required_objects_and_every_reachable_observer(self):
        for index in range(2):
            for position in range(7):
                if index == 1 and position == 3:
                    continue
                request = self.request(index)
                arguments = request.arguments()
                arguments[position] = None
                self.run_request(request, INVALID, arguments)
            request = self.request(index)
            request.plan.words = WordPointer()
            self.run_request(request, INVALID)
            for name in ("acquire", "version", "release", "service"):
                request = self.request(index)
                setattr(request.observers, name, VersionObserver() if name == "version" else Observer())
                self.run_request(request, OK if index == 1 and name == "service" else INVALID)

    def test_exact_handle_control_configuration_cpu_and_index(self):
        for index in range(2):
            for name, values in (("handle", (0, 1, 0x61726D10, 0xFFFFFFFF)),
                                 ("control", (0, 2, 0xFFFFFFFF))):
                for value in values:
                    request = self.request(index)
                    setattr(request.inputs.contents, name, value)
                    self.run_request(request, UNSUPPORTED)
            for field, values in (("configuration", (0, 0x1230FC5B, 0x1230FC1A, 0xFFFFFFFF)),
                                  ("cpu", (1, 0x41, 0x80000000, 0xFFFFFFFF))):
                for value in values:
                    request = self.request(index)
                    getattr(request, field).contents.value = value
                    self.run_request(request, UNSUPPORTED)
        for value in (0, 2, 7, 0xFFFFFFFF):
            request = self.request()
            request.index.contents.value = value
            self.run_request(request, UNSUPPORTED)
        for index in range(2):
            request = self.request(index)
            self.run_request(request)
            request.reset_observations()
            self.run_request(request, UNSUPPORTED)

    def test_every_reply_and_exact_logical_count_are_preflighted(self):
        for index in range(2):
            count = 3 if index == 0 else 2
            for reply_index in range(count):
                for value in (1, 4, 0xFFFFFFFF):
                    request = self.request(index)
                    request.words[reply_index] = value
                    self.run_request(request, UNSUPPORTED)
            for length in (0, count - 1, count + 1):
                request = self.request(index)
                request.plan.count = length
                self.run_request(request, BOUNDS if length < count else UNSUPPORTED)
        request = self.request(1)
        request.plan.count = 3
        request.words[1] = 7
        self.run_request(request, UNSUPPORTED)

    def test_all_objects_and_complete_reply_spans_are_disjoint(self):
        for index in range(2):
            for left, right in itertools.permutations(range(7), 2):
                request = self.request(index)
                arguments = request.arguments(include_index=True)
                arguments[right] = ctypes.cast(arguments[left], self.function.argtypes[right])
                self.run_request(request, OVERLAP, arguments)
            for position in range(7):
                request = self.request(index)
                arguments = request.arguments(include_index=True)
                request.plan.words = ctypes.cast(arguments[position], WordPointer)
                self.run_request(request, OVERLAP, arguments)
                if position == 4:
                    continue
                request = self.request(index)
                arguments = request.arguments(include_index=True)
                last_word = ctypes.addressof(request.words.contents) + 4 * (request.plan.count - 1)
                arguments[position] = ctypes.cast(last_word, self.function.argtypes[position])
                self.run_request(request, OVERLAP, arguments)
            request = self.request(index)
            alias = guarded(ReplyPlan())
            alias_plan = pointer(alias)
            first_word = ctypes.addressof(alias_plan.contents) - 4 * (request.plan.count - 1)
            alias_plan.contents.words = ctypes.cast(first_word, WordPointer)
            alias_plan.contents.count = request.plan.count
            before = bytes(alias)
            arguments = request.arguments(include_index=True)
            arguments[4] = alias_plan
            self.run_request(request, OVERLAP, arguments)
            self.assertEqual(bytes(alias), before)

    def test_address_and_reply_size_wrap_are_rejected_before_access(self):
        maximum = ctypes.c_size_t(-1).value
        for index in range(2):
            for position in range(7):
                request = self.request(index)
                arguments = request.arguments(include_index=True)
                arguments[position] = ctypes.cast(maximum - 1, self.function.argtypes[position])
                self.run_request(request, BOUNDS, arguments)
            request = self.request(index)
            request.plan.words = ctypes.cast(maximum - 1, WordPointer)
            self.run_request(request, BOUNDS)
            request = self.request(index)
            request.plan.count = maximum // 4 + 1
            self.run_request(request, BOUNDS)


if __name__ == "__main__":
    unittest.main()
