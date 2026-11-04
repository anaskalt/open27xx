# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check complete bounded registration, ordered observations and preflight."""

import ctypes
import hashlib
import itertools
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_suspend_helpers import (
    BOUNDS,
    INVALID,
    OK,
    OVERLAP,
    POINTER_MAX,
    SENTINEL,
    WORD_MAX,
    Buffer,
    Byte,
    BytePointer,
    Storage,
    View,
    Word,
    region,
)

ROOT = Path(__file__).resolve().parents[1]
OBJECT_BYTES = 2936
DI = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, Word)
P16 = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word)


class Inputs(ctypes.Structure):
    _fields_ = [("first", Word), ("callback", Word), ("cookie", Word), ("sr", Word)]


class ReadPlan(ctypes.Structure):
    _fields_ = [("words", ctypes.POINTER(Word)), ("count", ctypes.c_size_t)]


class Observers(ctypes.Structure):
    _fields_ = [("di", DI), ("read", P16), ("write", P16), ("context", ctypes.c_void_p)]


def object_bytes(count=0, records=(), tail=b"", fill=0xB7):
    data = bytearray(bytes([fill]) * OBJECT_BYTES + tail)
    data[0xB5C:0xB60] = (count & WORD_MAX).to_bytes(4, "little")
    for index, (first, callback, cookie) in enumerate(records):
        start = 0x1C + 36 * index
        data[start] = first & 255
        data[start + 4:start + 8] = callback.to_bytes(4, "little")
        data[start + 8:start + 12] = cookie.to_bytes(4, "little")
    return bytes(data)


def registration_result(data, keys, sr, name):
    expected = bytearray(data)
    expected[:4] = sr.to_bytes(4, "little")
    count = int.from_bytes(data[0xB5C:0xB60], "little")
    if count >= 40:
        return bytes(expected), WORD_MAX
    for index in range(count):
        start = 0x1C + 36 * index
        actual = (data[start], int.from_bytes(data[start + 4:start + 8], "little"),
                  int.from_bytes(data[start + 8:start + 12], "little"))
        if actual == keys:
            return bytes(expected), 0
    if keys[1] == 0:
        return bytes(expected), 1
    terminated = name.split(b"\0", 1)[0]
    basename = terminated[max(terminated.rfind(b"/"), terminated.rfind(b"\\")) + 1:][:21]
    start = 0x1C + 36 * count
    expected[start] = keys[0] & 255
    expected[start + 4:start + 8] = keys[1].to_bytes(4, "little")
    expected[start + 8:start + 12] = keys[2].to_bytes(4, "little")
    expected[start + 12:start + 13 + len(basename)] = basename + b"\0"
    expected[0xB5C:0xB60] = (count + 1).to_bytes(4, "little")
    expected[0xB74:0xB78] = b"\0" * 4
    return bytes(expected), 0


class Request:
    def __init__(self, data=None, keys=(0x1AB, 0x87654321, 0xFEDCBA98), sr=0xD5394E81,
                 name=b"parent\\dir/name\0ignored", logging=3, reads=(1, 0), unaligned=0):
        self.storage = {}
        self.events = []
        self.name_bytes = name
        self.keys = keys
        self.sr = sr
        self.read_values = reads
        self.data = object_bytes(tail=b"untouched tail") if data is None else data

        def add(label, value, offset=0):
            self.storage[label] = Storage(value, offset)
            return self.storage[label].pointer

        inputs = add("inputs", Inputs(*keys, sr))
        data_pointer = add("object_bytes", self.data, unaligned)
        object_view = add("object", Buffer(data_pointer, len(self.data)))
        name_view = None
        if name is not None:
            name_pointer = add("name_bytes", name, unaligned)
            name_view = add("name", View(name_pointer if name else None, len(name)))
        logging_pointer = None if logging is None else add("logging", Byte(logging))
        words = add("read_words", (Word * max(1, len(reads)))(*reads))
        plan = add("reads", ReadPlan(ctypes.cast(words, ctypes.POINTER(Word)), len(reads)))
        self.callbacks = (
            DI(lambda context, before, after: self.events.append(
                ("di", (before, after), self.snapshot()))),
            P16(lambda context, value: self.events.append(("read", (value,), self.snapshot()))),
            P16(lambda context, value: self.events.append(("write", (value,), self.snapshot()))),
        )
        observers = add("observers", Observers(*self.callbacks, None))
        raw = add("raw", Word(SENTINEL))
        self.names = ["inputs", "object", "name", "logging", "reads", "observers", "raw"]
        self.arguments = [inputs, object_view, name_view, logging_pointer, plan, observers, raw]

    def object(self, name):
        return self.storage[name].pointer.contents

    def snapshot(self):
        return {name: storage.snapshot() for name, storage in self.storage.items()}

    def redirect(self, name, address):
        if name == "object_bytes" or name == "name_bytes":
            self.object(name.removesuffix("_bytes")).bytes = ctypes.cast(address, BytePointer)
        elif name == "read_words":
            self.object("reads").words = ctypes.cast(address, ctypes.POINTER(Word))
        else:
            index = self.names.index(name)
            self.arguments[index] = ctypes.cast(address, type(self.arguments[index]))


class SuspendRegistrarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Suspend registrar tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="suspend-registrar-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "suspend_registrar.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/suspend_registrar.c"),
            str(ROOT / "src/start4/suspend_helpers.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.suspend_register
        cls.function.argtypes = [ctypes.POINTER(kind) for kind in
                                 (Inputs, Buffer, View, Byte, ReadPlan, Observers, Word)]
        cls.function.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/suspend-registrar.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = json.loads(path.read_text())["cases"]

    def run_request(self, request, status=OK, expected=None, raw=None):
        before = request.snapshot()
        self.assertEqual(self.function(*request.arguments), status)
        if status != OK:
            self.assertEqual(request.events, [])
            self.assertEqual(request.snapshot(), before)
            return
        if expected is None:
            expected, raw = registration_result(request.data, request.keys,
                                                request.sr, request.name_bytes)

        def replace(snapshot, label, value):
            result = dict(snapshot)
            storage = request.storage[label]
            changed = bytearray(result[label])
            changed[storage.offset:storage.offset + len(value)] = value
            result[label] = bytes(changed)
            return result

        completed = replace(before, "object_bytes", expected)
        events = [("di", (request.sr, request.sr & ~0x40000000), before)]
        events.extend(("read", (value,), before) for value in request.read_values)
        events.append(("write", (request.sr,), completed))
        self.assertEqual(request.events, events)
        self.assertEqual(request.snapshot(), replace(completed, "raw", raw.to_bytes(4, sys.byteorder)))

    def test_sixteen_complete_public_calls(self):
        self.assertEqual(self.fixture_hash,
                         "ad308116d008f0f3ae5a526c9d1292813cd61a159b636114993d08aad063f8dc")
        self.assertEqual(len(self.cases), 16)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                registers = case["setup"]["registers"]
                data, start = region(case, "setup", int(registers["gp"], 0) + 0x14E4)
                base = int.from_bytes(data[start:start + 4], "little")
                data, start = region(case, "setup", base)
                data = data[start:start + OBJECT_BYTES]
                expected, start = region(case, "expected", base)
                expected = expected[start:start + OBJECT_BYTES]
                count = int.from_bytes(data[0xB5C:0xB60], "little")
                try:
                    name, start = region(case, "setup", int(registers["r3"], 0))
                    name = name[start:-3]
                except AssertionError:
                    name = None
                logging = None
                if count < 40:
                    log, start = region(case, "setup", 0xE4105970)
                    logging = log[start]
                reads = tuple(int(event["value"], 0) for event in case["expected"]["events"]
                              if event["kind"] == "p16_read")
                request = Request(data=data, keys=tuple(int(registers[f"r{i}"], 0) for i in range(3)),
                                  sr=int(registers["sr"], 0), name=name, logging=logging,
                                  reads=reads, unaligned=3)
                self.run_request(request, expected=expected,
                                 raw=int(case["expected"]["registers"]["r0"], 0))
                expected_events = []
                for event in case["expected"]["events"]:
                    if event["kind"] == "irq_disable":
                        expected_events.append(("di", (int(event["sr_before"], 0),
                                                       int(event["sr_after"], 0))))
                    else:
                        expected_events.append((event["kind"].removeprefix("p16_"),
                                                (int(event["value"], 0),)))
                self.assertEqual([(kind, values) for kind, values, _ in request.events],
                                 expected_events)

    def test_general_counts_records_tuples_and_object_tails(self):
        generator = random.Random(0x49A8271)
        for count in range(40):
            records = [(generator.randrange(256), generator.getrandbits(32), generator.getrandbits(32))
                       for _ in range(count)]
            tail = generator.randbytes(33 + count)
            data = object_bytes(count, records, tail, fill=(count * 37) & 255)
            searches = [(generator.getrandbits(32), generator.getrandbits(32) or 1,
                         generator.getrandbits(32)), (1, 0, 0x79A31EF4)]
            if records:
                searches += [records[0], records[-1], (records[-1][0] + 256, *records[-1][1:])]
            for keys in searches:
                with self.subTest(count=count, keys=keys):
                    self.run_request(Request(data=data, keys=keys, sr=generator.getrandbits(32),
                        name=b"arbitrary/\xFFbasename\0\x80unused", logging=count % 4,
                        reads=(1,) * (count % 7) + (0,), unaligned=count % 8))

    def test_all_lookup_gates_duplicates_and_zero_callbacks(self):
        keys = (0xD9, 0x8765A430, 0xF1DC89B7)
        records = [(keys[0] ^ 1, *keys[1:]), (keys[0], keys[1] ^ 1, keys[2]),
                   (*keys[:2], keys[2] ^ 1), keys, keys]
        self.run_request(Request(data=object_bytes(5, records), keys=keys, name=b"no terminator"))
        keys = (7, 0, 0xFFFFFFFF)
        self.run_request(Request(data=object_bytes(2, [keys, keys]), keys=keys, name=None))
        self.run_request(Request(data=object_bytes(2, [keys, keys]), keys=(0x107, 0, keys[2]), name=None))

    def test_capacity_precedes_lookup_and_zero_callback(self):
        for count in (40, 41, 127, 65536, 0x7FFFFFFF):
            for callback in (0, 1, WORD_MAX):
                keys = (0x17, callback, 0x3E4A2109)
                for name in (None, b"", b"unterminated"):
                    for logging in (None, 0, 3, 4, 255):
                        with self.subTest(count=count, callback=callback, logging=logging):
                            self.run_request(Request(data=object_bytes(count, [keys]), keys=keys,
                                                     name=name, logging=logging))

    def test_unused_names_do_not_need_termination_or_nonzero_extent(self):
        keys = (3, 0x1F2E3D4C, 0xFEED2179)
        for name in (None, b"", b"\xFFnonterminated"):
            self.run_request(Request(data=object_bytes(1, [keys]), keys=keys, name=name))
            self.run_request(Request(keys=(keys[0], 0, keys[2]), name=name))

    def test_arbitrary_basename_bytes_separators_and_full_lengths(self):
        generator = random.Random(0xF3D7)
        names = [b"", b"/", b"\\", b"//\\", b"../..", b"a/b\\c/d", b"a\\b/c\\d",
                 b"a/b/", b"a\\b\\", bytes(range(1, 256))]
        names += [b"prefix/" + bytes(generator.randrange(1, 256) for _ in range(length))
                  for length in (1, 20, 21, 22, 23, 255, 4096, 8192)]
        for name in names:
            with self.subTest(length=len(name), prefix=name[:8]):
                self.run_request(Request(name=name + b"\0/ignored\\tail", unaligned=5))

    def test_all_sr_bits_and_finite_busy_plans(self):
        for bit in range(32):
            for sr in (1 << bit, WORD_MAX ^ (1 << bit)):
                self.run_request(Request(sr=sr, reads=(1,) * (bit % 11) + (0,)))
        self.run_request(Request(sr=0, reads=(1,) * 257 + (0,)))
        self.run_request(Request(sr=WORD_MAX, reads=(0,)))

    def test_insert_final_slot_then_capacity(self):
        request = Request(data=object_bytes(39), keys=(0x29, 0xC3901F65, 0xEA902D48))
        self.run_request(request)
        final = request.storage["object_bytes"].payload()
        self.assertEqual(int.from_bytes(final[0xB5C:0xB60], "little"), 40)
        self.run_request(Request(data=final, keys=request.keys, name=None, logging=None))

    def test_required_arguments_and_typed_alignment(self):
        for index in (0, 1, 4, 5, 6):
            request = Request()
            request.arguments[index] = None
            self.run_request(request, INVALID)
        for index in (0, 1, 2, 4, 5, 6):
            request = Request()
            pointer = request.arguments[index]
            request.arguments[index] = ctypes.cast(ctypes.addressof(pointer.contents) + 1, type(pointer))
            self.run_request(request, INVALID)
        request = Request()
        request.object("reads").words = ctypes.cast(request.storage["read_words"].address + 1,
                                                    ctypes.POINTER(Word))
        self.run_request(request, INVALID)

    def test_required_observers_before_effects(self):
        for kind, callback_type in (("di", DI), ("read", P16), ("write", P16)):
            for count in (0, 40):
                request = Request(data=object_bytes(count))
                setattr(request.object("observers"), kind, callback_type())
                self.run_request(request, INVALID)

    def test_every_pair_of_objects_and_complete_spans_is_disjoint(self):
        names = Request().names + ["object_bytes", "name_bytes", "read_words"]
        for left, right in itertools.combinations(names, 2):
            with self.subTest(left=left, right=right):
                request = Request()
                request.redirect(right, request.storage[left].address)
                self.run_request(request, OVERLAP)

    def test_declared_unused_tails_participate_in_overlap(self):
        for count in (0, 40):
            for name in ("object_bytes", "name_bytes", "read_words"):
                request = Request(data=object_bytes(count, tail=b"\xAB" * 128), name=b"\0" + b"T" * 127,
                                  reads=(1,) * 31 + (0,))
                storage = request.storage[name]
                end = storage.address + storage.length
                address = (end - 4) & ~3
                request.arguments[-1] = ctypes.cast(address, ctypes.POINTER(Word))
                self.run_request(request, OVERLAP)

    def test_logging_and_count_domain_reject_without_effects(self):
        for count in (0, 1, 39):
            for logging in (None, 4, 255):
                self.run_request(Request(data=object_bytes(count), logging=logging), INVALID)
        for count in (-1, -19, -0x80000000):
            self.run_request(Request(data=object_bytes(count)), BOUNDS)

    def test_read_plan_domain_rejects_complete_invalid_sequences(self):
        self.run_request(Request(reads=()), BOUNDS)
        for reads in ((1,), (1, 1), (2, 0), (WORD_MAX, 0), (0, 0), (0, 1), (1, 0, 1), (0, 1, 0)):
            self.run_request(Request(reads=reads), INVALID)
        request = Request()
        request.object("reads").words = None
        self.run_request(request, INVALID)
        for count in (WORD_MAX // 4 + 1, POINTER_MAX // 4 + 1):
            request = Request()
            request.object("reads").count = count
            self.run_request(request, BOUNDS)

    def test_full_extent_bounds_and_null_views(self):
        for length in (0, 2935, WORD_MAX + 1):
            if length > POINTER_MAX:
                continue
            request = Request()
            request.object("object").length = length
            self.run_request(request, BOUNDS)
        for label in ("object", "name"):
            request = Request()
            request.object(label).bytes = None
            self.run_request(request, INVALID)
        if POINTER_MAX > WORD_MAX:
            for count in (0, 40):
                request = Request(data=object_bytes(count))
                request.object("name").length = WORD_MAX + 1
                self.run_request(request, BOUNDS)

    def test_insertion_requires_complete_terminated_name(self):
        for name, status in ((None, INVALID), (b"", INVALID), (b"no-nul", BOUNDS),
                             (b"a" * 4096, BOUNDS)):
            self.run_request(Request(name=name), status)
        for extent in (0, 0x80000000, WORD_MAX):
            request = Request()
            request.object("name").length = extent
            if extent > 0x7FFFFFFF:
                request.object("name").bytes = ctypes.cast(0x10000, BytePointer)
            self.run_request(request, BOUNDS)

    def test_address_wrap_in_descriptors_and_full_unused_spans(self):
        for index in (0, 1, 2, 4, 5, 6):
            request = Request()
            pointer = request.arguments[index]
            alignment = ctypes.alignment(pointer._type_)
            request.arguments[index] = ctypes.cast(POINTER_MAX - alignment + 1, type(pointer))
            self.run_request(request, BOUNDS)
        for count in (0, 40):
            for label in ("object", "name"):
                request = Request(data=object_bytes(count))
                request.object(label).bytes = ctypes.cast(POINTER_MAX - 3, BytePointer)
                self.run_request(request, BOUNDS)
            request = Request(data=object_bytes(count))
            request.object("reads").words = ctypes.cast(POINTER_MAX - 3, ctypes.POINTER(Word))
            self.run_request(request, BOUNDS)
            request = Request(data=object_bytes(count))
            request.arguments[3] = ctypes.cast(POINTER_MAX, BytePointer)
            self.run_request(request, BOUNDS)


if __name__ == "__main__":
    unittest.main()
