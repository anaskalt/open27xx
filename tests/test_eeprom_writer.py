# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic tests for EEPROM serialization and section compression."""

import contextlib
import hashlib
import io
import os
import random
import struct
import tempfile
import unittest
from pathlib import Path

from tests.test_eeprom import bootcode, literals, name16, section
from tools import eeprom

try:
    import lz4.frame
except ImportError:
    lz4 = None


class ImageSerializationTest(unittest.TestCase):
    def test_preserves_sections_gaps_and_trailer(self):
        payloads = [
            (eeprom.BOOTCODE, bootcode(b"code")),
            (eeprom.FILE, name16("settings.txt") + b"setting=1\n"),
            (eeprom.PLAIN, name16("resource") + b"plain data"),
            (eeprom.LZSS, name16("packed") + literals(b"compressed data")
             + hashlib.sha256(b"compressed data").digest()),
            (eeprom.PAD, b"\xff" * 13),
            (0x77, b"opaque payload"),
        ]
        raw = bytearray()
        offsets = []
        for kind, payload in payloads:
            offsets.append(len(raw))
            raw += struct.pack(">II", eeprom.MAGIC | kind << 4, len(payload))
            raw += payload
            raw += bytes(range(-len(raw) % 8))
        trailer = b"\xff" * 4 + b"\x12\x34\x56\x78" + bytes(range(37))
        raw += trailer

        parsed = eeprom.Image.parse(bytes(raw))

        self.assertIsInstance(parsed.sections, tuple)
        self.assertEqual([s.offset for s in parsed.sections], offsets)
        self.assertEqual([(s.kind, s.payload) for s in parsed.sections], payloads)
        self.assertEqual(parsed.trailer, trailer)
        self.assertEqual(parsed.serialize(), bytes(raw))

    def test_zero_marker_preserves_remaining_bytes(self):
        body = section(eeprom.PLAIN, name16("resource") + b"data")
        trailer = bytes(4) + b"arbitrary bytes after the end marker"
        parsed = eeprom.Image.parse(body + trailer)
        self.assertEqual(len(parsed.sections), 1)
        self.assertEqual(parsed.trailer, trailer)
        self.assertEqual(parsed.serialize(), body + trailer)

    def test_no_marker_at_aligned_end(self):
        raw = section(eeprom.PLAIN, name16("resource") + b"12345678")
        parsed = eeprom.Image.parse(raw)
        self.assertEqual(len(parsed.sections), 1)
        self.assertEqual(parsed.trailer, b"")
        self.assertEqual(parsed.serialize(), raw)

    def test_short_trailer_is_preserved(self):
        body = section(eeprom.PLAIN, name16("resource") + b"12345678")
        for trailer in (b"\xff", b"\xff" * 4, b"\x01\x02\x03\x04\x05\x06\x07"):
            with self.subTest(trailer=trailer):
                parsed = eeprom.Image.parse(body + trailer)
                self.assertEqual(parsed.trailer, trailer)
                self.assertEqual(parsed.serialize(), body + trailer)

    def test_empty_image(self):
        parsed = eeprom.Image.parse(b"")
        self.assertEqual(parsed.sections, ())
        self.assertEqual(parsed.trailer, b"")
        self.assertEqual(parsed.serialize(), b"")

    def test_opaque_name_and_reserved_bytes_are_preserved(self):
        prefix = b"n\xffme\0" + bytes(range(11))
        for kind in (eeprom.FILE, eeprom.PLAIN):
            with self.subTest(kind=kind):
                raw = section(kind, prefix + b"data")
                parsed = eeprom.Image.parse(raw)
                self.assertEqual(parsed.sections[0].payload[:16], prefix)
                self.assertEqual(parsed.serialize(), raw)

    def test_rejects_short_named_payloads(self):
        for kind in (eeprom.FILE, eeprom.PLAIN):
            for length in (0, 12, 15):
                with self.subTest(kind=kind, length=length), self.assertRaises(eeprom.FormatError):
                    eeprom.Image.parse(section(kind, bytes(length)))

    def test_rejects_short_compressed_payloads(self):
        for kind in (eeprom.LZSS, eeprom.LZ4):
            for length in (0, 16, 32, 47):
                with self.subTest(kind=kind, length=length), self.assertRaises(eeprom.FormatError):
                    eeprom.Image.parse(section(kind, bytes(length)))


class LzssCompressionTest(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(eeprom.lzss_compress(b""), b"")

    def test_literal_groups(self):
        data = bytes(range(17))
        self.assertEqual(eeprom.lzss_compress(data), literals(data))

    def test_references_require_initialized_source_range(self):
        for value in (b"\0", b"a"):
            with self.subTest(value=value):
                data = value * 9
                packed = eeprom.lzss_compress(data)
                self.assertEqual(packed, bytes([0b11000]) + value * 3 + bytes([2, 2, 2, 2]))
                self.assertEqual(eeprom.lzss_decompress(packed), data)

    def test_snapshot_match_can_be_longer_than_distance(self):
        block = bytes(range(256))
        data = block + block[-1:] + block[:-1]
        packed = eeprom.lzss_compress(data)
        self.assertEqual(packed, literals(block) + bytes([1, 0, 255]))
        self.assertEqual(eeprom.lzss_decompress(packed), data)

    def test_equal_length_matches_choose_smallest_distance(self):
        data = b"abcXabcYabc"
        packed = eeprom.lzss_compress(data)
        self.assertEqual(packed, bytes([0b1010000]) + b"abcX" + bytes([3, 2])
                         + b"Y" + bytes([3, 2]))

    def test_longer_match_takes_precedence_over_nearer_match(self):
        data = b"abcdXabcYabcd"
        packed = eeprom.lzss_compress(data)
        self.assertEqual(packed, bytes([0b10100000]) + b"abcdX" + bytes([4, 2])
                         + b"Y" + bytes([8, 3]))

    def test_two_byte_match_remains_literal(self):
        self.assertEqual(eeprom.lzss_compress(b"abab"), b"\0abab")

    def test_three_byte_match_is_encoded(self):
        packed = eeprom.lzss_compress(b"abcabc")
        self.assertEqual(packed, bytes([0b1000]) + b"abc" + bytes([2, 2]))

    def test_maximum_distance_and_length(self):
        block = bytes(range(256))
        packed = eeprom.lzss_compress(block * 2)
        self.assertEqual(packed, literals(block) + bytes([1, 255, 255]))
        self.assertEqual(eeprom.lzss_decompress(packed), block * 2)

    def test_repetitive_and_incompressible_data(self):
        rng = random.Random(2711)
        random_data = bytes(rng.getrandbits(8) for _ in range(2049))
        inputs = [
            bytes(513),
            b"ab" * 300,
            b"abc" * 300,
            bytes(range(256)) * 4,
            random_data,
            random_data[:251] * 5,
            b"\0" * 270 + random_data + b"\0" * 270,
        ]
        for data in inputs:
            with self.subTest(size=len(data), prefix=data[:8]):
                packed = eeprom.lzss_compress(data)
                self.assertEqual(eeprom.lzss_decompress(packed), data)
                self.assertEqual(eeprom.lzss_compress(data), packed)


class SectionWriterTest(unittest.TestCase):
    def test_named_uncompressed_sections(self):
        for kind, name in ((eeprom.FILE, "settings.txt"),
                           (eeprom.PLAIN, "1234567890abcdef")):
            with self.subTest(kind=kind):
                found = eeprom.Section.from_data(kind, b"payload", name=name, offset=32)
                self.assertEqual(found.offset, 32)
                self.assertEqual(found.kind, kind)
                self.assertEqual(found.name, name)
                self.assertEqual(found.payload[:16], name16(name))
                self.assertEqual(found.data(), b"payload")
                self.assertIsNone(found.digest)

    def test_unknown_section_is_opaque(self):
        found = eeprom.Section.from_data(0x77, b"opaque data")
        self.assertEqual(found.kind, 0x77)
        self.assertEqual(found.name, "")
        self.assertEqual(found.payload, b"opaque data")

    def test_lzss_writer_stores_digest_of_decoded_contents(self):
        data = bytes(range(256)) * 2
        found = eeprom.Section.from_data(eeprom.LZSS, data, name="resource")
        self.assertEqual(found.data(), data)
        self.assertEqual(found.digest, hashlib.sha256(data).digest())
        self.assertEqual(found.payload[16:-32], eeprom.lzss_compress(data))

    def test_replacement_updates_digest_and_preserves_name(self):
        original = eeprom.Section.from_data(eeprom.LZSS, b"old", name="resource")
        replaced = original.with_data(b"replacement" * 31)
        self.assertEqual(replaced.name, original.name)
        self.assertEqual(replaced.kind, original.kind)
        self.assertEqual(replaced.data(), b"replacement" * 31)
        self.assertEqual(replaced.digest, hashlib.sha256(b"replacement" * 31).digest())
        self.assertEqual(original.data(), b"old")

    def test_preserves_raw_name_when_replacing_or_compressing(self):
        prefix = b"n\xffme\0" + bytes(range(11))
        raw = section(eeprom.PLAIN, prefix + b"original")
        original = eeprom.Image.parse(raw).sections[0]
        for kind in (None, eeprom.PLAIN, eeprom.LZSS):
            with self.subTest(kind=kind):
                replaced = original.with_data(b"replacement", kind=kind)
                self.assertEqual(replaced.payload[:16], prefix)
                self.assertEqual(replaced.data(), b"replacement")

    def test_file_replacement_preserves_reserved_bytes(self):
        prefix = b"settings.txt" + b"\x12\x34\x56\x78"
        original = eeprom.Image.parse(section(eeprom.FILE, prefix + b"old")).sections[0]
        replaced = original.with_data(b"replacement")
        self.assertEqual(replaced.payload[:16], prefix)
        self.assertEqual(replaced.data(), b"replacement")

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_conversion_between_compressed_types(self):
        data = bytes(range(256)) * 5 + b"repeated" * 77
        original = eeprom.Section.from_data(eeprom.LZSS, data, name="resource")
        lz4_section = original.with_data(data, kind=eeprom.LZ4)
        lzss_section = lz4_section.with_data(data, kind=eeprom.LZSS)
        for found, kind in ((lz4_section, eeprom.LZ4), (lzss_section, eeprom.LZSS)):
            with self.subTest(kind=kind):
                self.assertEqual(found.kind, kind)
                self.assertEqual(found.payload[:16], original.payload[:16])
                self.assertEqual(found.data(), data)
                self.assertEqual(found.digest, hashlib.sha256(data).digest())

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_lz4_writer_is_deterministic_and_decodes_empty_data(self):
        for data in (b"", b"a" * 1000):
            with self.subTest(size=len(data)):
                first = eeprom.Section.from_data(eeprom.LZ4, data, name="resource")
                second = eeprom.Section.from_data(eeprom.LZ4, data, name="resource")
                self.assertEqual(first.payload, second.payload)
                self.assertEqual(first.data(), data)
                self.assertEqual(first.digest, hashlib.sha256(data).digest())


def sized_image(*resources, size=16384, suffix=bytes(range(256)) * 16):
    body = section(eeprom.BOOTCODE, bootcode(b"code")) + b"".join(resources)
    if len(body) + len(suffix) > size:
        raise ValueError("synthetic sections exceed the image size")
    return body + b"\xff" * (size - len(body) - len(suffix)) + suffix


class ImageRecompressionTest(unittest.TestCase):
    def setUp(self):
        self.data = b"compressed resource" * 40
        payload = name16("resource") + literals(self.data) + hashlib.sha256(self.data).digest()
        self.original = eeprom.Image.parse(sized_image(section(eeprom.LZSS, payload)))

    def test_shrink_preserves_trailer_offsets_and_decoded_data(self):
        rebuilt = self.original.recompress()
        raw = rebuilt.serialize()
        original_raw = self.original.serialize()
        saved = len(rebuilt.trailer) - len(self.original.trailer)
        self.assertGreater(saved, 0)
        self.assertEqual(len(raw), len(original_raw))
        self.assertEqual(rebuilt.trailer, b"\xff" * saved + self.original.trailer)
        self.assertEqual(raw[-4096:], original_raw[-4096:])
        self.assertEqual(rebuilt.sections[1].data(), self.data)
        self.assertEqual(rebuilt.sections[1].digest, hashlib.sha256(self.data).digest())
        self.assertEqual(eeprom.check(raw), [])

    def test_controller_section_bytes_remain_unchanged(self):
        controller_data = bytes(300)
        payload = (name16("vl805hub.bin") + literals(controller_data)
                   + hashlib.sha256(controller_data).digest())
        controller = section(eeprom.LZSS, payload)
        original = eeprom.Image.parse(sized_image(
            self.original.sections[1].serialize(), controller))
        rebuilt = original.recompress("lzss")
        self.assertEqual(rebuilt.sections[2].serialize(), original.sections[2].serialize())
        self.assertEqual(rebuilt.sections[2].kind, eeprom.LZSS)
        self.assertEqual(rebuilt.sections[2].data(), controller_data)

    def test_rejects_unknown_codec(self):
        with self.assertRaises(eeprom.FormatError):
            self.original.recompress("unknown")

    def test_rejects_mismatched_digest(self):
        payload = name16("resource") + literals(self.data) + bytes(32)
        original = eeprom.Image.parse(sized_image(section(eeprom.LZSS, payload)))
        with self.assertRaisesRegex(eeprom.FormatError, "SHA-256 mismatch"):
            original.recompress()

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_codec_selection_preserves_data_and_digests(self):
        for codec, kind in (("original", eeprom.LZSS), ("lzss", eeprom.LZSS),
                            ("lz4", eeprom.LZ4)):
            with self.subTest(codec=codec):
                rebuilt = self.original.recompress(codec)
                self.assertEqual(rebuilt.sections[1].kind, kind)
                self.assertEqual(rebuilt.sections[1].data(), self.data)
                self.assertEqual(rebuilt.sections[1].digest, hashlib.sha256(self.data).digest())
                self.assertEqual(len(rebuilt.serialize()), len(self.original.serialize()))
                self.assertEqual(rebuilt.serialize()[-4096:], self.original.serialize()[-4096:])

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_growth_consumes_only_leading_ff_bytes(self):
        compressed = eeprom.Section.from_data(eeprom.LZSS, bytes(256), name="resource")
        original = eeprom.Image.parse(sized_image(compressed.serialize()))
        delta = len(compressed.with_data(bytes(256), eeprom.LZ4).serialize())
        delta -= len(compressed.serialize())
        self.assertGreater(delta, 0)
        rebuilt = original.recompress("lz4")
        self.assertEqual(rebuilt.trailer, original.trailer[delta:])
        self.assertEqual(len(rebuilt.serialize()), len(original.serialize()))
        self.assertEqual(rebuilt.serialize()[-4096:], original.serialize()[-4096:])
        self.assertEqual(eeprom.check(rebuilt.serialize()), [])

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_growth_cannot_consume_non_ff_trailer_bytes(self):
        compressed = eeprom.Section.from_data(eeprom.LZSS, bytes(256), name="resource")
        original = eeprom.Image.parse(sized_image(compressed.serialize()))
        trailer = b"\xff" * 8 + b"opaque trailer" + original.trailer[22:]
        original = eeprom.Image(original.sections, trailer)
        with self.assertRaises(eeprom.FormatError):
            original.recompress("lz4")

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_growth_keeps_metadata_before_reserved_tail_at_fixed_offsets(self):
        compressed = eeprom.Section.from_data(eeprom.LZSS, bytes(256), name="resource")
        original = eeprom.Image.parse(sized_image(compressed.serialize()))
        delta = len(compressed.with_data(bytes(256), eeprom.LZ4).serialize())
        delta -= len(compressed.serialize())
        trailer = b"\xff" * (delta + 8) + b"metadata" + original.trailer[delta + 16:]
        original = eeprom.Image(original.sections, trailer)
        metadata_offset = len(original.serialize()) - len(trailer) + delta + 8
        rebuilt = original.recompress("lz4")
        self.assertLess(metadata_offset, len(original.serialize()) - 4096)
        self.assertEqual(rebuilt.trailer[:16], b"\xff" * 8 + b"metadata")
        self.assertEqual(rebuilt.serialize()[metadata_offset:],
                         original.serialize()[metadata_offset:])
        self.assertEqual(eeprom.check(rebuilt.serialize()), [])

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_growth_cannot_consume_the_end_marker(self):
        compressed = eeprom.Section.from_data(eeprom.LZSS, bytes(256), name="resource")
        original = eeprom.Image.parse(sized_image(compressed.serialize()))
        delta = len(compressed.with_data(bytes(256), eeprom.LZ4).serialize())
        delta -= len(compressed.serialize())
        trailer = b"\xff" * delta + b"metadata" + original.trailer[delta + 8:]
        original = eeprom.Image(original.sections, trailer)
        with self.assertRaises(eeprom.FormatError):
            original.recompress("lz4")

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_growth_cannot_use_the_final_4096_bytes(self):
        compressed = eeprom.Section.from_data(eeprom.LZSS, bytes(256), name="resource")
        initial = section(eeprom.BOOTCODE, bootcode(b"code")) + compressed.serialize()
        padding = section(eeprom.PAD, b"\xff" * (8192 - 4096 - 8 - len(initial) - 8))
        original = eeprom.Image.parse(initial + padding + b"\xff" * (4096 + 8))
        self.assertEqual(len(original.serialize()), 8192)
        with self.assertRaises(eeprom.FormatError):
            original.recompress("lz4")


class WriterCommandTest(unittest.TestCase):
    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = eeprom.main([str(arg) for arg in args])
        return status, out.getvalue(), err.getvalue()

    def test_rebuild_default_is_byte_identical(self):
        raw = sized_image(section(eeprom.PLAIN, name16("resource") + b"data"))
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.bin", Path(tmp) / "output.bin"
            source.write_bytes(raw)
            status, _, err = self.run_main("rebuild", source, target)
            self.assertEqual((status, err), (0, ""))
            self.assertEqual(target.read_bytes(), raw)
            self.assertEqual(source.read_bytes(), raw)

    def test_rebuild_recompresses_when_requested(self):
        data = b"resource" * 100
        payload = name16("resource") + literals(data) + hashlib.sha256(data).digest()
        raw = sized_image(section(eeprom.LZSS, payload))
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.bin", Path(tmp) / "output.bin"
            source.write_bytes(raw)
            status, _, err = self.run_main("rebuild", source, target, "--recompress", "lzss")
            self.assertEqual((status, err), (0, ""))
            rebuilt = eeprom.Image.parse(target.read_bytes())
            self.assertNotEqual(target.read_bytes(), raw)
            self.assertEqual(len(target.read_bytes()), len(raw))
            self.assertEqual(rebuilt.sections[1].data(), data)
            self.assertEqual(rebuilt.sections[1].digest, hashlib.sha256(data).digest())

    def test_rebuild_refuses_existing_output(self):
        raw = sized_image()
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.bin", Path(tmp) / "output.bin"
            source.write_bytes(raw)
            target.write_bytes(b"keep existing contents")
            status, _, _ = self.run_main("rebuild", source, target)
            self.assertEqual(status, 1)
            self.assertEqual(target.read_bytes(), b"keep existing contents")
            self.assertEqual(source.read_bytes(), raw)

    def test_rebuild_refuses_input_and_link_aliases(self):
        raw = sized_image()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.bin"
            source.write_bytes(raw)
            hardlink, symlink = Path(tmp) / "hard.bin", Path(tmp) / "soft.bin"
            os.link(source, hardlink)
            symlink.symlink_to(source)
            for target in (source, hardlink, symlink):
                with self.subTest(target=target.name):
                    status, _, _ = self.run_main("rebuild", source, target)
                    self.assertEqual(status, 1)
                    self.assertEqual(source.read_bytes(), raw)
                    self.assertEqual(target.read_bytes(), raw)

    def test_rebuild_refuses_dangling_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.bin", Path(tmp) / "output.bin"
            destination = Path(tmp) / "absent.bin"
            source.write_bytes(sized_image())
            target.symlink_to(destination)
            status, _, _ = self.run_main("rebuild", source, target)
            self.assertEqual(status, 1)
            self.assertTrue(target.is_symlink())
            self.assertFalse(destination.exists())

    @unittest.skipIf(lz4 is None, "needs the lz4 package")
    def test_rebuild_overflow_does_not_create_output(self):
        compressed = eeprom.Section.from_data(eeprom.LZSS, bytes(256), name="resource")
        initial = section(eeprom.BOOTCODE, bootcode(b"code")) + compressed.serialize()
        padding = section(eeprom.PAD, b"\xff" * (8192 - 4096 - 8 - len(initial) - 8))
        raw = initial + padding + b"\xff" * (4096 + 8)
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.bin", Path(tmp) / "output.bin"
            source.write_bytes(raw)
            status, _, _ = self.run_main("rebuild", source, target, "--recompress", "lz4")
            self.assertEqual(status, 1)
            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), raw)

    def test_extract_rejects_duplicate_names_before_creating_files(self):
        resource = section(eeprom.PLAIN, name16("resource") + b"data")
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.bin", Path(tmp) / "output"
            source.write_bytes(sized_image(resource, resource))
            status, _, _ = self.run_main("extract", source, target)
            self.assertEqual(status, 1)
            self.assertFalse(target.exists())

    def test_extract_rejects_unsafe_names_before_creating_files(self):
        for name in ("../outside", "nested/file", r"nested\file"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                resource = section(eeprom.PLAIN, name16(name) + b"data")
                source, target = Path(tmp) / "input.bin", Path(tmp) / "output"
                source.write_bytes(sized_image(resource))
                status, _, _ = self.run_main("extract", source, target)
                self.assertEqual(status, 1)
                self.assertEqual(list(Path(tmp).iterdir()), [source])

    def test_extract_preserves_existing_files_without_partial_output(self):
        resource = section(eeprom.PLAIN, name16("resource") + b"data")
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.bin", Path(tmp) / "output"
            source.write_bytes(sized_image(resource))
            target.mkdir()
            existing = target / "resource"
            existing.write_bytes(b"keep existing contents")
            status, _, _ = self.run_main("extract", source, target)
            self.assertEqual(status, 1)
            self.assertEqual(existing.read_bytes(), b"keep existing contents")
            self.assertEqual(list(target.iterdir()), [existing])

    def test_extract_decode_failure_does_not_create_partial_output(self):
        valid = section(eeprom.PLAIN, name16("resource") + b"data")
        truncated = section(eeprom.LZSS, name16("broken") + b"\x01\x00" + bytes(32))
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "input.bin", Path(tmp) / "output"
            source.write_bytes(sized_image(valid, truncated))
            status, _, _ = self.run_main("extract", source, target)
            self.assertEqual(status, 1)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
