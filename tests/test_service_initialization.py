# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare service initialization state, numeric events and rejected inputs."""

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

ROOT = Path(__file__).resolve().parents[1]
Word = ctypes.c_uint32
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
VERSION, MMIO_WRITE, TABLE_READ, TABLE_WRITE = range(4)
WORD_MAX = 0xFFFFFFFF
POINTER_MAX = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
NORMALIZED = (0x04000162, 0x04000161, 0x04000160, 0x04000140, 0x04000104)
EXCLUDED = ((0xCEC002A0, 96), (0xCEC00DD0, 70), (0xCEC00D76, 12),
            (0xCEC01E80, 4), (0x7E002030, 4), (0x7E002830, 4),
            (0x7EE0003C, 4), (0x7EE00040, 4))


class Registers(ctypes.Structure):
    _fields_ = [("r", Word * 24)] + [(name, Word) for name in
                ("gp", "sp", "lr", "r27", "r28", "r29", "sr")]


class Input(ctypes.Structure):
    _fields_ = [("version", Word), ("registers", Registers)]


class Stack(ctypes.Structure):
    _fields_ = [("bytes", ctypes.POINTER(ctypes.c_uint8)),
               ("length", ctypes.c_size_t), ("address", Word)]


class Event(ctypes.Structure):
    _fields_ = [("kind", ctypes.c_int), ("source", Word), ("address", Word), ("word", Word)]


class Result(ctypes.Structure):
    _fields_ = [("registers", Registers), ("pc", Word), ("instructions", Word),
               ("event_count", Word), ("events", Event * 8)]


def register_words(registers):
    return {**{f"r{index}": value for index, value in enumerate(registers.r)},
            **{name: getattr(registers, name) for name, _ in Registers._fields_[1:]}}


def event_words(event):
    return tuple(getattr(event, name) for name, _ in Event._fields_)


class Storage:
    def __init__(self, value):
        self.backing = (ctypes.c_uint64 * 80)()
        ctypes.memset(self.backing, 0xA5, ctypes.sizeof(self.backing))
        self.address = ctypes.addressof(self.backing) + 64
        ctypes.memmove(self.address, ctypes.byref(value), ctypes.sizeof(value))
        self.pointer = ctypes.cast(self.address, ctypes.POINTER(type(value)))


class Call:
    names = ("input", "stack", "table", "result")

    def __init__(self, version=NORMALIZED[0], address=0x2400FFC0,
                 length=128, sp=0x24010000, lr=0x24040000, seed=0):
        randomizer = random.Random(seed)
        registers = Registers()
        for index in range(24):
            registers.r[index] = randomizer.getrandbits(32)
        for name, _ in Registers._fields_[1:]:
            setattr(registers, name, randomizer.getrandbits(32))
        registers.sp, registers.lr = sp, lr
        self.storage = {"bytes": Storage((ctypes.c_uint8 * length)(
            *(randomizer.getrandbits(8) for _ in range(length))))}
        values = (Input(version, registers),
                  Stack(ctypes.cast(self.storage["bytes"].address,
                                    ctypes.POINTER(ctypes.c_uint8)), length, address),
                  Word(0xCEC00DA0), Result())
        for name, value in zip(self.names, values):
            self.storage[name] = Storage(value)
        ctypes.memset(self.storage["result"].address, 0xD3, ctypes.sizeof(Result))
        self.arguments = [self.storage[name].pointer for name in self.names]

    def object(self, name):
        return self.arguments[self.names.index(name)].contents

    def redirect(self, name, address):
        index = self.names.index(name)
        self.arguments[index] = ctypes.cast(address, type(self.arguments[index]))

    def snapshot(self):
        return [(ctypes.addressof(item.backing), bytes(item.backing))
                for item in self.storage.values()]


class ServiceInitializationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Service initialization tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="service-initialization-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "service_initialization.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/service_initialization.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.service_initialization_run
        cls.function.argtypes = [ctypes.POINTER(kind) for kind in (Input, Stack, Word, Result)]
        cls.function.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/service-initialization.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = json.loads(path.read_text())["cases"]

    def expected_result(self, call):
        supplied = call.object("input")
        primary = supplied.version & 0x10000 == 0
        comparison = NORMALIZED.index(supplied.version & 0xFFFEFFF7)
        result = Result()
        result.registers = Registers.from_buffer_copy(supplied.registers)
        result.registers.r[0] = result.registers.sr = 0
        result.pc = supplied.registers.lr
        result.registers.r[1] = 0x7EE0003C if primary else 0x7E002830
        result.registers.r[2] = 0x7EE00040 if primary else 0xCEC01E00
        if primary:
            result.registers.r[5] = supplied.registers.lr
        result.instructions = (42 if primary else 18) + comparison * 2
        events = [(VERSION, 0xCEC002A0, 0, supplied.version),
                  (MMIO_WRITE, 0xCEC002BA, 0x7E002030 if primary else 0x7E002830, 0xCEC01E00),
                  (VERSION, 0xCEC002EA, 0, supplied.version)]
        if primary:
            events += [(TABLE_READ, 0xCEC00DDC, 0xCEC01E80, 0xCEC00DA0),
                       (TABLE_WRITE, 0xCEC00DE2, 0xCEC01E80, 0xCEC00DA1),
                       (MMIO_WRITE, 0xCEC00DF6, 0x7EE0003C, 0x0EC00000),
                       (MMIO_WRITE, 0xCEC00E02, 0x7EE00040, 0x0EC01FFF),
                       (MMIO_WRITE, 0xCEC00E0C, 0x7EE0003C, 0x0EC00001)]
        result.event_count = len(events)
        for index, values in enumerate(events):
            result.events[index] = Event(*values)
        return result

    def run_call(self, call, status=OK):
        before = call.snapshot()
        mutations = {}
        if status == OK:
            supplied, stack = call.object("input"), call.object("stack")
            expected = self.expected_result(call)
            stores = [(ctypes.addressof(call.object("result")), bytes(expected)),
                      (ctypes.cast(stack.bytes, ctypes.c_void_p).value
                       + supplied.registers.sp - 8 - stack.address,
                       bytes(4) + supplied.registers.lr.to_bytes(4, "little"))]
            if supplied.version & 0x10000 == 0:
                stores.append((ctypes.addressof(call.object("table")), bytes(Word(0xCEC00DA1))))
            for address, data in stores:
                mutations.update((address + offset, value) for offset, value in enumerate(data))
        self.assertEqual(self.function(*call.arguments), status)
        after = call.snapshot()
        for (address, old), (new_address, new) in zip(before, after):
            self.assertEqual(address, new_address)
            self.assertEqual(new, bytes(mutations.get(address + offset, value)
                                        for offset, value in enumerate(old)))
        if status == OK:
            self.assertEqual(bytes(call.object("result")), bytes(expected))

    def test_complete_recorded_calls(self):
        self.assertEqual(self.fixture_hash,
                         "2389936e44ae2b6deed89aff710b35cf6a801b50a7f756fd5d2f131c898b21d2")
        instructions = events = 0
        for case in self.cases:
            with self.subTest(case=case["id"]):
                execution, setup = case["execution"], case["setup"]
                memory = setup["memory"][0]
                call = Call(int(execution["version_input"]["word"], 0),
                            int(memory["address"], 0), memory["size"],
                            int(setup["registers"]["sp"], 0), int(execution["return_address"], 0))
                for name, value in setup["registers"].items():
                    if name.startswith("r") and name[1:].isdigit() and int(name[1:]) < 24:
                        call.object("input").registers.r[int(name[1:])] = int(value, 0)
                    else:
                        setattr(call.object("input").registers, name, int(value, 0))
                ctypes.memset(call.storage["bytes"].address, int(memory["fill"], 16), memory["size"])
                if call.object("input").version & 0x10000:
                    call.redirect("table", None)
                self.run_call(call)
                result = call.object("result")
                actual_registers = {**register_words(result.registers), "pc": result.pc}
                self.assertEqual(actual_registers,
                                 {name: int(value, 0) for name, value in
                                  case["expected"]["registers"].items()})
                self.assertEqual(ctypes.string_at(call.storage["bytes"].address, memory["size"]),
                                 bytes.fromhex(case["expected"]["memory"][0]["hex"]))
                expected_events = []
                kinds = {"version": VERSION, "mmio_write": MMIO_WRITE,
                         "elf_data_read": TABLE_READ, "elf_data_write": TABLE_WRITE}
                for item in case["expected"]["events"]:
                    word = (int(item["value"], 0) if item["kind"] == "version"
                            else int.from_bytes(bytes.fromhex(item["hex"]), "little"))
                    expected_events.append((kinds[item["kind"]], int(item["pc"], 0),
                                            int(item.get("address", "0"), 0), word))
                self.assertEqual([event_words(item) for item in result.events[:result.event_count]],
                                 expected_events)
                self.assertEqual(result.instructions, case["steps"])
                instructions += result.instructions
                events += result.event_count
        self.assertEqual((len(self.cases), instructions, events), (5, 182, 30))

    def test_all_versions_and_arbitrary_incoming_state(self):
        for normalized, branch, bit3, seed in itertools.product(NORMALIZED, (0, 0x10000),
                                                               (0, 8), range(32)):
            with self.subTest(normalized=normalized, branch=branch, bit3=bit3, seed=seed):
                call = Call(normalized | branch | bit3, seed=seed)
                if branch:
                    call.object("table").value = seed * 0x1020304
                self.run_call(call)

    def test_general_stack_locations_and_unaligned_host_bytes(self):
        for address, length, sp, lr in ((0, 8, 8, 8), (1, 15, 12, 0),
                                        (0xFFFFFFE0, 32, 0xFFFFFFFC, 0),
                                        (0x1000, 8, 0x1008, WORD_MAX - 1),
                                        (0x1001, 31, 0x1010, 0x1000)):
            for branch in (0, 0x10000):
                with self.subTest(address=address, branch=branch):
                    call = Call(NORMALIZED[0] | branch, address, length, sp, lr)
                    call.object("stack").bytes = ctypes.cast(call.storage["bytes"].address + 1,
                                                            ctypes.POINTER(ctypes.c_uint8))
                    self.run_call(call)

    def test_unsupported_versions_preserve_all_storage(self):
        rejected = {0, 1, WORD_MAX, 0x04000163, 0x04020162}
        for normalized in NORMALIZED:
            rejected.update(normalized ^ (1 << bit) for bit in range(32) if bit not in (3, 16))
        for version in sorted(rejected):
            if version & 0xFFFEFFF7 not in NORMALIZED:
                with self.subTest(version=version):
                    self.run_call(Call(version), UNSUPPORTED)

    def test_original_table_word_is_required_only_on_primary(self):
        call = Call()
        call.redirect("table", None)
        self.run_call(call, INVALID)
        for word in (0, 1, WORD_MAX, 0xCEC00DA1, 0xCEC00DA2):
            call = Call()
            call.object("table").value = word
            self.run_call(call, UNSUPPORTED)
            call = Call(NORMALIZED[0] | 0x10000)
            call.object("table").value = word
            self.run_call(call)
        call = Call(NORMALIZED[0] | 0x10000)
        call.redirect("table", None)
        self.run_call(call)
        call = Call()
        self.run_call(call)
        self.run_call(call, UNSUPPORTED)

    def test_missing_misaligned_and_wrapping_typed_objects(self):
        for name, kind in zip(Call.names, (Input, Stack, Word, Result)):
            for mode, status in (("null", INVALID), ("unaligned", INVALID), ("wrap", BOUNDS)):
                with self.subTest(name=name, mode=mode):
                    call = Call()
                    address = {"null": None, "unaligned": call.storage[name].address + 1,
                               "wrap": POINTER_MAX - ctypes.alignment(kind) + 1}[mode]
                    call.redirect(name, address)
                    self.run_call(call, status)

    def test_host_object_pairs_reject_full_and_partial_overlap(self):
        for branch in (0, 0x10000):
            for left, right in itertools.permutations(Call.names, 2):
                call = Call(NORMALIZED[0] | branch)
                right_kind = type(call.object(right))
                alignment = ctypes.alignment(right_kind)
                for offset in (0, alignment, -alignment):
                    with self.subTest(branch=branch, left=left, right=right, offset=offset):
                        call = Call(NORMALIZED[0] | branch)
                        call.redirect(right, call.storage[left].address + offset)
                        if (offset >= ctypes.sizeof(call.object(left))
                                or offset + ctypes.sizeof(right_kind) <= 0):
                            continue
                        self.run_call(call, OVERLAP)

    def test_full_declared_stack_bytes_reject_host_aliases(self):
        for branch, name in itertools.product((0, 0x10000), Call.names):
            for offset in (0, -4):
                with self.subTest(branch=branch, name=name, offset=offset):
                    call = Call(NORMALIZED[0] | branch)
                    call.object("stack").bytes = ctypes.cast(call.storage[name].address + offset,
                                                            ctypes.POINTER(ctypes.c_uint8))
                    self.run_call(call, OVERLAP)

    def test_adjacent_host_objects_are_allowed(self):
        for left, right in itertools.permutations(Call.names, 2):
            with self.subTest(left=left, right=right):
                call = Call()
                kind = type(call.object(right))
                alignment = ctypes.alignment(kind)
                address = call.storage[left].address + ctypes.sizeof(call.object(left))
                address = (address + alignment - 1) // alignment * alignment
                ctypes.memmove(address, ctypes.byref(call.object(right)), ctypes.sizeof(kind))
                call.redirect(right, address)
                self.run_call(call)

    def test_stack_storage_and_frame_bounds(self):
        for length in (0, 1, 7, 63):
            call = Call()
            call.object("stack").length = length
            self.run_call(call, BOUNDS)
        call = Call()
        call.object("stack").bytes = ctypes.POINTER(ctypes.c_uint8)()
        self.run_call(call, INVALID)
        call.object("stack").length = 0
        self.run_call(call, BOUNDS)
        call = Call()
        call.object("stack").bytes = ctypes.cast(POINTER_MAX - 31, ctypes.POINTER(ctypes.c_uint8))
        self.run_call(call, BOUNDS)
        if ctypes.sizeof(ctypes.c_size_t) > 4:
            call = Call()
            call.object("stack").length = 1 << 32
            self.run_call(call, BOUNDS)
        for sp in (0, 4, 7, 9, 0x24010001):
            call = Call()
            call.object("input").registers.sp = sp
            self.run_call(call, INVALID)
        for sp in (0x2400FFC0, 0x2400FFC4, 0x24010044):
            call = Call()
            call.object("input").registers.sp = sp
            self.run_call(call, BOUNDS)
        call = Call(address=0xFFFFFFE1, length=32, sp=0xFFFFFFFC, lr=0)
        self.run_call(call, BOUNDS)
        call = Call(lr=0x24040001)
        self.run_call(call, INVALID)
        for lr in (0x2400FFC0, 0x2400FFFE, 0x2401003E):
            self.run_call(Call(lr=lr), OVERLAP)

    def test_all_fixed_regions_exclude_the_whole_virtual_stack_and_lr(self):
        for branch, (address, length) in itertools.product((0, 0x10000), EXCLUDED):
            version = NORMALIZED[0] | branch
            for point in (address, address + length - 2):
                with self.subTest(branch=branch, lr=point):
                    self.run_call(Call(version, lr=point), OVERLAP)
            with self.subTest(branch=branch, span=address):
                self.run_call(Call(version, address=address - 12, length=20,
                                   sp=address & ~3, lr=0), OVERLAP)
                self.run_call(Call(version, address=address + length - 1, length=17,
                                   sp=(address + length + 15) & ~3, lr=0), OVERLAP)
            # Consecutive MMIO spans have no gap for an adjacent frame.
            if address not in (0x7EE0003C, 0x7EE00040):
                start = (address & ~3) - 8
                self.run_call(Call(version, address=start, length=address - start,
                                   sp=address & ~3, lr=0))
                end = address + length
                sp = (end + 11) & ~3
                self.run_call(Call(version, address=end, length=sp - end,
                                   sp=sp, lr=0))


if __name__ == "__main__":
    unittest.main()
