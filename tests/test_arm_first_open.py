# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check selected callback registration and complete table-zero first opens."""

import ctypes
import hashlib
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
Word = ctypes.c_uint32
WordPointer = ctypes.POINTER(Word)
BytePointer = ctypes.POINTER(ctypes.c_uint8)
Observer = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, WordPointer, ctypes.c_size_t, Word)
VersionObserver = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, Word, Word)
ReadObserver = ctypes.CFUNCTYPE(None, ctypes.c_void_p, Word, Word, Word, Word)
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
SENTINEL = 0xD451BE70
STATE_ADDRESSES = (0xE403B474, 0xE403B478, 0xE403B47C, 0xE403B51C, 0xE400E3D4, 0xE403B488)
POINTER_ARGUMENTS = (0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11)


class Inputs(ctypes.Structure):
    _fields_ = [("parameter_word", Word), ("parameter_byte", Word), ("configuration_source", Word)]


class State(ctypes.Structure):
    _fields_ = [(name, Word) for name in
                ("open_count", "object", "capacity", "configuration", "selected_callback", "old_callback")]


class ReplyPlan(ctypes.Structure):
    _fields_ = [("words", WordPointer), ("count", ctypes.c_size_t)]


class Read(ctypes.Structure):
    _fields_ = [(name, Word) for name in ("pc", "address", "size", "word")]


class ReadPlan(ctypes.Structure):
    _fields_ = [("entries", ctypes.POINTER(Read)), ("count", ctypes.c_size_t)]


class Observers(ctypes.Structure):
    _fields_ = [("acquire", Observer), ("registrar_acquire", Observer),
                ("registrar_diagnostic", Observer), ("registrar_release", Observer),
                ("version", VersionObserver), ("service", Observer),
                ("read", ReadObserver), ("context", ctypes.c_void_p)]


def guarded(value):
    class Guard(ctypes.Structure):
        _fields_ = [("before", ctypes.c_uint64), ("value", type(value)), ("after", ctypes.c_uint64)]
    return Guard(0x713AC924713AC924, value, 0x57DDEF8357DDEF83)


def pointer(guard):
    return ctypes.cast(ctypes.byref(guard, type(guard).value.offset),
                       ctypes.POINTER(type(guard)._fields_[1][1]))


def fixture_bytes(case, phase, address, size):
    for region in case[phase]["memory"]:
        start = int(region["address"], 0)
        data = (bytes.fromhex(region["hex"]) if "hex" in region else
                bytes.fromhex(region["fill"]) * region["size"])
        if start <= address and address + size <= start + len(data):
            return data[address - start:address - start + size]
    raise AssertionError(f"Unmapped fixture bytes: {address:#x}+{size}")


def fixture_word(case, phase, address):
    return int.from_bytes(fixture_bytes(case, phase, address, 4), "little")


def state_words(state):
    return tuple(getattr(state, name) for name, _ in State._fields_)


class Request:
    def __init__(self, case, unaligned=0):
        cpu = int(case["execution"]["version_input"]["word"], 0)
        secondary = fixture_word(case, "setup", 0xE40CC934) if cpu else SENTINEL
        self.service = cpu == 0 or secondary == 1
        response = case["execution"]["mmio_responses"][0]
        self.guards = {
            "inputs": guarded(Inputs(fixture_word(case, "setup", 0x24002000),
                                     fixture_bytes(case, "setup", 0x24002004, 1)[0],
                                     fixture_word(case, "setup", 0xE40CC93C))),
            "state": guarded(State(*(fixture_word(case, "setup", address) for address in STATE_ADDRESSES))),
            "cpu": guarded(Word(cpu)), "secondary": guarded(Word(secondary)),
            "index": guarded(Word(fixture_word(case, "setup", 0xE403B490) if self.service else SENTINEL)),
            "handle": guarded(Word(fixture_word(case, "setup", 0x24003000))),
            "raw": guarded(Word(SENTINEL)),
            "replies": guarded((Word * 6)()),
            "reads": guarded((Read * 2)(Read(int(response["pc"], 0), int(response["address"], 0),
                                               len(bytes.fromhex(response["hex"])),
                                               int.from_bytes(bytes.fromhex(response["hex"]), "little")))),
        }
        for name in ("inputs", "state", "cpu", "secondary", "index", "handle", "raw"):
            setattr(self, name, pointer(self.guards[name]))
        self.words = ctypes.cast(pointer(self.guards["replies"]), WordPointer)
        self.entries = ctypes.cast(pointer(self.guards["reads"]), ctypes.POINTER(Read))
        self.replies = ReplyPlan(self.words, 5 if self.service else 4)
        self.reads = ReadPlan(self.entries, 1)
        self.record_offset = 16 + unaligned
        self.record_storage = (ctypes.c_uint8 * (self.record_offset + 928 + 16))()
        ctypes.memset(self.record_storage, 0xB6, ctypes.sizeof(self.record_storage))
        self.records = ctypes.cast(ctypes.addressof(self.record_storage) + self.record_offset, BytePointer)
        ctypes.memmove(self.records, fixture_bytes(case, "setup", 0xE40DA4C4, 896), 896)
        self.events, self.snapshots, self.contexts = [], [], []
        self.bookkeeping = Word(0)

        def record(context, event):
            self.events.append(event)
            self.snapshots.append((state_words(self.state.contents), bytes(self.records[:928]),
                                   self.handle.contents.value, self.raw.contents.value))
            self.contexts.append(context)
            self.bookkeeping.value += 1

        @Observer
        def observe(context, entry, arguments, count, reply):
            record(context, ("boundary", entry, tuple(arguments[:count]), reply))

        @VersionObserver
        def version(context, site, destination, word):
            record(context, ("version", site, destination, word))

        @ReadObserver
        def read(context, pc, address, size, word):
            record(context, ("read", pc, address, size, word))

        self.observe, self.version, self.read = observe, version, read
        self.observers = Observers(observe, observe, observe, observe, version, observe, read,
                                   ctypes.addressof(self.bookkeeping))

    def arguments(self):
        return [self.inputs, self.state, self.records, 928, self.cpu, self.secondary, self.index,
                self.handle, ctypes.byref(self.replies), ctypes.byref(self.reads),
                ctypes.byref(self.observers), self.raw]

    def storage(self):
        return (bytes(self.replies), bytes(self.reads), bytes(self.observers), bytes(self.record_storage),
                {name: bytes(value) for name, value in self.guards.items()})


class ArmFirstOpenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("ARM first-open tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="arm-first-open-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "arm_first_open.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/arm_first_open.c"), str(ROOT / "src/start4/arm_object.c"),
            "-o", str(library)], check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.arm_first_open_execute
        cls.function.argtypes = [ctypes.POINTER(Inputs), ctypes.POINTER(State), BytePointer, ctypes.c_size_t,
                                WordPointer, WordPointer, WordPointer, WordPointer,
                                ctypes.POINTER(ReplyPlan), ctypes.POINTER(ReadPlan),
                                ctypes.POINTER(Observers), WordPointer]
        cls.function.restype = ctypes.c_int
        cls.registration = cls.library.arm_callback_register
        cls.registration.argtypes = [Word, Word, WordPointer, WordPointer, WordPointer]
        cls.registration.restype = ctypes.c_int
        cls.fixtures = {}
        for name in ("arm-first-open", "arm-callback-registration"):
            path = ROOT / f"tests/vectors/start4/{name}.json"
            cls.fixtures[name] = (hashlib.sha256(path.read_bytes()).hexdigest(), json.loads(path.read_text())["cases"])
        cls.cases = cls.fixtures["arm-first-open"][1]

    def request(self, index=0, unaligned=0):
        return Request(self.cases[index], unaligned)

    def run_request(self, request, expected=OK, arguments=None):
        before = request.storage()
        incoming_raw = request.raw.contents.value
        self.assertEqual(self.function(*(request.arguments() if arguments is None else arguments)), expected)
        if expected != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.events, [])
        self.assertEqual(request.storage()[:3], before[:3])
        for name in request.guards.keys() - {"state", "raw"}:
            self.assertEqual(bytes(request.guards[name]), before[4][name])
        for guard in request.guards.values():
            self.assertEqual((guard.before, guard.after), (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        self.assertEqual(bytes(request.record_storage[:request.record_offset]),
                         before[3][:request.record_offset])
        self.assertEqual(bytes(request.record_storage[request.record_offset + 896:]),
                         before[3][request.record_offset + 896:])
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)] * len(request.events))
        self.assertEqual(request.bookkeeping.value, len(request.events))
        self.assertTrue(all(raw == incoming_raw and handle == 0xA5A5A5A5
                            for _, _, handle, raw in request.snapshots))

    def test_three_registration_fixtures(self):
        digest, cases = self.fixtures["arm-callback-registration"]
        self.assertEqual(digest, "60377c5327f87fb5f95ca4cbed0d438dae5a1d26731a0e02c398c6f00cad7250")
        self.assertEqual(len(cases), 3)
        for case in cases:
            selected = guarded(Word(fixture_word(case, "setup", 0xE400E3D4)))
            old = guarded(Word(fixture_word(case, "setup", 0xE403B488)))
            raw = guarded(Word(SENTINEL))
            self.assertEqual(self.registration(int(case["setup"]["registers"]["r0"], 0),
                                               int(case["setup"]["registers"]["r1"], 0),
                                               pointer(selected), pointer(old), pointer(raw)), OK)
            self.assertEqual(selected.value, fixture_word(case, "expected", 0xE400E3D4))
            self.assertEqual(old.value, fixture_word(case, "expected", 0xE403B488))
            self.assertEqual(raw.value, int(case["expected"]["registers"]["r0"], 0))
            for guard in (selected, old, raw):
                self.assertEqual((guard.before, guard.after), (0x713AC924713AC924, 0x57DDEF8357DDEF83))

    def test_registration_domain_and_storage_errors_preserve_all_words(self):
        controls = [(0, 0, UNSUPPORTED), (0, 0x5F, UNSUPPORTED), (1, 0, UNSUPPORTED),
                    (1, 0x0EC5716F, UNSUPPORTED)]
        controls += [(position, None, INVALID) for position in (2, 3, 4)]
        controls += [(position, ctypes.cast(ctypes.c_size_t(-1).value - 1, WordPointer), BOUNDS)
                     for position in (2, 3, 4)]
        for position, value, expected in controls:
            guards = [guarded(Word(value)) for value in (0, 0xA5A5A5A5, SENTINEL)]
            arguments = [0x5E, 0x0EC5716E, *(pointer(guard) for guard in guards)]
            arguments[position] = value
            before = [bytes(guard) for guard in guards]
            self.assertEqual(self.registration(*arguments), expected)
            self.assertEqual([bytes(guard) for guard in guards], before)
        for field, value in ((0, 1), (0, 0x0EC5716E), (0, 0xFFFFFFFF), (1, 0), (1, 0xA5A5A5A4)):
            words = [Word(0), Word(0xA5A5A5A5), Word(SENTINEL)]
            words[field].value = value
            before = [word.value for word in words]
            self.assertEqual(self.registration(0x5E, 0x0EC5716E, *(ctypes.byref(word) for word in words)),
                             UNSUPPORTED)
            self.assertEqual([word.value for word in words], before)
        for left, right in itertools.combinations(range(3), 2):
            words = [Word(0), Word(0xA5A5A5A5), Word(SENTINEL)]
            arguments = [ctypes.byref(word) for word in words]
            arguments[right] = arguments[left]
            before = [word.value for word in words]
            self.assertEqual(self.registration(0x5E, 0x0EC5716E, *arguments), OVERLAP)
            self.assertEqual([word.value for word in words], before)

    def test_complete_first_open_fixtures_and_every_observer_snapshot(self):
        self.assertEqual(self.fixtures["arm-first-open"][0],
                         "937f35212d420b4c3918b661466d6144152c88ef2180c69da348a15208aa4ce9")
        self.assertEqual(len(self.cases), 3)
        for index, case in enumerate(self.cases):
            for unaligned in (0, 1):
                request = self.request(index, unaligned)
                initial = state_words(request.state.contents)
                self.run_request(request)
                events = []
                stubs = {int(stub["entry"], 0): stub for stub in case["execution"]["stubs"]}
                for event in case["expected"]["events"]:
                    if event["kind"] == "version":
                        events.append(("version", int(event["pc"], 0), int(event["destination"][1:]),
                                       int(event["value"], 0)))
                    elif event["kind"] == "supplied_mmio_read":
                        data = bytes.fromhex(event["hex"])
                        events.append(("read", int(event["pc"], 0), int(event["address"], 0), len(data),
                                       int.from_bytes(data, "little")))
                    else:
                        entry = int(event["entry"], 0)
                        count = {0x0ED17442: 3, 0x0ED65284: 6}.get(entry, 1)
                        reply = stubs[entry]["replies"][event["reply_index"]]["registers"]["r0"]
                        events.append(("boundary", entry, tuple(int(word, 0) for word in event["arguments"][:count]),
                                       int(reply, 0)))
                self.assertEqual(request.events, events)
                final = tuple(fixture_word(case, "expected", address) for address in STATE_ADDRESSES)
                final_records = fixture_bytes(case, "expected", 0xE40DA4C4, 896)
                self.assertEqual(state_words(request.state.contents), final)
                self.assertEqual(bytes(request.records[:896]), final_records)
                self.assertEqual(request.raw.contents.value, int(case["expected"]["registers"]["r0"], 0))
                for phase, (state, records, _, _) in enumerate(request.snapshots):
                    expected_state = (initial if phase == 0 else
                                      (1, 0, *initial[2:]) if phase == 1 else
                                      (1, final[1], *initial[2:]) if phase < 4 else
                                      (*final[:5], initial[5]))
                    self.assertEqual(state, expected_state)
                    self.assertEqual(records, (bytes(896) if phase < 2 else final_records) + b"\xB6" * 32)

    def test_unused_words_and_service_observer_have_no_content_premise(self):
        for index, unused_position in ((0, 5), (1, 6)):
            for value in (None, 0, 2, 0xFFFFFFFF):
                request = self.request(index)
                arguments = request.arguments()
                if value is None:
                    arguments[unused_position] = None
                else:
                    arguments[unused_position].contents.value = value
                if index == 1:
                    request.observers.service = Observer()
                request.raw.contents.value = 0
                self.run_request(request, arguments=arguments)

    def test_required_objects_and_late_observers_precede_all_effects(self):
        for index in range(3):
            for position in POINTER_ARGUMENTS:
                if (index == 0 and position == 5) or (index == 1 and position == 6):
                    continue
                request = self.request(index)
                arguments = request.arguments()
                arguments[position] = None
                self.run_request(request, INVALID, arguments)
            for name, kind in Observers._fields_[:-1]:
                request = self.request(index)
                setattr(request.observers, name, kind())
                self.run_request(request, OK if index == 1 and name == "service" else INVALID)
            for plan, field, kind in (("replies", "words", WordPointer),
                                      ("reads", "entries", ctypes.POINTER(Read))):
                request = self.request(index)
                setattr(getattr(request, plan), field, kind())
                self.run_request(request, INVALID)

    def test_exact_initial_domains_including_nested_record_tail(self):
        for index in range(3):
            for object_name, fields in (("inputs", Inputs._fields_), ("state", State._fields_)):
                for field, _ in fields:
                    request = self.request(index)
                    obj = getattr(request, object_name).contents
                    setattr(obj, field, getattr(obj, field) ^ 1)
                    self.run_request(request, UNSUPPORTED)
            for name in ("cpu", "handle"):
                request = self.request(index)
                getattr(request, name).contents.value ^= 1
                self.run_request(request, UNSUPPORTED)
            for offset in (0, 4, 20, 27, 28, 895):
                request = self.request(index)
                request.records[offset] = 1
                self.run_request(request, UNSUPPORTED)
            request = self.request(index)
            arguments = request.arguments()
            arguments[3] = 895
            self.run_request(request, BOUNDS, arguments)
        for index, name in ((1, "secondary"), (2, "secondary"), (0, "index"), (2, "index")):
            request = self.request(index)
            getattr(request, name).contents.value = 2
            self.run_request(request, UNSUPPORTED)

    def test_all_reply_and_read_premises_are_preflighted(self):
        for index in range(3):
            for slot in range(4 if index == 1 else 5):
                request = self.request(index)
                request.words[slot] = 1
                self.run_request(request, UNSUPPORTED)
            for plan_name in ("replies", "reads"):
                for difference in (-1, 1):
                    request = self.request(index)
                    getattr(request, plan_name).count += difference
                    self.run_request(request, BOUNDS if difference < 0 else UNSUPPORTED)
            for field, _ in Read._fields_:
                request = self.request(index)
                setattr(request.entries[0], field, getattr(request.entries[0], field) ^ 1)
                self.run_request(request, UNSUPPORTED)

    def test_all_objects_unused_words_and_full_array_extents_are_disjoint(self):
        for left, right in itertools.combinations(POINTER_ARGUMENTS, 2):
            request = self.request()
            arguments = request.arguments()
            arguments[right] = ctypes.cast(arguments[left], self.function.argtypes[right])
            self.run_request(request, OVERLAP, arguments)
        for index, unused_position in ((0, 5), (1, 6)):
            for address_kind in ("record-tail", "last-reply", "read-end"):
                request = self.request(index)
                addresses = {"record-tail": ctypes.addressof(request.records.contents) + 924,
                             "last-reply": ctypes.addressof(request.words.contents) + 4 * (request.replies.count - 1),
                             "read-end": ctypes.addressof(request.entries.contents) + ctypes.sizeof(Read) - 4}
                arguments = request.arguments()
                arguments[unused_position] = ctypes.cast(addresses[address_kind], WordPointer)
                self.run_request(request, OVERLAP, arguments)
        for plan_name, field, kind in (("replies", "words", WordPointer),
                                       ("reads", "entries", ctypes.POINTER(Read))):
            for position in POINTER_ARGUMENTS:
                request = self.request()
                arguments = request.arguments()
                setattr(getattr(request, plan_name), field, ctypes.cast(arguments[position], kind))
                self.run_request(request, OVERLAP, arguments)
        request = self.request()
        request.reads.entries = ctypes.cast(request.words, ctypes.POINTER(Read))
        self.run_request(request, OVERLAP)

    def test_pointer_and_plan_multiplication_wrap_precede_content_access(self):
        maximum = ctypes.c_size_t(-1).value
        for index in range(3):
            for position in POINTER_ARGUMENTS:
                request = self.request(index)
                arguments = request.arguments()
                arguments[position] = ctypes.cast(maximum - 1, self.function.argtypes[position])
                self.run_request(request, BOUNDS, arguments)
            for plan_name, field, kind, size in (("replies", "words", WordPointer, 4),
                                                ("reads", "entries", ctypes.POINTER(Read), ctypes.sizeof(Read))):
                request = self.request(index)
                getattr(request, plan_name).count = maximum // size + 1
                self.run_request(request, BOUNDS)
                request = self.request(index)
                setattr(getattr(request, plan_name), field, ctypes.cast(maximum - 1, kind))
                self.run_request(request, BOUNDS)
        request = self.request()
        arguments = request.arguments()
        arguments[3] = maximum
        self.run_request(request, BOUNDS, arguments)


if __name__ == "__main__":
    unittest.main()
