# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check bounded suspend operations, complete fixtures and rejected storage."""

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

ROOT = Path(__file__).resolve().parents[1]
Byte = ctypes.c_uint8
Word = ctypes.c_uint32
BytePointer = ctypes.POINTER(Byte)
OK, INVALID, BOUNDS, OVERLAP = 0, -1, -3, -4
SENTINEL = 0x7965C3E1
WORD_MAX = 0xFFFFFFFF
POINTER_MAX = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1


class View(ctypes.Structure):
    _fields_ = [("bytes", BytePointer), ("length", ctypes.c_size_t)]


class Buffer(ctypes.Structure):
    _fields_ = [("bytes", BytePointer), ("length", ctypes.c_size_t)]


class LookupInputs(ctypes.Structure):
    _fields_ = [("count", ctypes.c_int32), ("first", Word), ("second", Word), ("third", Word)]


class CopyInputs(ctypes.Structure):
    _fields_ = [("capacity", Word), ("offset", Word)]


class Storage:
    def __init__(self, value, unaligned=0):
        self.is_bytes = isinstance(value, bytes)
        self.type = Byte if self.is_bytes else type(value)
        data = value if self.is_bytes else bytes(value)
        self.offset = 16 + unaligned
        self.length = len(data)
        self.backing = (ctypes.c_uint64 * ((self.offset + max(128, len(data)) + 23) // 8))()
        ctypes.memset(self.backing, 0xA5, ctypes.sizeof(self.backing))
        self.address = ctypes.addressof(self.backing) + self.offset
        ctypes.memmove(self.address, data, len(data))
        self.pointer = ctypes.cast(self.address, ctypes.POINTER(self.type))

    def snapshot(self):
        return bytes(self.backing)

    def payload(self):
        return ctypes.string_at(self.address, self.length)


class Request:
    def __init__(self, operation, source=b"\xD6length\0unused", destination=b"!" * 64,
                 capacity=17, offset=2, records=None, count=1, keys=(7, 0x12345678, 0xFEDCBA98),
                 unaligned=0):
        self.operation = operation
        self.storage = {}
        self.views = {}

        def add(name, value, byte_offset=0):
            self.storage[name] = Storage(value, byte_offset)
            return self.storage[name].pointer

        def view(name, data, view_type):
            address = add(name + "_bytes", data, unaligned)
            self.views[name + "_bytes"] = name
            return add(name, view_type(address if data else None, len(data)))

        raw = add("raw", Word(SENTINEL))
        if operation == "lookup":
            if records is None:
                record = bytearray(b"\xE3" * 36)
                record[0] = keys[0]
                record[4:8] = keys[1].to_bytes(4, "little")
                record[8:12] = keys[2].to_bytes(4, "little")
                records = bytes(record)
            inputs = add("inputs", LookupInputs(count, *keys))
            record_view = view("records", records, View)
            self.names = ["inputs", "records", "raw"]
            self.arguments = [inputs, record_view, raw]
        elif operation == "length":
            source_view = view("source", source, View)
            self.names = ["source", "raw"]
            self.arguments = [source_view, raw]
        else:
            inputs = add("inputs", CopyInputs(capacity, offset))
            destination_view = view("destination", destination, Buffer)
            source_view = view("source", source, View)
            self.names = ["inputs", "destination", "source", "raw"]
            self.arguments = [inputs, destination_view, source_view, raw]

    def object(self, name):
        return self.storage[name].pointer.contents

    def snapshot(self):
        return {name: storage.snapshot() for name, storage in self.storage.items()}


def region(case, phase, address):
    for item in case[phase]["memory"]:
        start = int(item["address"], 0)
        data = (bytes.fromhex(item["hex"]) if "hex" in item else
                bytes.fromhex(item["fill"]) * item["size"])
        if start <= address < start + len(data):
            return data, address - start
    raise AssertionError(f"Missing fixture address {address:#x}")


class SuspendHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Suspend helper tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="suspend-helpers-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "suspend_helpers.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/suspend_helpers.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.functions = {}
        for operation, types in {
                "lookup": [LookupInputs, View, Word], "length": [View, Word],
                "copy": [CopyInputs, Buffer, View, Word]}.items():
            function = getattr(cls.library, "suspend_" + operation)
            function.argtypes = [ctypes.POINTER(kind) for kind in types]
            function.restype = ctypes.c_int
            cls.functions[operation] = function
        path = ROOT / "tests/vectors/start4/suspend-helpers.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = json.loads(path.read_text())["cases"]

    def run_request(self, request, status=OK, raw=None, destination=None):
        before = request.snapshot()
        self.assertEqual(self.functions[request.operation](*request.arguments), status)
        expected = dict(before)
        changes = {} if status != OK else {"raw": raw.to_bytes(4, sys.byteorder)}
        if status == OK and destination is not None:
            changes["destination_bytes"] = destination
        for name, data in changes.items():
            storage = request.storage[name]
            updated = bytearray(before[name])
            updated[storage.offset:storage.offset + len(data)] = data
            expected[name] = bytes(updated)
        self.assertEqual(request.snapshot(), expected)

    def test_twenty_complete_public_calls(self):
        self.assertEqual(self.fixture_hash,
                         "6c7f1850c4877b2aaea02c2f44f7b64b636fe8ad4e11792b4063884f5c3e2339")
        self.assertEqual(len(self.cases), 20)
        counts = {"lookup": 0, "length": 0, "copy": 0}
        for case in self.cases:
            with self.subTest(case=case["id"]):
                registers = case["setup"]["registers"]
                arguments = [int(registers.get("r" + str(index), "0"), 0) for index in range(4)]
                operation = case["id"].split("-")[0]
                counts[operation] += 1
                if operation == "lookup":
                    gp = int(registers["gp"], 0)
                    data, start = region(case, "setup", gp + 0x14E4)
                    base = int.from_bytes(data[start:start + 4], "little")
                    data, start = region(case, "setup", base + 0xB5C)
                    count = int.from_bytes(data[start:start + 4], "little", signed=True)
                    records = b""
                    if count > 0:
                        data, start = region(case, "setup", base + 0x1C)
                        records = data[start:start + 36 * count]
                        self.assertEqual(len(records), 36 * count)
                    request = Request(operation, records=records, count=count,
                                      keys=tuple(arguments[:3]), unaligned=1)
                    destination = None
                else:
                    source_address = arguments[0 if operation == "length" else 1]
                    data, start = region(case, "setup", source_address)
                    source = data[start:]
                    if operation == "length":
                        request = Request(operation, source=source, unaligned=3)
                        destination = None
                    else:
                        data, start = region(case, "setup", arguments[0])
                        request = Request(operation, source=source, destination=data[start:],
                                          capacity=arguments[2], offset=arguments[3], unaligned=5)
                        expected, start = region(case, "expected", arguments[0])
                        destination = expected[start:]
                self.assertEqual(case["expected"]["events"], [])
                self.run_request(request, raw=int(case["expected"]["registers"]["r0"], 0),
                                 destination=destination)
        self.assertEqual(counts, {"lookup": 7, "length": 4, "copy": 9})

    def test_general_lookup_values_padding_duplicates_and_stride(self):
        randomizer = random.Random(0x371C)
        tuples = [(randomizer.randrange(256), randomizer.getrandbits(32), randomizer.getrandbits(32))
                  for _ in range(97)]
        tuples[75] = tuples[12]
        records = bytearray(randomizer.randbytes(36 * len(tuples) + 39))
        for index, keys in enumerate(tuples):
            records[36 * index] = keys[0]
            records[36 * index + 4:36 * index + 8] = keys[1].to_bytes(4, "little")
            records[36 * index + 8:36 * index + 12] = keys[2].to_bytes(4, "little")
        searches = tuples + [(tag + 256, second, third) for tag, second, third in tuples]
        searches += [(tag, second ^ 1, third) for tag, second, third in tuples]
        searches += [(tag, second, third ^ 1) for tag, second, third in tuples]
        for alignment, keys in enumerate(searches):
            with self.subTest(keys=keys):
                expected = tuples.index(keys) if keys in tuples else WORD_MAX
                self.run_request(Request("lookup", records=bytes(records), count=len(tuples),
                                         keys=keys, unaligned=alignment % 8), raw=expected)

    def test_nonpositive_counts_and_unused_views(self):
        for count in (0, -1, -7, -0x7FFFFFFF, -0x80000000):
            for records in (b"", b"\x80" * 73):
                request = Request("lookup", records=records, count=count)
                self.run_request(request, raw=WORD_MAX)
        request = Request("lookup", records=b"", count=-32)
        request.object("records").bytes = ctypes.cast(POINTER_MAX, BytePointer)
        self.run_request(request, raw=WORD_MAX)

    def test_general_lengths_and_copy_capacity_offset_matrix(self):
        randomizer = random.Random(0xC0F1)
        for length in (0, 1, 2, 17, 255, 1024):
            source = bytes(randomizer.randrange(1, 256) for _ in range(length)) + b"\0ignored\0tail"
            self.run_request(Request("length", source=source, unaligned=length % 7), raw=length)
            for capacity in (0, 1, 2, 7, 17, 63):
                for offset in (0, 1, 3, capacity, capacity + 1, WORD_MAX - 1, WORD_MAX):
                    with self.subTest(length=length, capacity=capacity, offset=offset):
                        destination = bytes(range(80))
                        expected = bytearray(destination)
                        if offset < capacity:
                            copied = min(length, capacity - offset - 1)
                            expected[offset:offset + copied] = source[:copied]
                            expected[offset + copied] = 0
                        self.run_request(Request("copy", source=source, destination=destination,
                            capacity=capacity, offset=offset, unaligned=3),
                            raw=(length + offset) & WORD_MAX, destination=bytes(expected))
        self.run_request(Request("copy", destination=b"", capacity=0, offset=WORD_MAX), raw=6)

    def test_missing_and_misaligned_typed_arguments(self):
        for operation in self.functions:
            for index in range(len(Request(operation).arguments)):
                for missing in (True, False):
                    with self.subTest(operation=operation, argument=index, missing=missing):
                        request = Request(operation)
                        pointer = request.arguments[index]
                        request.arguments[index] = (None if missing else ctypes.cast(
                            ctypes.addressof(pointer.contents) + 1, type(pointer)))
                        self.run_request(request, INVALID)

    def test_every_pair_of_objects_and_full_views_is_disjoint(self):
        for operation in self.functions:
            template = Request(operation)
            names = template.names + list(template.views)
            for left, right in itertools.combinations(names, 2):
                with self.subTest(operation=operation, left=left, right=right):
                    request = Request(operation)
                    if right in request.views:
                        descriptor = request.object(request.views[right])
                        descriptor.bytes = ctypes.cast(request.storage[left].address, BytePointer)
                    else:
                        index = request.names.index(left)
                        request.arguments[index] = ctypes.cast(request.storage[right].address,
                                                                type(request.arguments[index]))
                    self.run_request(request, OVERLAP)

    def test_unused_record_tail_and_source_tail_overlap(self):
        for operation in self.functions:
            request = Request(operation, count=-1)
            view_name = "records" if operation == "lookup" else "source"
            storage = request.storage[view_name + "_bytes"]
            descriptor = request.object(view_name)
            descriptor.length = 100
            raw = Word.from_address(storage.address + 96)
            raw.value = SENTINEL
            request.arguments[-1] = ctypes.pointer(raw)
            self.run_request(request, OVERLAP)
        request = Request("copy", capacity=0, offset=WORD_MAX)
        destination = request.storage["destination_bytes"]
        raw = Word.from_address(destination.address + 96)
        request.object("destination").length = 100
        request.arguments[-1] = ctypes.pointer(raw)
        self.run_request(request, OVERLAP)

    def test_invalid_record_extents_and_count_products(self):
        for count, extent in ((1, 35), (4, 143), (WORD_MAX // 36, 36),
                              (WORD_MAX // 36 + 1, 36), (0x7FFFFFFF, 36)):
            request = Request("lookup", count=count)
            request.object("records").length = extent
            self.run_request(request, BOUNDS)
        for count in (0, -1, 1):
            request = Request("lookup", count=count)
            request.object("records").bytes = None
            self.run_request(request, INVALID)
        request = Request("lookup", count=1, records=b"")
        self.run_request(request, BOUNDS)
        if ctypes.sizeof(ctypes.c_size_t) > 4:
            request = Request("lookup", count=0)
            request.object("records").length = WORD_MAX + 1
            self.run_request(request, BOUNDS)

    def test_copy_preflights_full_source_and_capacity_before_writing(self):
        for source in (b"unterminated", b"\x80" * 4096, b""):
            for capacity, offset in ((0, WORD_MAX), (1, 0), (7, 2), (5, 5)):
                request = Request("copy", source=source, capacity=capacity, offset=offset)
                self.run_request(request, INVALID if not source else BOUNDS)
        for offset in (0, 64, WORD_MAX):
            self.run_request(Request("copy", capacity=65, offset=offset), BOUNDS)
        request = Request("copy", destination=b"", capacity=1, offset=WORD_MAX)
        self.run_request(request, BOUNDS)
        request = Request("copy", capacity=0)
        request.object("destination").bytes = None
        self.run_request(request, INVALID)

    def test_source_domain_and_missing_nul(self):
        for operation in ("length", "copy"):
            for source, status in ((b"", INVALID), (b"abc", BOUNDS)):
                self.run_request(Request(operation, source=source), status)
            for extent in (0, 0x80000000, WORD_MAX):
                request = Request(operation)
                request.object("source").length = extent
                if extent > 0x7FFFFFFF:
                    request.object("source").bytes = ctypes.cast(0x10000, BytePointer)
                self.run_request(request, BOUNDS)
            request = Request(operation)
            request.object("source").bytes = None
            self.run_request(request, INVALID)
        if ctypes.sizeof(ctypes.c_size_t) > 4:
            request = Request("copy", capacity=0, offset=WORD_MAX)
            request.object("destination").length = WORD_MAX + 1
            self.run_request(request, BOUNDS)

    def test_address_wrap_for_typed_objects_and_full_views(self):
        for operation in self.functions:
            template = Request(operation)
            for index, pointer in enumerate(template.arguments):
                with self.subTest(operation=operation, argument=index):
                    request = Request(operation)
                    alignment = ctypes.alignment(pointer._type_)
                    request.arguments[index] = ctypes.cast(POINTER_MAX - alignment + 1, type(pointer))
                    self.run_request(request, BOUNDS)
            for name in template.views.values():
                with self.subTest(operation=operation, view=name):
                    request = Request(operation, count=-1, capacity=0, offset=WORD_MAX)
                    request.object(name).bytes = ctypes.cast(POINTER_MAX - 3, BytePointer)
                    request.object(name).length = 8
                    self.run_request(request, BOUNDS)


if __name__ == "__main__":
    unittest.main()
