#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""List, extract, verify and rebuild a BCM2711 SPI EEPROM image.

The image format is described in docs/bcm2711/eeprom.md. Encoding and
decoding type 0x44 sections need the lz4 package.
"""

import argparse
import hashlib
import struct
import sys
from dataclasses import dataclass, replace
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
    padding: bytes = b""

    @classmethod
    def from_data(cls, kind, data, name="", offset=0):
        """Build a section from decoded bytes with canonical name and padding."""
        if not 0 <= kind <= 0xFF:
            raise FormatError("section type is outside the 8-bit range")
        if offset < 0 or offset % 8:
            raise FormatError("section offset must be a nonnegative multiple of 8")
        prefix = b""
        if kind in (FILE, PLAIN, LZSS, LZ4):
            try:
                encoded = name.encode("ascii")
            except UnicodeEncodeError as error:
                raise FormatError("section name must be ASCII") from error
            limit = 12 if kind == FILE else 16
            if not encoded or b"\0" in encoded or len(encoded) > limit:
                raise FormatError(f"section name must contain 1 to {limit} nonzero bytes")
            prefix = encoded.ljust(16, b"\0")
        elif name:
            raise FormatError("this section type has no stored name")
        payload = prefix + _encode_data(kind, data)
        return cls(offset, kind, payload, b"\xff" * (-len(payload) % 8))

    def serialize(self):
        """Return the header, payload and stored alignment bytes."""
        return (struct.pack(">II", MAGIC | self.kind << 4, len(self.payload))
                + self.payload + self.padding)

    def with_data(self, data, kind=None):
        """Encode replacement contents and retain the stored name when possible."""
        kind = self.kind if kind is None else kind
        named = (FILE, PLAIN, LZSS, LZ4)
        if self.kind not in named or kind not in named:
            if kind != self.kind:
                raise FormatError("cannot convert an unnamed section")
            return self.from_data(kind, data, offset=self.offset)
        if (kind == FILE) != (self.kind == FILE):
            return self.from_data(kind, data, self.name, self.offset)
        payload = self.payload[:16] + _encode_data(kind, data)
        return Section(self.offset, kind, payload, b"\xff" * (-len(payload) % 8))

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
            _require_lz4()
            return lz4.frame.decompress(self.payload[16:-DIGEST_SIZE])
        return self.payload


@dataclass(frozen=True)
class Image:
    sections: tuple
    trailer: bytes = b""

    @classmethod
    def parse(cls, image):
        """Parse sections while retaining alignment bytes and the entire trailer."""
        image = bytes(image)
        found = []
        offset = 0
        while offset + HEADER_SIZE <= len(image):
            magic, length = struct.unpack_from(">II", image, offset)
            if magic in (0x00000000, 0xFFFFFFFF):
                break
            if magic & MAGIC_MASK != MAGIC:
                raise FormatError(f"bad magic 0x{magic:08x} at 0x{offset:06x}")
            start = offset + HEADER_SIZE
            end = start + length
            if end > len(image):
                raise FormatError(f"section at 0x{offset:06x} ends past the image")
            kind = (magic >> 4) & 0xFF
            minimum = 48 if kind in (LZSS, LZ4) else 16 if kind in (FILE, PLAIN) else 0
            if length < minimum:
                raise FormatError(f"section at 0x{offset:06x} is shorter than {minimum} bytes")
            aligned = min((end + 7) & ~7, len(image))
            found.append(Section(offset, kind, image[start:end], image[end:aligned]))
            offset = aligned
        return cls(tuple(found), image[offset:])

    def serialize(self):
        """Return the stored bytes without changing padding or the trailer."""
        return b"".join(section.serialize() for section in self.sections) + self.trailer

    def recompress(self, codec="original"):
        """Re-encode compressed CM4 resources within the existing image size.

        Preserve the final 4096 bytes and any non-FF trailer contents at
        their original offsets. Controller resources remain unchanged.
        """
        kinds = {"original": None, "lzss": LZSS, "lz4": LZ4}
        if codec not in kinds:
            raise FormatError(f"unknown compression format: {codec}")
        rebuilt = []
        offset = 0
        for section in self.sections:
            if section.digest is not None and not section.name.startswith("vl805"):
                data = section.data()
                if hashlib.sha256(data).digest() != section.digest:
                    raise FormatError(f"{section.name}: SHA-256 mismatch")
                section = section.with_data(data, kinds[codec])
            section = replace(section, offset=offset)
            rebuilt.append(section)
            offset += len(section.serialize())
        original = self.serialize()
        delta = offset - (len(original) - len(self.trailer))
        if delta > 0:
            erased = len(self.trailer) - len(self.trailer.lstrip(b"\xff"))
            available = min(erased - 8, len(self.trailer) - 4096)
            if delta > available:
                raise FormatError("recompressed sections do not fit before the reserved trailer")
            trailer = self.trailer[delta:]
        else:
            trailer = b"\xff" * -delta + self.trailer
        result = Image(tuple(rebuilt), trailer)
        if result.serialize()[-4096:] != original[-4096:]:
            raise FormatError("recompressed sections overlap the final 4096 bytes")
        return result


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
    yield from Image.parse(image).sections


def _require_lz4():
    if lz4 is None:
        raise RuntimeError("type 0x44 sections need the lz4 package")


def _encode_data(kind, data):
    if kind == LZSS:
        return lzss_compress(data) + hashlib.sha256(data).digest()
    if kind == LZ4:
        _require_lz4()
        frame = lz4.frame.compress(data, compression_level=9,
                                   block_size=lz4.frame.BLOCKSIZE_MAX64KB,
                                   block_linked=True, content_checksum=False,
                                   block_checksum=False, store_size=True)
        return frame + hashlib.sha256(data).digest()
    return bytes(data)


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
    References read a snapshot of initialized history before emitting bytes.
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
                if len(out) < 256 and (distance > len(out) or length > distance):
                    raise FormatError("back-reference reads unwritten history")
                start = (pos - distance) & 0xFF
                reference = (window + window)[start:start + length]
                for c in reference:
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


def lzss_compress(data):
    """Encode LZSS using the longest match, then the smallest distance.

    Matches use 3 to 256 bytes at distances from 1 to 256 bytes. Shorter
    matches cost at least as much as literals. References use only the
    initialized ring snapshot, without bytes emitted by the same reference.
    """
    source = bytes(data)
    out = bytearray()
    pos = 0
    while pos < len(source):
        flag_at = len(out)
        out.append(0)
        for bit in range(8):
            if pos == len(source):
                break
            limit = min(256, len(source) - pos)
            best_length, best_distance = 0, 0
            if limit >= 3:
                key = source[pos:pos + 3]
                history = source[max(0, pos - 256):pos]
                size = len(history)
                end = size
                if size == 256:
                    # Duplicate the ring to include matches across its end.
                    history += history
                    end += 2
                while True:
                    candidate = history.rfind(key, 0, end)
                    if candidate < 0:
                        break
                    length = 3
                    available = min(limit, len(history) - candidate)
                    while (length < available
                           and history[candidate + length] == source[pos + length]):
                        length += 1
                    if length > best_length:
                        best_length, best_distance = length, size - candidate
                    if length == limit:
                        break
                    end = candidate + 2
            if best_length >= 3:
                out[flag_at] |= 1 << bit
                out.extend((best_distance - 1, best_length - 1))
                pos += best_length
            else:
                out.append(source[pos])
                pos += 1
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
    outputs = {}
    for s in sections(image):
        if s.kind == PAD:
            continue
        name = s.name
        if s.kind == BOOTCODE:
            name = "bootsys.bin"
        if name in ("", ".", ".."):
            continue
        if "/" in name or "\\" in name:
            raise FormatError(f"unsafe section filename: {name!r}")
        path = directory / name
        if path in outputs or path.exists() or path.is_symlink():
            raise FormatError(f"output already exists or occurs more than once: {path}")
        outputs[path] = s.data()
    directory.mkdir(parents=True, exist_ok=True)
    for path, data in outputs.items():
        _write_new(path, data)
        print(path)
    return 0


def _write_new(path, data):
    """Exclusive creation also rejects hard links and dangling symlinks."""
    with path.open("xb") as output:
        output.write(data)


def _rebuild(image, output, codec):
    parsed = Image.parse(image)
    if codec is not None:
        parsed = parsed.recompress(codec)
    _write_new(output, parsed.serialize())
    print(output)
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
                       ("verify", "check the footer length and section digests"),
                       ("rebuild", "serialize an image to a new file")):
        command = commands.add_parser(name, help=text)
        command.add_argument("image", type=Path)
        if name == "extract":
            command.add_argument("directory", type=Path)
        if name == "rebuild":
            command.add_argument("output", type=Path)
            command.add_argument("--recompress", choices=("original", "lzss", "lz4"),
                                 help="re-encode compressed CM4 resources using this format")
    args = parser.parse_args(argv)
    try:
        image = args.image.read_bytes()
        if args.command == "list":
            return _list(image)
        if args.command == "extract":
            return _extract(image, args.directory)
        if args.command == "rebuild":
            return _rebuild(image, args.output, args.recompress)
        return _verify(image)
    except (OSError, FormatError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
