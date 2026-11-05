# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check complete mask rejections, retained state and whole-call validation."""

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

from tests.test_arm_first_open import (
    STATE_ADDRESSES,
    Observer,
    Read,
    ReadObserver,
    ReadPlan,
    ReplyPlan,
    VersionObserver,
    fixture_bytes,
    fixture_word,
)
from tests.test_arm_first_open import Inputs as PrefixInputs
from tests.test_arm_first_open import State as PrefixState
from tests.test_suspend_helpers import (
    BOUNDS,
    INVALID,
    OK,
    OVERLAP,
    POINTER_MAX,
    SENTINEL,
    WORD_MAX,
    Buffer,
    Byte,
    BytePointer,
    Storage,
    View,
    Word,
    region,
)
from tests.test_suspend_registrar import DI, P16, object_bytes, registration_result
from tests.test_suspend_registrar import ReadPlan as P16Plan

ROOT = Path(__file__).resolve().parents[1]
UNSUPPORTED = -2
KEYS = (1, 0x0ED004C6, 0)
RECORD_BASE = 0xE40DA4C4
DRIVER_ADDRESSES = (0xE403B480, 0xE403B520, 0xE403B524, 0xE403B528, 0xE403B52C)


class Inputs(ctypes.Structure):
    _fields_ = [("first_open", PrefixInputs), ("sr", Word), ("version", Word),
                ("secondary", Word), ("opaque", Word)]


class State(ctypes.Structure):
    _fields_ = [("first_open", PrefixState), ("driver_table", Word), ("driver_words", Word * 4)]


class Observers(ctypes.Structure):
    _fields_ = [("acquire", Observer), ("registrar_acquire", Observer),
                ("registrar_diagnostic", Observer), ("registrar_release", Observer),
                ("version", VersionObserver), ("read", ReadObserver), ("write", ReadObserver),
                ("release", Observer), ("di", DI), ("p16_read", P16), ("p16_write", P16),
                ("context", ctypes.c_void_p)]


def record_bytes(profile=0, tail=b"record tail"):
    data = bytearray(896)
    if profile == 1:
        data[:4] = RECORD_BASE.to_bytes(4, "little")
    if profile == 2:
        words = (0, 0x55667788, 0x11223344, 0xAABBCCDD, 0x89ABCDEF, 0xDEADBEEF, 0x76543210)
        data[:28] = b"".join(word.to_bytes(4, "little") for word in words)
    return bytes(data) + tail


def replaced(snapshot, storage, label, value):
    result = dict(snapshot)
    changed = bytearray(result[label])
    offset = storage[label].offset
    changed[offset:offset + len(value)] = value
    result[label] = bytes(changed)
    return result


class Request:
    def __init__(self, parameter=0x400, switch=2, source=0x12345678,
                 sr=0, version=0x40, opaque=0xD3D3D3D3, profile=0,
                 callback=0x0EC3EA48, records=None, data=None,
                 masks=b"\0\0\0\x40\0\0\0\0mask tail", name=b"parent/irq.c\0tail",
                 logging=2, p16=(0,), read_word=0x11223344, handle=0xA5A5A5A5,
                 unaligned=0, initial_state=None):
        self.storage = {}
        self.events = []
        self.contexts = []
        self.bookkeeping = Word()
        self.data = object_bytes(tail=b"object tail") if data is None else data
        self.records = record_bytes(profile) if records is None else records
        self.name_bytes = name
        self.p16 = p16

        def add(label, value, offset=0):
            self.storage[label] = Storage(value, offset)
            return self.storage[label].pointer

        def view(label, data, kind):
            pointer = add(label + "_bytes", data, unaligned)
            return add(label, kind(pointer if data else None, len(data)))

        def observe(kind, *arguments):
            context, *values = arguments
            self.contexts.append(context)
            self.bookkeeping.value += 1
            self.events.append((kind, tuple(values), self.snapshot()))

        boundary = Observer(lambda context, entry, words, count, reply:
                            observe("boundary", context, entry, tuple(words[:count]), reply))
        self.callbacks = (
            boundary, boundary, boundary, boundary,
            VersionObserver(lambda *args: observe("version", *args)),
            ReadObserver(lambda *args: observe("read", *args)),
            ReadObserver(lambda *args: observe("write", *args)), boundary,
            DI(lambda *args: observe("di", *args)),
            P16(lambda *args: observe("p16_read", *args)),
            P16(lambda *args: observe("p16_write", *args)),
        )
        inputs = add("inputs", Inputs(PrefixInputs(parameter, switch, source), sr, version, 0, opaque))
        if initial_state is None:
            initial_state = State(PrefixState(0, 0xA5A5A5A5, 0xABCD, 0xDEADBEEF,
                                              callback, 0xA5A5A5A5), 0x87654321,
                                  (Word * 4)(0x10203040, 0x5678, 0x9ABC, 0xDEF0))
        state = add("state", initial_state)
        records_pointer = add("records", self.records, unaligned)
        masks_view = view("masks", masks, Buffer)
        object_view = view("object", self.data, Buffer)
        name_view = None if name is None else view("name", name, View)
        logging_pointer = None if logging is None else add("logging", Byte(logging))
        handle_pointer = add("handle", Word(handle))
        reply_words = add("reply_words", (Word * 6)())
        replies = add("replies", ReplyPlan(ctypes.cast(reply_words, ctypes.POINTER(Word)), 5))
        read_entries = add("read_entries", (Read * 2)(Read(0x0EC59E12, 0x7E00B44C, 4, read_word)))
        reads = add("reads", ReadPlan(ctypes.cast(read_entries, ctypes.POINTER(Read)), 1))
        p16_words = add("p16_words", (Word * max(1, len(p16)))(*p16))
        p16_reads = add("p16_reads", P16Plan(ctypes.cast(p16_words, ctypes.POINTER(Word)), len(p16)))
        observers = add("observers", Observers(*self.callbacks, ctypes.addressof(self.bookkeeping)))
        raw = add("raw", Word(SENTINEL))
        self.names = ["inputs", "state", "records", None, "masks", "object", "name", "logging",
                      "handle", "replies", "reads", "p16_reads", "observers", "raw"]
        self.arguments = [inputs, state, records_pointer, len(self.records), masks_view, object_view,
                          name_view, logging_pointer, handle_pointer, replies, reads, p16_reads, observers, raw]

    def object(self, name):
        return self.storage[name].pointer.contents

    def snapshot(self):
        return {name: storage.snapshot() for name, storage in self.storage.items()}

    def redirect(self, name, address):
        if name.endswith("_bytes"):
            self.object(name.removesuffix("_bytes")).bytes = ctypes.cast(address, BytePointer)
        elif name in ("reply_words", "p16_words", "read_entries"):
            plan, field, kind = {"reply_words": ("replies", "words", Word),
                                 "p16_words": ("p16_reads", "words", Word),
                                 "read_entries": ("reads", "entries", Read)}[name]
            setattr(self.object(plan), field, ctypes.cast(address, ctypes.POINTER(kind)))
        else:
            index = self.names.index(name)
            self.arguments[index] = ctypes.cast(address, type(self.arguments[index]))


class ArmFirstOpenMaskedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Masked first-open tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="arm-first-open-masked-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "arm_first_open_masked.so"
        sources = ("arm_first_open_masked", "arm_first_open", "arm_object", "driver_open",
                   "suspend_registrar", "suspend_helpers", "mask_operations")
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            *(str(ROOT / f"src/start4/{source}.c") for source in sources), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.arm_first_open_masked
        cls.function.argtypes = [ctypes.POINTER(Inputs), ctypes.POINTER(State), BytePointer, ctypes.c_size_t,
                                ctypes.POINTER(Buffer), ctypes.POINTER(Buffer), ctypes.POINTER(View),
                                BytePointer, ctypes.POINTER(Word), ctypes.POINTER(ReplyPlan),
                                ctypes.POINTER(ReadPlan), ctypes.POINTER(P16Plan),
                                ctypes.POINTER(Observers), ctypes.POINTER(Word)]
        cls.function.restype = ctypes.c_int

    def run_request(self, request, status=OK):
        before = request.snapshot()
        inputs = Inputs.from_buffer_copy(request.storage["inputs"].payload())
        state = State.from_buffer_copy(request.storage["state"].payload())
        self.assertEqual(self.function(*request.arguments), status)
        if status != OK:
            self.assertEqual(request.snapshot(), before)
            self.assertEqual((request.events, request.contexts, request.bookkeeping.value), ([], [], 0))
            return
        events = []

        def event(kind, values, snapshot):
            events.append((kind, values, snapshot))

        def state_snapshot(snapshot):
            return replaced(snapshot, request.storage, "state", bytes(state))

        event("boundary", (0x0ED64D02, (0xE403B470,), 0), before)
        state.first_open.open_count = 1
        state.first_open.object = 0
        manager = state_snapshot(before)
        event("boundary", (0x0ED64D02, (0xE40DA4C0,), 0), manager)
        record = bytearray(request.records)
        slot = next(index for index in range(32) if record[index * 28:index * 28 + 4] == b"\0" * 4)
        identity = RECORD_BASE + 28 * slot
        for offset, value in ((0, identity), (4, slot), (20, 0x0EC59E8C), (24, 0x158)):
            record[slot * 28 + offset:slot * 28 + offset + 4] = value.to_bytes(4, "little")
        state.first_open.object = identity
        registered = state_snapshot(replaced(manager, request.storage, "records", record))
        event("boundary", (0x0ED17442, (0x4000, 0x0ED7C990, identity), 0), registered)
        event("boundary", (0x0ED64D3A, (0xE40DA4C0,), 0), registered)
        state.first_open.capacity = inputs.first_open.parameter_word
        selector = (0x80, 0x100, 0x200, 0x400).index(inputs.first_open.parameter_word)
        state.first_open.configuration = ((inputs.first_open.configuration_source & 0xFFF0001C)
                                          | selector | 0xF000 | (0, 0x800, 0xC00)[inputs.first_open.parameter_byte])
        configured = state_snapshot(registered)
        event("version", (0x0EC59DE0, 4, inputs.version), configured)
        read = request.object("read_entries")[0]
        event("read", (read.pc, read.address, read.size, read.word), configured)
        prior = state.first_open.selected_callback
        state.first_open.old_callback = 0 if prior == 0x0EC3EA48 else prior
        state.first_open.selected_callback = 0x0EC5716E
        callbacks = state_snapshot(configured)
        event("write", (0x0EC59E34, 0x7E00B9BC, 4, 8), callbacks)
        state.driver_words[:] = (1, 0, 1, 0)
        words = state_snapshot(callbacks)
        event("write", (0x0EC59E44, 0x7E00B9BC, 4, 1), words)
        state.driver_table = 0x0EDFA4DC
        table = state_snapshot(words)
        saved = (inputs.sr & 0xFFFFFFF0) | (6 if prior == 0x0EC3EA48 else 0)
        event("di", (saved, saved & ~0x40000000), table)
        for value in request.p16:
            event("p16_read", (value,), table)
        expected_object, _ = registration_result(request.data, KEYS, saved, request.name_bytes)
        complete = replaced(table, request.storage, "object_bytes", expected_object)
        event("p16_write", (saved,), complete)
        event("boundary", (0x0ED64D3A, (0xE403B470,), 0), complete)
        self.assertEqual(request.events, events)
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)] * len(events))
        self.assertEqual(request.bookkeeping.value, len(events))
        self.assertEqual(request.snapshot(), replaced(complete, request.storage, "raw", bytes(Word(1))))

    def test_five_complete_public_calls(self):
        fixtures = (("arm-first-open-post-registrar", "9ac0b3e66c591013cc5b51c54968238cb2759d2292f3aead90c6d3c622a06e7c"),
                    ("arm-first-open-masked", "9723fc811759aa8f791406529f51295ea99ec81ed5b3aeba1dbc07e2b55aab5f"))
        count = 0
        for filename, digest in fixtures:
            path = ROOT / f"tests/vectors/start4/{filename}.json"
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            for case in json.loads(path.read_text())["cases"]:
                if case["id"] == "first-open-service-prefix":
                    continue
                count += 1
                with self.subTest(case=case["id"]):
                    setup = lambda address, case=case: fixture_word(case, "setup", address)
                    data = fixture_bytes(case, "setup", setup(0xE40014E4), 2936)
                    name = None
                    logging = None
                    try:
                        available, offset = region(case, "setup", 0xE4009FE0)
                        name = available[offset:]
                    except AssertionError:
                        pass
                    if int.from_bytes(data[0xB5C:0xB60], "little") < 40:
                        logging = fixture_bytes(case, "setup", 0xE4105970, 1)[0]
                    response = case["execution"]["mmio_responses"][0]
                    initial = State(PrefixState(*(setup(address) for address in STATE_ADDRESSES)),
                                    setup(DRIVER_ADDRESSES[0]),
                                    (Word * 4)(*(setup(address) for address in DRIVER_ADDRESSES[1:])))
                    request = Request(parameter=setup(0x24002000),
                        switch=fixture_bytes(case, "setup", 0x24002004, 1)[0], source=setup(0xE40CC93C),
                        sr=int(case["setup"]["registers"].get("sr", "0"), 0),
                        version=int(case["execution"]["version_input"]["word"], 0), opaque=setup(0xE403B484),
                        records=fixture_bytes(case, "setup", RECORD_BASE, 896), data=data,
                        masks=fixture_bytes(case, "setup", 0xE40CB498, 8), name=name, logging=logging,
                        p16=tuple(int(event["value"], 0) for event in case["expected"]["events"]
                                  if event["kind"] == "p16_read"),
                        read_word=int.from_bytes(bytes.fromhex(response["hex"]), "little"),
                        handle=setup(0x24003000), initial_state=initial, unaligned=3)
                    self.run_request(request)
                    actual = request.object("state")
                    self.assertEqual(bytes(actual.first_open), bytes(PrefixState(*(
                        fixture_word(case, "expected", address) for address in STATE_ADDRESSES))))
                    self.assertEqual((actual.driver_table, *actual.driver_words), tuple(
                        fixture_word(case, "expected", address) for address in DRIVER_ADDRESSES))
                    self.assertEqual(request.storage["records"].payload(), fixture_bytes(case, "expected", RECORD_BASE, 896))
                    self.assertEqual(request.storage["object_bytes"].payload(),
                                     fixture_bytes(case, "expected", setup(0xE40014E4), 2936))
                    self.assertEqual(request.object("raw").value, int(case["expected"]["registers"]["r0"], 0))
                    expected_events = []
                    for event in case["expected"]["events"]:
                        kind = event["kind"]
                        if kind == "stub":
                            entry = int(event["entry"], 0)
                            size = 3 if entry == 0x0ED17442 else 1
                            expected_events.append(("boundary", (entry,
                                tuple(int(word, 0) for word in event["arguments"][:size]), 0)))
                        elif kind == "version":
                            expected_events.append((kind, (int(event["pc"], 0),
                                int(event["destination"][1:]), int(event["value"], 0))))
                        elif kind in ("supplied_mmio_read", "mmio_write"):
                            payload = bytes.fromhex(event["hex"])
                            expected_events.append(("read" if kind == "supplied_mmio_read" else "write",
                                (int(event["pc"], 0), int(event["address"], 0), len(payload),
                                 int.from_bytes(payload, "little"))))
                        elif kind == "irq_disable":
                            expected_events.append(("di", (int(event["sr_before"], 0), int(event["sr_after"], 0))))
                        else:
                            self.assertIn(kind, ("p16_read", "p16_write"))
                            expected_events.append((kind, (int(event["value"], 0),)))
                    self.assertEqual([(kind, values) for kind, values, _ in request.events], expected_events)
        self.assertEqual(count, 5)

    def test_cartesian_parameters_profiles_and_full_width_words(self):
        randomizer = random.Random(0xF10C)
        for parameter, switch, profile, callback in itertools.product(
                (0x80, 0x100, 0x200, 0x400), range(3), range(3), (0x0EC3EA48, 0x11223344)):
            with self.subTest(parameter=parameter, switch=switch, profile=profile, callback=callback):
                words = [randomizer.getrandbits(32) for _ in range(12)]
                state = State(PrefixState(0, 0xA5A5A5A5, words[5], words[6], callback, 0xA5A5A5A5),
                              words[7], (Word * 4)(*words[8:]))
                self.run_request(Request(parameter=parameter, switch=switch, profile=profile,
                    source=words[0], sr=words[1], version=words[2] | 0x40, opaque=words[3],
                    read_word=words[4], handle=words[5], initial_state=state, unaligned=profile + 1,
                    masks=(words[6] | 0x40000000).to_bytes(4, "little") + words[7].to_bytes(4, "little") + b"tail"))

    def test_general_registrar_counts_matches_names_and_busy_streams(self):
        randomizer = random.Random(0x5716E)
        for count in range(40):
            records = [(randomizer.randrange(256), randomizer.getrandbits(32), randomizer.getrandbits(32))
                       for _ in range(count)]
            for match in (False, True) if count else (False,):
                if match:
                    records[count // 2] = KEYS
                for name in (None, b"unterminated") if match else (
                        b"\0", b"parent/\0", b"prefix\\" + bytes(range(128, 160)) + b"\0ignored"):
                    self.run_request(Request(data=object_bytes(count, records, b"preserved", fill=count),
                        name=name, logging=count % 4, sr=randomizer.getrandbits(32),
                        callback=(0x11223344 if count % 2 else 0x0EC3EA48), p16=(1,) * (count % 7) + (0,)))
        for count, name, logging in itertools.product((40, 41, 0x7FFFFFFF), (None, b"", b"no NUL"), (None, 4, 255)):
            self.run_request(Request(data=object_bytes(count), name=name, logging=logging))

    def test_invalid_domains_are_rejected_before_effects(self):
        for field, values in (("parameter_word", (0, 0x81, 0x800, 0x10000080)),
                              ("parameter_byte", (3, 256, WORD_MAX))):
            for value in values:
                request = Request()
                setattr(request.object("inputs").first_open, field, value)
                self.run_request(request, UNSUPPORTED)
        for field, value in (("version", 0), ("version", 0xFFFFFFBF), ("secondary", 1)):
            request = Request()
            setattr(request.object("inputs"), field, value)
            self.run_request(request, UNSUPPORTED)
        for field, value in (("open_count", 1), ("object", 0), ("selected_callback", 0),
                              ("selected_callback", 0x11223345), ("old_callback", 0)):
            request = Request()
            setattr(request.object("state").first_open, field, value)
            self.run_request(request, UNSUPPORTED)
        for offset in (0, 4, 27, 28, 895):
            request = Request()
            request.storage["records"].pointer[offset] ^= 1
            self.run_request(request, UNSUPPORTED)
        request = Request(masks=b"\xff\xff\xff\xbf" + b"\xff" * 4)
        self.run_request(request, UNSUPPORTED)
        full = bytearray(896)
        for index in range(32):
            full[index * 28:index * 28 + 8] = ((RECORD_BASE + index * 28).to_bytes(4, "little")
                                               + index.to_bytes(4, "little"))
        self.run_request(Request(records=bytes(full)), UNSUPPORTED)

    def test_conditional_name_logging_count_and_p16_failures_are_atomic(self):
        for name, expected in ((None, INVALID), (b"", INVALID), (b"unterminated", BOUNDS)):
            self.run_request(Request(name=name), expected)
        request = Request(name=b"x")
        request.object("name").length = 0
        self.run_request(request, BOUNDS)
        for logging in (None, 4, 255):
            self.run_request(Request(logging=logging), INVALID)
        for count in (0x80000000, WORD_MAX):
            self.run_request(Request(data=object_bytes(count)), BOUNDS)
        for reads in ((), (1,), (2, 0), (0, 0), (1, 0, 1), (WORD_MAX, 0)):
            self.run_request(Request(p16=reads), BOUNDS if not reads else INVALID)

    def test_missing_storage_observers_and_each_late_plan_entry_are_atomic(self):
        for index, name in enumerate(Request().names):
            if name is not None:
                request = Request()
                request.arguments[index] = None
                self.run_request(request, INVALID)
        for name, kind in Observers._fields_[:-1]:
            request = Request()
            setattr(request.object("observers"), name, kind())
            self.run_request(request, INVALID)
        for name in ("masks_bytes", "object_bytes", "name_bytes", "reply_words", "read_entries", "p16_words"):
            request = Request()
            request.redirect(name, 0)
            self.run_request(request, INVALID)
        for slot in range(5):
            request = Request()
            request.object("reply_words")[slot] = 1
            self.run_request(request, UNSUPPORTED)
        for label, count in (("replies", 5), ("reads", 1)):
            for difference in (-1, 1):
                request = Request()
                request.object(label).count = count + difference
                self.run_request(request, BOUNDS if difference < 0 else UNSUPPORTED)
        for field in ("pc", "address", "size"):
            request = Request()
            entry = request.object("read_entries")[0]
            setattr(entry, field, getattr(entry, field) ^ 1)
            self.run_request(request, UNSUPPORTED)

    def test_all_typed_storage_requires_natural_alignment(self):
        request = Request()
        names = [name for name in request.names if name not in (None, "records", "logging")]
        names += ["reply_words", "read_entries", "p16_words"]
        for name in names:
            with self.subTest(name=name):
                request = Request()
                shifted = Storage(request.storage[name].payload(), 1)
                request.storage["misaligned"] = shifted
                request.redirect(name, shifted.address)
                self.run_request(request, INVALID)

    def test_every_caller_span_pair_including_unused_views_is_disjoint(self):
        names = [name for name in Request().names if name is not None]
        names += ["masks_bytes", "object_bytes", "name_bytes", "reply_words", "read_entries", "p16_words"]
        for left, right in itertools.combinations(names, 2):
            with self.subTest(left=left, right=right):
                request = Request(data=object_bytes(40))
                request.redirect(right, request.storage[left].address)
                self.run_request(request, OVERLAP)
        for name, tail in (("records", 896), ("masks_bytes", 8), ("object_bytes", 2936), ("name_bytes", 16)):
            request = Request(data=object_bytes(40, tail=b"unchanged object tail"), name=b"unused name long enough")
            request.redirect("handle", request.storage[name].address + tail)
            self.run_request(request, OVERLAP)

    def test_extent_and_address_bounds_precede_any_content_access(self):
        for name, minimum in (("masks", 8), ("object", 2936)):
            for length in (minimum - 1, WORD_MAX + 1):
                request = Request()
                request.object(name).length = length
                self.run_request(request, BOUNDS)
        for length in (895, WORD_MAX + 1):
            request = Request()
            request.arguments[3] = length
            self.run_request(request, BOUNDS)
        for label, field, value in (("name", "length", WORD_MAX + 1),
                                    ("replies", "count", POINTER_MAX // 4 + 1),
                                    ("reads", "count", POINTER_MAX // ctypes.sizeof(Read) + 1),
                                    ("p16_reads", "count", WORD_MAX // 4 + 1)):
            request = Request()
            setattr(request.object(label), field, value)
            self.run_request(request, BOUNDS)
        names = [name for name in Request().names if name is not None]
        names += ["masks_bytes", "object_bytes", "name_bytes", "reply_words", "read_entries", "p16_words"]
        for name in names:
            with self.subTest(name=name):
                request = Request()
                alignment = ctypes.alignment(request.storage[name].type)
                request.redirect(name, POINTER_MAX - (alignment - 1))
                self.run_request(request, BOUNDS)


if __name__ == "__main__":
    unittest.main()
