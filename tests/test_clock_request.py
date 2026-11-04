# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare fixed clock requests, initialization and repeated state with fixtures."""

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
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
ACQUIRE, DIAGNOSTIC, SOURCE, CLOCK, DIVIDER, NOTIFY, RELEASE = range(7)
MANAGER_BYTES, MISS_BYTES, SENTINEL = 1156, 86, 0xA5A5A5A5
TABLE, HANDLE, REFERENCE, SOURCE_RATE = 4, 8, 0x24, 0x44
DIVIDER_RATE, COUNT, REQUESTED, NOTIFICATIONS = 0x11C, 0x188, 0x334, 0x464
Word = ctypes.c_uint32
Byte = ctypes.c_uint8
BytePointer = ctypes.POINTER(Byte)
WordPointer = ctypes.POINTER(Word)
Provider = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, Word,
                           WordPointer, ctypes.c_size_t, Word)
OpenProvider = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, Word, BytePointer, Word, Word)


class State(ctypes.Structure):
    _fields_ = [("initialized", Word), ("descriptor_miss", Byte * MISS_BYTES),
                ("divider_miss", Word), ("source_miss", Word)]


class Inputs(ctypes.Structure):
    _fields_ = [("identifier", Word), ("requested", ctypes.c_uint64),
                ("argument3", Word), ("argument4", Word), ("skip", Word),
                ("selection", Word), ("comparison_handle", Word),
                ("override_heads", Word * 3), ("planner_input", Word),
                ("mutex_identity", Word)]


class Plan(ctypes.Structure):
    _fields_ = [(name, Provider) for name in
                ("acquire", "diagnostic", "source", "clock", "divider", "notify", "release")]
    _fields_ += [("context", ctypes.c_void_p), ("source_reply", Word), ("clock_reply", Word),
                 ("divider_replies", Word * 2), ("notification_replies", Word * 2)]


class OpenPlan(ctypes.Structure):
    _fields_ = [("open", OpenProvider), ("context", ctypes.c_void_p),
                ("reply", Word), ("handle_write", Word)]


def guarded(value):
    class Guarded(ctypes.Structure):
        _fields_ = [("before", ctypes.c_uint64), ("value", type(value)),
                    ("after", ctypes.c_uint64)]
    return Guarded(0x713AC924713AC924, value, 0x57DDEF8357DDEF83)


def fixture_bytes(case, phase, address, length):
    for region in case[phase]["memory"]:
        start = int(region["address"], 0)
        raw = (bytes.fromhex(region["hex"]) if "hex" in region
               else bytes.fromhex(region["fill"]) * region["size"])
        if start <= address and address + length <= start + len(raw):
            return raw[address - start:address - start + length]
    raise AssertionError(f"missing fixture extent {address:#x}+{length}")


def fixture_word(case, phase, address):
    return int.from_bytes(fixture_bytes(case, phase, address, 4), "little")


class Request:
    def __init__(self):
        self.manager_storage = guarded((Byte * (MANAGER_BYTES + 16))())
        self.manager = self.manager_storage.value
        self.manager[MANAGER_BYTES:] = b"\x5a" * 16
        self.put(TABLE, 0x0EDE7F04, 4)
        self.put(HANDLE, 0xC10C1234, 4)
        self.put(REQUESTED, 500000000)
        self.state_storage = guarded(State())
        self.state = self.state_storage.value
        self.state.initialized = 1
        self.output_storage = (Byte * 48)(*([0xA5] * 48))
        self.output = ctypes.cast(ctypes.byref(self.output_storage, 16), BytePointer)
        self.raw_storage = guarded(Word(SENTINEL))
        self.raw = self.raw_storage.value
        self.inputs = Inputs(0x30, 600000000, 0, 0, 0, 1, 0xC10C1234,
                             (Word * 3)(), 1200, 0xE403E810)
        self.calls, self.snapshots, self.contexts = [], [], []
        self.bookkeeping = Word()
        self.provider = Provider(self.observe)
        self.open_provider = OpenProvider(self.observe_open)
        self.plan = Plan()
        for name in ("acquire", "diagnostic", "source", "clock", "divider", "release"):
            setattr(self.plan, name, self.provider)
        self.plan.context = ctypes.addressof(self.bookkeeping)
        self.open_plan = OpenPlan(self.open_provider, ctypes.addressof(self.bookkeeping),
                                  0, 0xC10C1234)

    def put(self, offset, value, size=8):
        self.manager[offset:offset + size] = value.to_bytes(size, "little")

    def get(self, offset, size=8):
        return int.from_bytes(bytes(self.manager[offset:offset + size]), "little")

    def snapshot(self):
        return (bytes(self.manager), bytes(self.state), bytes(self.output_storage),
                bytes(self.raw_storage))

    def observe(self, context, kind, identity, arguments, count, reply):
        self.calls.append((kind, identity, list(arguments[:count]), reply))
        self.contexts.append(context)
        self.snapshots.append(self.snapshot())
        self.bookkeeping.value += 1

    def observe_open(self, context, table, argument, handle_output, reply, handle_write):
        self.calls.append((table, argument, ctypes.addressof(handle_output.contents),
                           reply, handle_write))
        self.contexts.append(context)
        self.snapshots.append(self.snapshot())
        self.bookkeeping.value += 1

    def arguments(self):
        return [ctypes.byref(self.inputs), self.manager, len(self.manager),
                ctypes.byref(self.state), self.output, 8, ctypes.byref(self.plan),
                ctypes.cast(ctypes.byref(self.raw_storage, type(self.raw_storage).value.offset), WordPointer)]

    def init_arguments(self):
        return [1, 0x0EDE7F04, self.manager, len(self.manager), ctypes.byref(self.state),
                ctypes.byref(self.open_plan),
                ctypes.cast(ctypes.byref(self.raw_storage, type(self.raw_storage).value.offset), WordPointer)]

    def cold_arguments(self):
        arguments = self.arguments()
        return [arguments[0], 0x0EDE7F04, *arguments[1:6],
                ctypes.byref(self.open_plan), *arguments[6:]]

    def fresh_outputs(self):
        self.output_storage = (Byte * 48)(*([0xA5] * 48))
        self.output = ctypes.cast(ctypes.byref(self.output_storage, 16), BytePointer)
        self.raw_storage = guarded(Word(SENTINEL))
        self.calls.clear()
        self.snapshots.clear()
        self.contexts.clear()
        self.bookkeeping.value = 0

    def storage(self):
        return tuple(bytes(value) for value in (self.manager_storage, self.state_storage,
                     self.output_storage, self.raw_storage, self.inputs, self.plan, self.open_plan))

    def notify(self, pre=0, post=7):
        self.manager[NOTIFICATIONS] = 0x30
        self.put(NOTIFICATIONS + 4, 0x24030000, 4)
        self.plan.notify = self.provider
        self.plan.notification_replies[:] = pre, post


class ClockRequestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Clock-request tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="clock-request-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "clock_request.so"
        subprocess.run(compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/clock_request.c"), "-o", str(library),
        ], check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.execute = cls.library.clock_request_execute
        cls.execute.argtypes = [ctypes.POINTER(Inputs), BytePointer, ctypes.c_size_t,
                               ctypes.POINTER(State), BytePointer, ctypes.c_size_t,
                               ctypes.POINTER(Plan), WordPointer]
        cls.execute.restype = ctypes.c_int
        cls.initialize = cls.library.clock_request_initialize
        cls.initialize.argtypes = [Word, Word, BytePointer, ctypes.c_size_t,
                                  ctypes.POINTER(State), ctypes.POINTER(OpenPlan), WordPointer]
        cls.initialize.restype = ctypes.c_int
        cls.execute_cold = cls.library.clock_request_execute_cold
        cls.execute_cold.argtypes = [ctypes.POINTER(Inputs), Word, BytePointer, ctypes.c_size_t,
                                    ctypes.POINTER(State), BytePointer, ctypes.c_size_t,
                                    ctypes.POINTER(OpenPlan), ctypes.POINTER(Plan), WordPointer]
        cls.execute_cold.restype = ctypes.c_int
        cls.cases = json.loads((ROOT / "tests/vectors/start4/clock-request.json")
                               .read_text())["cases"]
        cls.state_cases = json.loads((ROOT / "tests/vectors/start4/clock-request-state.json")
                                     .read_text())["cases"]

    def run_request(self, request, status=OK, arguments=None, initialize=False, cold=False):
        before = request.storage()
        function = self.execute_cold if cold else self.initialize if initialize else self.execute
        if arguments is None:
            arguments = (request.cold_arguments() if cold else request.init_arguments()
                         if initialize else request.arguments())
        self.assertEqual(function(*arguments), status)
        if status != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.calls, [])
        else:
            self.assertEqual(request.storage()[4:], before[4:])
        self.assertEqual(request.contexts,
                         [ctypes.addressof(request.bookkeeping)] * len(request.calls))
        self.assertEqual(request.bookkeeping.value, len(request.calls))
        for storage in (request.manager_storage, request.state_storage, request.raw_storage):
            self.assertEqual((storage.before, storage.after),
                             (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        self.assertEqual(bytes(request.manager[MANAGER_BYTES:]), b"\x5a" * 16)
        self.assertEqual(bytes(request.output_storage[:16]), b"\xa5" * 16)
        self.assertEqual(bytes(request.output_storage[24:]), b"\xa5" * 24)

    def fixture_request(self, case):
        request = Request()
        gp = int(case["setup"]["registers"]["gp"], 0)
        request.manager[:MANAGER_BYTES] = fixture_bytes(case, "setup", gp + 0x3E810, MANAGER_BYTES)
        request.state.initialized = fixture_word(case, "setup", gp + 0x184C)
        if case["function"]["entry"] == "0x0EC7E764":
            stub = case["execution"]["stubs"][0]
            reply = stub["replies"][0]
            request.open_plan.reply = int(reply["registers"]["r0"], 0)
            request.open_plan.handle_write = int.from_bytes(
                bytes.fromhex(reply["memory"][0]["hex"]), "little")
            return request
        registers = case["setup"]["registers"]
        request.inputs.identifier = int(registers["r0"], 0)
        request.inputs.requested = int(registers["r1"], 0) | int(registers["r2"], 0) << 32
        request.inputs.argument3 = int(registers["r3"], 0)
        request.inputs.argument4 = int(registers["r4"], 0)
        request.inputs.skip = fixture_word(case, "setup", gp + 0xD33F8)
        request.inputs.selection = fixture_word(case, "setup", gp + 0x1564)
        request.inputs.comparison_handle = fixture_word(case, "setup", gp + 0x3E494)
        request.inputs.planner_input = fixture_word(case, "setup", gp + 0x3B938)
        request.inputs.mutex_identity = gp + 0x3E810
        for index, offset in enumerate((0xD1B80, 0xD1B7C, 0xD1B78)):
            request.inputs.override_heads[index] = fixture_word(case, "setup", gp + offset)
        request.state.descriptor_miss[:] = fixture_bytes(case, "setup", gp + 0xD1B88, MISS_BYTES)
        request.state.divider_miss = fixture_word(case, "setup", gp + 0xD1BE4)
        request.state.source_miss = fixture_word(case, "setup", gp + 0xD1BE0)
        request.output_storage[:] = fixture_bytes(case, "setup", 0x24020000, 48)
        for field, *_ in Plan._fields_[:7]:
            setattr(request.plan, field, Provider())
        fields = {0x0ED64D02: "acquire", 0x0ED17442: "diagnostic", 0x0EC7D978: "source",
                  0x0EC7C7D0: "clock", 0x0EC7D5EA: "divider", 0x24030000: "notify",
                  0x0ED64D3A: "release"}
        for stub in case["execution"]["stubs"]:
            if int(stub["entry"], 0) == 0x0EC7B978:
                reply = stub["replies"][0]
                request.open_plan.reply = int(reply["registers"]["r0"], 0)
                request.open_plan.handle_write = int.from_bytes(
                    bytes.fromhex(reply["memory"][0]["hex"]), "little")
                continue
            field = fields[int(stub["entry"], 0)]
            setattr(request.plan, field, request.provider)
            for index, reply in enumerate(stub["replies"]):
                self.assertEqual(reply["memory"], [])
                word = int(reply["registers"]["r0"], 0)
                if field in ("source", "clock"):
                    setattr(request.plan, field + "_reply", word)
                elif field == "divider":
                    request.plan.divider_replies[index] = word
                elif field == "notify":
                    request.plan.notification_replies[index] = word
                else:
                    self.assertEqual(word, 0)
        return request

    def test_recorded_cases(self):
        self.assertEqual(len(self.cases), 12)
        self.assertEqual(len(self.state_cases), 4)
        for case in self.cases + self.state_cases:
            with self.subTest(case=case["id"]):
                request = self.fixture_request(case)
                initialize = case["function"]["entry"] == "0x0EC7E764"
                cold = not initialize and request.state.initialized == 0
                self.run_request(request, initialize=initialize, cold=cold)
                self.assertEqual(request.raw_storage.value,
                                 int(case["expected"]["registers"]["r0"], 0))
                gp = int(case["setup"]["registers"]["gp"], 0)
                self.assertEqual(bytes(request.manager[:MANAGER_BYTES]),
                                 fixture_bytes(case, "expected", gp + 0x3E810, MANAGER_BYTES))
                expected_flag = (fixture_word(case, "expected", gp + 0x184C)
                                 if initialize or case in self.state_cases else 1)
                self.assertEqual(request.state.initialized, expected_flag)
                if initialize:
                    self.assertEqual(request.calls, [(0x0EDE7F04, 0,
                                     ctypes.addressof(request.manager) + 8,
                                     request.open_plan.reply, request.open_plan.handle_write)])
                else:
                    self.assertEqual(bytes(request.output_storage),
                                     fixture_bytes(case, "expected", 0x24020000, 48))
                    self.assertEqual(bytes(request.state.descriptor_miss),
                                     fixture_bytes(case, "expected", gp + 0xD1B88, MISS_BYTES))
                    self.assertEqual(request.state.divider_miss,
                                     fixture_word(case, "expected", gp + 0xD1BE4))
                    self.assertEqual(request.state.source_miss,
                                     fixture_word(case, "expected", gp + 0xD1BE0))
                    self.assert_fixture_calls(case, request)

    def assert_fixture_calls(self, case, request):
        mapping = {0x0ED64D02: (ACQUIRE, 1), 0x0ED17442: (DIAGNOSTIC, 6),
                   0x0EC7D978: (SOURCE, 4), 0x0EC7C7D0: (CLOCK, 6),
                   0x0EC7D5EA: (DIVIDER, 3), 0x24030000: (NOTIFY, 4),
                   0x0ED64D3A: (RELEASE, 1)}
        replies = {int(stub["entry"], 0): stub["replies"] for stub in case["execution"]["stubs"]}
        expected = []
        for event in case["expected"]["events"]:
            identity = int(event["entry"], 0)
            reply = int(replies[identity][event["reply_index"]]["registers"]["r0"], 0)
            if identity == 0x0EC7B978:
                expected.append((0x0EDE7F04, 0, ctypes.addressof(request.manager) + HANDLE,
                                 reply, request.open_plan.handle_write))
                continue
            kind, count = mapping[identity]
            arguments = [int(v, 0) for v in event["arguments"][:count]]
            if kind == DIAGNOSTIC:
                arguments.append(0)
            expected.append((kind, identity, arguments, reply))
        self.assertEqual(request.calls, expected)

    def test_null_arguments(self):
        for initialize, indexes in ((False, (0, 1, 3, 4, 6, 7)), (True, (2, 4, 5, 6))):
            for index in indexes:
                with self.subTest(initialize=initialize, index=index):
                    request = Request()
                    request.state.initialized = 0 if initialize else 1
                    args = request.init_arguments() if initialize else request.arguments()
                    args[index] = None
                    self.run_request(request, INVALID, args, initialize)

    def test_short_and_wrapped_buffers(self):
        maximum = ctypes.c_size_t(-1).value
        for initialize, pointer, length, required in (
                (False, 1, 2, MANAGER_BYTES), (False, 4, 5, 8), (True, 2, 3, MANAGER_BYTES)):
            for size in (0, required - 1, maximum):
                request = Request()
                request.state.initialized = 0 if initialize else 1
                args = request.init_arguments() if initialize else request.arguments()
                args[length] = size
                self.run_request(request, INVALID if size == maximum else BOUNDS, args, initialize)
            request = Request()
            request.state.initialized = 0 if initialize else 1
            args = request.init_arguments() if initialize else request.arguments()
            args[pointer] = ctypes.cast(maximum - required + 1, BytePointer)
            args[length] = required
            self.run_request(request, INVALID, args, initialize)

    def test_overlapping_objects(self):
        for initialize, indexes, types in (
                (False, (0, 1, 3, 4, 6, 7),
                 (Inputs, Byte, State, Byte, Plan, Word)),
                (True, (2, 4, 5, 6), (Byte, State, OpenPlan, Word))):
            for left, right in itertools.combinations(range(len(indexes)), 2):
                request = Request()
                request.state.initialized = 0 if initialize else 1
                args = request.init_arguments() if initialize else request.arguments()
                args[indexes[right]] = ctypes.cast(args[indexes[left]], ctypes.POINTER(types[right]))
                self.run_request(request, OVERLAP, args, initialize)

    def test_unsupported_inputs_preserve_state(self):
        changes = [(name, value) for name, value in (
            ("identifier", 0x31), ("requested", 600000001), ("requested", (1 << 32) + 600000000),
            ("argument3", 1), ("argument4", 1), ("skip", 2), ("selection", 0),
            ("comparison_handle", 0), ("planner_input", 1400))]
        for name, value in changes:
            with self.subTest(name=name, value=value):
                request = Request()
                setattr(request.inputs, name, value)
                self.run_request(request, UNSUPPORTED)
        for index in range(3):
            request = Request()
            request.inputs.override_heads[index] = 1
            self.run_request(request, UNSUPPORTED)
        for field in ("initialized", "divider_miss", "source_miss"):
            request = Request()
            setattr(request.state, field, 2)
            self.run_request(request, UNSUPPORTED)
        for index in (0, 0x30, 85):
            request = Request()
            request.state.descriptor_miss[index] = 1
            self.run_request(request, UNSUPPORTED)
        for offset, value, size in ((TABLE, 0, 4), (HANDLE, 0, 4), (COUNT, 2, 4),
                                    (REQUESTED, 600000000, 8), (SOURCE_RATE, 1 << 32, 8),
                                    (DIVIDER_RATE, 1 << 32, 8)):
            request = Request()
            request.put(offset, value, size)
            self.run_request(request, UNSUPPORTED)

    def test_only_recorded_profile_combinations(self):
        for source, divider in ((0, 1), (1000000000, 0), (2000000000, 250000000),
                                (1200000000, 600000000)):
            request = Request()
            request.put(SOURCE_RATE, source)
            request.put(DIVIDER_RATE, divider)
            self.run_request(request, UNSUPPORTED)
        for change in ("planner", "notification", "reply", "skip"):
            request = Request()
            request.put(SOURCE_RATE, 1000000000)
            request.put(DIVIDER_RATE, 250000000)
            if change == "planner":
                request.inputs.planner_input = 1500
            elif change == "notification":
                request.notify()
            elif change == "reply":
                request.plan.divider_replies[1] = 0xFFFFFFFF
            else:
                request.inputs.skip = 1
            self.run_request(request, UNSUPPORTED)
        for replies in ((0, 0), (1, 7), (0, 0xFFFFFFFF)):
            request = Request()
            request.notify(*replies)
            self.run_request(request, UNSUPPORTED)
        for field in ("source_reply", "clock_reply"):
            request = Request()
            setattr(request.plan, field, 0xFFFFFFFF)
            self.run_request(request, UNSUPPORTED)
        for index in range(4):
            request = Request()
            request.put(NOTIFICATIONS + index * 8 + 4, 1, 4)
            self.run_request(request, UNSUPPORTED)
        request = Request()
        request.notify()
        request.manager[NOTIFICATIONS] = 0x31
        self.run_request(request, UNSUPPORTED)

    def test_reachable_providers_only(self):
        for name in ("acquire", "diagnostic", "source", "clock", "divider", "release"):
            request = Request()
            setattr(request.plan, name, Provider())
            self.run_request(request, INVALID)
        for name in ("notify", "source", "clock", "divider", "release"):
            request = Request()
            request.notify()
            setattr(request.plan, name, Provider())
            self.run_request(request, INVALID)
        for skip in (1, 0xFFFFFFFF):
            request = Request()
            request.inputs.skip = skip
            request.plan = Plan()
            before = request.snapshot()
            self.run_request(request)
            self.assertEqual(request.snapshot()[:3], before[:3])
            self.assertEqual(request.calls, [])
            self.assertEqual(request.raw_storage.value, 0x30)
        request = Request()
        request.notify(7, 0x12345678)
        request.plan.source = request.plan.clock = request.plan.divider = Provider()
        request.plan.source_reply = request.plan.clock_reply = 0x12345678
        request.plan.divider_replies[:] = 0x12345678, 0x87654321
        self.run_request(request)
        self.assertEqual(request.raw_storage.value, 500000000)
        request = Request()
        request.put(SOURCE_RATE, 1200000000)
        request.put(DIVIDER_RATE, 300000000)
        request.plan.source = Provider()
        request.plan.source_reply = 0x12345678
        request.plan.divider_replies[1] = 0x87654321
        self.run_request(request)

    def test_cold_initializer_preflight(self):
        for selection, table, flag, reply, handle, status in (
                (0, 1, 0, 0, 0xC10C1234, UNSUPPORTED),
                (1, 0, 0, 0, 0xC10C1234, UNSUPPORTED),
                (1, 1, 1, 0, 0xC10C1234, UNSUPPORTED),
                (1, 1, 0, 0, 0, UNSUPPORTED),
                (1, 1, 0, 7, 0xC10C1234, UNSUPPORTED),
                (1, 1, 0, 1, 0, UNSUPPORTED)):
            request = Request()
            request.state.initialized = flag
            request.open_plan.reply, request.open_plan.handle_write = reply, handle
            args = request.init_arguments()
            args[0], args[1] = selection, table
            self.run_request(request, status, args, True)
        request = Request()
        request.state.initialized = 0
        request.open_plan.open = OpenProvider()
        self.run_request(request, INVALID, initialize=True)

    def test_cold_initializer_visibility(self):
        for reply, handle in ((0, 0xC10C1234), (7, 0)):
            request = Request()
            request.manager[:MANAGER_BYTES] = b"\xa5" * MANAGER_BYTES
            request.state.initialized = 0
            request.state.descriptor_miss[:] = b"\x5a" * MISS_BYTES
            request.state.divider_miss = 0xABCDEF01
            request.state.source_miss = 0x12345678
            before_state = bytes(request.state)
            request.open_plan.reply, request.open_plan.handle_write = reply, handle
            self.run_request(request, initialize=True)
            expected = bytearray(MANAGER_BYTES + 16)
            expected[TABLE:TABLE + 4] = (0x0EDE7F04).to_bytes(4, "little")
            expected[MANAGER_BYTES:] = b"\x5a" * 16
            manager, state, output, raw = request.snapshots[0]
            self.assertEqual(manager, expected)
            self.assertEqual(state, b"\x01\x00\x00\x00" + before_state[4:])
            self.assertEqual(output, b"\xa5" * 48)
            self.assertEqual(raw, bytes(guarded(Word(SENTINEL))))
            self.assertEqual(request.get(HANDLE, 4), handle)
            self.assertEqual(request.get(REFERENCE), 54000000)
            self.assertEqual(request.raw_storage.value, reply)
            self.assertEqual(bytes(request.state), state)

    def test_request_callback_visibility(self):
        for source, divider, planner, pre in (
                (0, 0, 1200, None), (1000000000, 250000000, 1200, None),
                (2000000000, 500000000, 1200, None),
                (1200000000, 300000000, 1200, None), (0, 0, 1500, None),
                (0, 0, 1200, 7), (0, 0, 1200, 0)):
            with self.subTest(source=source, planner=planner, pre=pre):
                request = Request()
                request.put(SOURCE_RATE, source)
                request.put(DIVIDER_RATE, divider)
                request.inputs.planner_input = planner
                if pre is not None:
                    request.notify(pre, 7)
                before_manager = bytes(request.manager)
                before_raw = bytes(request.raw_storage)
                self.run_request(request)
                planned_source, planned_count = ((1200000000, 2) if planner == 1200
                                                 else (1800000000, 3))
                divider_seen = 0
                self.assertEqual(len(request.calls), len(request.snapshots))
                for call, snapshot in zip(request.calls, request.snapshots):
                    kind, _, arguments, _ = call
                    manager, state_bytes, output, raw = snapshot
                    state = State.from_buffer_copy(state_bytes)
                    expected_source, expected_divider, count, clock = source, divider, 0, 500000000
                    expected_output = b"\xa5" * 48
                    descriptor, rate_misses = 0, False
                    if kind == NOTIFY and arguments[1] == 0:
                        descriptor = 1
                    elif kind in (SOURCE, CLOCK, DIVIDER) or (kind == NOTIFY and arguments[1] == 2):
                        descriptor, rate_misses = 1, True
                        count = planned_count
                        if kind == SOURCE and source != 1000000000:
                            pass
                        elif kind == DIVIDER and source == 1000000000 and divider_seen == 0:
                            count = 0
                        else:
                            expected_source, expected_divider = planned_source, 600000000
                        if kind == NOTIFY:
                            clock = 600000000
                    elif kind == RELEASE:
                        descriptor = 1
                        if pre != 7:
                            expected_source, expected_divider = planned_source, 600000000
                            count, clock, rate_misses = planned_count, 600000000, True
                            expected_output = (b"\xa5" * 16 + clock.to_bytes(8, "little")
                                               + b"\xa5" * 24)
                    if kind == DIVIDER:
                        divider_seen += 1
                    expected_manager = bytearray(before_manager)
                    for offset, word, size in ((SOURCE_RATE, expected_source, 8),
                                              (DIVIDER_RATE, expected_divider, 8),
                                              (COUNT, count, 4), (REQUESTED, clock, 8)):
                        expected_manager[offset:offset + size] = word.to_bytes(size, "little")
                    self.assertEqual(manager, expected_manager)
                    self.assertEqual(list(state.descriptor_miss),
                                     [descriptor if index == 0x30 else 0 for index in range(86)])
                    self.assertEqual((state.divider_miss, state.source_miss),
                                     (0x20, 0x80) if rate_misses else (0, 0))
                    self.assertEqual(state.initialized, 1)
                    self.assertEqual(output, expected_output)
                    self.assertEqual(raw, before_raw)

    def test_unaligned_adjacent_buffers(self):
        request = Request()
        backing = (Byte * (MANAGER_BYTES + 10))(*([0xA5] * (MANAGER_BYTES + 10)))
        backing[1:MANAGER_BYTES + 1] = request.manager[:MANAGER_BYTES]
        args = request.arguments()
        args[1] = ctypes.cast(ctypes.byref(backing, 1), BytePointer)
        args[2] = MANAGER_BYTES
        args[4] = ctypes.cast(ctypes.byref(backing, MANAGER_BYTES + 1), BytePointer)
        args[5] = 8
        self.assertEqual(self.execute(*args), OK)
        expected = Request()
        self.run_request(expected)
        self.assertEqual(bytes(backing[1:MANAGER_BYTES + 1]), bytes(expected.manager[:MANAGER_BYTES]))
        self.assertEqual(bytes(backing[MANAGER_BYTES + 1:-1]), (600000000).to_bytes(8, "little"))
        self.assertEqual((backing[0], backing[-1]), (0xA5, 0xA5))

    def test_output_tail_is_preserved(self):
        request = Request()
        args = request.arguments()
        args[5] = 32
        self.run_request(request, arguments=args)

    def test_overlap_in_declared_tail(self):
        request = Request()
        args = request.arguments()
        args[4] = ctypes.cast(ctypes.byref(request.manager, MANAGER_BYTES), BytePointer)
        self.run_request(request, OVERLAP, args)
        request = Request()
        args = request.arguments()
        args[5] = ctypes.sizeof(request.output_storage)
        args[7] = ctypes.cast(ctypes.byref(request.output_storage, 32), WordPointer)
        self.run_request(request, OVERLAP, args)

    def test_wrapped_typed_objects(self):
        maximum = ctypes.c_size_t(-1).value
        for initialize, entries in ((False, ((0, Inputs), (3, State), (6, Plan), (7, Word))),
                                   (True, ((4, State), (5, OpenPlan), (6, Word)))):
            for index, value_type in entries:
                request = Request()
                request.state.initialized = 0 if initialize else 1
                args = request.init_arguments() if initialize else request.arguments()
                args[index] = ctypes.cast(maximum - ctypes.sizeof(value_type) + 1,
                                          ctypes.POINTER(value_type))
                self.run_request(request, INVALID, args, initialize)

    def test_opaque_identity_tokens_and_reserved_bytes(self):
        request = Request()
        request.put(TABLE, 0x12345678, 4)
        request.put(HANDLE, 0x87654321, 4)
        request.inputs.comparison_handle = 0x87654321
        request.inputs.mutex_identity = 0xABCDEF01
        request.notify()
        request.put(NOTIFICATIONS + 4, 0x11223344, 4)
        for offset in (0, 0x10, 0x30, 0x200, 0x400, NOTIFICATIONS + 1, NOTIFICATIONS + 9):
            request.manager[offset] = 0x5A
        self.run_request(request)
        self.assertEqual([call[1] for call in request.calls if call[0] == NOTIFY],
                         [0x11223344, 0x11223344])
        for kind, _, arguments, _ in request.calls:
            if kind in (SOURCE, CLOCK, DIVIDER):
                self.assertEqual(arguments[0], 0x87654321)
            if kind in (ACQUIRE, RELEASE):
                self.assertEqual(arguments, [0xABCDEF01])
        for offset in (0, 0x10, 0x30, 0x200, 0x400, NOTIFICATIONS + 1, NOTIFICATIONS + 9):
            self.assertEqual(request.manager[offset], 0x5A)

    def test_sequential_requests_write_fresh_outputs(self):
        for origin in ("initialized", "cold", "reference-zero"):
            with self.subTest(origin=origin):
                request = Request()
                if origin != "reference-zero":
                    request.manager[:MANAGER_BYTES] = b"\xa5" * MANAGER_BYTES
                    request.state.initialized = 0
                if origin == "initialized":
                    self.run_request(request, initialize=True)
                    request.fresh_outputs()
                self.run_request(request, cold=origin == "cold")
                previous_manager, previous_state = bytes(request.manager), bytes(request.state)
                previous_output, previous_raw = request.output_storage, request.raw_storage
                request.fresh_outputs()
                self.assertNotEqual(ctypes.addressof(request.output_storage),
                                    ctypes.addressof(previous_output))
                self.assertNotEqual(ctypes.addressof(request.raw_storage),
                                    ctypes.addressof(previous_raw))
                request.plan.source = request.plan.divider = Provider()
                request.plan.source_reply = 0x12345678
                request.plan.divider_replies[:] = 0x87654321, 0xFFFFFFFF
                self.run_request(request)
                self.assertEqual(bytes(request.manager), previous_manager)
                self.assertEqual(bytes(request.state), previous_state)
                self.assertEqual([call[0] for call in request.calls],
                                 [ACQUIRE, DIAGNOSTIC, CLOCK, RELEASE])
                self.assertEqual(bytes(request.output_storage),
                                 b"\xa5" * 16 + (600000000).to_bytes(8, "little") + b"\xa5" * 24)
                self.assertEqual(request.raw_storage.value, 0)

    def test_state_profile_callback_visibility(self):
        for case in self.state_cases:
            with self.subTest(case=case["id"]):
                request = self.fixture_request(case)
                cold = request.state.initialized == 0
                repeated = request.get(REQUESTED) == 600000000
                initial_manager = bytes(request.manager)
                before_raw = bytes(request.raw_storage)
                self.run_request(request, cold=cold)
                for call, snapshot in zip(request.calls, request.snapshots):
                    manager, state_bytes, output, raw = snapshot
                    state = State.from_buffer_copy(state_bytes)
                    expected = bytearray(initial_manager)
                    is_open = len(call) == 5
                    kind = None if is_open else call[0]
                    if cold:
                        expected[:MANAGER_BYTES] = b"\x00" * MANAGER_BYTES
                        expected[TABLE:TABLE + 4] = (0x0EDE7F04).to_bytes(4, "little")
                        if not is_open:
                            expected[HANDLE:HANDLE + 4] = (0xC10C1234).to_bytes(4, "little")
                            expected[REFERENCE:REFERENCE + 8] = (54000000).to_bytes(8, "little")
                    if not repeated:
                        if kind in (SOURCE, CLOCK, DIVIDER, RELEASE):
                            expected[COUNT:COUNT + 4] = (2).to_bytes(4, "little")
                        if kind in (CLOCK, DIVIDER, RELEASE):
                            expected[SOURCE_RATE:SOURCE_RATE + 8] = (1200000000).to_bytes(8, "little")
                            expected[DIVIDER_RATE:DIVIDER_RATE + 8] = (600000000).to_bytes(8, "little")
                        if kind == RELEASE:
                            expected[REQUESTED:REQUESTED + 8] = (600000000).to_bytes(8, "little")
                    planned = repeated or kind in (SOURCE, CLOCK, DIVIDER, RELEASE)
                    self.assertEqual(manager, expected)
                    self.assertEqual(state.initialized, 1)
                    self.assertEqual(list(state.descriptor_miss),
                                     [1 if planned and index == 0x30 else 0 for index in range(MISS_BYTES)])
                    self.assertEqual((state.divider_miss, state.source_miss),
                                     (0x20, 0x80) if planned else (0, 0))
                    expected_output = bytearray(b"\xa5" * 48)
                    if kind == RELEASE:
                        expected_output[16:24] = (600000000).to_bytes(8, "little")
                    self.assertEqual(output, expected_output)
                    self.assertEqual(raw, before_raw)

    def test_state_profile_reachable_providers(self):
        for case in self.state_cases:
            cold = case["id"] == "cold-wrapper-open-zero"
            repeated = case["id"].startswith("repeat-")
            names = ["acquire", "diagnostic", "clock", "release"]
            if not repeated:
                names += ["source", "divider"]
            for name in names + (["open"] if cold else []):
                with self.subTest(case=case["id"], missing=name):
                    request = self.fixture_request(case)
                    if name == "open":
                        request.open_plan.open = OpenProvider()
                    else:
                        setattr(request.plan, name, Provider())
                    self.run_request(request, INVALID, cold=cold)

    def test_state_profiles_do_not_expand_original_combinations(self):
        for case in self.state_cases:
            cold = case["id"] == "cold-wrapper-open-zero"
            repeated = case["id"].startswith("repeat-")
            for field, value in (("skip", 1), ("skip", 0xFFFFFFFF), ("planner_input", 1500),
                                 ("requested", 600000001), ("selection", 0),
                                 ("comparison_handle", 0), ("argument3", 1), ("argument4", 1)):
                with self.subTest(case=case["id"], field=field, value=value):
                    request = self.fixture_request(case)
                    setattr(request.inputs, field, value)
                    self.run_request(request, UNSUPPORTED, cold=cold)
            for index in range(3):
                request = self.fixture_request(case)
                request.inputs.override_heads[index] = 1
                self.run_request(request, UNSUPPORTED, cold=cold)
            for name in ["clock_reply"] + ([] if repeated else ["source_reply", "divider_reply"]):
                request = self.fixture_request(case)
                if name == "divider_reply":
                    request.plan.divider_replies[0] = 0xFFFFFFFF
                else:
                    setattr(request.plan, name, 0xFFFFFFFF)
                self.run_request(request, UNSUPPORTED, cold=cold)
            for index in range(4):
                request = self.fixture_request(case)
                request.manager[NOTIFICATIONS + 8 * index] = 0x30
                request.put(NOTIFICATIONS + 8 * index + 4, 0x24030000, 4)
                request.plan.notify = request.provider
                request.plan.notification_replies[:] = 0, 7
                self.run_request(request, UNSUPPORTED, cold=cold)

    def test_state_profile_fields_must_match(self):
        for case in self.state_cases:
            cold = case["id"] == "cold-wrapper-open-zero"
            for offset, size in ((TABLE, 4), (HANDLE, 4), (REFERENCE, 8), (SOURCE_RATE, 8),
                                 (DIVIDER_RATE, 8), (COUNT, 4), (REQUESTED, 8)):
                request = self.fixture_request(case)
                value = 0 if offset in (TABLE, HANDLE) else request.get(offset, size) + 1
                request.put(offset, value, size)
                self.run_request(request, UNSUPPORTED, cold=cold)
            for index in (0, 0x30, MISS_BYTES - 1):
                request = self.fixture_request(case)
                request.state.descriptor_miss[index] ^= 1
                self.run_request(request, UNSUPPORTED, cold=cold)
            for field in ("initialized", "divider_miss", "source_miss"):
                request = self.fixture_request(case)
                setattr(request.state, field, getattr(request.state, field) ^ 1)
                self.run_request(request, UNSUPPORTED, cold=cold)
        for offset in (0, MANAGER_BYTES - 1):
            request = self.fixture_request(self.state_cases[1])
            request.manager[offset] = 0
            self.run_request(request, UNSUPPORTED, cold=True)

    def test_cold_request_open_profile(self):
        for reply, handle in ((7, 0), (7, 0xC10C1234), (0, 0), (0, 0x12345678)):
            request = self.fixture_request(self.state_cases[1])
            request.open_plan.reply, request.open_plan.handle_write = reply, handle
            request.inputs.comparison_handle = handle
            self.run_request(request, UNSUPPORTED, cold=True)
        request = self.fixture_request(self.state_cases[1])
        arguments = request.cold_arguments()
        arguments[1] = 0
        self.run_request(request, UNSUPPORTED, arguments, cold=True)
        request = self.fixture_request(self.state_cases[1])
        self.run_request(request, UNSUPPORTED)

    def test_cold_request_storage_preflight(self):
        maximum = ctypes.c_size_t(-1).value
        entries = ((0, Inputs), (2, Byte), (4, State), (5, Byte),
                   (7, OpenPlan), (8, Plan), (9, Word))
        for index, value_type in entries:
            for invalid in (None, ctypes.cast(maximum - ctypes.sizeof(value_type) + 1,
                                              ctypes.POINTER(value_type))):
                request = self.fixture_request(self.state_cases[1])
                arguments = request.cold_arguments()
                arguments[index] = invalid
                self.run_request(request, INVALID, arguments, cold=True)
        for (left, _), (right, right_type) in itertools.combinations(entries, 2):
            request = self.fixture_request(self.state_cases[1])
            arguments = request.cold_arguments()
            arguments[right] = ctypes.cast(arguments[left], ctypes.POINTER(right_type))
            self.run_request(request, OVERLAP, arguments, cold=True)
        for length, required in ((3, MANAGER_BYTES), (6, 8)):
            for size in (0, required - 1, maximum):
                request = self.fixture_request(self.state_cases[1])
                arguments = request.cold_arguments()
                arguments[length] = size
                self.run_request(request, INVALID if size == maximum else BOUNDS,
                                 arguments, cold=True)
        request = self.fixture_request(self.state_cases[1])
        arguments = request.cold_arguments()
        arguments[5] = ctypes.cast(ctypes.byref(request.manager, MANAGER_BYTES), BytePointer)
        self.run_request(request, OVERLAP, arguments, cold=True)
        request = self.fixture_request(self.state_cases[1])
        arguments = request.cold_arguments()
        arguments[6] = 32
        arguments[9] = ctypes.cast(ctypes.byref(request.output_storage, 32), WordPointer)
        self.run_request(request, OVERLAP, arguments, cold=True)

    def test_state_profile_identity_tokens_and_reserved_bytes(self):
        for case in self.state_cases:
            request = self.fixture_request(case)
            cold = request.state.initialized == 0
            request.inputs.mutex_identity = 0x87654321
            if cold:
                arguments = request.cold_arguments()
                arguments[1] = 0x12345678
            else:
                request.put(TABLE, 0x12345678, 4)
                request.put(HANDLE, 0x11223344, 4)
                request.inputs.comparison_handle = 0x11223344
                for offset in (0, 0x10, 0x30, 0x200, 0x400, NOTIFICATIONS + 1):
                    request.manager[offset] = 0x5A
                arguments = request.arguments()
            self.run_request(request, arguments=arguments, cold=cold)
            self.assertEqual(request.get(TABLE, 4), 0x12345678)
            for call in request.calls:
                if len(call) == 5:
                    self.assertEqual(call[0], 0x12345678)
                elif call[0] in (ACQUIRE, RELEASE):
                    self.assertEqual(call[2], [0x87654321])
                elif call[0] in (SOURCE, CLOCK, DIVIDER):
                    self.assertEqual(call[2][0], 0xC10C1234 if cold else 0x11223344)
            if not cold:
                for offset in (0, 0x10, 0x30, 0x200, 0x400, NOTIFICATIONS + 1):
                    self.assertEqual(request.manager[offset], 0x5A)


if __name__ == "__main__":
    unittest.main()
