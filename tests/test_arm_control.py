# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare portable request callbacks with the ARM control contract."""

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
OK, INVALID, UNSUPPORTED, OVERLAP = 0, -1, -2, -3
HANDLE = 0x61726D11
SENTINEL = 0x89ABCDEF
CONFIGURATION_FIELDS = {
    "driver": 0x1660, "selection": 0x1564, "handle": 0x19C8,
    "service_index": 0x3B490, "word_a": 0xCC948, "word_b": 0xCC934,
    "word_c": 0xCCA24, "word_d": 0xCCA1C,
}
START_FIELDS = {
    "open_count": 0x3B474, "mapping_marker": 0x3B518,
    "active": 0x3B494, "resource_object": 0x3B478,
}


class Configuration(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in CONFIGURATION_FIELDS]


class StartState(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in START_FIELDS]


Service = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, *([ctypes.c_uint32] * 6))
Mutex = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p)
Resource = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, *([ctypes.c_uint32] * 4))


class StartCallbacks(ctypes.Structure):
    _fields_ = [("acquire", Mutex), ("release", Mutex), ("request", Resource),
                ("context", ctypes.c_void_p)]


def guarded(value):
    class Guarded(ctypes.Structure):
        _fields_ = [("before", ctypes.c_uint32), ("value", type(value)),
                    ("after", ctypes.c_uint32)]
    return Guarded(0x713AC924, value, 0x57DDEF83)


def configuration(**words):
    values = {"driver": 0x0EDE54D4, "selection": 1, "handle": HANDLE, "service_index": 1,
              "word_a": 0, "word_b": 0, "word_c": 0, "word_d": 0}
    values.update(words)
    return Configuration(**values)


def start_state(**words):
    values = {"open_count": 1, "mapping_marker": 1, "active": 0, "resource_object": 0x12345678}
    values.update(words)
    return StartState(**values)


def fixture_state(case, fields, state_type):
    gp = int(case["setup"]["registers"]["gp"], 0)
    words = {int(region["address"], 0): int.from_bytes(bytes.fromhex(region["hex"]), "little")
             for region in case["setup"]["memory"] if "hex" in region}
    return state_type(**{name: words[gp + offset] for name, offset in fields.items()})


class ServiceRecorder:
    def __init__(self, replies=()):
        self.replies = replies
        self.calls = []
        self.contexts = []
        self.callback = Service(self.call)

    def call(self, context, *arguments):
        index = len(self.calls)
        self.calls.append(list(arguments))
        self.contexts.append(context)
        return self.replies[index] if index < len(self.replies) else 0


class StartRecorder:
    def __init__(self, state, result, acquire=0, release=0, resource=0):
        self.state = state
        self.result = result
        self.mutex = ctypes.c_uint32(0x1234ABCD)
        self.context = ctypes.c_uint32(0x5678ABCD)
        self.replies = {"acquire": acquire, "release": release, "request": resource}
        self.calls = []
        self.snapshots = []
        self.contexts = []
        self.outputs = []
        self.callbacks = StartCallbacks(
            Mutex(lambda context, mutex: self.call("acquire", context, mutex)),
            Mutex(lambda context, mutex: self.call("release", context, mutex)),
            Resource(lambda context, *arguments: self.call("request", context, *arguments)),
            ctypes.addressof(self.context),
        )

    def call(self, kind, context, *arguments):
        self.calls.append((kind, list(arguments)))
        self.contexts.append(context)
        self.snapshots.append(bytes(self.state))
        self.outputs.append(self.result.value)
        return self.replies[kind]


class ArmControlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("ARM control tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="arm-control-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "arm_control.so"
        command = compiler + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/arm_control.c"), "-o", str(library),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.configure = cls.library.arm_control_configure
        cls.configure.argtypes = [ctypes.POINTER(Configuration), ctypes.c_uint32,
                                  Service, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        cls.configure.restype = ctypes.c_int
        cls.start = cls.library.arm_control_start
        cls.start.argtypes = [ctypes.POINTER(StartState), ctypes.c_uint32, ctypes.c_void_p,
                              ctypes.POINTER(StartCallbacks), ctypes.POINTER(ctypes.c_uint32)]
        cls.start.restype = ctypes.c_int
        cls.cases = [case for name in ("arm-control.json", "arm-control-replies.json")
                     for case in json.loads((ROOT / "tests/vectors/start4" / name).read_text())["cases"]]

    def assert_guards(self, storage):
        self.assertEqual((storage.before, storage.after), (0x713AC924, 0x57DDEF83))

    def assert_fixture_state(self, case, state, fields):
        gp = int(case["setup"]["registers"]["gp"], 0)
        observed = {gp + offset: getattr(state, name).to_bytes(4, "little")
                    for name, offset in fields.items()}
        self.assertEqual(observed, {int(region["address"], 0): bytes.fromhex(region["hex"])
                                    for region in case["expected"]["memory"]})

    def run_start(self, state, recorder, result, handle=HANDLE):
        return self.start(ctypes.byref(state), handle, ctypes.byref(recorder.mutex),
                          ctypes.byref(recorder.callbacks), ctypes.byref(result))

    def assert_start_context(self, recorder):
        self.assertEqual(recorder.contexts, [ctypes.addressof(recorder.context)] * len(recorder.calls))
        for kind, arguments in recorder.calls:
            if kind in ("acquire", "release"):
                self.assertEqual(arguments, [ctypes.addressof(recorder.mutex)])
        self.assertEqual(recorder.mutex.value, 0x1234ABCD)
        self.assertEqual(recorder.context.value, 0x5678ABCD)

    def test_fixture_scope(self):
        entries = [int(case["function"]["entry"], 0) for case in self.cases]
        self.assertEqual(entries.count(0x0EC5EE2A), 24)
        self.assertEqual(entries.count(0x0EC5A81E), 16)
        excluded = [case["id"] for case in self.cases
                    if int(case["function"]["entry"], 0) not in (0x0EC5EE2A, 0x0EC5A81E)]
        self.assertEqual(excluded, ["release-zero-flag-boundary"])

    def test_recorded_configuration(self):
        for case in self.cases:
            if int(case["function"]["entry"], 0) != 0x0EC5EE2A:
                continue
            with self.subTest(case=case["id"]):
                storage = guarded(fixture_state(case, CONFIGURATION_FIELDS, Configuration))
                before = bytes(storage)
                result = guarded(ctypes.c_uint32(SENTINEL))
                output = ctypes.cast(ctypes.byref(result, type(result).value.offset),
                                     ctypes.POINTER(ctypes.c_uint32))
                replies = [int(reply["registers"]["r0"], 0)
                           for stub in case["execution"]["stubs"] for reply in stub["replies"]]
                recorder = ServiceRecorder(replies)
                context = ctypes.c_uint32(19)
                incoming = int(case["setup"]["registers"].get("r0", case["setup"]["register_default"]), 0)
                self.assertEqual(self.configure(ctypes.byref(storage.value), incoming,
                                               recorder.callback, ctypes.byref(context), output), OK)
                self.assertEqual(result.value, int(case["expected"]["registers"]["r0"], 0))
                self.assertEqual(recorder.calls, [[int(value, 0) for value in event["arguments"]]
                                                  for event in case["expected"]["events"]])
                for index, event in enumerate(case["expected"]["events"]):
                    self.assertEqual((event["kind"], int(event["entry"], 0), event["reply_index"]),
                                     ("stub", 0x0ED65284, index))
                self.assertEqual(recorder.contexts, [ctypes.addressof(context)] * len(recorder.calls))
                self.assert_fixture_state(case, storage.value, CONFIGURATION_FIELDS)
                self.assertEqual(bytes(storage), before)
                self.assert_guards(result)

    def test_recorded_start_requests(self):
        names = {0x0ED64D02: ("acquire", 1), 0x0ED64D3A: ("release", 1),
                 0x0ED7C9B0: ("request", 4)}
        for case in self.cases:
            if int(case["function"]["entry"], 0) != 0x0EC5A81E:
                continue
            with self.subTest(case=case["id"]):
                storage = guarded(fixture_state(case, START_FIELDS, StartState))
                state = storage.value
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                replies = {names[int(stub["entry"], 0)][0]: int(stub["replies"][0]["registers"]["r0"], 0)
                           for stub in case["execution"]["stubs"]}
                recorder = StartRecorder(state, result, acquire=replies["acquire"],
                                         release=replies["release"], resource=replies.get("request", 0))
                self.assertEqual(self.run_start(state, recorder, result,
                                                int(case["setup"]["registers"]["r0"], 0)), OK)
                self.assertEqual(result.value, int(case["expected"]["registers"]["r0"], 0))
                expected_calls = []
                gp = int(case["setup"]["registers"]["gp"], 0)
                for event in case["expected"]["events"]:
                    kind, count = names[int(event["entry"], 0)]
                    arguments = [int(value, 0) for value in event["arguments"][:count]]
                    if kind in ("acquire", "release"):
                        self.assertEqual(arguments, [gp + 0x3B470])
                        arguments = [ctypes.addressof(recorder.mutex)]
                    expected_calls.append((kind, arguments))
                    self.assertEqual((event["kind"], event["reply_index"]), ("stub", 0))
                self.assertEqual(recorder.calls, expected_calls)
                self.assertEqual(recorder.snapshots[:-1], [before] * (len(recorder.calls) - 1))
                self.assertEqual(recorder.snapshots[-1], bytes(state))
                self.assertEqual(recorder.outputs, [SENTINEL] * len(recorder.calls))
                self.assert_start_context(recorder)
                self.assert_fixture_state(case, state, START_FIELDS)
                self.assert_guards(storage)

    def test_configuration_nonzero_words(self):
        for words in itertools.product((0, 2, 0x80000000, 0xFFFFFFFF), repeat=4):
            with self.subTest(words=words):
                state = configuration(**dict(zip(("word_a", "word_b", "word_c", "word_d"), words)))
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                recorder = ServiceRecorder()
                self.assertEqual(self.configure(ctypes.byref(state), SENTINEL, recorder.callback,
                                                None, ctypes.byref(result)), OK)
                case = next(case for case in self.cases
                            if case["id"] == "configuration-" + "".join(str(int(bool(word))) for word in words))
                self.assertEqual(recorder.calls, [[int(value, 0) for value in event["arguments"]]
                                                  for event in case["expected"]["events"]])
                self.assertEqual(bytes(state), before)
                self.assertEqual(result.value, 0)

    def test_configuration_service_index_and_driver_are_opaque(self):
        for word in (0, 1, 2, 0x80000000, 0xFFFFFFFF):
            with self.subTest(word=word):
                state = configuration(driver=word or 1, service_index=word)
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                recorder = ServiceRecorder()
                self.assertEqual(self.configure(ctypes.byref(state), 7, recorder.callback,
                                                None, ctypes.byref(result)), OK)
                self.assertEqual([call[0] for call in recorder.calls], [word] * 6)
                self.assertEqual(bytes(state), before)

    def test_missing_driver_preserves_incoming_result(self):
        for incoming in (0, 1, 7, 0x80000000, 0xFFFFFFFF):
            with self.subTest(incoming=incoming):
                state = configuration(driver=0, selection=0, handle=0)
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                self.assertEqual(self.configure(ctypes.byref(state), incoming, Service(),
                                                None, ctypes.byref(result)), OK)
                self.assertEqual(result.value, incoming)
                self.assertEqual(bytes(state), before)

    def test_unsupported_routing_emits_no_request(self):
        for field, word in itertools.product(("selection", "handle"), (0, 2, 0x80000000, 0xFFFFFFFF)):
            with self.subTest(field=field, word=word):
                state = configuration(**{field: word})
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                recorder = ServiceRecorder()
                self.assertEqual(self.configure(ctypes.byref(state), 0, recorder.callback,
                                                None, ctypes.byref(result)), UNSUPPORTED)
                self.assertEqual(recorder.calls, [])
                self.assertEqual(result.value, SENTINEL)
                self.assertEqual(bytes(state), before)

    def test_configuration_return_words_do_not_stop_requests(self):
        for index, reply in itertools.product(range(7), (1, 7, 0x80000000, 0xFFFFFFFF)):
            with self.subTest(index=index, reply=reply):
                state = configuration(word_d=1)
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                recorder = ServiceRecorder([0] * index + [reply])
                self.assertEqual(self.configure(ctypes.byref(state), 0, recorder.callback,
                                                None, ctypes.byref(result)), OK)
                self.assertEqual(len(recorder.calls), 7)
                self.assertEqual(result.value, 0)
                self.assertEqual(bytes(state), before)

    def test_start_nonzero_gate_words_and_resource_values(self):
        for opened, mapped, resource, reply in itertools.product(
                (1, 2, 0x80000000, 0xFFFFFFFF), repeat=4):
            with self.subTest(opened=opened, mapped=mapped, resource=resource, reply=reply):
                state = start_state(open_count=opened, mapping_marker=mapped, resource_object=resource)
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                recorder = StartRecorder(state, result, resource=reply)
                self.assertEqual(self.run_start(state, recorder, result), OK)
                self.assertEqual(result.value, reply)
                self.assertEqual(bytes(state), before)
                self.assertEqual(recorder.calls[1], ("request", [resource, 23, 1, 1]))
                self.assert_start_context(recorder)

    def test_start_zero_resource_object_and_repeated_request(self):
        state = start_state(resource_object=0, open_count=0xFFFFFFFF, mapping_marker=0x80000000)
        result = ctypes.c_uint32(SENTINEL)
        recorder = StartRecorder(state, result)
        self.assertEqual(self.run_start(state, recorder, result), OK)
        self.assertEqual((result.value, state.active), (0, 1))
        self.assertEqual(recorder.calls[1], ("request", [0, 23, 1, 1]))
        before = bytes(state)
        recorder.calls.clear()
        self.assertEqual(self.run_start(state, recorder, result), OK)
        self.assertEqual(result.value, 0xFFFFFFFF)
        self.assertEqual(bytes(state), before)
        self.assertEqual([kind for kind, _ in recorder.calls], ["acquire", "release"])

    def test_start_gate_rejections_release_mutex(self):
        cases = [("active", word) for word in (1, 2, 0x80000000, 0xFFFFFFFF)]
        cases += [("open_count", 0), ("mapping_marker", 0)]
        cases += [("handle", word) for word in (0, 1, 0x80000000, 0xFFFFFFFF)]
        for field, word in cases:
            with self.subTest(field=field, word=word):
                state = start_state(**({field: word} if field != "handle" else {}))
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                recorder = StartRecorder(state, result)
                self.assertEqual(self.run_start(state, recorder, result,
                                                word if field == "handle" else HANDLE), OK)
                self.assertEqual(result.value, 0xFFFFFFFF)
                self.assertEqual(bytes(state), before)
                self.assertEqual([kind for kind, _ in recorder.calls], ["acquire", "release"])
                self.assert_start_context(recorder)

    def test_start_mutex_return_words_do_not_replace_resource_result(self):
        for boundary, reply, resource in itertools.product(
                ("acquire", "release"), (1, 7, 0x80000000, 0xFFFFFFFF), (0, 7)):
            with self.subTest(boundary=boundary, reply=reply, resource=resource):
                state = start_state()
                before = bytes(state)
                result = ctypes.c_uint32(SENTINEL)
                recorder = StartRecorder(state, result, resource=resource, **{boundary: reply})
                self.assertEqual(self.run_start(state, recorder, result), OK)
                self.assertEqual(result.value, resource)
                self.assertEqual([kind for kind, _ in recorder.calls],
                                 ["acquire", "request", "release"])
                expected = StartState.from_buffer_copy(before)
                if resource == 0:
                    expected.active = 1
                self.assertEqual(bytes(state), bytes(expected))
                self.assert_start_context(recorder)

    def test_required_null_arguments_do_not_call_or_write(self):
        state = configuration()
        before = bytes(state)
        result = ctypes.c_uint32(SENTINEL)
        recorder = ServiceRecorder()
        for missing in ("state", "result", "service"):
            with self.subTest(configuration=missing):
                self.assertEqual(self.configure(None if missing == "state" else ctypes.byref(state),
                                                0, Service() if missing == "service" else recorder.callback,
                                                None, None if missing == "result" else ctypes.byref(result)), INVALID)
                self.assertEqual((bytes(state), result.value, recorder.calls), (before, SENTINEL, []))
        state = start_state()
        before = bytes(state)
        for missing in ("state", "result", "callbacks", "mutex", "acquire", "release", "request"):
            with self.subTest(start=missing):
                recorder = StartRecorder(state, result)
                if missing in ("acquire", "release"):
                    setattr(recorder.callbacks, missing, Mutex())
                if missing == "request":
                    recorder.callbacks.request = Resource()
                self.assertEqual(self.start(None if missing == "state" else ctypes.byref(state), HANDLE,
                                            None if missing == "mutex" else ctypes.byref(recorder.mutex),
                                            None if missing == "callbacks" else ctypes.byref(recorder.callbacks),
                                            None if missing == "result" else ctypes.byref(result)), INVALID)
                self.assertEqual((bytes(state), result.value, recorder.calls), (before, SENTINEL, []))

    def test_overlapping_objects_rejected_before_callbacks(self):
        state = configuration()
        before = bytes(state)
        recorder = ServiceRecorder()
        for offset in range(0, ctypes.sizeof(state), 4):
            output = ctypes.cast(ctypes.byref(state, offset), ctypes.POINTER(ctypes.c_uint32))
            self.assertEqual(self.configure(ctypes.byref(state), 0, recorder.callback, None, output), OVERLAP)
            self.assertEqual(bytes(state), before)
            self.assertEqual(recorder.calls, [])
        state = start_state()
        before = bytes(state)
        result = ctypes.c_uint32(SENTINEL)
        recorder = StartRecorder(state, result)
        callbacks_before = bytes(recorder.callbacks)
        for target in (state, recorder.callbacks):
            for offset in range(0, ctypes.sizeof(target), 4):
                output = ctypes.cast(ctypes.byref(target, offset), ctypes.POINTER(ctypes.c_uint32))
                self.assertEqual(self.start(ctypes.byref(state), HANDLE, ctypes.byref(recorder.mutex),
                                            ctypes.byref(recorder.callbacks), output), OVERLAP)
                self.assertEqual(bytes(state), before)
                self.assertEqual(bytes(recorder.callbacks), callbacks_before)
                self.assertEqual(recorder.calls, [])
        shared = ctypes.cast(ctypes.byref(recorder.callbacks), ctypes.POINTER(StartState))
        self.assertEqual(self.start(shared, HANDLE, ctypes.byref(recorder.mutex),
                                    ctypes.byref(recorder.callbacks), ctypes.byref(result)), OVERLAP)
        self.assertEqual(bytes(recorder.callbacks), callbacks_before)
        self.assertEqual((result.value, recorder.calls), (SENTINEL, []))
