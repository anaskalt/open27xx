# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Replay boot-information contracts against the freestanding C helpers."""

import ctypes
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, INVALID, BOUNDS, OVERFLOW, ALLOCATION, OVERLAP = 0, -1, -2, -3, -4, -5
MAGIC = 0x45545342
REVISION = 0x52455642
TAGS = [0x4E4F4342, 0x45535047, 0x434D4D42, 0x4D545342, 0x4E545342,
        0x36565049, 0x454D564E, 0x52575042, 0x4B534452, 0x43545242,
        0x52445342, 0x43455342, 0x53545342, 0x42535542, REVISION]


class Buffer(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("length", ctypes.c_size_t)]


class State(ctypes.Structure):
    _fields_ = [("complete", ctypes.c_uint32), ("cache", Buffer * 15)]


Allocate = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t,
                           ctypes.c_size_t, ctypes.POINTER(Buffer))
Heap = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t,
                       ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                       ctypes.POINTER(Buffer))


class ZeroAllocator(ctypes.Structure):
    _fields_ = [("allocate", Heap), ("context", ctypes.c_void_p),
                ("caller_word", ctypes.c_uint32)]


class Memory:
    """Translate fixture addresses while keeping every supplied byte observable."""

    def __init__(self, regions):
        values = {}
        for region in regions:
            data = (bytes.fromhex(region["hex"]) if "hex" in region else
                    bytes.fromhex(region["fill"]) * region["size"])
            base = int(region["address"], 0)
            values.update((base + offset, byte) for offset, byte in enumerate(data))
        self.blocks = []
        for address in sorted(values):
            if not self.blocks or address != self.blocks[-1][0] + len(self.blocks[-1][1]):
                self.blocks.append((address, bytearray()))
            self.blocks[-1][1].append(values[address])
        self.blocks = [(base, bytearray(b"\x79") + data + b"\x83")
                       for base, data in self.blocks]
        self.arrays = [(ctypes.c_uint8 * len(data)).from_buffer(data) for _, data in self.blocks]

    def span(self, address):
        if not address:
            return Buffer()
        for (base, data), array in zip(self.blocks, self.arrays):
            if base <= address < base + len(data) - 2:
                offset = address - base
                return Buffer(ctypes.addressof(array) + 1 + offset, len(data) - 2 - offset)
        # Completion and cached-identity paths must not dereference absent backing.
        return Buffer(address, 0)

    def address(self, pointer):
        if not pointer:
            return 0
        for (base, data), array in zip(self.blocks, self.arrays):
            start = ctypes.addressof(array) + 1
            if start <= pointer < start + len(data) - 2:
                return base + pointer - start
        return pointer

    def snapshot(self):
        return {base + offset: byte for base, data in self.blocks
                for offset, byte in enumerate(data[1:-1])}

    def word(self, address):
        memory = self.snapshot()
        return int.from_bytes(bytes(memory[address + i] for i in range(4)), "little")

    def check_guards(self, test):
        for _, data in self.blocks:
            test.assertEqual((data[0], data[-1]), (0x79, 0x83))


def fixture(name):
    return json.loads((ROOT / "tests/vectors" / name).read_text())["cases"]


def records(tag=REVISION, declared=12, payload=b"", next_offset=0, total=None):
    child = struct.pack("<3I", tag, declared, next_offset) + payload
    return bytearray(struct.pack("<3I", MAGIC, total or 12 + len(child), 12) + child)


class BootInformationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Boot-information tests require a host C compiler; set CC")
        temporary = tempfile.TemporaryDirectory(prefix="open27xx-boot-info-")
        cls.addClassCleanup(temporary.cleanup)
        cls.compiler = compiler
        cls.temporary_path = Path(temporary.name)
        library = cls.temporary_path / "boot_info.so"
        command = compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-fPIC", "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/boot_info.c"), "-o", str(library),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"Boot-information compilation failed:\n{result.stdout}{result.stderr}")
        cls.library = ctypes.CDLL(str(library))
        cls.parse = cls.library.boot_info_parse
        cls.parse.argtypes = [ctypes.POINTER(State), ctypes.c_void_p, ctypes.c_size_t,
                              Allocate, ctypes.c_void_p]
        cls.parse.restype = ctypes.c_int
        cls.lookup = cls.library.boot_info_lookup
        cls.lookup.argtypes = cls.parse.argtypes + [ctypes.c_uint32, ctypes.POINTER(Buffer)]
        cls.lookup.restype = ctypes.c_int
        cls.zero = cls.library.boot_info_allocate_zeroed
        cls.zero.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                             ctypes.POINTER(Buffer)]
        cls.zero.restype = ctypes.c_int
        cls.prepare = cls.library.boot_info_prepare_pointer
        cls.prepare.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        cls.prepare.restype = ctypes.c_int
        cls.revision = cls.library.boot_info_fallback_revision
        cls.revision.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        cls.revision.restype = ctypes.c_uint32

    def assert_memory(self, case, memory, state=None):
        actual = memory.snapshot()
        if state is not None:
            gp = int(case["setup"]["registers"]["gp"], 0)
            outputs = [(gp + 0x171C, struct.pack("<I", state.complete)),
                       (gp + 0x1734, struct.pack("<15I", *[
                           memory.address(slot.data) for slot in state.cache]))]
            for base, data in outputs:
                actual.update((base + i, value) for i, value in enumerate(data))
        for region in case["expected"]["memory"]:
            expected = bytes.fromhex(region["hex"])
            base = int(region["address"], 0)
            self.assertEqual(bytes(actual[base + i] for i in range(len(expected))), expected,
                             f"observed region {base:#x}")
        memory.check_guards(self)

    def replay(self, case, composed=False):
        memory = Memory(case["setup"]["memory"])
        registers = case["setup"]["registers"]
        gp = int(registers["gp"], 0)
        state = State()
        state.complete = memory.word(gp + 0x171C)
        for index in range(15):
            state.cache[index] = memory.span(memory.word(gp + 0x1734 + 4 * index))
        source = memory.span(memory.word(gp - 0x2C))
        calls = []
        replies = [reply for stub in case["execution"]["stubs"] for reply in stub["replies"]]

        def allocate(context, count, size, result):
            reply = replies[len(calls)]
            calls.append([count, size])
            result[0] = memory.span(int(reply["registers"]["r0"], 0))
            return OK

        def heap(context, length, argument1, argument2, caller, result):
            reply = replies[len(calls)]
            calls.append([length, argument1, argument2, caller])
            result[0] = memory.span(int(reply["registers"]["r0"], 0))
            return OK

        allocator = Allocate(allocate)
        lower = Heap(heap)
        zero_context = ZeroAllocator(lower, None, 0)
        context = None
        if composed:
            # The caller word is an opaque supplied input to the portable wrapper.
            zero_context.caller_word = int(case["expected"]["events"][0]["arguments"][3], 0) & 0x7FFFFFFF
            allocator = Allocate(("boot_info_allocate_zeroed", self.library))
            context = ctypes.byref(zero_context)
        entry = int(case["function"]["entry"], 0)
        output = Buffer()
        if entry == 0x0EC6246E:
            status = self.lookup(ctypes.byref(state), source.data, source.length, allocator,
                                 context, REVISION, ctypes.byref(output))
            word = (int.from_bytes(ctypes.string_at(output.data + 0x68, 4), "little")
                    if output.data else 0)
            self.assertEqual(self.revision(bool(output.data), word),
                             int(case["expected"]["registers"]["r6"], 0))
        elif entry == 0x0EC642FC:
            status = self.lookup(ctypes.byref(state), source.data, source.length, allocator,
                                 context, int(registers["r0"], 0), ctypes.byref(output))
            self.assertEqual(memory.address(output.data), int(case["expected"]["registers"]["r0"], 0))
        else:
            self.assertEqual(entry, 0x0EC644E0)
            status = self.parse(ctypes.byref(state), source.data, source.length, allocator, context)
        self.assertEqual(status, OK)
        self.assert_memory(case, memory, state)
        events = case["expected"]["events"]
        self.assertEqual(len(calls), len(events))
        for index, (call, event) in enumerate(zip(calls, events)):
            self.assertEqual(event["kind"], "stub")
            self.assertEqual(int(event["entry"], 0), 0x0ED64EBC if composed else 0x0EC731F6)
            self.assertEqual(event["reply_index"], index)
            # Only the documented arguments are part of the portable callback ABI.
            self.assertEqual(call, [int(value, 0) for value in event["arguments"][:len(call)]])
        abi_registers = {"sp", "r1", "r6"} if entry == 0x0EC6246E else {"sp", "r0"}
        self.assertEqual(set(case["expected"]["registers"]) - abi_registers, set())

    def test_recorded_parser_and_lookup(self):
        names = ("boot-information.json", "boot-information-lookup.json",
                 "boot-information-revision.json")
        cases = [case for name in names for case in fixture("start4/" + name)]
        self.assertEqual(len(cases), 115)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay(case)

    def test_recorded_zeroing_allocation(self):
        for case in fixture("start4/boot-information-allocation.json"):
            with self.subTest(case=case["id"]):
                if int(case["function"]["entry"], 0) == 0x0EC644E0:
                    self.replay(case, composed=True)
                    continue
                memory = Memory(case["setup"]["memory"])
                calls = []

                def heap(context, length, argument1, argument2, caller, result,
                         calls=calls, case=case, memory=memory):
                    calls.append([length, argument1, argument2, caller])
                    reply = case["execution"]["stubs"][0]["replies"][0]
                    result[0] = memory.span(int(reply["registers"]["r0"], 0))
                    return OK

                allocator = ZeroAllocator(Heap(heap), None, int(case["execution"]["return_address"], 0))
                output = Buffer()
                registers = case["setup"]["registers"]
                self.assertEqual(self.zero(ctypes.byref(allocator), int(registers["r0"], 0),
                                           int(registers["r1"], 0), ctypes.byref(output)), OK)
                self.assertEqual(memory.address(output.data), int(case["expected"]["registers"]["r0"], 0))
                self.assertEqual(calls, [[int(value, 0) for value in event["arguments"][:4]]
                                        for event in case["expected"]["events"]])
                self.assertEqual(len(calls), 1)
                self.assert_memory(case, memory)

    def test_recorded_pointer_preparation(self):
        for case in fixture("bootmain/boot-information-pointer.json"):
            with self.subTest(case=case["id"]):
                memory = Memory(case["setup"]["memory"])
                section = memory.span(int(case["setup"]["registers"]["r0"], 0))
                self.assertEqual(self.prepare(section.data, section.length), OK)
                self.assert_memory(case, memory)
                self.assertEqual(case["expected"]["events"], [])

    def parse_data(self, data, state=None, allocation_length=200, pointer=None):
        state = State() if state is None else state
        memory = Memory([{"address": "0x24000000", "hex": bytes(data).hex()},
                         {"address": "0x24040000", "size": 224, "fill": "a5"}])
        calls = []

        def allocate(context, count, size, result):
            calls.append((count, size))
            result[0] = memory.span(0x24040000 if pointer is None else pointer)
            result[0].length = allocation_length
            return OK

        source = memory.span(0x24000000)
        status = self.parse(ctypes.byref(state), source.data, len(data), Allocate(allocate), None)
        return status, state, memory, calls

    def test_missing_backing_before_callback(self):
        inputs = [b"\0" * size for size in range(4)]
        inputs += [struct.pack("<I", MAGIC) + b"\0" * size for size in range(4)]
        inputs += [struct.pack("<2I", MAGIC, 12) + b"\0" * size for size in range(4)]
        inputs += [records(declared=164)]
        for data in inputs:
            with self.subTest(data=data.hex()):
                status, state, memory, calls = self.parse_data(data)
                self.assertEqual(status, BOUNDS)
                self.assertEqual(state.complete, 0)
                self.assertFalse(any(slot.data for slot in state.cache))
                self.assertEqual(calls, [])
                memory.check_guards(self)

    def test_failed_short_and_overlapping_allocation(self):
        for pointer, length, expected in ((0, 200, ALLOCATION), (None, 163, BOUNDS),
                                          (0x24000000, 24, BOUNDS),
                                          (0x24000000, 200, OVERLAP)):
            with self.subTest(pointer=pointer, length=length):
                data = records()
                status, state, memory, calls = self.parse_data(data, allocation_length=length,
                                                               pointer=pointer)
                self.assertEqual(status, expected)
                self.assertEqual(state.complete, 0)
                self.assertFalse(any(slot.data for slot in state.cache))
                self.assertEqual(calls, [(1, 164)])
                self.assertEqual(bytes(memory.snapshot()[0x24000000 + i]
                                       for i in range(len(data))), data)
                memory.check_guards(self)

    def test_completion_and_cached_identity_survive_source_changes(self):
        status, state, memory, calls = self.parse_data(records())
        self.assertEqual(status, OK)
        pointer = state.cache[14].data
        expected = memory.snapshot()
        for complete in (1, 2, 0x80000000, 0xFFFFFFFF):
            state.complete = complete
            output = Buffer()
            self.assertEqual(self.lookup(ctypes.byref(state), 1, 0, Allocate(), None,
                                         REVISION, ctypes.byref(output)), OK)
            self.assertEqual(output.data, pointer)
            self.assertEqual(state.complete, complete)
            self.assertEqual(memory.snapshot(), expected)
        self.assertEqual(calls, [(1, 164)])
        state.complete = 0
        self.assertEqual(self.parse(ctypes.byref(state), None, 123, Allocate(), None), OK)
        self.assertEqual(state.complete, 0)
        self.assertEqual(state.cache[14].data, pointer)

    def test_lookup_hides_cached_pointer_until_complete(self):
        state = State()
        state.cache[14] = Buffer(1, 164)
        output = Buffer(2, 10)
        self.assertEqual(self.lookup(ctypes.byref(state), None, 0, Allocate(), None,
                                     REVISION, ctypes.byref(output)), OK)
        self.assertFalse(output.data)
        self.assertEqual(state.cache[14].data, 1)
        self.assertEqual(state.complete, 0)
        data = struct.pack("<2I", MAGIC, 32769)
        source = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        self.assertEqual(self.lookup(ctypes.byref(state), ctypes.addressof(source), len(data),
                                     Allocate(), None, REVISION, ctypes.byref(output)), OK)
        self.assertFalse(output.data)
        self.assertEqual(state.cache[14].data, 1)
        self.assertEqual(state.complete, 0)

    def test_lookup_rejects_output_inside_state(self):
        state = State()
        state.complete = 1
        state.cache[14] = Buffer(1, 164)
        expected = bytes(state)
        self.assertEqual(self.lookup(ctypes.byref(state), None, 0, Allocate(), None,
                                     REVISION, ctypes.byref(state.cache[14])), OVERLAP)
        self.assertEqual(bytes(state), expected)

    def test_revision_mask_and_absence(self):
        for present in (0, 1, 0xFFFFFFFF):
            for ignored in (0, 1, 0x80000000, 0xFFFFFFF9):
                for mask, expected in ((0, 0xA03110), (2, 0xA03114),
                                       (4, 0xC031C0), (6, 0xA03115)):
                    self.assertEqual(self.revision(present, ignored | mask),
                                     expected if present else 0xA03110)

    def test_partial_cache_survives_failure_and_retry(self):
        data = bytearray(struct.pack("<3I", MAGIC, 40, 12)
                         + struct.pack("<4I", TAGS[0], 16, 16, 0x12345678)
                         + struct.pack("<3I", REVISION, 164, 0))
        source = (ctypes.c_uint8 * len(data)).from_buffer(data)
        destinations = [(ctypes.c_uint8 * 200)(*([0xA5] * 200)) for _ in range(2)]
        state = State()
        calls = []

        def allocate(context, count, size, result):
            result[0] = Buffer(ctypes.addressof(destinations[len(calls)]), 200)
            calls.append((count, size))
            return OK

        callback = Allocate(allocate)
        self.assertEqual(self.parse(ctypes.byref(state), ctypes.addressof(source), len(data),
                                    callback, None), BOUNDS)
        self.assertEqual(state.complete, 0)
        first = state.cache[0].data
        self.assertTrue(first)
        self.assertFalse(state.cache[14].data)
        self.assertEqual(calls, [(1, 16)])
        preserved = bytes(destinations[0])
        struct.pack_into("<I", data, 24, 0xFFFFFFFF)
        struct.pack_into("<I", data, 32, 12)
        self.assertEqual(self.parse(ctypes.byref(state), ctypes.addressof(source), len(data),
                                    callback, None), OK)
        self.assertEqual(state.complete, 1)
        self.assertEqual(state.cache[0].data, first)
        self.assertEqual(state.cache[0].length, 16)
        self.assertEqual(bytes(destinations[0]), preserved)
        self.assertEqual(calls, [(1, 16), (1, 164)])
        self.assertEqual(state.cache[14].data, ctypes.addressof(destinations[1]))

    def test_reused_allocation_is_rejected_before_second_copy(self):
        data = bytearray(struct.pack("<3I", MAGIC, 40, 12)
                         + struct.pack("<4I", TAGS[0], 16, 16, 0x12345678)
                         + struct.pack("<3I", REVISION, 12, 0))
        status, state, memory, calls = self.parse_data(data)
        self.assertEqual(status, OVERLAP)
        self.assertEqual(state.complete, 0)
        self.assertTrue(state.cache[0].data)
        self.assertFalse(state.cache[14].data)
        self.assertEqual(calls, [(1, 16), (1, 164)])
        self.assertEqual(ctypes.string_at(state.cache[0].data, 16), data[12:28])
        memory.check_guards(self)

    def test_host_invalid_arguments_and_address_overflow(self):
        state = State()
        output = Buffer()
        maximum = ctypes.c_size_t(-1).value
        self.assertEqual(self.parse(None, None, 0, Allocate(), None), INVALID)
        self.assertEqual(self.lookup(ctypes.byref(state), None, 0, Allocate(), None,
                                     REVISION, None), INVALID)
        self.assertEqual(self.lookup(None, None, 0, Allocate(), None,
                                     REVISION, ctypes.byref(output)), INVALID)
        self.assertFalse(output.data)
        self.assertEqual(self.parse(ctypes.byref(state), maximum - 1, 4,
                                    Allocate(), None), OVERFLOW)
        self.assertEqual(self.prepare(maximum - 1, 8), OVERFLOW)
        self.assertEqual(self.parse(ctypes.byref(state), ctypes.addressof(state),
                                    ctypes.sizeof(state), Allocate(), None), OVERLAP)

    def test_zero_wrapper_host_failures(self):
        data = (ctypes.c_uint8 * 32)(*([0xA5] * 32))
        calls = []

        def heap(context, length, a1, a2, caller, output):
            calls.append((length, a1, a2, caller))
            output[0] = Buffer(ctypes.addressof(data), 16)
            return OK

        allocator = ZeroAllocator(Heap(heap), None, 0xFFFFFFFF)
        result = Buffer(1, 1)
        maximum = ctypes.c_size_t(-1).value
        self.assertEqual(self.zero(ctypes.byref(allocator), maximum, 2, ctypes.byref(result)), OVERFLOW)
        self.assertEqual(calls, [])
        self.assertFalse(result.data)
        self.assertEqual(self.zero(ctypes.byref(allocator), 1, 17, ctypes.byref(result)), BOUNDS)
        self.assertFalse(result.data)
        self.assertEqual(bytes(data), b"\xA5" * 32)
        self.assertEqual(calls, [(17, 32, 1, 0xFFFFFFFF)])
        self.assertEqual(self.zero(None, 1, 1, ctypes.byref(result)), INVALID)
        self.assertEqual(self.zero(ctypes.byref(allocator), 1, 1, None), INVALID)

    def test_native_exact_allocation_bounds(self):
        executable = self.temporary_path / "boot_info_safety"
        flags = ["-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-pedantic"]
        if os.environ.get("OPEN27XX_SANITIZERS") == "1":
            flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                      "-fno-omit-frame-pointer"]
        command = self.compiler + flags + [str(ROOT / "tests/boot_info_safety.c"),
                                          str(ROOT / "src/start4/boot_info.c"),
                                          "-o", str(executable)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run([str(executable)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pointer_bounds_and_unaligned_storage(self):
        for offset in range(8):
            for length in range(12):
                data = bytearray(b"\xA5" * 32)
                struct.pack_into("<2I", data, offset, 0x41545342, 0xFFFFFFFF)
                expected = data.copy()
                array = (ctypes.c_uint8 * len(data)).from_buffer(data)
                status = self.prepare(ctypes.addressof(array) + offset, length)
                if length < 8:
                    self.assertEqual(status, BOUNDS)
                else:
                    self.assertEqual(status, OK)
                    struct.pack_into("<I", expected, offset + 4, 0x40000)
                self.assertEqual(data, expected)
        self.assertEqual(self.prepare(None, 0), OK)
        self.assertEqual(self.prepare(None, ctypes.c_size_t(-1).value), OK)


if __name__ == "__main__":
    unittest.main()
