# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Unit tests for tools/eeprom.py on synthetic images."""

import contextlib
import hashlib
import io
import struct
import tempfile
import unittest
from pathlib import Path

from tools import eeprom

try:
    import lz4.frame
except ImportError:
    lz4 = None


def section(kind, payload):
    raw = struct.pack(">II", eeprom.MAGIC | kind << 4, len(payload)) + payload
    return raw + b"\xff" * (-len(raw) % 8)


def name16(name):
    return name.encode().ljust(16, b"\0")


def bootcode(code, key_index=1):
    footer = struct.pack("<II", len(code), key_index)
    return code + footer + bytes(range(256)) + b"\x5a" * 20


def literals(data):
    """Encode data as LZSS literals only."""
    out = bytearray()
    for i in range(0, len(data), 8):
        out.append(0)
        out += data[i:i + 8]
    return bytes(out)


class SectionTest(unittest.TestCase):
    def test_chain_is_aligned_and_ends_at_marker(self):
        image = (section(eeprom.BOOTCODE, bootcode(b"\0" * 3))
                 + section(eeprom.FILE, b"bootconf.txt" + bytes(4) + b"[all]\n")
                 + b"\xff" * 64)
        found = list(eeprom.sections(image))
        self.assertEqual([s.kind for s in found], [eeprom.BOOTCODE, eeprom.FILE])
        self.assertEqual(found[1].offset, 0x128)
        self.assertEqual(found[1].name, "bootconf.txt")
        self.assertEqual(found[1].data(), b"[all]\n")

    def test_zero_magic_ends_chain(self):
        image = section(eeprom.PAD, b"\xff" * 8) + bytes(16)
        self.assertEqual(len(list(eeprom.sections(image))), 1)

    def test_bad_magic(self):
        with self.assertRaises(eeprom.FormatError):
            list(eeprom.sections(b"\x12\x34\x56\x78" + bytes(4)))

    def test_section_past_end(self):
        image = struct.pack(">II", eeprom.MAGIC, 64) + bytes(8)
        with self.assertRaises(eeprom.FormatError):
            list(eeprom.sections(image))

    def test_plain_section(self):
        s = next(eeprom.sections(section(eeprom.PLAIN, name16("memsys00.bin") + b"abc")))
        self.assertEqual((s.name, s.data(), s.digest), ("memsys00.bin", b"abc", None))


class FooterTest(unittest.TestCase):
    def test_fields(self):
        footer = eeprom.parse_footer(bootcode(b"\x01" * 100, key_index=1))
        self.assertEqual(footer.size, 100)
        self.assertEqual(footer.key_index, 1)
        self.assertEqual(footer.signature, bytes(range(256)))
        self.assertEqual(footer.hmac, b"\x5a" * 20)

    def test_too_short(self):
        with self.assertRaises(eeprom.FormatError):
            eeprom.parse_footer(bytes(100))


class LzssTest(unittest.TestCase):
    def test_literals(self):
        data = bytes(range(20))
        self.assertEqual(eeprom.lzss_decompress(literals(data)), data)

    def test_back_reference_overlaps_output(self):
        # literals "ab", then distance 2, length 6
        packed = bytes([0b100, ord("a"), ord("b"), 1, 5])
        self.assertEqual(eeprom.lzss_decompress(packed), b"abababab")

    def test_flags_are_lsb_first(self):
        # literal "x", back-reference distance 1 length 3, literal "y"
        packed = bytes([0b010, ord("x"), 0, 2, ord("y")])
        self.assertEqual(eeprom.lzss_decompress(packed), b"xxxxy")

    def test_window_wraps(self):
        # 264 literals, then distance 256 length 4: the output from index 8
        data = bytes(range(256)) + b"tail_end"
        packed = literals(data) + bytes([1, 255, 3])
        self.assertEqual(eeprom.lzss_decompress(packed), data + data[8:12])

    def test_truncated_back_reference(self):
        with self.assertRaises(eeprom.FormatError):
            eeprom.lzss_decompress(bytes([1, 0]))

    def test_lzss_section_digest(self):
        data = b"vl805 firmware" * 3
        payload = name16("vl805hub.bin") + literals(data) + hashlib.sha256(data).digest()
        s = next(eeprom.sections(section(eeprom.LZSS, payload)))
        self.assertEqual(s.data(), data)
        self.assertEqual(s.digest, hashlib.sha256(data).digest())


def image_with_lz4(data, digest=None):
    digest = hashlib.sha256(data).digest() if digest is None else digest
    payload = name16("bootmain") + lz4.frame.compress(data) + digest
    return section(eeprom.BOOTCODE, bootcode(b"\0" * 64)) + section(eeprom.LZ4, payload)


@unittest.skipIf(lz4 is None, "needs the lz4 package")
class Lz4Test(unittest.TestCase):
    def test_section(self):
        data = bytes(range(256)) * 4
        s = list(eeprom.sections(image_with_lz4(data)))[1]
        self.assertEqual(s.data(), data)
        self.assertEqual(eeprom.check(image_with_lz4(data)), [])

    def test_digest_mismatch(self):
        image = image_with_lz4(b"data", digest=bytes(32))
        self.assertEqual(eeprom.check(image), ["bootmain: SHA-256 mismatch"])


@unittest.skipIf(lz4 is None, "needs the lz4 package")
class CommandTest(unittest.TestCase):
    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = eeprom.main([str(a) for a in args])
        return status, out.getvalue(), err.getvalue()

    def test_verify_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.bin"
            path.write_bytes(image_with_lz4(b"payload" * 10))
            status, out, _ = self.run_main("verify", path)
            self.assertEqual(status, 0)
            self.assertIn("sha256 ok", out)
            status, _, _ = self.run_main("extract", path, Path(tmp) / "out")
            self.assertEqual(status, 0)
            self.assertEqual((Path(tmp) / "out" / "bootmain").read_bytes(), b"payload" * 10)

    def test_missing_file(self):
        status, _, err = self.run_main("list", Path(tempfile.gettempdir()) / "missing.bin")
        self.assertEqual(status, 1)
        self.assertIn("error:", err)

    def test_verify_fails_on_bad_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.bin"
            path.write_bytes(image_with_lz4(b"data", digest=bytes(32)))
            status, _, err = self.run_main("verify", path)
            self.assertEqual(status, 1)
            self.assertIn("SHA-256 mismatch", err)


if __name__ == "__main__":
    unittest.main()
