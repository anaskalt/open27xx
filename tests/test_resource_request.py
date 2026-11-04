# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare fixed resource requests and check outcomes with recorded cases."""

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
RETURNED, STOPPED = 0, 1
DIAGNOSTIC, ACQUIRE, RELEASE, ENABLE, CONTEXT = range(5)
BIT, DEPENDENCIES, SENTINEL = 0x800000, 0x180, 0xA5A5A5A5
Word = ctypes.c_uint32
WordPointer = ctypes.POINTER(Word)
Provider = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                           WordPointer, ctypes.c_size_t, Word)


class OutcomeValue(ctypes.Union):
    _fields_ = [("raw_return", Word), ("stop_flag", Word)]


class Outcome(ctypes.Structure):
    _fields_ = [("kind", ctypes.c_int), ("value", OutcomeValue)]


class Context(ctypes.Structure):
    _fields_ = [("descriptor", Word), ("callback", Word), ("opaque", Word),
                ("reply", Word), ("provider", Provider), ("context", ctypes.c_void_p)]


class Record(ctypes.Structure):
    _fields_ = [("self", Word), ("requests", Word)]


class State(ctypes.Structure):
    _fields_ = [("held", Word), ("aggregate", Word)]


class Inputs(ctypes.Structure):
    _fields_ = [("object_present", Word), ("identity", Word),
                ("record_index", ctypes.c_size_t), ("logical_index", Word),
                ("argument2", Word), ("argument3", Word), ("selection", Word),
                ("handle", Word), ("mutex_identity", Word)]


class Plan(ctypes.Structure):
    _fields_ = [("diagnostic", Provider), ("acquire", Provider),
                ("release", Provider), ("enable", Provider),
                ("context", ctypes.c_void_p), ("enable_replies", Word * 2),
                ("check_context", ctypes.POINTER(Context))]


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
        self.records_storage = guarded((Record * 34)())
        self.records = self.records_storage.value
        self.records[0].self = 0x12345678
        self.records[32] = Record(0x99887766, 0x11223344)
        self.records[33] = Record(0x77889900, 0x55667788)
        self.state_storage = guarded(State(0, SENTINEL))
        self.state = self.state_storage.value
        self.outcome_storage = guarded(Outcome(-29, OutcomeValue(SENTINEL)))
        self.outcome = self.outcome_storage.value
        self.inputs = Inputs(1, self.records[0].self, 0, 23, 1, 1, 0, 0, 0x87654321)
        self.calls, self.snapshots, self.contexts = [], [], []
        self.bookkeeping = Word(0)
        self.provider = Provider(self.observe)
        self.context = Context(0x24060010, 0x24070000, 0xC0DEC0DE, 0,
                               self.provider, ctypes.addressof(self.bookkeeping))
        self.plan = Plan(self.provider, self.provider, self.provider, self.provider,
                         ctypes.addressof(self.bookkeeping), (Word * 2)(0, 0), None)

    def observe(self, context, kind, arguments, count, reply):
        self.calls.append((kind, list(arguments[:count]), reply))
        self.contexts.append(context)
        self.snapshots.append((bytes(self.records), bytes(self.state), bytes(self.outcome)))
        self.bookkeeping.value += 1

    def use_context(self, reply=0):
        self.context.reply = reply
        self.plan.check_context = ctypes.pointer(self.context)

    def arguments(self, count=32):
        return [ctypes.byref(self.inputs), self.records, count, ctypes.byref(self.state),
                ctypes.byref(self.plan), ctypes.byref(self.outcome)]

    def storage(self):
        return tuple(bytes(value) for value in (
            self.records_storage, self.state_storage, self.outcome_storage,
            self.inputs, self.plan, self.context))


class ResourceRequestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Resource-request tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="resource-request-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "resource_request.so"
        subprocess.run(compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/resource_request.c"), "-o", str(library),
        ], check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.execute = cls.library.resource_request_execute
        cls.execute.argtypes = [ctypes.POINTER(Inputs), ctypes.POINTER(Record),
                                ctypes.c_size_t, ctypes.POINTER(State), ctypes.POINTER(Plan),
                                ctypes.POINTER(Outcome)]
        cls.execute.restype = ctypes.c_int
        cls.dependency = cls.library.resource_request_dependency
        cls.dependency.argtypes = [Word, Word, WordPointer]
        cls.dependency.restype = ctypes.c_int
        cls.context_call = cls.library.resource_request_context_call
        cls.context_call.argtypes = [ctypes.POINTER(Context), ctypes.POINTER(Outcome)]
        cls.context_call.restype = ctypes.c_int
        cls.check = cls.library.resource_request_check
        cls.check.argtypes = [Word, ctypes.POINTER(Context), ctypes.POINTER(Outcome)]
        cls.check.restype = ctypes.c_int
        cls.cases = [case for name in ("resource-request", "resource-context")
                     for case in json.loads((ROOT / "tests/vectors/start4" /
                                             f"{name}.json").read_text())["cases"]]

    def assert_guards(self, request):
        for storage in (request.records_storage, request.state_storage, request.outcome_storage):
            self.assertEqual((storage.before, storage.after),
                             (0x713AC924713AC924, 0x57DDEF8357DDEF83))

    def run_request(self, request, status=OK, arguments=None):
        before = request.storage()
        self.assertEqual(self.execute(*(arguments or request.arguments())), status)
        if status != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.calls, [])
            self.assertEqual(request.bookkeeping.value, 0)
        else:
            self.assertEqual(request.storage()[3:], before[3:])
            self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)]
                             * len(request.calls))
            self.assertEqual(request.bookkeeping.value, len(request.calls))
            self.assertEqual(bytes(request.records)[32 * ctypes.sizeof(Record):],
                             bytes((Record * 2)(Record(0x99887766, 0x11223344),
                                                Record(0x77889900, 0x55667788))))
        self.assert_guards(request)

    def fixture_request(self, case):
        request = Request()
        gp = int(case["setup"]["registers"]["gp"], 0)
        identity = int(case["setup"]["registers"]["r0"], 0)
        request.inputs.object_present = int(identity != 0)
        request.inputs.identity = identity
        request.inputs.mutex_identity = gp + 0xDA4C0
        request.inputs.handle = fixture_word(case, "setup", gp + 0xDA988)
        request.inputs.selection = fixture_word(case, "setup", gp + 0xCD4)
        for index in range(32):
            address = gp + 0xDA4C4 + 28 * index
            request.records[index] = Record(fixture_word(case, "setup", address),
                                            fixture_word(case, "setup", address + 8))
        request.state.held = fixture_word(case, "setup", gp + 0xDA98C)
        output = fixture_word(case, "setup", gp + 0x14B0)
        request.state.aggregate = fixture_word(case, "setup", output)
        request.plan.diagnostic = request.plan.acquire = request.plan.release = Provider()
        request.plan.enable = Provider()
        for stub in case["execution"]["stubs"]:
            entry = int(stub["entry"], 0)
            if entry == 0x24070000:
                request.use_context(int(stub["replies"][0]["registers"]["r0"], 0))
            else:
                field = {0x0ED17442: "diagnostic", 0x0ED64D02: "acquire",
                         0x0ED64D3A: "release", 0x0ED550B2: "enable"}[entry]
                setattr(request.plan, field, request.provider)
                for index, reply in enumerate(stub["replies"]):
                    word = int(reply["registers"]["r0"], 0)
                    self.assertEqual(reply["memory"], [])
                    if field == "enable":
                        request.plan.enable_replies[index] = word
                    else:
                        self.assertEqual(word, 0)
        return request

    def assert_fixture_calls(self, case, calls):
        mapping = {0x0ED17442: (DIAGNOSTIC, 6), 0x0ED64D02: (ACQUIRE, 1),
                   0x0ED64D3A: (RELEASE, 1), 0x0ED550B2: (ENABLE, 2),
                   0x24070000: (CONTEXT, 3)}
        replies = {int(stub["entry"], 0): stub["replies"] for stub in case["execution"]["stubs"]}
        expected = []
        for event in case["expected"]["events"]:
            entry = int(event["entry"], 0)
            kind, count = mapping[entry]
            reply = int(replies[entry][event["reply_index"]]["registers"]["r0"], 0)
            expected.append((kind, [int(value, 0) for value in event["arguments"][:count]], reply))
        self.assertEqual(calls, expected)

    def assert_outcome(self, case, outcome):
        if int(case["execution"]["return_address"], 0) == 0x0ED7C75A:
            self.assertEqual((outcome.kind, outcome.value.stop_flag), (STOPPED, 1))
            address = int(case["expected"]["registers"]["sp"], 0)
            self.assertEqual(fixture_word(case, "expected", address), 1)
        else:
            self.assertEqual((outcome.kind, outcome.value.raw_return),
                             (RETURNED, int(case["expected"]["registers"]["r0"], 0)))

    def test_fixture_scope(self):
        entries = [int(case["function"]["entry"], 0) for case in self.cases
                   if case["id"] != "real-selection-prefix"]
        self.assertEqual(len(entries), 16)
        self.assertEqual([entries.count(entry) for entry in
                          (0x0ED56032, 0x0ED64C08, 0x0ED7C744, 0x0ED7C9B0)], [2, 2, 3, 9])
        excluded = [case for case in self.cases if case["id"] == "real-selection-prefix"]
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["execution"]["return_address"], "0x0ED55648")

    def test_recorded_manager_calls_and_stops(self):
        for case in self.cases:
            if int(case["function"]["entry"], 0) != 0x0ED7C9B0 or case["id"] == "real-selection-prefix":
                continue
            with self.subTest(case=case["id"]):
                request = self.fixture_request(case)
                self.run_request(request)
                self.assert_fixture_calls(case, request.calls)
                self.assert_outcome(case, request.outcome)
                gp = int(case["setup"]["registers"]["gp"], 0)
                for index, record in enumerate(request.records[:32]):
                    address = gp + 0xDA4C4 + 28 * index
                    self.assertEqual((record.self, record.requests),
                                     (fixture_word(case, "expected", address),
                                      fixture_word(case, "expected", address + 8)))
                self.assertEqual(request.state.held, fixture_word(case, "expected", gp + 0xDA98C))
                output = fixture_word(case, "setup", gp + 0x14B0)
                self.assertEqual(request.state.aggregate, fixture_word(case, "expected", output))
                # Rebuild the represented regions to compare their untouched bytes and guards.
                replacements = {gp + 0xDA98C: request.state.held, output: request.state.aggregate}
                for index, record in enumerate(request.records[:32]):
                    replacements[gp + 0xDA4C4 + 28 * index] = record.self
                    replacements[gp + 0xDA4CC + 28 * index] = record.requests
                for region in case["expected"]["memory"]:
                    address = int(region["address"], 0)
                    if address < gp and not output - 16 <= address <= output:
                        continue
                    expected = bytes.fromhex(region["hex"])
                    actual = bytearray(fixture_bytes(case, "setup", address, len(expected)))
                    for position, value in replacements.items():
                        if address <= position and position + 4 <= address + len(actual):
                            actual[position - address:position - address + 4] = value.to_bytes(4, "little")
                    self.assertEqual(actual, expected)

    def test_recorded_dependency_context_and_check(self):
        for case in self.cases:
            entry = int(case["function"]["entry"], 0)
            if entry == 0x0ED7C9B0:
                continue
            with self.subTest(case=case["id"]):
                request = Request()
                gp = int(case["setup"]["registers"]["gp"], 0)
                if entry == 0x0ED56032:
                    result = Word(SENTINEL)
                    self.assertEqual(self.dependency(23, fixture_word(case, "setup", gp + 0xCD4),
                                                     ctypes.byref(result)), OK)
                    self.assertEqual(result.value, int(case["expected"]["registers"]["r0"], 0))
                    continue
                condition = int(case["setup"]["registers"]["r0"], 0)
                context = None
                if case["execution"]["stubs"]:
                    request.context.descriptor = fixture_word(case, "setup", gp + 0xE50)
                    request.context.opaque = fixture_word(case, "setup", gp + 0xE54)
                    request.context.callback = fixture_word(case, "setup", request.context.descriptor + 0x18)
                    request.context.reply = int(case["execution"]["stubs"][0]["replies"][0]
                                                ["registers"]["r0"], 0)
                    context = ctypes.byref(request.context)
                before = bytes(request.context)
                arguments = [context, ctypes.byref(request.outcome)]
                if entry == 0x0ED64C08:
                    status = self.context_call(*arguments)
                else:
                    status = self.check(condition, *arguments)
                self.assertEqual(status, OK)
                self.assertEqual(bytes(request.context), before)
                self.assert_fixture_calls(case, request.calls)
                self.assert_outcome(case, request.outcome)
                self.assert_guards(request)

    def test_reachable_provider_preflight(self):
        for duplicate, reply in itertools.product((False, True), (0, 7)):
            for missing in ("check_context", "provider", "diagnostic", "acquire", "release", "enable"):
                with self.subTest(duplicate=duplicate, reply=reply, missing=missing):
                    request = Request()
                    request.records[0].requests = BIT if duplicate else 0
                    request.plan.enable_replies[0] = 0 if duplicate else 7
                    request.use_context(reply)
                    reachable = missing not in (("release",) if reply == 7 else ())
                    reachable &= missing != "enable" or not duplicate
                    if missing == "check_context":
                        request.plan.check_context = None
                    elif missing == "provider":
                        request.context.provider = Provider()
                    else:
                        setattr(request.plan, missing, Provider())
                    self.run_request(request, INVALID if reachable else OK)
        request = Request()
        request.plan.check_context = ctypes.cast(1, ctypes.POINTER(Context))
        self.run_request(request)
        request = Request()
        request.records[31] = Record(31, BIT)
        request.plan.enable = Provider()
        request.plan.enable_replies[:] = [0xFFFFFFFF, 0xFFFFFFFF]
        self.run_request(request)

    def test_state_visibility_and_stopped_effects(self):
        for duplicate, reply, held in itertools.product((False, True), (0, 7), (0, DEPENDENCIES)):
            with self.subTest(duplicate=duplicate, reply=reply, held=held):
                request = Request()
                request.state.held = held
                request.records[0].requests = BIT if duplicate else 0
                request.plan.enable_replies[0] = 7
                request.use_context(reply)
                initial_records, initial_state, initial_outcome = (
                    bytes(request.records), bytes(request.state), bytes(request.outcome))
                self.run_request(request)
                self.assertEqual(request.snapshots[:2],
                                 [(initial_records, initial_state, initial_outcome)] * 2)
                for (kind, _, _), (records, state, outcome) in zip(request.calls, request.snapshots):
                    self.assertEqual(outcome, initial_outcome)
                    if kind not in (DIAGNOSTIC, ACQUIRE):
                        self.assertEqual(State.from_buffer_copy(state).aggregate, DEPENDENCIES)
                        self.assertEqual((Record * 34).from_buffer_copy(records)[0].requests, BIT)
                will_stop = reply == 7 and (duplicate or held == 0)
                self.assertEqual(request.outcome.kind, STOPPED if will_stop else RETURNED)
                self.assertEqual(request.state.held, held if duplicate and will_stop else 0)
                if will_stop:
                    self.assertNotIn(RELEASE, [call[0] for call in request.calls])

    def test_record_scan_and_selected_index(self):
        for selected, shared, active, selection in itertools.product((0, 31), (1, 30, 31), (0, 1), (0, 1)):
            if selected == shared:
                continue
            with self.subTest(selected=selected, shared=shared, active=active, selection=selection):
                request = Request()
                request.records[0] = Record()
                request.records[selected] = Record(0xF1234567, 0)
                request.records[shared] = Record(0xF0000000 if active else 0, BIT)
                request.inputs.identity, request.inputs.record_index = 0xF1234567, selected
                request.inputs.selection = selection
                request.inputs.handle = 0xFFFFFFFF
                self.run_request(request, arguments=request.arguments(34))
                self.assertEqual(request.records[selected].requests, BIT)
                self.assertEqual(request.state.aggregate, DEPENDENCIES)
                enable_calls = [call for call in request.calls if call[0] == ENABLE]
                self.assertEqual(enable_calls, [] if active else
                                 [(ENABLE, [0xFFFFFFFF, 0x80], 0), (ENABLE, [0xFFFFFFFF, 0x100], 0)])

    def test_vendor_object_rejection_is_not_host_error(self):
        for present, stored in ((0, 0x12345678), (1, 0), (1, 0xDEADBEEF)):
            request = Request()
            request.inputs.object_present = present
            request.records[0].self = stored
            request.plan = Plan()
            before = bytes(request.records), bytes(request.state)
            self.run_request(request)
            self.assertEqual((bytes(request.records), bytes(request.state)), before)
            self.assertEqual((request.outcome.kind, request.outcome.value.raw_return), (RETURNED, 0xFFFFFFFF))
            self.assertEqual(request.calls, [])

    def test_unsupported_words_and_reply_plans_have_no_effects(self):
        for field, values in (("object_present", (2, 0xFFFFFFFF)), ("identity", (0,)),
                              ("logical_index", (0, 22, 24, 32)), ("argument2", (0, 2)),
                              ("argument3", (0, 2)), ("selection", (2, 0xFFFFFFFF))):
            for value in values:
                with self.subTest(field=field, value=value):
                    request = Request()
                    setattr(request.inputs, field, value)
                    self.run_request(request, UNSUPPORTED)
        for index, value in itertools.product((0, 31), (1, BIT | 1, 0xFFFFFFFF)):
            request = Request()
            request.records[index].requests = value
            self.run_request(request, UNSUPPORTED)
        for value in (1, 0x80, 0x100, 0xFFFFFFFF):
            request = Request()
            request.state.held = value
            self.run_request(request, UNSUPPORTED)
        for index, value in ((0, 1), (0, 0xFFFFFFFF), (1, 7), (1, 0xFFFFFFFF)):
            request = Request()
            request.plan.enable_replies[index] = value
            self.run_request(request, UNSUPPORTED)
        for field, value in (("reply", 1), ("reply", 0xFFFFFFFF), ("descriptor", 0), ("callback", 0)):
            request = Request()
            request.plan.enable_replies[0] = 7
            request.use_context()
            setattr(request.context, field, value)
            self.run_request(request, UNSUPPORTED)
        request = Request()
        request.plan.enable_replies[:] = [7, 0xFFFFFFFF]
        request.use_context(7)
        request.plan.release = Provider()
        self.run_request(request)

    def test_null_bounds_and_wrapping_extents(self):
        for position in (0, 1, 3, 4, 5):
            request = Request()
            arguments = request.arguments()
            arguments[position] = None
            self.run_request(request, INVALID, arguments)
        for count in (0, 1, 31):
            request = Request()
            self.run_request(request, BOUNDS, request.arguments(count))
        request = Request()
        arguments = request.arguments(31)
        arguments[1] = ctypes.cast(1, ctypes.POINTER(Record))
        self.run_request(request, BOUNDS, arguments)
        for index in (32, 33, 0xFFFFFFFF):
            request = Request()
            request.inputs.record_index = index
            self.run_request(request, BOUNDS)
        maximum = ctypes.c_size_t(-1).value
        for position, pointer_type in ((0, Inputs), (1, Record), (3, State), (4, Plan), (5, Outcome)):
            request = Request()
            arguments = request.arguments()
            arguments[position] = ctypes.cast(maximum - 1, ctypes.POINTER(pointer_type))
            self.run_request(request, INVALID, arguments)
        for count in (maximum, maximum // ctypes.sizeof(Record)):
            request = Request()
            self.run_request(request, INVALID, request.arguments(count))
        request = Request()
        request.plan.enable_replies[0] = 7
        request.plan.check_context = ctypes.cast(maximum - 1, ctypes.POINTER(Context))
        self.run_request(request, INVALID)

    def test_overlaps_and_adjacency(self):
        objects = ((0, Inputs), (1, Record), (3, State), (4, Plan), (5, Outcome))
        for (left, left_type), (right, right_type) in itertools.combinations(objects, 2):
            for offset in (0, 1, ctypes.sizeof(left_type) - 1):
                with self.subTest(left=left, right=right, offset=offset):
                    request = Request()
                    arguments = request.arguments()
                    address = ctypes.cast(arguments[left], ctypes.c_void_p).value
                    arguments[right] = ctypes.cast(address + offset, ctypes.POINTER(right_type))
                    self.run_request(request, OVERLAP, arguments)
        for name in ("inputs", "records", "state", "plan", "outcome"):
            request = Request()
            request.plan.enable_replies[0] = 7
            request.plan.check_context = ctypes.cast(ctypes.addressof(getattr(request, name)),
                                                     ctypes.POINTER(Context))
            self.run_request(request, OVERLAP)

        class Adjacent(ctypes.Structure):
            _fields_ = [("inputs", Inputs), ("records", Record * 32), ("state", State),
                        ("plan", Plan), ("outcome", Outcome), ("context", Context)]

        request = Request()
        adjacent = Adjacent(request.inputs, (Record * 32)(*request.records[:32]),
                            request.state, request.plan, request.outcome, request.context)
        adjacent.records[0].requests = BIT
        adjacent.plan.check_context = ctypes.pointer(adjacent.context)
        self.assertEqual(self.execute(ctypes.byref(adjacent.inputs), adjacent.records, 32,
                                      ctypes.byref(adjacent.state), ctypes.byref(adjacent.plan),
                                      ctypes.byref(adjacent.outcome)), OK)
        self.assertEqual((adjacent.outcome.kind, adjacent.outcome.value.raw_return), (RETURNED, 0))

    def test_direct_validation_and_true_conditions(self):
        result = Word(SENTINEL)
        for index, selection in ((22, 0), (24, 0), (23, 2), (23, 0xFFFFFFFF)):
            self.assertEqual(self.dependency(index, selection, ctypes.byref(result)), UNSUPPORTED)
            self.assertEqual(result.value, SENTINEL)
        self.assertEqual(self.dependency(23, 0, None), INVALID)
        for condition in (1, 2, 0x80000000, 0xFFFFFFFF):
            request = Request()
            self.assertEqual(self.check(condition, None, ctypes.byref(request.outcome)), OK)
            self.assertEqual((request.outcome.kind, request.outcome.value.raw_return), (RETURNED, condition))
            self.assertEqual(request.calls, [])
        for direct in (False, True):
            for problem in ("context", "outcome", "provider", "reply", "overlap", "wrap"):
                with self.subTest(direct=direct, problem=problem):
                    request = Request()
                    context, outcome = ctypes.byref(request.context), ctypes.byref(request.outcome)
                    status = INVALID
                    if problem == "context":
                        context = None
                    elif problem == "outcome":
                        outcome = None
                    elif problem == "provider":
                        request.context.provider = Provider()
                    elif problem == "reply":
                        request.context.reply, status = 1, UNSUPPORTED
                    elif problem == "overlap":
                        outcome = ctypes.cast(ctypes.byref(request.context, 1), ctypes.POINTER(Outcome))
                        status = OVERLAP
                    else:
                        context = ctypes.cast(ctypes.c_size_t(-1).value - 1, ctypes.POINTER(Context))
                    before = request.storage()
                    actual = (self.context_call(context, outcome) if direct
                              else self.check(0, context, outcome))
                    self.assertEqual(actual, status)
                    self.assertEqual(request.storage(), before)
                    self.assertEqual(request.calls, [])


if __name__ == "__main__":
    unittest.main()
