# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Host bounds checks for the open start4 build output."""

import struct
import unittest

from tools import start4


def executable():
    data = bytearray(512)
    data[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHIIIIIHHHHHH", data, 16,
                     2, 137, 1, start4.RAM_START + 32, 52, 352, 0, 52, 32, 1, 40, 4, 3)
    struct.pack_into("<8I", data, 52, 1, 128, start4.RAM_START, start4.RAM_START, 64, 128, 7, 4)
    struct.pack_into("<4I", data, 128, 0x41545342, 0, 0, 0)
    struct.pack_into("<4I", data, 144, 3, 0, 0, 0)
    names = b"\0.text.bootloader_state\0.text.firmware_rev\0.shstrtab\0"
    data[256:256 + len(names)] = names
    struct.pack_into("<10I", data, 392, 1, 1, 3, start4.RAM_START, 128, 16, 0, 0, 4, 0)
    struct.pack_into("<10I", data, 432, 24, 1, 3, start4.RAM_START + 16, 144, 16, 0, 0, 4, 0)
    struct.pack_into("<10I", data, 472, 43, 3, 0, 0, 256, len(names), 0, 0, 1, 0)
    return data


class Start4ImageTest(unittest.TestCase):
    def test_open_executable(self):
        result = start4.check_elf(executable())
        self.assertEqual(result["entry"], "0xC4000020")
        self.assertEqual(result["size"], 512)

    def test_truncated_images(self):
        data = executable()
        for length in (0, 16, 51, 84, 511):
            with self.subTest(length=length), self.assertRaises(ValueError):
                start4.check_elf(data[:length])

    def test_reject_header_mismatches(self):
        for offset, fmt, value in ((0, "I", 0), (18, "H", 40), (42, "H", 0), (44, "H", 0)):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                data = executable()
                struct.pack_into("<" + fmt, data, offset, value)
                start4.check_elf(data)

    def test_reject_nonload_program_header(self):
        data = executable()
        struct.pack_into("<I", data, 52, 4)
        with self.assertRaisesRegex(ValueError, "non-load"):
            start4.check_elf(data)

    def test_reject_segment_bounds(self):
        for offset, value in ((56, 500), (60, 0xC6000000), (60, 0xC5FF0000), (68, 129)):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                data = executable()
                struct.pack_into("<I", data, offset, value)
                start4.check_elf(data)

    def test_reject_entry_in_zero_fill(self):
        data = executable()
        struct.pack_into("<I", data, 24, start4.RAM_START + 64)
        with self.assertRaisesRegex(ValueError, "entry point"):
            start4.check_elf(data)

    def test_allocator_and_stack_boundary(self):
        data = executable()
        available = start4.RAM_END - start4.STACK_SIZE - start4.RAM_START
        struct.pack_into("<I", data, 72, available)
        start4.check_elf(data)
        struct.pack_into("<I", data, 72, available + 1)
        with self.assertRaisesRegex(ValueError, "memory region"):
            start4.check_elf(data)

    def test_reject_missing_loader_metadata(self):
        data = executable()
        struct.pack_into("<I", data, 432, 43)
        with self.assertRaises(ValueError):
            start4.check_elf(data)

    def test_reject_unloaded_loader_metadata(self):
        data = executable()
        struct.pack_into("<I", data, 404, start4.RAM_END)
        with self.assertRaisesRegex(ValueError, "unloaded"):
            start4.check_elf(data)

    def test_reject_zero_fill_metadata(self):
        data = executable()
        struct.pack_into("<I", data, 396, 8)
        with self.assertRaisesRegex(ValueError, "invalid loader"):
            start4.check_elf(data)

    def test_reject_overlapping_segments(self):
        data = executable()
        struct.pack_into("<H", data, 44, 2)
        data[84:116] = data[52:84]
        with self.assertRaisesRegex(ValueError, "overlapping"):
            start4.check_elf(data)
