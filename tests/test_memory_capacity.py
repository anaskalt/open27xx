# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare the complete capacity helper with its supplied byte-service cases."""

import ctypes
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
OK, INVALID, OVERLAP = 0, -1, -2
SENTINEL = 0x89ABCDEF
WordPointer = ctypes.POINTER(ctypes.c_uint32)
ByteService = ctypes.CFUNCTYPE(ctypes.c_uint8, ctypes.c_void_p,
                              ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32)
REQUESTS = [(selector, first, second)
            for second in range(2) for first in range(2) for selector in (5, 8)] * 2


class Output(ctypes.Structure):
    _fields_ = [("before", ctypes.c_uint32 * 4), ("word", ctypes.c_uint32),
                ("after", ctypes.c_uint32 * 4)]

    def __init__(self, value=SENTINEL):
        super().__init__()
        ctypes.memset(ctypes.addressof(self), 0xA5, ctypes.sizeof(self))
        self.word = value

    def pointer(self):
        return ctypes.cast(ctypes.byref(self, Output.word.offset), WordPointer)


class ReplyContext(ctypes.Structure):
    _fields_ = [("cursor", ctypes.c_uint32), ("replies", ctypes.c_uint8 * 16)]


class Recorder:
    def __init__(self, replies, size, result):
        self.context = ReplyContext(0, (ctypes.c_uint8 * 16)(*replies))
        self.size = size
        self.result = result
        self.calls = []
        self.snapshots = []
        self.contexts = []
        self.callback = ByteService(self.call)

    def call(self, context, *arguments):
        state = ctypes.cast(context, ctypes.POINTER(ReplyContext)).contents
        index = state.cursor
        state.cursor += 1
        self.calls.append(arguments)
        self.snapshots.append((self.size.word, self.result.word))
        self.contexts.append(context)
        return state.replies[index] if index < 16 else 0


class MemoryCapacityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Memory-capacity tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="memory-capacity-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "memory_capacity.so"
        command = compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/memory_capacity.c"), "-o", str(library),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.measure = cls.library.memory_capacity_measure
        cls.measure.argtypes = [ByteService, ctypes.c_void_p, WordPointer, WordPointer]
        cls.measure.restype = ctypes.c_int
        fixture = ROOT / "tests/vectors/start4/memory-capacity.json"
        cls.cases = json.loads(fixture.read_text())["cases"]

    def assert_guards(self, output):
        self.assertEqual(bytes(output.before), b"\xA5" * 16)
        self.assertEqual(bytes(output.after), b"\xA5" * 16)

    def assert_observations(self, recorder):
        self.assertEqual(recorder.calls, REQUESTS)
        self.assertEqual(recorder.snapshots, [(256, SENTINEL)] * 16)
        self.assertEqual(recorder.context.cursor, 16)
        self.assertEqual(recorder.contexts, [ctypes.addressof(recorder.context)] * 16)
        self.assert_guards(recorder.size)
        self.assert_guards(recorder.result)

    def run_replies(self, replies):
        size, result = Output(), Output()
        recorder = Recorder(replies, size, result)
        status = self.measure(recorder.callback, ctypes.byref(recorder.context),
                              size.pointer(), result.pointer())
        self.assertEqual(status, OK)
        self.assert_observations(recorder)
        self.assertEqual(list(recorder.context.replies), replies)
        return size.word, result.word, recorder

    @staticmethod
    def replies(case):
        return [int(reply["registers"]["r0"], 0)
                for reply in case["execution"]["stubs"][0]["replies"]]

    def test_fixture_scope(self):
        complete = [case for case in self.cases if not case["inputs"]["integrated"]]
        slices = [case for case in self.cases if case["inputs"]["integrated"]]
        self.assertEqual(len(complete), 24)
        self.assertEqual({int(case["function"]["entry"], 0) for case in complete}, {0x0ECC3E60})
        self.assertEqual([case["id"] for case in slices],
                         ["cache-density-0", "cache-density-2",
                          "cache-density-4", "cache-density-6"])
        self.assertEqual({int(case["function"]["entry"], 0) for case in slices}, {0x0EC62714})

    def test_recorded_complete_calls(self):
        for case in self.cases:
            if case["inputs"]["integrated"]:
                continue
            with self.subTest(case=case["id"]):
                replies = self.replies(case)
                self.assertEqual(len(replies), 16)
                self.assertTrue(all(0 <= reply <= 255 for reply in replies))
                size, result, recorder = self.run_replies(replies)
                self.assertEqual(result, int(case["expected"]["registers"]["r0"], 0))
                output_address = int(case["setup"]["registers"]["r0"], 0)
                region = next(region for region in case["expected"]["memory"]
                              if int(region["address"], 0) == output_address - 16)
                observed = bytes(recorder.size.before) + size.to_bytes(4, "little")
                observed += bytes(recorder.size.after)
                self.assertEqual(observed, bytes.fromhex(region["hex"]))
                events = case["expected"]["events"]
                self.assertEqual(recorder.calls, [tuple(int(word, 0) for word in event["arguments"][:3])
                                                  for event in events])
                for index, event in enumerate(events):
                    self.assertEqual((event["kind"], int(event["entry"], 0), event["reply_index"]),
                                     ("stub", 0x0ED6B4C6, index))

    def test_unused_replies_still_observed(self):
        case = next(case for case in self.cases if case["id"] == "different-two-samples")
        replies = self.replies(case)
        for unused in (0, 1, 128, 255):
            with self.subTest(unused=unused):
                for start in (4, 12):
                    replies[start:start + 4] = [unused] * 4
                size, result, _ = self.run_replies(replies)
                self.assertEqual((size, result), (1024, 4))

    def test_passes_are_distinct_and_ordered(self):
        case = next(case for case in self.cases if case["id"] == "different-two-samples")
        replies = self.replies(case)
        size, result, _ = self.run_replies(replies[8:] + replies[:8])
        self.assertEqual((size, result), (4096, 2))

    def test_class_seven_is_success_with_distinct_sizes(self):
        sizes = []
        for name in ("density-code-01", "density-code-03", "density-code-05"):
            case = next(case for case in self.cases if case["id"] == name)
            size, result, _ = self.run_replies(self.replies(case))
            self.assertEqual(result, 7)
            sizes.append(size)
        self.assertEqual(sizes, [1536, 3072, 6144])

    def test_null_arguments_preserve_outputs_without_callbacks(self):
        for missing in itertools.product((False, True), repeat=3):
            if not any(missing):
                continue
            with self.subTest(missing=missing):
                size, result = Output(), Output()
                recorder = Recorder([0] * 16, size, result)
                before = bytes(size), bytes(result), bytes(recorder.context)
                status = self.measure(ByteService() if missing[0] else recorder.callback,
                                      ctypes.byref(recorder.context),
                                      None if missing[1] else size.pointer(),
                                      None if missing[2] else result.pointer())
                self.assertEqual(status, INVALID)
                self.assertEqual((bytes(size), bytes(result), bytes(recorder.context)), before)
                self.assertEqual(recorder.calls, [])

    def test_overlapping_outputs_rejected_before_access(self):
        storage = (ctypes.c_uint32 * 4)(*([SENTINEL] * 4))
        calls = []
        callback = ByteService(lambda *args: calls.append(args) or 0)
        before = bytes(storage)
        for offset in range(-3, 4):
            with self.subTest(offset=offset):
                size = ctypes.cast(ctypes.byref(storage, 4), WordPointer)
                result = ctypes.cast(ctypes.byref(storage, 4 + offset), WordPointer)
                self.assertEqual(self.measure(callback, None, size, result), OVERLAP)
                self.assertEqual(bytes(storage), before)
                self.assertEqual(calls, [])

    def test_adjacent_outputs_and_null_context(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                storage = (ctypes.c_uint32 * 4)(*([SENTINEL] * 4))
                size_index, class_index = (2, 1) if reverse else (1, 2)
                calls = []
                observations = []

                def service(context, *arguments, calls=calls, observations=observations,
                            storage=storage, size_index=size_index, class_index=class_index):
                    calls.append((context, arguments))
                    observations.append((storage[size_index], storage[class_index]))
                    return 255

                callback = ByteService(service)
                size = ctypes.cast(ctypes.byref(storage, 4 * size_index), WordPointer)
                result = ctypes.cast(ctypes.byref(storage, 4 * class_index), WordPointer)
                self.assertEqual(self.measure(callback, None, size, result), OK)
                self.assertEqual(calls, [(None, request) for request in REQUESTS])
                self.assertEqual(observations, [(256, SENTINEL)] * 16)
                self.assertEqual((storage[size_index], storage[class_index]), (2048, 3))
                self.assertEqual((storage[0], storage[3]), (SENTINEL, SENTINEL))


if __name__ == "__main__":
    unittest.main()
