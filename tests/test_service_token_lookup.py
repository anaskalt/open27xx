# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check fixed service tokens, full scalar state and portable input rejection."""

import ctypes
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Word = ctypes.c_uint32
OK, INVALID, BOUNDS, OVERLAP = 0, -1, -3, -4
WORD_MAX = 0xFFFFFFFF
POINTER_MAX = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
TABLE_BASE = 0xCEC01B60
EXCLUDED = ((0xCEC00D82, 0xCEC00DA0), (TABLE_BASE, 0xCEC01C08))
BOUNDARY_WORDS = (0, 1, 2, 3, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFE, WORD_MAX)


class Registers(ctypes.Structure):
    _fields_ = [("r", Word * 24)] + [(name, Word) for name in
                ("gp", "sp", "lr", "r27", "r28", "r29", "sr")]


class Result(ctypes.Structure):
    _fields_ = [("registers", Registers), ("pc", Word),
                ("instructions", Word), ("table_reads", Word)]


def register_words(registers):
    return {**{f"r{index}": value for index, value in enumerate(registers.r)},
            **{name: getattr(registers, name) for name, _ in Registers._fields_[1:]}}


def set_register(registers, name, value):
    if name.startswith("r") and name[1:].isdigit() and int(name[1:]) < 24:
        registers.r[int(name[1:])] = value
    else:
        setattr(registers, name, value)


class Call:
    def __init__(self, query=0, seed=0, input_offset=64, result_offset=512):
        self.backing = (ctypes.c_uint64 * 128)()
        ctypes.memset(self.backing, 0xA5, ctypes.sizeof(self.backing))
        self.address = ctypes.addressof(self.backing)
        self.input = ctypes.cast(self.address + input_offset, ctypes.POINTER(Registers))
        self.result = ctypes.cast(self.address + result_offset, ctypes.POINTER(Result))
        randomizer = random.Random(seed)
        for name in register_words(self.input.contents):
            set_register(self.input.contents, name, randomizer.getrandbits(32))
        self.input.contents.r[0] = query
        self.input.contents.lr = 0x24040000


class ServiceTokenLookupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Service token tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="service-token-lookup-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "service_token_lookup.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
            "-pedantic", "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/service_token_lookup.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.service_token_lookup
        cls.function.argtypes = [ctypes.POINTER(Registers), ctypes.POINTER(Result)]
        cls.function.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/service-token-lookup.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = json.loads(path.read_text())["cases"]
        document = (ROOT / "docs/bcm2711/service-token-lookup.md").read_text()
        cls.table = [tuple(int(value, 0) for value in match) for match in re.findall(
            r"^\| (\d+) \| (0x[0-9A-F]+) \| (0x[0-9A-F]+) \|$",
            document, re.MULTILINE)]
        cls.indices = {token: index for index, _, token in cls.table}

    def run_call(self, call, status=OK):
        before = bytes(call.backing)
        expected = None
        if status == OK:
            supplied = call.input.contents
            expected = Result()
            expected.registers = Registers.from_buffer_copy(supplied)
            query = supplied.r[0]
            raw = self.indices.get(query, WORD_MAX)
            reads = 42 if raw == WORD_MAX else raw + 1
            expected.registers.r[0] = expected.registers.r[3] = raw
            expected.registers.r[1] = TABLE_BASE + 4 * reads
            expected.registers.r[2] = 42
            expected.registers.r[4] = self.table[-1][2] if raw == WORD_MAX else query
            expected.pc = supplied.lr
            expected.instructions = 132 if raw == WORD_MAX else 7 + 3 * raw
            expected.table_reads = reads
        self.assertEqual(self.function(call.input, call.result), status)
        after = bytes(call.backing)
        if expected is None:
            self.assertEqual(after, before)
        else:
            offset = ctypes.addressof(call.result.contents) - call.address
            self.assertEqual(after, before[:offset] + bytes(expected)
                             + before[offset + ctypes.sizeof(Result):])
            self.assertEqual(bytes(call.result.contents), bytes(expected))

    def test_documented_table_identity(self):
        self.assertEqual(len(self.table), 42)
        self.assertEqual(len(self.indices), 42)
        for expected_index, (index, address, _) in enumerate(self.table):
            self.assertEqual(index, expected_index)
            self.assertEqual(address, TABLE_BASE + index * 4)
        numeric_bytes = b"".join(token.to_bytes(4, "little") for _, _, token in self.table)
        self.assertEqual(hashlib.sha256(numeric_bytes).hexdigest(),
                         "bf1e371e217c0090fe5493b0ba54f9507c59c7fcd80a13bd3537ed619e35512b")

    def test_recorded_scalar_results(self):
        self.assertEqual(self.fixture_hash,
                         "0a50b8cbde34f021743ecd1a7965de3e8be193645be406b9cba0f411bb6d3f41")
        instructions = registers = reads = 0
        for case in self.cases:
            with self.subTest(case=case["id"]):
                call = Call()
                for name, value in case["setup"]["registers"].items():
                    set_register(call.input.contents, name, int(value, 0))
                call.input.contents.lr = int(case["execution"]["return_address"], 0)
                self.run_call(call)
                result = call.result.contents
                observed = {**register_words(result.registers), "pc": result.pc}
                self.assertEqual(observed, {name: int(value, 0) for name, value in
                                           case["expected"]["registers"].items()})
                self.assertEqual(result.instructions, case["steps"])
                self.assertEqual(case["expected"]["events"], [])
                instructions += result.instructions
                registers += len(observed)
                reads += result.table_reads
        self.assertEqual((len(self.cases), registers, instructions, reads), (5, 160, 438, 138))

    def test_all_tokens_and_neighboring_queries(self):
        for index, _, token in self.table:
            for difference in range(-3, 4):
                with self.subTest(index=index, difference=difference):
                    self.run_call(Call((token + difference) & WORD_MAX, seed=index))

    def test_every_query_bit(self):
        for index, _, token in self.table:
            for bit in range(32):
                with self.subTest(index=index, bit=bit):
                    self.run_call(Call(token ^ (1 << bit), seed=bit + index * 32))

    def test_full_width_queries(self):
        randomizer = random.Random(0x0D82)
        queries = list(BOUNDARY_WORDS)
        queries.extend(randomizer.getrandbits(32) for _ in range(2048))
        queries.extend(address for region in EXCLUDED for address in region)
        queries.extend((0x24040000, 0x24010000, 0xE40CB488, 0x7E002010))
        for index, query in enumerate(queries):
            with self.subTest(query=hex(query)):
                self.run_call(Call(query, seed=index))

    def test_arbitrary_incoming_scalar_words(self):
        names = [name for name in register_words(Registers()) if name not in ("r0", "lr")]
        for query in (self.table[0][2], self.table[21][2], self.table[-1][2], 0):
            for name in names:
                for value in BOUNDARY_WORDS:
                    with self.subTest(query=hex(query), name=name, value=hex(value)):
                        call = Call(query)
                        set_register(call.input.contents, name, value)
                        self.run_call(call)

    def test_equal_numeric_words_do_not_alias_host_storage(self):
        for query in (0, 0x24040000, 0xE40CB488, self.table[10][2], WORD_MAX):
            call = Call(query)
            for name in register_words(call.input.contents):
                if name != "lr":
                    set_register(call.input.contents, name, query)
            self.run_call(call)

    def test_completion_address_boundaries(self):
        addresses = [0, 2, WORD_MAX - 1, 0x24040000]
        addresses.extend(address for start, end in EXCLUDED for address in (start - 2, end))
        for address in addresses:
            for query in (self.table[0][2], self.table[-1][2], 0):
                with self.subTest(lr=hex(address), query=hex(query)):
                    call = Call(query)
                    call.input.contents.lr = address
                    self.run_call(call)

    def test_odd_completion_addresses(self):
        for address in (1, 3, 0x24040001, 0xCEC00D81, 0xCEC00DA1,
                        0xCEC01B5F, 0xCEC01C09, WORD_MAX):
            with self.subTest(lr=hex(address)):
                call = Call()
                call.input.contents.lr = address
                self.run_call(call, INVALID)

    def test_complete_source_and_table_exclusions(self):
        for start, end in EXCLUDED:
            for address in range(start, end, 2):
                for query in (self.table[0][2], self.table[-1][2], 0):
                    with self.subTest(lr=hex(address), query=hex(query)):
                        call = Call(query)
                        call.input.contents.lr = address
                        self.run_call(call, OVERLAP)

    def test_null_objects(self):
        for names in (("input",), ("result",), ("input", "result")):
            with self.subTest(names=names):
                call = Call()
                for name in names:
                    setattr(call, name, None)
                self.run_call(call, INVALID)

    def test_typed_misalignment(self):
        for name, kind in (("input", Registers), ("result", Result)):
            for offset in range(1, ctypes.alignment(kind)):
                with self.subTest(name=name, offset=offset):
                    call = Call()
                    address = ctypes.addressof(getattr(call, name).contents) + offset
                    setattr(call, name, ctypes.cast(address, ctypes.POINTER(kind)))
                    self.run_call(call, INVALID)

    def test_wrapping_host_spans(self):
        for name, kind in (("input", Registers), ("result", Result)):
            for distance in range(ctypes.alignment(kind), ctypes.sizeof(kind) + 1,
                                  ctypes.alignment(kind)):
                with self.subTest(name=name, distance=distance):
                    call = Call()
                    address = POINTER_MAX + 1 - distance
                    setattr(call, name, ctypes.cast(address, ctypes.POINTER(kind)))
                    self.run_call(call, BOUNDS)

    def test_all_aligned_host_overlap_offsets(self):
        for offset in range(-ctypes.sizeof(Result) + 4, ctypes.sizeof(Registers), 4):
            with self.subTest(offset=offset):
                call = Call(input_offset=256)
                call.result = ctypes.cast(call.address + 256 + offset, ctypes.POINTER(Result))
                self.run_call(call, OVERLAP)

    def test_adjacent_host_spans(self):
        offsets = ((64, 64 + ctypes.sizeof(Registers)),
                   (64 + ctypes.sizeof(Result), 64))
        for input_offset, result_offset in offsets:
            for query in (self.table[0][2], self.table[-1][2], 0):
                with self.subTest(input_offset=input_offset, query=hex(query)):
                    self.run_call(Call(query, input_offset=input_offset,
                                       result_offset=result_offset))

    def test_repeated_calls_keep_no_query_or_state(self):
        call = Call()
        for index, query in enumerate([item[2] for item in self.table] + [0, WORD_MAX]):
            call.input.contents.r[0] = query
            call.input.contents.sr = WORD_MAX ^ index
            call.input.contents.sp = index
            self.run_call(call)


if __name__ == "__main__":
    unittest.main()
