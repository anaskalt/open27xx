# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check fixed-table startup clearing, scalar state and host rejection policy."""

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
WORD_MAX = 0xFFFFFFFF
POINTER_MAX = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
LENGTHS = (2352, 2048, 1011288)
EXCLUDED = ((0x0EE056A0, 2352), (0x0EE33200, 2048), (0x0EE33A00, 1011288),
            (0x0EC3D740, 182), (0x0EC3D7F6, 2), (0x0ED1FDF0, 4),
            (0x0ED1FE14, 56), (0x0EDD7870, 36))


class Registers(ctypes.Structure):
    _fields_ = [("r", Word * 24)] + [(name, Word) for name in
                ("gp", "sp", "lr", "r27", "r28", "r29", "sr")]


class Buffer(ctypes.Structure):
    _fields_ = [("bytes", BytePointer), ("length", ctypes.c_size_t)]


class Destinations(ctypes.Structure):
    _fields_ = [("buffers", Buffer * 3)]


class Stack(ctypes.Structure):
    _fields_ = [("bytes", BytePointer), ("length", ctypes.c_size_t), ("address", Word)]


class Result(ctypes.Structure):
    _fields_ = [("registers", Registers), ("pc", Word)]


def byte_pointer(address):
    return ctypes.cast(address, BytePointer)


def register_words(registers):
    return {**{f"r{index}": value for index, value in enumerate(registers.r)},
            **{name: getattr(registers, name) for name, _ in Registers._fields_[1:]}}


class Storage:
    def __init__(self, length, data=None):
        self.backing = (ctypes.c_uint64 * ((length + 383) // 8))()
        ctypes.memset(self.backing, 0xA5, ctypes.sizeof(self.backing))
        self.address = ctypes.addressof(self.backing) + 64
        if data is not None:
            ctypes.memmove(self.address, data, len(data))


class Call:
    kinds: ClassVar[dict] = {"input": Registers, "destinations": Destinations,
                            "stack": Stack, "result": Result}
    byte_names = ("destination0", "destination1", "destination2", "bytes")

    def __init__(self, address=0x24010040, length=128,
                 sp=0x24010080, lr=0x24000000, seed=0):
        randomizer = random.Random(seed)
        registers = Registers()
        for index in range(24):
            registers.r[index] = randomizer.getrandbits(32)
        for name, _ in Registers._fields_[1:]:
            setattr(registers, name, randomizer.getrandbits(32))
        registers.gp, registers.sp, registers.lr = 0x0EE04140, sp, lr
        self.storage = {}
        for name, size in zip(self.byte_names, (*LENGTHS, length)):
            pattern = bytes(randomizer.randrange(256) for _ in range(256))
            self.storage[name] = Storage(size, (pattern * ((size + 255) // 256))[:size])
        values = (registers,
                  Destinations((Buffer * 3)(*(Buffer(byte_pointer(
                      self.storage[f"destination{index}"].address), size)
                      for index, size in enumerate(LENGTHS)))),
                  Stack(byte_pointer(self.storage["bytes"].address), length, address),
                  Result())
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
            self.object("destinations").buffers[int(name[-1])].bytes = byte_pointer(address)

    def snapshot(self):
        return [(ctypes.addressof(item.backing), bytes(item.backing))
                for item in self.storage.values()]


class StartupInitializationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Startup initialization tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="startup-initialization-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "startup_initialization.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/startup_initialization.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.startup_initialization_run
        cls.function.argtypes = [ctypes.POINTER(kind) for kind in Call.kinds.values()]
        cls.function.restype = ctypes.c_int

    def run_call(self, call, status=OK):
        before = call.snapshot()
        stores = []
        if status == OK:
            supplied, stack = call.object("input"), call.object("stack")
            expected = Result(Registers.from_buffer_copy(supplied), supplied.lr)
            for index in (0, 1, 2, 4):
                expected.registers.r[index] = 0
            expected.registers.r[3], expected.registers.r[5] = 0x0EF2A858, 0x0EDD7870
            expected.registers.lr = 0x0EC3D77A
            expected.registers.sr = (supplied.sr & 0xFFFFFFF0) | 6
            stores.append((ctypes.addressof(call.object("result")), bytes(expected)))
            frame = b"".join(value.to_bytes(4, "little") for value in
                             (*reversed(supplied.r[6:10]), supplied.lr))
            stores.append((ctypes.cast(stack.bytes, ctypes.c_void_p).value
                           + supplied.sp - 20 - stack.address, frame))
            for buffer in call.object("destinations").buffers:
                stores.append((ctypes.cast(buffer.bytes, ctypes.c_void_p).value,
                               bytes(buffer.length)))
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
            self.assertEqual(register_words(call.object("result").registers),
                             register_words(expected.registers))
            self.assertEqual(call.object("result").pc, expected.pc)

    def test_two_documented_caller_profiles(self):
        profiles = ((0x11110000, 0x101, 0x24010080, 0x24000000, 0x13579BDA, 0x3C, 0xA5),
                    (0xEEEE0000, 0x303, 0x24010280, 0x24000004, 0xA5A5A5A5, 0xC3, 0x5A))
        for base, step, sp, lr, sr, stack_fill, poison in profiles:
            with self.subTest(sp=sp):
                call = Call(address=sp - 64, sp=sp, lr=lr)
                supplied = call.object("input")
                for index in range(24):
                    supplied.r[index] = base + index * step
                for index in (27, 28, 29):
                    setattr(supplied, f"r{index}", base + index * step)
                supplied.sr = sr
                ctypes.memset(call.storage["bytes"].address, stack_fill, 128)
                for index, length in enumerate(LENGTHS):
                    ctypes.memset(call.storage[f"destination{index}"].address, poison, length)
                self.run_call(call)

    def test_arbitrary_registers_and_bytes_for_every_sr_low_nibble(self):
        for upper, low in itertools.product((0, 0xA5A5A5A0, 0xFFFFFFF0), range(16)):
            with self.subTest(upper=upper, low=low):
                call = Call(seed=upper + low)
                call.object("input").sr = upper | low
                self.run_call(call)
                self.run_call(call)

    def test_zero_and_full_width_incoming_words(self):
        for word in (0, WORD_MAX):
            call = Call()
            supplied = call.object("input")
            for index in range(24):
                supplied.r[index] = word
            supplied.r27 = supplied.r28 = supplied.r29 = supplied.sr = word
            for name, length in zip(Call.byte_names, (*LENGTHS, 128)):
                ctypes.memset(call.storage[name].address, word & 255, length)
            self.run_call(call)

    def test_minimal_boundary_and_unaligned_byte_spans(self):
        cases = ((0, 24, 24, 24), (1, 27, 28, 0), (0x1001, 31, 0x1020, 0x1000),
                 (0x1000, 24, 0x1018, WORD_MAX - 1),
                 (0xFFFFFFE0, 32, 0xFFFFFFFC, 0),
                 (0xFFFFFFE4, 24, 0xFFFFFFFC, WORD_MAX - 1))
        for address, length, sp, lr in cases:
            with self.subTest(address=address, length=length):
                call = Call(address, length, sp, lr)
                for name in Call.byte_names:
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
            with self.subTest(name=name):
                call = Call()
                call.set_byte_pointer(name, None)
                self.run_call(call, INVALID)
                call = Call()
                call.set_byte_pointer(name, POINTER_MAX - 15)
                self.run_call(call, BOUNDS)

    def test_wrong_destination_lengths_preserve_every_object(self):
        for index, required in enumerate(LENGTHS):
            for length in (0, 1, required - 1, required + 1, WORD_MAX):
                with self.subTest(index=index, length=length):
                    call = Call()
                    call.object("destinations").buffers[index].length = length
                    self.run_call(call, BOUNDS)

    def test_unsupported_gp_and_invalid_scalar_inputs(self):
        for gp in (0, 1, WORD_MAX, 0x0EE0413F, 0x0EE04141, 0xCEE04140):
            call = Call()
            call.object("input").gp = gp
            self.run_call(call, UNSUPPORTED)
        for sp in (0, 4, 20, 23, 25, 0x24010081, WORD_MAX):
            call = Call()
            call.object("input").sp = sp
            self.run_call(call, INVALID)
        for lr in (1, 0x24000001, WORD_MAX):
            self.run_call(Call(lr=lr), INVALID)

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
        for lr in (0x24010040, 0x24010080, 0x240100BE):
            self.run_call(Call(lr=lr), OVERLAP)
        for lr in (0x2401003E, 0x240100C0):
            self.run_call(Call(lr=lr))

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
        order = ("destinations", "stack", "input", "result", *Call.byte_names)
        sizes = {**{name: ctypes.sizeof(kind) for name, kind in Call.kinds.items()},
                 **dict(zip(Call.byte_names, (*LENGTHS, 128)))}
        arena = Storage(sum(sizes.values()))
        call.storage["arena"] = arena
        cursor = arena.address
        for name in order:
            if name in Call.kinds:
                self.assertEqual(cursor % ctypes.alignment(Call.kinds[name]), 0)
                ctypes.memmove(cursor, ctypes.byref(call.object(name)), sizes[name])
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
            names = tuple(reversed(Call.byte_names)) if reverse else Call.byte_names
            for name in names:
                call.set_byte_pointer(name, cursor)
                cursor += sizes[name]
            self.run_call(call)

    def test_fixed_ranges_exclude_lr_and_entire_virtual_stack(self):
        for address, length in EXCLUDED:
            with self.subTest(address=address):
                for lr in (address, address + length - 2):
                    self.run_call(Call(lr=lr), OVERLAP)
                sp = address & ~3
                self.run_call(Call(address=sp - 24, length=address - sp + 25,
                                   sp=sp, lr=0), OVERLAP)
                end = address + length
                sp = (end + 27) & ~3
                self.run_call(Call(address=end - 1, length=sp - end + 1, sp=sp, lr=0), OVERLAP)

    def test_fixed_virtual_range_adjacency_is_allowed(self):
        # Neighboring ranges are one exclusion when testing their outside edges.
        merged = []
        for address, length in sorted(EXCLUDED):
            if merged and merged[-1][1] == address:
                merged[-1] = (merged[-1][0], address + length)
            else:
                merged.append((address, address + length))
        for start, end in merged:
            with self.subTest(start=start, end=end):
                for lr in (start - 2, end):
                    self.run_call(Call(lr=lr))
                sp = start & ~3
                before = (sp - 24, start - sp + 24)
                after_sp = (end + 27) & ~3
                after = (end, after_sp - end)
                for address, length in (before, after):
                    if any(address < stop and begin < address + length
                           for begin, stop in merged):
                        continue
                    self.run_call(Call(address=address, length=length,
                                       sp=sp if address < start else after_sp, lr=0))


if __name__ == "__main__":
    unittest.main()
