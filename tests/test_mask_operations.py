# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check mask membership, full-width shift counts and storage preflight."""

import ctypes
import hashlib
import itertools
import json
import mmap
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


class Pair(ctypes.Structure):
    _fields_ = [("low", Word), ("high", Word)]


class Storage:
    def __init__(self, value, unaligned=0):
        kind = Byte if isinstance(value, bytes) else type(value)
        data = value if isinstance(value, bytes) else bytes(value)
        self.backing = (ctypes.c_uint64 * ((len(data) + 191) // 8))()
        ctypes.memset(self.backing, 0xA5, ctypes.sizeof(self.backing))
        self.address = ctypes.addressof(self.backing) + 64 + unaligned
        ctypes.memmove(self.address, data, len(data))
        self.pointer = ctypes.cast(self.address, ctypes.POINTER(kind))

    def snapshot(self):
        return bytes(self.backing)


class PredicateCall:
    def __init__(self, code=0x5E, mask=0x123456789ABCDEF0, tail=b"unused", unaligned=0):
        self.code = code
        data = mask.to_bytes(8, "little") + tail
        self.storage = {"bytes": Storage(data, unaligned), "raw": Storage(Word(SENTINEL))}
        self.storage["view"] = Storage(View(self.storage["bytes"].pointer, len(data)))
        self.view = self.storage["view"].pointer
        self.raw = self.storage["raw"].pointer

    def snapshot(self):
        return {name: storage.snapshot() for name, storage in self.storage.items()}


def scalar_pair(low, high, count):
    if count == 0:
        return low, high
    distance = count % 32
    moved_low = sum(1 << (bit + distance) for bit in range(32 - distance)
                    if low & (1 << bit))
    if 32 <= count <= 0x8000001F:
        return 0, moved_low
    moved_high = sum(1 << (bit + distance) for bit in range(32 - distance)
                     if high & (1 << bit))
    carry_distance = (-count) % 32
    carry = sum(1 << (bit - carry_distance) for bit in range(carry_distance, 32)
                if low & (1 << bit))
    return moved_low, moved_high | carry


class MaskOperationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Mask operation tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="mask-operations-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        cls.library_path = Path(temporary.name) / "mask_operations.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/mask_operations.c"), "-o", str(cls.library_path)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(cls.library_path))
        cls.predicate = cls.library.mask_predicate
        cls.predicate.argtypes = [Word, ctypes.POINTER(View), ctypes.POINTER(Word)]
        cls.predicate.restype = ctypes.c_int
        cls.shift = cls.library.mask_shift
        cls.shift.argtypes = [Word, Word, Word, ctypes.POINTER(Pair)]
        cls.shift.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/mask-predicate.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = json.loads(path.read_text())["cases"]

    def run_predicate(self, call, status=OK, expected=None):
        before = call.snapshot()
        if expected is None and status == OK:
            expected = 0
            if 0x40 <= call.code < 0x80:
                mask = int.from_bytes(ctypes.string_at(call.view.contents.bytes, 8), "little")
                expected = (mask >> (call.code - 0x40)) & 1
        self.assertEqual(self.predicate(call.code, call.view, call.raw), status)
        after = dict(before)
        if status == OK:
            self.assertEqual(call.raw.contents.value, expected)
            result_address = ctypes.addressof(call.raw.contents)
            for name, storage in call.storage.items():
                offset = result_address - ctypes.addressof(storage.backing)
                if 0 <= offset <= ctypes.sizeof(storage.backing) - 4:
                    data = bytearray(after[name])
                    data[offset:offset + 4] = expected.to_bytes(4, sys.byteorder)
                    after[name] = bytes(data)
        self.assertEqual(call.snapshot(), after)

    def run_shift(self, low, high, count, expected=None):
        storage = Storage(Pair(SENTINEL, SENTINEL ^ WORD_MAX))
        before = bytearray(storage.snapshot())
        self.assertEqual(self.shift(low, high, count, storage.pointer), OK)
        if expected is None:
            expected = scalar_pair(low, high, count)
        actual = storage.pointer.contents
        self.assertEqual((actual.low, actual.high), expected)
        before[64:72] = bytes(Pair(*expected))
        self.assertEqual(storage.snapshot(), bytes(before))

    def test_complete_public_fixture_outputs(self):
        self.assertEqual(self.fixture_hash,
                         "56db3bb0eae86cdfb5ee7eb6cca01969ba43878e6dcc649de2661a0e1450b4c7")
        self.assertEqual(len(self.cases), 28)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                inputs = case["setup"]["registers"]
                outputs = case["expected"]["registers"]
                self.assertEqual(case["expected"]["events"], [])
                if int(case["function"]["entry"], 0) == 0x0EC2FCAA:
                    self.run_shift(*(int(inputs[f"r{index}"], 0) for index in range(3)),
                                   expected=tuple(int(outputs[f"r{index}"], 0)
                                                  for index in range(2)))
                    continue
                call = PredicateCall(int(inputs["r0"], 0))
                if not 0x40 <= call.code < 0x80:
                    call.view = None
                else:
                    address = int(inputs["gp"], 0) + 0xCB498
                    for memory in case["setup"]["memory"]:
                        if "hex" not in memory:
                            continue
                        start = int(memory["address"], 0)
                        data = bytes.fromhex(memory["hex"])
                        if start <= address and address + 8 <= start + len(data):
                            offset = address - start
                            call = PredicateCall(call.code,
                                int.from_bytes(data[offset:offset + 8], "little"),
                                data[offset + 8:])
                            expected_memory = next(item for item in case["expected"]["memory"]
                                                   if item["address"] == memory["address"])
                            self.assertEqual(expected_memory["hex"], memory["hex"])
                            break
                    else:
                        self.fail("Missing mask fixture storage")
                self.run_predicate(call, expected=int(outputs["r0"], 0))

    def test_every_predicate_code_and_mask_bit(self):
        for code, bit, complement in itertools.product(range(0x40, 0x80), range(64), (False, True)):
            with self.subTest(code=code, bit=bit, complement=complement):
                mask = 1 << bit
                if complement:
                    mask ^= (1 << 64) - 1
                self.run_predicate(PredicateCall(code, mask, unaligned=code % 8))

    def test_zero_full_and_random_masks_with_arbitrary_tails(self):
        randomizer = random.Random(0xCB498)
        for code in range(0x40, 0x80):
            for mask in (0, (1 << 64) - 1, randomizer.getrandbits(64)):
                tail = bytes(randomizer.getrandbits(8) for _ in range(257))
                self.run_predicate(PredicateCall(code, mask, tail, unaligned=7))

    def test_outside_codes_and_optional_views(self):
        randomizer = random.Random(0xED00640)
        codes = list(range(0x40)) + [0x80, 0x81, 0x7FFFFFFF, 0x80000000, WORD_MAX]
        codes += [randomizer.randrange(0x80, WORD_MAX + 1) for _ in range(1024)]
        for code in codes:
            call = PredicateCall(code)
            call.view = None
            self.run_predicate(call)
        for code, length in itertools.product((0, 0x3F, 0x80, WORD_MAX), range(14)):
            call = PredicateCall(code)
            call.view.contents.length = length
            self.run_predicate(call)
        for code in (0, 0x80, WORD_MAX):
            call = PredicateCall(code)
            call.view.contents.bytes = None
            call.view.contents.length = 0
            self.run_predicate(call)

    def test_logical_shift_domain_against_whole_integer(self):
        randomizer = random.Random(0x64)
        words = [(0, 0), (WORD_MAX, WORD_MAX), (0x89ABCDEF, 0x76543210)]
        words += [(randomizer.getrandbits(32), randomizer.getrandbits(32)) for _ in range(32)]
        for count, (low, high) in itertools.product(range(64), words):
            with self.subTest(count=count, low=low, high=high):
                value = ((high << 32) | low) << count
                self.run_shift(low, high, count, (value & WORD_MAX, (value >> 32) & WORD_MAX))

    def test_each_input_bit_at_all_subshifts_and_branch_boundaries(self):
        starts = (0, 32, 64, 0x7FFFFFE0, 0x80000000, 0x80000020, 0xFFFFFFE0)
        for start, residual, bit in itertools.product(starts, range(32), range(64)):
            low, high = (1 << bit, 0) if bit < 32 else (0, 1 << (bit - 32))
            self.run_shift(low, high, start + residual)

    def test_general_random_shift_words_and_counts(self):
        randomizer = random.Random(0xEC2FCAA)
        for _ in range(4096):
            self.run_shift(*(randomizer.getrandbits(32) for _ in range(3)))

    def test_missing_and_misaligned_predicate_objects(self):
        for code, name in itertools.product((0, 0x40, 0x7F, WORD_MAX), ("view", "raw")):
            for address in (None, 1):
                call = PredicateCall(code)
                if name == "view" and address is None and not 0x40 <= code < 0x80:
                    continue
                pointer = getattr(call, name)
                address = None if address is None else call.storage[name].address + address
                setattr(call, name, ctypes.cast(address, type(pointer)))
                self.run_predicate(call, INVALID)

    def test_typed_spans_reject_wrap_before_access(self):
        for code, name in itertools.product((0, 0x40, WORD_MAX), ("view", "raw")):
            call = PredicateCall(code)
            kind = View if name == "view" else Word
            address = POINTER_MAX - ctypes.alignment(kind) + 1
            setattr(call, name, ctypes.cast(address, type(getattr(call, name))))
            self.run_predicate(call, BOUNDS)

    def test_shift_invalid_result_preserves_storage(self):
        storage = Storage(Pair(SENTINEL, SENTINEL))
        before = storage.snapshot()
        cases = [(None, INVALID), (storage.address + 1, INVALID),
                 (POINTER_MAX - ctypes.alignment(Pair) + 1, BOUNDS)]
        for address, expected in cases:
            for count in (0, 31, 32, 63, 64, 0x80000020, WORD_MAX):
                pointer = ctypes.cast(address, ctypes.POINTER(Pair))
                self.assertEqual(self.shift(WORD_MAX, WORD_MAX, count, pointer), expected)
                self.assertEqual(storage.snapshot(), before)

    def test_in_range_short_views_and_null_nonempty_views(self):
        for code, length in itertools.product((0x40, 0x5F, 0x60, 0x7F), range(8)):
            call = PredicateCall(code)
            call.view.contents.length = length
            self.run_predicate(call, BOUNDS)
            if length == 0:
                call.view.contents.bytes = None
                self.run_predicate(call, BOUNDS)
        for code, length in itertools.product((0, 0x40, 0x7F, WORD_MAX), (1, 7, 8, WORD_MAX)):
            call = PredicateCall(code)
            call.view.contents.bytes = None
            call.view.contents.length = length
            self.run_predicate(call, INVALID)

    def test_byte_span_wrap_and_excess_extent(self):
        for code, length in itertools.product((0, 0x40, WORD_MAX), (1, 7, 8, 32, WORD_MAX)):
            call = PredicateCall(code)
            call.view.contents.bytes = ctypes.cast(POINTER_MAX - length + 1, BytePointer)
            call.view.contents.length = length
            self.run_predicate(call, BOUNDS)
        if ctypes.sizeof(ctypes.c_size_t) > 4:
            for code in (0, 0x40, WORD_MAX):
                call = PredicateCall(code)
                call.view.contents.length = WORD_MAX + 1
                self.run_predicate(call, BOUNDS)

    def test_descriptor_and_result_full_and_partial_overlap(self):
        for code in (0, 0x40, WORD_MAX):
            for offset in range(-4 + ctypes.alignment(Word), ctypes.sizeof(View),
                                ctypes.alignment(Word)):
                call = PredicateCall(code)
                call.raw = ctypes.cast(call.storage["view"].address + offset, ctypes.POINTER(Word))
                self.run_predicate(call, OVERLAP)
            for offset in range(-ctypes.sizeof(View) + ctypes.alignment(View), 4,
                                ctypes.alignment(View)):
                call = PredicateCall(code)
                call.view = ctypes.cast(call.storage["raw"].address + offset, ctypes.POINTER(View))
                self.run_predicate(call, OVERLAP)

    def test_bytes_overlap_descriptor_or_output_including_unused_tails(self):
        for code, name in itertools.product((0, 0x40, 0x7F, WORD_MAX), ("view", "raw")):
            size = ctypes.sizeof(View if name == "view" else Word)
            for offset in range(-31, size):
                call = PredicateCall(code)
                call.view.contents.bytes = ctypes.cast(call.storage[name].address + offset,
                                                       BytePointer)
                call.view.contents.length = 32
                self.run_predicate(call, OVERLAP)

    def test_adjacent_spans_and_empty_byte_aliases_are_valid(self):
        for code in (0, 0x40, 0x7F, WORD_MAX):
            for name in ("view", "raw"):
                for before in (False, True):
                    call = PredicateCall(code)
                    kind = View if name == "view" else Word
                    address = call.storage[name].address
                    address += -8 if before else ctypes.sizeof(kind)
                    ctypes.memmove(address, bytes.fromhex("0123456789abcdef"), 8)
                    call.view.contents.bytes = ctypes.cast(address, BytePointer)
                    call.view.contents.length = 8
                    self.run_predicate(call)
            call = PredicateCall(code)
            address = call.storage["view"].address + ctypes.sizeof(View)
            call.raw = ctypes.cast(address, ctypes.POINTER(Word))
            self.run_predicate(call)
        for name, address in (("view", None), ("raw", None), (None, POINTER_MAX)):
            call = PredicateCall(0)
            if name is not None:
                address = call.storage[name].address
            call.view.contents.bytes = ctypes.cast(address, BytePointer)
            call.view.contents.length = 0
            self.run_predicate(call)

    @unittest.skipUnless(ctypes.sizeof(ctypes.c_size_t) > 4, "Requires 64-bit address space")
    def test_maximum_declared_extent_is_accepted_without_tail_reads(self):
        with mmap.mmap(-1, WORD_MAX) as allocation:
            byte = Byte.from_buffer(allocation)
            allocation[:8] = b"\xff" * 8
            address = ctypes.addressof(byte)
            for code in (0, 0x40, 0x7F, WORD_MAX):
                call = PredicateCall(code)
                call.view.contents.bytes = ctypes.cast(address, BytePointer)
                call.view.contents.length = WORD_MAX
                self.run_predicate(call, expected=int(0x40 <= code < 0x80))
            self.assertEqual(allocation[:8], b"\xff" * 8)
            del byte


if __name__ == "__main__":
    unittest.main()
