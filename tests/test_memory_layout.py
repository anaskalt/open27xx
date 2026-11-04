# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare the bounded memory-bank serializer with complete recorded calls."""

import ctypes
import itertools
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, INVALID, UNSUPPORTED, CAPACITY, OVERLAP = 0, -1, -2, -3, -4
SENTINEL = 0x89ABCDEF
BytePointer = ctypes.POINTER(ctypes.c_uint8)
SizePointer = ctypes.POINTER(ctypes.c_size_t)


class Record(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint32), ("selector", ctypes.c_uint32)]


class Inputs(ctypes.Structure):
    _fields_ = [("address_cells", ctypes.c_uint32), ("size_cells", ctypes.c_uint32),
                ("lower_span_bytes", ctypes.c_uint32), ("total_mib", ctypes.c_uint32),
                ("control_word", ctypes.c_uint32), ("record", ctypes.POINTER(Record))]

    def __init__(self, address_cells=2, size_cells=2, lower_span_bytes=994050048,
                 total_mib=8192, control_word=0, record=None):
        super().__init__(address_cells, size_cells, lower_span_bytes, total_mib,
                         control_word, ctypes.pointer(record) if record is not None else None)


class Length(ctypes.Structure):
    _fields_ = [("before", ctypes.c_size_t * 2), ("value", ctypes.c_size_t),
                ("after", ctypes.c_size_t * 2)]

    def __init__(self):
        super().__init__()
        ctypes.memset(ctypes.addressof(self), 0xA5, ctypes.sizeof(self))
        self.value = SENTINEL

    def pointer(self):
        return ctypes.cast(ctypes.byref(self, Length.value.offset), SizePointer)


def byte_pointer(storage, offset=0):
    return ctypes.cast(ctypes.byref(storage, offset), BytePointer)


class MemoryLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Memory-layout tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="memory-layout-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "memory_layout.so"
        command = compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/memory_layout.c"), "-o", str(library),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.serialize = cls.library.memory_layout_serialize
        cls.serialize.argtypes = [ctypes.POINTER(Inputs), BytePointer,
                                  ctypes.c_size_t, SizePointer]
        cls.serialize.restype = ctypes.c_int
        fixture = ROOT / "tests/vectors/start4/memory-layout.json"
        cls.cases = json.loads(fixture.read_text())["cases"]
        cls.complete = [case for case in cls.cases if case["inputs"]["mode"] == "helper"]

    def call(self, inputs, capacity=512, expected_status=OK, offset=16):
        output = (ctypes.c_uint8 * 544)(*([0xA5] * 544))
        length = Length()
        original = bytes(output), bytes(length)
        input_before = bytes(inputs)
        record_before = bytes(inputs.record.contents) if inputs.record else None
        status = self.serialize(ctypes.byref(inputs), byte_pointer(output, offset),
                                capacity, length.pointer())
        self.assertEqual(status, expected_status)
        self.assertEqual(bytes(inputs), input_before)
        if inputs.record:
            self.assertEqual(bytes(inputs.record.contents), record_before)
        if status != OK:
            self.assertEqual((bytes(output), bytes(length)), original)
        else:
            self.assertEqual(bytes(output[:offset]), b"\xA5" * offset)
            self.assertEqual(bytes(output[offset + length.value:]),
                             b"\xA5" * (544 - offset - length.value))
            self.assertEqual(bytes(length.before), b"\xA5" * ctypes.sizeof(length.before))
            self.assertEqual(bytes(length.after), b"\xA5" * ctypes.sizeof(length.after))
        return bytes(output), length.value

    @staticmethod
    def fixture_inputs(case):
        values = case["inputs"]
        record = Record(values["record_flags"], values["record_count"])
        return Inputs(values["address_cells"], values["size_cells"], values["low_bytes"],
                      values["total_mib"], values["hole_flag"],
                      record if values["record_present"] else None)

    def test_fixture_scope(self):
        self.assertEqual(len(self.complete), 44)
        self.assertEqual({int(case["function"]["entry"], 0) for case in self.complete},
                         {0x0ECB2A50})
        slices = [case for case in self.cases if case["inputs"]["mode"] != "helper"]
        self.assertEqual([case["id"] for case in slices],
                         ["cached-capacity", "cached-capacity-minimum",
                          "limited-capacity", "limit-above-capacity"])
        self.assertEqual({int(case["function"]["entry"], 0) for case in slices},
                         {0x0EC574E0, 0x0EC574E8})

    def test_recorded_complete_calls(self):
        for case in self.complete:
            with self.subTest(case=case["id"]):
                inputs = self.fixture_inputs(case)
                output, length = self.call(inputs)
                registers = case["setup"]["registers"]
                self.assertEqual([int(registers[f"r{index}"], 0) for index in range(1, 5)],
                                 [inputs.address_cells, inputs.size_cells,
                                  inputs.lower_span_bytes, inputs.total_mib])
                output_address = int(registers["r0"], 0) - 16
                expected = case["expected"]
                region = next(region for region in expected["memory"]
                              if int(region["address"], 0) == output_address)
                self.assertEqual(output, bytes.fromhex(region["hex"]))
                self.assertEqual(length, int(expected["registers"]["r0"], 0))
                self.assertEqual(expected["events"], [])
                for observed in expected["memory"]:
                    if observed is region:
                        continue
                    initial = next(item for item in case["setup"]["memory"]
                                   if item["address"] == observed["address"])
                    self.assertEqual(observed["hex"], initial["hex"])

    def test_exact_capacity_and_short_buffers(self):
        for case in self.complete:
            required = int(case["expected"]["registers"]["r0"], 0)
            for capacity in (0, required - 1, required):
                with self.subTest(case=case["id"], capacity=capacity):
                    status = OK if capacity == required else CAPACITY
                    self.call(self.fixture_inputs(case), capacity, status)

    def test_null_required_arguments(self):
        for missing in itertools.product((False, True), repeat=3):
            if not any(missing):
                continue
            with self.subTest(missing=missing):
                inputs, length = Inputs(), Length()
                output = (ctypes.c_uint8 * 64)(*([0xA5] * 64))
                before = bytes(inputs), bytes(length), bytes(output)
                status = self.serialize(None if missing[0] else ctypes.byref(inputs),
                                        None if missing[1] else output, 64,
                                        None if missing[2] else length.pointer())
                self.assertEqual(status, INVALID)
                self.assertEqual((bytes(inputs), bytes(length), bytes(output)), before)

    def test_unsupported_numeric_domain(self):
        for field, values in (("address_cells", (0, 3, 0xFFFFFFFF)),
                              ("size_cells", (0, 3, 0xFFFFFFFF)),
                              ("total_mib", (16385, 0xFFFFFFFF))):
            for value in values:
                with self.subTest(field=field, value=value):
                    inputs = Inputs()
                    setattr(inputs, field, value)
                    self.call(inputs, expected_status=UNSUPPORTED)

    def test_one_address_cell_checks_selected_bases(self):
        for size_cells in (1, 2):
            for total, record, accepted in (
                    (4096, None, True), (4097, None, False),
                    (16384, Record(16, 24), True),
                    (3072, Record(16, 48), True), (3073, Record(16, 48), False),
                    (16384, Record(0, 24), False)):
                with self.subTest(size_cells=size_cells, total=total, accepted=accepted):
                    inputs = Inputs(1, size_cells, total_mib=total, record=record)
                    self.call(inputs, expected_status=OK if accepted else UNSUPPORTED)

    def test_full_width_words_and_lower_span(self):
        inputs = Inputs(total_mib=8192, control_word=1)
        ordinary = self.call(inputs)
        for control in (2, 0x80000000, 0xFFFFFFFF):
            inputs.control_word = control
            self.assertEqual(self.call(inputs), ordinary)
        for selector in (0x10018, 0x80000030, 0xFFFFFFFF):
            inputs.record = ctypes.pointer(Record(0xFFFFFFFF, selector))
            self.assertEqual(self.call(inputs), ordinary)
        for control in (0, 1, 0xFFFFFFFF):
            inputs = Inputs(total_mib=16384, control_word=control, record=Record(16, 24))
            special = self.call(inputs)
            self.assertEqual(special, self.call(Inputs(total_mib=3072, record=Record(16, 24))))
        for cells in (1, 2):
            inputs = Inputs(cells, cells, lower_span_bytes=0xFFFFFFFF, total_mib=0)
            output, length = self.call(inputs, offset=17)
            self.assertEqual(length, 8 * cells)
            self.assertEqual(output[17:17 + length],
                             bytes(4 * cells) + (4095 << 20).to_bytes(4 * cells, "big"))

    def test_split_threshold_and_repeated_parts(self):
        for total, sizes in ((8191, [4095]), (8192, [2048, 2048]),
                              (10239, [2048, 4095]), (10240, [2048, 2048, 2048]),
                              (16384, [2048] * 6)):
            with self.subTest(total=total):
                output, length = self.call(Inputs(2, 1, total_mib=total))
                tuples = [(int.from_bytes(output[index:index + 8], "big") >> 20,
                           int.from_bytes(output[index + 8:index + 12], "big") >> 20)
                          for index in range(16, 16 + length, 12)]
                self.assertEqual(tuples[:2], [(0, 948), (1024, 3008)])
                self.assertEqual(tuples[2:], [(4096 + 2048 * index, size)
                                             for index, size in enumerate(sizes)])

    def test_overlaps_preserve_all_storage(self):
        storage = (ctypes.c_uint64 * 64)()
        inputs = Inputs.from_buffer(storage, 128)
        record = Record.from_buffer(storage, 192)
        scenarios = []
        for start, extent in ((128, ctypes.sizeof(Inputs)), (192, ctypes.sizeof(Record))):
            for offset in (-15, 0, extent - 1):
                scenarios.append((start + offset, 16, 256))
            for offset in (-ctypes.sizeof(ctypes.c_size_t) + 1, 0, extent - 1):
                scenarios.append((16, 64, start + offset))
        scenarios.extend((256 + offset, 16, 256)
                         for offset in (-15, 0, ctypes.sizeof(ctypes.c_size_t) - 1))
        scenarios.append((16, 200, 256))
        for output_offset, capacity, length_offset in scenarios:
            with self.subTest(output=output_offset, capacity=capacity, length=length_offset):
                ctypes.memset(ctypes.addressof(storage), 0xA5, ctypes.sizeof(storage))
                inputs.address_cells, inputs.size_cells = 2, 2
                inputs.lower_span_bytes, inputs.total_mib, inputs.control_word = 0, 0, 0
                inputs.record = ctypes.pointer(record)
                record.flags, record.selector = 16, 24
                before = bytes(storage)
                status = self.serialize(ctypes.byref(inputs), byte_pointer(storage, output_offset),
                                        capacity, ctypes.cast(ctypes.byref(storage, length_offset),
                                                              SizePointer))
                self.assertEqual(status, OVERLAP)
                self.assertEqual(bytes(storage), before)

    def test_adjacent_storage(self):
        class Adjacent(ctypes.Structure):
            _fields_ = [("inputs", Inputs), ("record", Record), ("output", ctypes.c_uint8 * 48),
                        ("length", ctypes.c_size_t)]

        storage = Adjacent()
        storage.inputs = Inputs(record=storage.record)
        storage.record.flags, storage.record.selector = 16, 24
        before_inputs, before_record = bytes(storage.inputs), bytes(storage.record)
        status = self.serialize(ctypes.byref(storage.inputs), storage.output, 48,
                                ctypes.cast(ctypes.byref(storage, Adjacent.length.offset), SizePointer))
        self.assertEqual(status, OK)
        self.assertEqual(storage.length, 48)
        self.assertEqual((bytes(storage.inputs), bytes(storage.record)),
                         (before_inputs, before_record))

    def test_wrapping_extents_rejected_before_access(self):
        maximum = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
        inputs, length = Inputs(), Length()
        output = (ctypes.c_uint8 * 64)(*([0xA5] * 64))
        before = bytes(output), bytes(length)
        calls = [
            (ctypes.cast(maximum - 1, ctypes.POINTER(Inputs)), output, 64, length.pointer()),
            (ctypes.byref(inputs), ctypes.cast(maximum - 7, BytePointer), 16, length.pointer()),
            (ctypes.byref(inputs), output, maximum, length.pointer()),
            (ctypes.byref(inputs), output, 64, ctypes.cast(maximum - 1, SizePointer)),
        ]
        for arguments in calls:
            self.assertEqual(self.serialize(*arguments), INVALID)
            self.assertEqual((bytes(output), bytes(length)), before)
        inputs.record = ctypes.cast(maximum - 1, ctypes.POINTER(Record))
        self.assertEqual(self.serialize(ctypes.byref(inputs), output, 64, length.pointer()), INVALID)
        self.assertEqual((bytes(output), bytes(length)), before)


if __name__ == "__main__":
    unittest.main()
