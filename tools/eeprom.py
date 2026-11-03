#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""List, extract and verify the sections of a BCM2711 SPI EEPROM image.

The image format is described in docs/bcm2711/eeprom.md. Type 0x44
sections need the lz4 package.
"""

import argparse
import hashlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import lz4.frame
except ImportError:
    lz4 = None

MAGIC = 0x55AAF00F
MAGIC_MASK = 0xFFFFF00F
HEADER_SIZE = 8
FOOTER_SIZE = 284
DIGEST_SIZE = 32

BOOTCODE = 0x00
FILE = 0x11
PLAIN = 0x22
LZSS = 0x33
LZ4 = 0x44
PAD = 0xEE

TYPE_NAMES = {
    BOOTCODE: "bootcode",
    FILE: "file",
    PLAIN: "plain",
    LZSS: "lzss",
    LZ4: "lz4",
    PAD: "pad",
}


class FormatError(ValueError):
    """The data does not follow the EEPROM image format."""


@dataclass(frozen=True)
class Section:
    offset: int
    kind: int
    payload: bytes

    @property
    def name(self):
        if self.kind == BOOTCODE:
            return "bootsys"
        if self.kind == FILE:
            return _cstring(self.payload[:12])
        if self.kind in (PLAIN, LZSS, LZ4):
            return _cstring(self.payload[:16])
        return ""

    @property
    def digest(self):
        """SHA-256 of the decompressed data, stored after a compressed body."""
        if self.kind in (LZSS, LZ4):
            return self.payload[-DIGEST_SIZE:]
        return None

    def data(self):
        """Return the contents of the section, decompressed if needed."""
        if self.kind in (FILE, PLAIN):
            return self.payload[16:]
        if self.kind == LZSS:
            return lzss_decompress(self.payload[16:-DIGEST_SIZE])
        if self.kind == LZ4:
            if lz4 is None:
                raise RuntimeError("type 0x44 sections need the lz4 package")
            return lz4.frame.decompress(self.payload[16:-DIGEST_SIZE])
        return self.payload


@dataclass(frozen=True)
class Footer:
    size: int
    key_index: int
    signature: bytes
    hmac: bytes


def _cstring(raw):
    return raw.split(b"\0", 1)[0].decode("ascii", "replace")


def sections(image):
    """Yield the sections of an image in order, up to the end marker."""
    offset = 0
    while offset + HEADER_SIZE <= len(image):
        magic, length = struct.unpack_from(">II", image, offset)
        if magic in (0x00000000, 0xFFFFFFFF):
            return
        if magic & MAGIC_MASK != MAGIC:
            raise FormatError(f"bad magic 0x{magic:08x} at 0x{offset:06x}")
        start = offset + HEADER_SIZE
        if start + length > len(image):
            raise FormatError(f"section at 0x{offset:06x} ends past the image")
        yield Section(offset, (magic >> 4) & 0xFF, image[start:start + length])
        offset = (start + length + 7) & ~7


def parse_footer(code):
    """Split the footer from the end of a bootcode section."""
    if len(code) < FOOTER_SIZE:
        raise FormatError("bootcode is shorter than its footer")
    end = len(code) - FOOTER_SIZE
    size, key_index = struct.unpack_from("<II", code, end)
    return Footer(size, key_index, code[end + 8:end + 264], code[end + 264:])


def lzss_decompress(data):
    """Decompress the body of a type 0x33 section.

    A flag byte describes the next eight items, least significant bit
    first. A clear bit is one literal byte. A set bit is a back-reference
    of two bytes, distance - 1 and length - 1, into a 256-byte window.
    """
    out = bytearray()
    window = bytearray(256)
    pos = 0
    i = 0
    while i < len(data):
        flags = data[i]
        i += 1
        for _ in range(8):
            if i >= len(data):
                break
            if flags & 1:
                if i + 2 > len(data):
                    raise FormatError("truncated back-reference")
                distance = data[i] + 1
                length = data[i + 1] + 1
                i += 2
                for _ in range(length):
                    c = window[(pos - distance) & 0xFF]
                    window[pos] = c
                    pos = (pos + 1) & 0xFF
                    out.append(c)
            else:
                c = data[i]
                i += 1
                window[pos] = c
                pos = (pos + 1) & 0xFF
                out.append(c)
            flags >>= 1
    return bytes(out)


def check(image):
    """Return a list of problems; an empty list means the image is consistent."""
    problems = []
    found = list(sections(image))
    if not found or found[0].kind != BOOTCODE:
        return ["the first section is not bootcode"]
    bootsys = found[0].payload
    footer = parse_footer(bootsys)
    if footer.size != len(bootsys) - FOOTER_SIZE:
        problems.append(f"bootsys: footer size {footer.size}, "
                        f"expected {len(bootsys) - FOOTER_SIZE}")
    for s in found:
        if s.digest is not None and hashlib.sha256(s.data()).digest() != s.digest:
            problems.append(f"{s.name}: SHA-256 mismatch")
    return problems


def _list(image):
    print(f"{'offset':8}  {'type':8}  {'length':>7}  {'size':>7}  name")
    for s in sections(image):
        if s.kind == PAD:
            continue
        kind = TYPE_NAMES.get(s.kind, f"0x{s.kind:02x}")
        size = len(s.data()) if s.kind in TYPE_NAMES else len(s.payload)
        print(f"0x{s.offset:06x}  {kind:8}  {len(s.payload):7}  {size:7}  {s.name}")
    return 0


def _extract(image, directory):
    directory.mkdir(parents=True, exist_ok=True)
    for s in sections(image):
        if s.kind == PAD:
            continue
        name = Path(s.name).name
        if s.kind == BOOTCODE:
            name = "bootsys.bin"
        if name in ("", ".", ".."):
            continue
        (directory / name).write_bytes(s.data())
        print(directory / name)
    return 0


def _verify(image):
    found = list(sections(image))
    bootsys = found[0].payload if found and found[0].kind == BOOTCODE else b""
    if bootsys:
        footer = parse_footer(bootsys)
        print(f"bootsys: {len(bootsys)} bytes, key index {footer.key_index}")
    for s in found:
        if s.digest is None:
            continue
        digest = hashlib.sha256(s.data()).digest()
        status = "ok" if digest == s.digest else "MISMATCH"
        at = bootsys.find(digest)
        where = f"bootsys+0x{at:04x}" if at >= 0 else "not in bootsys"
        print(f"{s.name:16}  sha256 {status:8}  {where}")
    problems = check(image)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("list", "print the section table"),
                       ("extract", "write every section to a directory"),
                       ("verify", "check the footer length and section digests")):
        command = commands.add_parser(name, help=text)
        command.add_argument("image", type=Path)
        if name == "extract":
            command.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        image = args.image.read_bytes()
        if args.command == "list":
            return _list(image)
        if args.command == "extract":
            return _extract(image, args.directory)
        return _verify(image)
    except (OSError, FormatError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
