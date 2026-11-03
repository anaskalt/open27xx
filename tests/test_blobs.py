# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration tests on the pinned vendor firmware.

Run scripts/fetch-blobs.sh first; the tests skip when the files are absent.
OPEN27XX_BLOBS selects another blobs/ directory.
"""

import hashlib
import os
import unittest
from pathlib import Path

from tools import eeprom

try:
    import lz4.frame
except ImportError:
    lz4 = None

ROOT = Path(__file__).resolve().parents[1]
BLOBS = Path(os.environ.get("OPEN27XX_BLOBS", ROOT / "blobs")) / "bcm2711"
IMAGE = BLOBS / "pieeprom-2026-10-30.bin"
BOOTFILES = BLOBS / "bootfiles" / "2711"
HISTORY = BLOBS / "history"

SECTION_MAP = [
    (0x000000, eeprom.BOOTCODE, "bootsys", 50930),
    (0x00C918, eeprom.LZ4, "bootmain", 211955),
    (0x040518, eeprom.LZ4, "memsys00.bin", 12706),
    (0x0436C8, eeprom.LZ4, "memsys01.bin", 11237),
    (0x0462B8, eeprom.LZ4, "memsys02.bin", 10368),
    (0x048B40, eeprom.LZ4, "memsys03.bin", 9963),
    (0x04B238, eeprom.LZ4, "memsys04.bin", 11885),
    (0x04E0B0, eeprom.LZ4, "memsys05.bin", 11829),
    (0x050EF0, eeprom.LZ4, "memsys06.bin", 11026),
    (0x053A10, eeprom.LZ4, "memsys07.bin", 12103),
    (0x056960, eeprom.LZ4, "memsys08.bin", 10488),
    (0x059260, eeprom.LZ4, "mcb.bin", 1340),
    (0x0597A8, eeprom.LZSS, "vl805hub.bin", 7028),
    (0x05B328, eeprom.LZSS, "vl805mcu.bin", 60451),
    (0x069F58, eeprom.LZ4, "logo.bin", 2256),
    (0x06A830, eeprom.LZ4, "font.bin", 7422),
    (0x06C538, eeprom.FILE, "versioninfo", 70),
    (0x06C588, eeprom.FILE, "updatetime", 24),
    (0x06C600, eeprom.FILE, "pubkey.bin", 528),
    (0x06C900, eeprom.FILE, "cacert.der", 2064),
    (0x06D200, eeprom.FILE, "bootconf.sig", 1040),
    (0x06D700, eeprom.FILE, "bootconf.txt", 95),
]

DIGEST_TABLE = {
    "logo.bin": 0xB8C0,
    "font.bin": 0xB8E0,
    "mcb.bin": 0xB900,
    **{f"memsys{i:02}.bin": 0xB920 + 32 * i for i in range(9)},
    "vl805hub.bin": 0xBA40,
    "vl805mcu.bin": 0xBA60,
    "bootmain": 0xBBA8,
}


@unittest.skipUnless(IMAGE.exists(), "run scripts/fetch-blobs.sh first")
class PinnedImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE.read_bytes()
        cls.sections = [s for s in eeprom.sections(cls.image) if s.kind != eeprom.PAD]
        cls.bootsys = cls.sections[0].payload

    def test_section_map(self):
        found = [(s.offset, s.kind, s.name, len(s.payload)) for s in self.sections]
        self.assertEqual(found, SECTION_MAP)

    def test_end_marker(self):
        self.assertEqual(self.image[0x06D768:0x06D76C], b"\xff" * 4)
        self.assertEqual(set(self.image[0x06D768:]), {0xFF})

    def test_footer(self):
        footer = eeprom.parse_footer(self.bootsys)
        self.assertEqual((footer.size, footer.key_index), (50646, 1))

    def test_versioninfo(self):
        versioninfo = next(s for s in self.sections if s.name == "versioninfo")
        self.assertEqual(versioninfo.data(),
                         b"VERSIONINFO 2026/10/30 23:20:35 13c4219f R 2711 MFG02\0")

    def test_bootcode_matches_bootfiles(self):
        self.assertEqual((BOOTFILES / "bootcode4.bin").read_bytes(), self.bootsys)

    def test_recovery_footer(self):
        recovery = (BLOBS / "recovery.bin").read_bytes()
        footer = eeprom.parse_footer(recovery)
        self.assertEqual((len(recovery), footer.size, footer.key_index), (83842, 83558, 1))

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_digests(self):
        self.assertEqual(eeprom.check(self.image), [])
        for s in self.sections:
            if s.digest is not None:
                at = DIGEST_TABLE[s.name]
                self.assertEqual(self.bootsys[at:at + 32], s.digest, s.name)

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_resources_match_bootfiles(self):
        for s in self.sections:
            if s.digest is not None and not s.name.startswith("vl805"):
                self.assertEqual((BOOTFILES / s.name).read_bytes(), s.data(), s.name)


@unittest.skipUnless(HISTORY.is_dir(), "run scripts/fetch-blobs.sh --all first")
@unittest.skipIf(lz4 is None, "needs the lz4 package")
class HistoryTest(unittest.TestCase):
    def test_every_published_image_verifies(self):
        images = sorted(HISTORY.glob("pieeprom-*.bin"))
        digests = set()
        for path in images:
            data = path.read_bytes()
            digests.add(hashlib.sha256(data).digest())
            self.assertEqual(len(data), 512 * 1024, path.name)
            self.assertEqual(eeprom.check(data), [], path.name)
        self.assertEqual((len(images), len(digests)), (120, 119))


if __name__ == "__main__":
    unittest.main()
