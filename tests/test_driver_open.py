# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check optional mask copies, complete registration and whole-call preflight."""

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

from tests.test_suspend_helpers import (
    BOUNDS,
    INVALID,
    OK,
    OVERLAP,
    POINTER_MAX,
    WORD_MAX,
    Buffer,
    Byte,
    BytePointer,
    Storage,
    View,
    Word,
    region,
)
from tests.test_suspend_registrar import (
    DI,
    OBJECT_BYTES,
    P16,
    Observers,
    ReadPlan,
    object_bytes,
    registration_result,
)
from tests.test_suspend_registrar import Request as RegistrationRequest

ROOT = Path(__file__).resolve().parents[1]
KEYS = (1, 0x0ED004C6, 0)


class Inputs(ctypes.Structure):
    _fields_ = [("sr", Word)]


class Request(RegistrationRequest):
    def __init__(self, masks=b"\xD9\x23\xA4\x71\x06\xFF\x80\x39mask tail",
                 source=b"\x18\xBC\x35\xFE\x61\x02\x99\xA7source tail", **kwargs):
        super().__init__(keys=KEYS, **kwargs)
        self.mask_bytes = masks
        self.source_bytes = source

        def add(label, value, offset=0):
            self.storage[label] = Storage(value, offset)
            return self.storage[label].pointer

        inputs = add("inputs", Inputs(self.sr))
        masks_pointer = add("masks_bytes", masks, kwargs.get("unaligned", 0))
        masks_view = add("masks", Buffer(masks_pointer if masks else None, len(masks)))
        source_view = None
        if source is not None:
            source_pointer = add("source_bytes", source, kwargs.get("unaligned", 0))
            source_view = add("source", View(source_pointer if source else None, len(source)))
        self.names = ["inputs", "masks", "source", "object", "name", "logging",
                      "reads", "observers", "raw"]
        self.arguments = [inputs, masks_view, source_view, *self.arguments[1:]]

    def redirect(self, name, address):
        if name in ("masks_bytes", "source_bytes"):
            self.object(name.removesuffix("_bytes")).bytes = ctypes.cast(address, BytePointer)
        else:
            super().redirect(name, address)


class DriverOpenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Driver-open tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="driver-open-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "driver_open.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/driver_open.c"),
            str(ROOT / "src/start4/suspend_registrar.c"),
            str(ROOT / "src/start4/suspend_helpers.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.driver_open_register
        cls.function.argtypes = [ctypes.POINTER(kind) for kind in
                                 (Inputs, Buffer, View, Buffer, View, Byte,
                                  ReadPlan, Observers, Word)]
        cls.function.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/driver-open-masks.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = json.loads(path.read_text())["cases"]

    def run_request(self, request, status=OK, expected=None, masks=None):
        before = request.snapshot()
        self.assertEqual(self.function(*request.arguments), status)
        if status != OK:
            self.assertEqual(request.events, [])
            self.assertEqual(request.snapshot(), before)
            return
        if expected is None:
            expected, _ = registration_result(request.data, KEYS, request.sr, request.name_bytes)
        if masks is None:
            masks = request.mask_bytes
            if request.source_bytes:
                masks = request.source_bytes[:8] + masks[8:]

        def replace(snapshot, label, value):
            result = dict(snapshot)
            storage = request.storage[label]
            changed = bytearray(result[label])
            changed[storage.offset:storage.offset + len(value)] = value
            result[label] = bytes(changed)
            return result

        copied = replace(before, "masks_bytes", masks)
        completed = replace(copied, "object_bytes", expected)
        events = [("di", (request.sr, request.sr & ~0x40000000), copied)]
        events.extend(("read", (value,), copied) for value in request.read_values)
        events.append(("write", (request.sr,), completed))
        self.assertEqual(request.events, events)
        self.assertEqual(request.snapshot(), replace(completed, "raw", b"\0" * 4))

    def test_six_complete_public_calls(self):
        self.assertEqual(self.fixture_hash,
                         "39f2b2f6f46096c5a783fd451e8d687371b4c91696ea0ad246013854c79b647c")
        self.assertEqual(len(self.cases), 6)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                registers = case["setup"]["registers"]
                gp = int(registers["gp"], 0)
                pointer, offset = region(case, "setup", gp + 0x14E4)
                base = int.from_bytes(pointer[offset:offset + 4], "little")
                data, offset = region(case, "setup", base)
                data = data[offset:offset + OBJECT_BYTES]
                expected, offset = region(case, "expected", base)
                expected = expected[offset:offset + OBJECT_BYTES]
                masks, offset = region(case, "setup", gp + 0xCB498)
                masks = masks[offset:offset + 8]
                expected_masks, offset = region(case, "expected", gp + 0xCB498)
                expected_masks = expected_masks[offset:offset + 8]
                source = None
                if int(registers["r0"], 0):
                    source, offset = region(case, "setup", int(registers["r0"], 0))
                    source = source[offset:offset + 8]
                name = None
                try:
                    name, offset = region(case, "setup", gp + 0x9FE0)
                    name = name[offset:-3]
                except AssertionError:
                    pass
                logging = None
                if int.from_bytes(data[0xB5C:0xB60], "little") < 40:
                    value, offset = region(case, "setup", 0xE4105970)
                    logging = value[offset]
                reads = tuple(int(event["value"], 0) for event in case["expected"]["events"]
                              if event["kind"] == "p16_read")
                request = Request(data=data, masks=masks, source=source, name=name,
                                  sr=int(registers["sr"], 0), logging=logging,
                                  reads=reads, unaligned=3)
                self.run_request(request, expected=expected, masks=expected_masks)
                self.assertEqual(int(case["expected"]["registers"]["r0"], 0), 0)
                expected_events = []
                for event in case["expected"]["events"]:
                    if event["kind"] == "irq_disable":
                        expected_events.append(("di", (int(event["sr_before"], 0),
                                                       int(event["sr_after"], 0))))
                    else:
                        expected_events.append((event["kind"].removeprefix("p16_"),
                                                (int(event["value"], 0),)))
                self.assertEqual([(kind, values) for kind, values, _ in request.events],
                                 expected_events)

    def test_all_counts_arbitrary_records_and_mask_words(self):
        generator = random.Random(0xD027C4)
        for count in range(40):
            records = [(generator.randrange(256), generator.getrandbits(32),
                        generator.getrandbits(32)) for _ in range(count)]
            if records:
                records[0] = (1, 0, 0)
            for matching in (False, True) if count else (False,):
                if matching:
                    records[-1] = KEYS
                for source in (None, b"", generator.randbytes(8 + count)):
                    with self.subTest(count=count, matching=matching, source=source):
                        self.run_request(Request(data=object_bytes(count, records,
                            tail=generator.randbytes(17 + count), fill=(count * 19) & 255),
                            masks=generator.randbytes(8 + count), source=source,
                            sr=generator.getrandbits(32), logging=count % 4,
                            name=b"prefix/\xFFname\0ignored", reads=(1,) * (count % 9) + (0,),
                            unaligned=count % 8))

    def test_capacity_retains_copies_without_name_or_logging_contents(self):
        for count in (40, 41, 127, 65536, 0x7FFFFFFF):
            for source in (None, b"", bytes(range(8)) + b"source tail"):
                for name in (None, b"", b"nonterminated"):
                    for logging in (None, 3, 4, 255):
                        with self.subTest(count=count, source=source, name=name, logging=logging):
                            self.run_request(Request(data=object_bytes(count, [KEYS]),
                                source=source, name=name, logging=logging))

    def test_match_gates_duplicates_and_unused_names(self):
        records = [(0, KEYS[1], 0), (1, 0, 0), (1, KEYS[1], 1), KEYS, KEYS]
        for source in (None, bytes(range(8))):
            for name in (None, b"", b"\xFFunterminated"):
                self.run_request(Request(data=object_bytes(len(records), records),
                                         source=source, name=name))

    def test_general_names_and_truncation(self):
        generator = random.Random(0xBA5E27)
        names = [b"", b"/", b"\\", b"//\\", b"../..", b"a/b\\c/d", b"a\\b/c\\d",
                 b"a/b/", b"a\\b\\", bytes(range(1, 256))]
        names += [b"prefix/" + bytes(generator.randrange(1, 256) for _ in range(length))
                  for length in (1, 20, 21, 22, 255, 4096, 8192)]
        for name in names:
            for source in (None, b"\xFF" * 8):
                with self.subTest(name=name[:32], length=len(name), source=source):
                    self.run_request(Request(name=name + b"\0/ignored\\tail", source=source,
                                             unaligned=5))

    def test_all_status_and_mask_bits_and_finite_busy_plans(self):
        for bit in range(32):
            for word in (1 << bit, WORD_MAX ^ (1 << bit)):
                source = word.to_bytes(4, "little") + (word ^ WORD_MAX).to_bytes(4, "little")
                self.run_request(Request(sr=word, masks=source[::-1], source=source,
                                         reads=(1,) * (bit % 11) + (0,)))
        self.run_request(Request(sr=0, source=b"\0" * 8, reads=(1,) * 257 + (0,)))
        self.run_request(Request(sr=WORD_MAX, source=b"\xFF" * 8, reads=(0,)))

    def test_final_slot_insertion_then_capacity_and_repeated_match(self):
        for initial in (0, 39):
            request = Request(data=object_bytes(initial))
            self.run_request(request)
            data = request.storage["object_bytes"].payload()
            self.assertEqual(int.from_bytes(data[0xB5C:0xB60], "little"), initial + 1)
            self.run_request(Request(data=data, masks=request.storage["masks_bytes"].payload(),
                source=b"\xC9" * 8, name=None, logging=None if initial == 39 else 0))

    def test_required_arguments_alignment_and_observers(self):
        for index in (0, 1, 3, 6, 7, 8):
            request = Request()
            request.arguments[index] = None
            self.run_request(request, INVALID)
        for index in (0, 1, 2, 3, 4, 6, 7, 8):
            request = Request()
            pointer = request.arguments[index]
            request.arguments[index] = ctypes.cast(ctypes.addressof(pointer.contents) + 1,
                                                   type(pointer))
            self.run_request(request, INVALID)
        request = Request()
        request.object("reads").words = ctypes.cast(request.storage["read_words"].address + 1,
                                                    ctypes.POINTER(Word))
        self.run_request(request, INVALID)
        for kind, callback_type in (("di", DI), ("read", P16), ("write", P16)):
            for count in (0, 40):
                request = Request(data=object_bytes(count))
                setattr(request.object("observers"), kind, callback_type())
                self.run_request(request, INVALID)

    def test_every_pair_of_objects_and_full_spans_is_disjoint(self):
        names = Request().names + ["masks_bytes", "source_bytes", "object_bytes",
                                   "name_bytes", "read_words"]
        for left, right in itertools.combinations(names, 2):
            with self.subTest(left=left, right=right):
                request = Request()
                request.redirect(right, request.storage[left].address)
                self.run_request(request, OVERLAP)

    def test_unused_tails_and_source_suffixes_participate_in_storage_checks(self):
        for count in (0, 40):
            for label in ("masks_bytes", "source_bytes", "object_bytes", "name_bytes", "read_words"):
                request = Request(data=object_bytes(count, tail=b"T" * 128),
                    masks=b"M" * 128, source=b"S" * 128, name=b"\0" + b"N" * 127,
                    reads=(1,) * 31 + (0,))
                storage = request.storage[label]
                address = (storage.address + storage.length - 4) & ~3
                request.arguments[-1] = ctypes.cast(address, ctypes.POINTER(Word))
                self.run_request(request, OVERLAP)

    def test_mask_source_presence_and_extent_bounds(self):
        for source in (None, b"", bytes(range(8))):
            self.run_request(Request(source=source))
        for label in ("masks", "source"):
            request = Request()
            request.object(label).bytes = None
            self.run_request(request, INVALID)
            for length in (0, 1, 4, 7, WORD_MAX + 1):
                if length > POINTER_MAX:
                    continue
                request = Request()
                request.object(label).length = length
                self.run_request(request, BOUNDS)
        request = Request(source=None)
        request.object("masks").bytes = None
        request.object("masks").length = 0
        self.run_request(request, INVALID)
        request = Request(source=b"")
        request.object("source").length = 1
        self.run_request(request, INVALID)

    def test_all_registrar_invalidity_precedes_mask_stores(self):
        for source in (None, bytes(range(8))):
            for count in (-1, -19, -0x80000000):
                self.run_request(Request(source=source, data=object_bytes(count)), BOUNDS)
            for count in (0, 1, 39):
                for logging in (None, 4, 255):
                    self.run_request(Request(source=source, data=object_bytes(count),
                                             logging=logging), INVALID)
            for name, status in ((None, INVALID), (b"", INVALID), (b"no-nul", BOUNDS),
                                 (b"a" * 4096, BOUNDS)):
                self.run_request(Request(source=source, name=name), status)
            self.run_request(Request(source=source, reads=()), BOUNDS)
            for reads in ((1,), (1, 1), (2, 0), (WORD_MAX, 0), (0, 0), (0, 1), (1, 0, 1)):
                self.run_request(Request(source=source, reads=reads), INVALID)
        request = Request()
        request.object("reads").words = None
        self.run_request(request, INVALID)
        for count in (WORD_MAX // 4 + 1, POINTER_MAX // 4 + 1):
            request = Request()
            request.object("reads").count = count
            self.run_request(request, BOUNDS)
        for length in (0, OBJECT_BYTES - 1, WORD_MAX + 1):
            if length > POINTER_MAX:
                continue
            request = Request()
            request.object("object").length = length
            self.run_request(request, BOUNDS)
        for label in ("object", "name"):
            request = Request()
            request.object(label).bytes = None
            self.run_request(request, INVALID)
        for length in (0, 0x80000000, WORD_MAX):
            request = Request()
            request.object("name").length = length
            if length > 0x7FFFFFFF:
                request.object("name").bytes = ctypes.cast(0x10000, BytePointer)
            self.run_request(request, BOUNDS)
        if POINTER_MAX > WORD_MAX:
            request = Request(data=object_bytes(40))
            request.object("name").length = WORD_MAX + 1
            self.run_request(request, BOUNDS)

    def test_wrapping_descriptors_and_full_spans_precede_content_access(self):
        for index in (0, 1, 2, 3, 4, 6, 7, 8):
            request = Request()
            pointer = request.arguments[index]
            alignment = ctypes.alignment(pointer._type_)
            request.arguments[index] = ctypes.cast(POINTER_MAX - alignment + 1, type(pointer))
            self.run_request(request, BOUNDS)
        for count in (0, 40):
            for label in ("masks", "source", "object", "name"):
                request = Request(data=object_bytes(count))
                request.object(label).bytes = ctypes.cast(POINTER_MAX - 3, BytePointer)
                self.run_request(request, BOUNDS)
            request = Request(data=object_bytes(count))
            request.object("reads").words = ctypes.cast(POINTER_MAX - 3, ctypes.POINTER(Word))
            self.run_request(request, BOUNDS)
            request = Request(data=object_bytes(count))
            request.arguments[5] = ctypes.cast(POINTER_MAX, BytePointer)
            self.run_request(request, BOUNDS)


if __name__ == "__main__":
    unittest.main()
