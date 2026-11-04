# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Replay ARM stub metadata fixtures against the firmware C helper."""

import ctypes
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVALID = -1
UNCHANGED = 0
PREPARED = 1
MAGIC = 0x5AFE570B


def guarded_buffer(length=320, offset=16, magic=MAGIC):
    data = bytearray((index * 37 + 19) & 0xFF for index in range(offset + length + 16))
    struct.pack_into("<4I", data, offset + 0xF0, magic, 0x11223344, 0x55667788, 0x99AABBCC)
    return data


class ArmstubMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("ARM stub tests require a host C compiler; set CC to its command")
        temporary = tempfile.TemporaryDirectory(prefix="open27xx-armstub-")
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "armstub.so"
        command = compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-fPIC", "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/armstub.c"), "-o", str(library),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"ARM stub test compilation failed:\n{result.stdout}{result.stderr}")
        cls.library = ctypes.CDLL(str(library))
        cls.prepare = cls.library.armstub_prepare
        cls.prepare.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t] + [ctypes.c_uint32] * 4
        cls.prepare.restype = ctypes.c_int

    def prepare_buffer(self, data, length=320, offset=16,
                       dtb=0x01234567, present=1, kernel=0x89ABCDEF, result=0):
        buffer = (ctypes.c_uint8 * len(data)).from_buffer(data)
        pointer = ctypes.cast(ctypes.byref(buffer, offset), ctypes.POINTER(ctypes.c_uint8))
        return self.prepare(pointer, length, dtb, present, kernel, result)

    def test_recorded_cases(self):
        fixture = json.loads((ROOT / "tests/vectors/start4/armstub-metadata.json").read_text())
        self.assertEqual(len(fixture["cases"]), 5)
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                registers = case["setup"]["registers"]
                memory = {int(region["address"], 0): bytes.fromhex(region["hex"])
                          for region in case["setup"]["memory"]}
                metadata_address = int(registers["r17"], 0) + 0x30
                metadata = memory[metadata_address]
                stack = memory[int(registers["sp"], 0)]
                result, present = struct.unpack_from("<2I", stack, 0x28)
                expected_metadata = next(
                    bytes.fromhex(region["hex"]) for region in case["expected"]["memory"]
                    if int(region["address"], 0) == metadata_address
                )
                self.assertEqual(len(metadata), 16)
                self.assertEqual(len(expected_metadata), 16)
                data = guarded_buffer()
                data[16 + 0xF0:16 + 0x100] = metadata
                expected = data.copy()
                expected[16 + 0xF0:16 + 0x100] = expected_metadata
                status = self.prepare_buffer(data, dtb=int(registers["r6"], 0), present=present,
                                             kernel=int(registers["r7"], 0), result=result)
                self.assertEqual(status, PREPARED if struct.unpack_from("<I", metadata)[0] == MAGIC
                                 else UNCHANGED)
                self.assertEqual(data, expected)

    def test_reject_all_short_lengths_without_mutation(self):
        for length in range(256):
            with self.subTest(length=length):
                data = guarded_buffer()
                expected = data.copy()
                self.assertEqual(self.prepare_buffer(data, length=length), INVALID)
                self.assertEqual(data, expected)

    def test_reject_null_buffer(self):
        for length in (0, 255, 256, 320, ctypes.c_size_t(-1).value):
            with self.subTest(length=length):
                self.assertEqual(self.prepare(None, length, 1, 1, 1, 0), INVALID)

    def test_minimum_length_and_unaligned_buffers(self):
        for offset in range(16, 24):
            for length in (256, 257, 320):
                with self.subTest(offset=offset, length=length):
                    data = guarded_buffer(length=length, offset=offset)
                    expected = data.copy()
                    expected[offset + 0xF0:offset + 0x100] = bytes.fromhex(
                        "000000000000000067452301efcdab89"
                    )
                    self.assertEqual(self.prepare_buffer(data, length=length, offset=offset), PREPARED)
                    self.assertEqual(data, expected)

    def test_nonzero_presence_and_load_result(self):
        for present in (0, 1, 2, 0x80000000, 0xFFFFFFFF):
            for result in (0, 1, 2, 0x80000000, 0xFFFFFFFF):
                with self.subTest(present=present, result=result):
                    data = guarded_buffer()
                    expected = data.copy()
                    struct.pack_into("<4I", expected, 16 + 0xF0, 0, 0,
                                     0x01234567 if present else 0,
                                     0x89ABCDEF if result == 0 else 0)
                    self.assertEqual(self.prepare_buffer(data, present=present, result=result), PREPARED)
                    self.assertEqual(data, expected)

    def test_all_32_bit_values_are_fields(self):
        for dtb in (0, 1, 0x80000000, 0xFFFFFFFF):
            for kernel in (0, 1, 0x80000000, 0xFFFFFFFF):
                with self.subTest(dtb=dtb, kernel=kernel):
                    data = guarded_buffer()
                    expected = data.copy()
                    struct.pack_into("<4I", expected, 16 + 0xF0, 0, 0, dtb, kernel)
                    self.assertEqual(self.prepare_buffer(data, dtb=dtb, kernel=kernel), PREPARED)
                    self.assertEqual(data, expected)

    def test_version_does_not_gate_preparation(self):
        for version in (0, 1, 0x80000000, 0xFFFFFFFF):
            with self.subTest(version=version):
                data = guarded_buffer()
                struct.pack_into("<I", data, 16 + 0xF4, version)
                expected = data.copy()
                struct.pack_into("<4I", expected, 16 + 0xF0, 0, 0, 0x01234567, 0x89ABCDEF)
                self.assertEqual(self.prepare_buffer(data), PREPARED)
                self.assertEqual(data, expected)

    def test_different_magic_leaves_entire_buffer_unchanged(self):
        for magic in (0, 0xFFFFFFFF, 0x0B57FE5A, *(MAGIC ^ (1 << bit) for bit in range(32))):
            with self.subTest(magic=magic):
                data = guarded_buffer(magic=magic)
                expected = data.copy()
                self.assertEqual(self.prepare_buffer(data), UNCHANGED)
                self.assertEqual(data, expected)

    def test_preparation_clears_magic_for_subsequent_calls(self):
        data = guarded_buffer()
        self.assertEqual(self.prepare_buffer(data), PREPARED)
        expected = data.copy()
        self.assertEqual(self.prepare_buffer(data, dtb=0, kernel=0), UNCHANGED)
        self.assertEqual(data, expected)
