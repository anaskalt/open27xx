# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check conditional SoC state, guarded storage and atomic host rejection."""

import ctypes
import itertools
import os
import random
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
Word = ctypes.c_uint32
BytePointer = ctypes.POINTER(ctypes.c_uint8)
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
VERSION2, MMIO = 0, 1
WORD_MAX = 0xFFFFFFFF
POINTER_MAX = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
LENGTHS = (16, 16, 12, 8, 20, 12, 12)
OFFSETS = (0x1560, 0x16E0, 0x3B890, 0x3B8AC, 0x3B920, 0xCCDB4, 0x3B480)
FIXED = ((0x0EC6221C, 342), (0x7E0000B4, 4))
FLAGS = {0x04000160: 1, 0x04000161: 1, 0x04000162: 2, 0x04000170: 3,
         0x04000180: 3, 0x04000181: 3, 0x04000182: 3, 0x04000183: 3, 0x04000184: 4}


class Registers(ctypes.Structure):
    _fields_ = [("r", Word * 24)] + [(name, Word) for name in
                ("gp", "sp", "lr", "r27", "r28", "r29", "sr")]


class Observations(ctypes.Structure):
    _fields_ = [("version1", Word), ("kind", ctypes.c_int), ("word", Word)]


class Buffer(ctypes.Structure):
    _fields_ = [("bytes", BytePointer), ("length", ctypes.c_size_t)]


class Memory(ctypes.Structure):
    _fields_ = [("buffers", Buffer * 7)]


class Stack(ctypes.Structure):
    _fields_ = [("bytes", BytePointer), ("length", ctypes.c_size_t), ("address", Word)]


class Result(ctypes.Structure):
    _fields_ = [("registers", Registers), ("pc", Word)]


def byte_pointer(address):
    return ctypes.cast(address, BytePointer)


def pointer_address(pointer):
    return ctypes.cast(pointer, ctypes.c_void_p).value


class Storage:
    def __init__(self, length, data=None):
        self.backing = (ctypes.c_uint64 * ((length + 383) // 8))()
        ctypes.memset(self.backing, 0xA5, ctypes.sizeof(self.backing))
        self.address = ctypes.addressof(self.backing) + 64
        if data is not None:
            ctypes.memmove(self.address, data, len(data))


class Call:
    kinds: ClassVar[dict] = {"input": Registers, "observations": Observations,
                            "memory": Memory, "stack": Stack, "result": Result}
    byte_names = tuple(f"region{index}" for index in range(7)) + ("bytes",)

    def __init__(self, version=0x04000184, word=0xDEADBEEF, diagnostic=3,
                 gp=0x0EE04140, address=0x24010040, length=128,
                 sp=0x24010080, lr=0x24000000, seed=0):
        randomizer = random.Random(seed)
        registers = Registers()
        for index in range(24):
            registers.r[index] = randomizer.getrandbits(32)
        for name, _ in Registers._fields_[1:]:
            setattr(registers, name, randomizer.getrandbits(32))
        registers.gp, registers.sp, registers.lr = gp, sp, lr
        self.storage = {}
        for name, size in zip(self.byte_names, (*LENGTHS, length)):
            data = bytes(randomizer.randrange(256) for _ in range(size))
            self.storage[name] = Storage(size, data)
        ctypes.c_uint8.from_address(self.storage["region5"].address + 4).value = diagnostic
        values = (registers, Observations(version, MMIO if version in FLAGS else VERSION2, word),
                  Memory((Buffer * 7)(*(Buffer(byte_pointer(self.storage[f"region{index}"].address),
                                              size) for index, size in enumerate(LENGTHS)))),
                  Stack(byte_pointer(self.storage["bytes"].address), length, address), Result())
        self.arguments = []
        for (name, kind), value in zip(self.kinds.items(), values):
            self.storage[name] = Storage(ctypes.sizeof(kind), bytes(value))
            self.arguments.append(ctypes.cast(self.storage[name].address, ctypes.POINTER(kind)))
        ctypes.memset(self.storage["result"].address, 0xD3, ctypes.sizeof(Result))

    def object(self, name):
        return self.arguments[list(self.kinds).index(name)].contents

    def redirect(self, name, address):
        self.arguments[list(self.kinds).index(name)] = ctypes.cast(
            address, ctypes.POINTER(self.kinds[name]))

    def set_byte_pointer(self, name, address):
        if name == "bytes":
            self.object("stack").bytes = byte_pointer(address)
        else:
            self.object("memory").buffers[int(name[-1])].bytes = byte_pointer(address)

    def snapshot(self):
        return [(ctypes.addressof(item.backing), bytes(item.backing))
                for item in self.storage.values()]


class SocInitializationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("SoC initialization tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="soc-initialization-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "soc_initialization.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/soc_initialization.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.soc_initialization_run
        cls.function.argtypes = [ctypes.POINTER(kind) for kind in Call.kinds.values()]
        cls.function.restype = ctypes.c_int

    def run_call(self, call, status=OK):
        before = call.snapshot()
        stores = []
        if status == OK:
            supplied, stack = call.object("input"), call.object("stack")
            observations = call.object("observations")
            buffers = call.object("memory").buffers
            diagnostic = buffers[5].bytes[4]
            flags = FLAGS.get(observations.version1, 0)
            expected = Result(Registers.from_buffer_copy(supplied), supplied.lr)
            expected.registers.r[4] = (observations.version1 - 0x04000160) & WORD_MAX
            if flags:
                bit = observations.word & 1
                control = int.from_bytes(bytes(buffers[4].bytes[4:8]), "little")
                control |= 0x07000000 if bit else 0x05000000
                for region, offset in ((0, 4), (0, 8), (1, 4), (1, 8))[:flags]:
                    stores.append((pointer_address(buffers[region].bytes) + offset, b"\x01\0\0\0"))
                stores.append((pointer_address(buffers[4].bytes) + 4,
                               control.to_bytes(4, "little")))
                classification, mode = 3, 0x37F5
                expected.registers.r[1:4] = (observations.word, diagnostic, 0x7E000080)
                if bit:
                    expected.registers.r[0], expected.registers.r[4] = control, diagnostic
            else:
                bit = (observations.word >> 6) & 1
                classification, mode = bit, 0x7FF5
                expected.registers.r[1], expected.registers.r[2] = bit, observations.word
                expected.registers.r[5] = diagnostic
            expected.registers.sr = (supplied.sr & 0xFFFFFFF0) | (0 if bit else 0xA)
            stores.extend(((pointer_address(buffers[2].bytes) + 4, b"\x01\0\0\0"),
                           (pointer_address(buffers[3].bytes) + 2, bytes([classification])),
                           (pointer_address(buffers[4].bytes) + 12, mode.to_bytes(4, "little")),
                           (ctypes.addressof(call.object("result")), bytes(expected))))
            frame = b"".join(value.to_bytes(4, "little") for value in
                             (*reversed(supplied.r[6:11]), supplied.lr))
            stores.append((pointer_address(stack.bytes) + supplied.sp - 24 - stack.address, frame))
        self.assertEqual(self.function(*call.arguments), status)
        for (address, old), (new_address, new) in zip(before, call.snapshot()):
            self.assertEqual(address, new_address)
            expected_bytes = bytearray(old)
            for target, data in stores:
                begin, end = max(address, target), min(address + len(old), target + len(data))
                if begin < end:
                    expected_bytes[begin - address:end - address] = data[begin - target:end - target]
            self.assertEqual(new, bytes(expected_bytes))
        if status == OK:
            self.assertEqual(bytes(call.object("result")), bytes(expected))

    def test_every_selector_diagnostic_and_followup_bit(self):
        for selector, diagnostic, bit in itertools.product(range(37), range(4), range(2)):
            with self.subTest(selector=selector, diagnostic=diagnostic, bit=bit):
                version = 0x04000160 + selector
                word = (0xA5A5A5A4 | bit) if version in FLAGS else (0xDEADBEAF | (bit << 6))
                self.run_call(Call(version, word, diagnostic, seed=selector + diagnostic + bit))

    def test_default_range_edges_and_full_width_aliases(self):
        versions = (0, WORD_MAX, 0x0400015F, 0x04000185, 0x04010160,
                    0x84000160, 0xF4000184, 0x00000160)
        for version, word in itertools.product(versions, (0, 1, 0x40, 0xFFFFFFBF, WORD_MAX)):
            with self.subTest(version=version, word=word):
                self.run_call(Call(version, word, seed=version ^ word))

    def test_arbitrary_state_sr_nibbles_and_repeated_calls(self):
        for version, bit, low in itertools.product((0x04000162, 0x04000170, 0), range(2), range(16)):
            call = Call(version, bit if version else bit << 6, low % 4, seed=version + low)
            call.object("input").sr = 0xFEDCBA90 | low
            self.run_call(call)
            self.run_call(call)

    def test_zero_and_full_width_state_and_every_control_bit(self):
        controls = (0, WORD_MAX, 0x01000000, 0x05000000, 0x07000000,
                    *(1 << bit for bit in range(32)))
        for version, word, control in itertools.product((0x04000184, 0), (0, WORD_MAX), controls):
            call = Call(version, word)
            supplied = call.object("input")
            for index in range(24):
                supplied.r[index] = word
            supplied.r27 = supplied.r28 = supplied.r29 = supplied.sr = word
            ctypes.memmove(call.storage["region4"].address + 4, control.to_bytes(4, "little"), 4)
            self.run_call(call)

    def test_general_gp_frame_boundaries_and_unaligned_byte_storage(self):
        cases = ((0, 0, 24, 24, 24), (4, 1, 27, 28, 0),
                 (0x13579000, 0x1001, 31, 0x1020, 0x1000),
                 (0xFFF33240, 0x1000, 24, 0x1018, 0),
                 (0, 0xFFFFFFE0, 32, 0xFFFFFFFC, 0),
                 (0, 0xFFFFFFE4, 24, 0xFFFFFFFC, WORD_MAX - 1))
        for gp, address, length, sp, lr in cases:
            with self.subTest(gp=gp, address=address, length=length):
                call = Call(gp=gp, address=address, length=length, sp=sp, lr=lr)
                for name in Call.byte_names:
                    ctypes.memmove(call.storage[name].address + 1, call.storage[name].address,
                                   length if name == "bytes" else LENGTHS[int(name[-1])])
                    call.set_byte_pointer(name, call.storage[name].address + 1)
                self.run_call(call)

    def test_null_misaligned_and_wrapping_typed_objects(self):
        for name, kind in Call.kinds.items():
            for mode, status in (("null", INVALID), ("unaligned", INVALID), ("wrap", BOUNDS)):
                with self.subTest(name=name, mode=mode):
                    call = Call()
                    address = {"null": None, "unaligned": call.storage[name].address + 1,
                               "wrap": POINTER_MAX - ctypes.alignment(kind) + 1}[mode]
                    call.redirect(name, address)
                    self.run_call(call, status)

    def test_required_byte_pointers_and_host_span_wrap(self):
        for name in Call.byte_names:
            for address, status in ((None, INVALID), (POINTER_MAX - 3, BOUNDS)):
                with self.subTest(name=name, address=address):
                    call = Call()
                    call.set_byte_pointer(name, address)
                    self.run_call(call, status)

    def test_wrong_region_lengths_preserve_every_object(self):
        for index, required in enumerate(LENGTHS):
            for length in (0, 1, required - 1, required + 1, WORD_MAX):
                with self.subTest(index=index, length=length):
                    call = Call()
                    call.object("memory").buffers[index].length = length
                    self.run_call(call, BOUNDS)

    def test_invalid_scalars_tags_and_unsupported_diagnostics(self):
        for name, values in (("gp", (1, 0x0EE04141, WORD_MAX)),
                             ("sp", (0, 4, 20, 23, 25, 0x24010081, WORD_MAX)),
                             ("lr", (1, 0x24000001, WORD_MAX))):
            for value in values:
                call = Call()
                setattr(call.object("input"), name, value)
                self.run_call(call, INVALID)
        for version in (0, 0x04000184):
            for tag in (-1, 2, 0x7FFFFFFF, VERSION2 if version else MMIO):
                call = Call(version)
                call.object("observations").kind = tag
                self.run_call(call, INVALID)
            for diagnostic in range(4, 256):
                self.run_call(Call(version, diagnostic=diagnostic), UNSUPPORTED)

    def test_stack_length_frame_and_virtual_wrap(self):
        for length in (0, 1, 23, 63):
            call = Call()
            call.object("stack").length = length
            self.run_call(call, BOUNDS)
        if ctypes.sizeof(ctypes.c_size_t) > 4:
            call = Call()
            call.object("stack").length = 1 << 32
            self.run_call(call, BOUNDS)
        for sp in (0x24010040, 0x24010054, 0x240100C4):
            call = Call()
            call.object("input").sp = sp
            self.run_call(call, BOUNDS)
        self.run_call(Call(address=0xFFFFFFE1, length=32, sp=0xFFFFFFFC, lr=0), BOUNDS)
        for gp in (0xFFF33244, 0xFFFFF000, 0xFFFFFFFC):
            self.run_call(Call(gp=gp), BOUNDS)

    def test_typed_object_pairs_reject_full_and_partial_overlap(self):
        for left, right in itertools.permutations(Call.kinds, 2):
            alignment = ctypes.alignment(Call.kinds[right])
            for offset in (0, alignment, -alignment):
                with self.subTest(left=left, right=right, offset=offset):
                    call = Call()
                    call.redirect(right, call.storage[left].address + offset)
                    self.run_call(call, OVERLAP)

    def test_all_byte_spans_exclude_each_typed_object(self):
        for byte_name, object_name in itertools.product(Call.byte_names, Call.kinds):
            for offset in (0, -1, ctypes.sizeof(Call.kinds[object_name]) - 1):
                with self.subTest(bytes=byte_name, object=object_name, offset=offset):
                    call = Call()
                    call.set_byte_pointer(byte_name, call.storage[object_name].address + offset)
                    self.run_call(call, OVERLAP)

    def test_byte_span_pairs_reject_one_byte_overlap_and_containment(self):
        lengths = dict(zip(Call.byte_names, (*LENGTHS, 128)))
        for left, right in itertools.permutations(Call.byte_names, 2):
            for offset in (0, lengths[left] - 1, 1 - lengths[right]):
                with self.subTest(left=left, right=right, offset=offset):
                    call = Call()
                    call.set_byte_pointer(right, call.storage[left].address + offset)
                    self.run_call(call, OVERLAP)

    def test_adjacent_host_objects_and_byte_spans(self):
        call = Call()
        order = ("memory", "stack", "input", "observations", "result", *Call.byte_names)
        sizes = {**{name: ctypes.sizeof(kind) for name, kind in Call.kinds.items()},
                 **dict(zip(Call.byte_names, (*LENGTHS, 128)))}
        arena = Storage(sum(sizes.values()))
        call.storage["arena"] = arena
        cursor = arena.address
        for name in order:
            ctypes.memmove(cursor, call.storage[name].address, sizes[name])
            if name in Call.kinds:
                self.assertEqual(cursor % ctypes.alignment(Call.kinds[name]), 0)
                call.redirect(name, cursor)
            else:
                call.set_byte_pointer(name, cursor)
            cursor += sizes[name]
        self.run_call(call)
        for reverse in (False, True):
            call = Call()
            arena = Storage(sum(LENGTHS) + 129)
            call.storage["arena"] = arena
            cursor = arena.address + 1
            for name in tuple(reversed(Call.byte_names)) if reverse else Call.byte_names:
                ctypes.memmove(cursor, call.storage[name].address, sizes[name])
                call.set_byte_pointer(name, cursor)
                cursor += sizes[name]
            self.run_call(call)

    def test_virtual_lr_and_full_stack_exclusions_and_adjacency(self):
        ordinary = tuple((0x0EE04140 + offset, length) for offset, length in zip(OFFSETS, LENGTHS))
        for address, length in (*FIXED, *ordinary):
            with self.subTest(address=address):
                for lr in (address, address + length - 2):
                    self.run_call(Call(lr=lr), OVERLAP)
                for lr in (address - 2, address + length):
                    self.run_call(Call(lr=lr))
                sp = address & ~3
                self.run_call(Call(address=sp - 24, length=address - sp + 25,
                                   sp=sp, lr=0), OVERLAP)
                end = address + length
                sp = (end + 27) & ~3
                self.run_call(Call(address=end - 1, length=sp - end + 1, sp=sp, lr=0), OVERLAP)
                for start, stop, sp in ((address - 24, address, address),
                                        (end, end + 26, (end + 26) & ~3)):
                    if any(start < other + size and other < stop
                           for other, size in (*FIXED, *ordinary)):
                        continue
                    self.run_call(Call(address=start, length=stop - start, sp=sp, lr=0))
        for lr in (0x24010040, 0x24010080, 0x240100BE):
            self.run_call(Call(lr=lr), OVERLAP)
        for lr in (0x2401003E, 0x240100C0):
            self.run_call(Call(lr=lr))

    def test_all_ordinary_spans_exclude_fixed_intervals_on_both_paths(self):
        for version, (fixed, fixed_length), (offset, length) in itertools.product(
                (0, 0x04000184), FIXED, zip(OFFSETS, LENGTHS)):
            with self.subTest(version=version, fixed=fixed, offset=offset):
                for gp in (fixed - offset, (fixed + fixed_length - 1 - offset) & ~3):
                    self.run_call(Call(version, gp=gp), OVERLAP)
                for gp in (fixed - length - offset, (fixed + fixed_length + 3 - offset) & ~3):
                    spans = [(gp + item, size) for item, size in zip(OFFSETS, LENGTHS)]
                    if any(start < excluded + size and excluded < start + span_length
                           for start, span_length in spans for excluded, size in FIXED):
                        continue
                    self.run_call(Call(version, gp=gp))


if __name__ == "__main__":
    unittest.main()
