# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check service word arithmetic, complete observations and storage preflight."""

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
OK, INVALID, BOUNDS, OVERLAP = 0, -1, -3, -4
VERSION, READ, WRITE = 0, 1, 2
WORD_MAX = 0xFFFFFFFF
POINTER_MAX = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
SENTINEL = 0x7965C3E1
Observe = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, Word, Word)


class Inputs(ctypes.Structure):
    _fields_ = [("opaque", Word), ("code", Word), ("value", Word)]


class Plan(ctypes.Structure):
    _fields_ = [("version", Word), ("read_address", Word),
                ("old_word", Word), ("write_address", Word)]


class Observer(ctypes.Structure):
    _fields_ = [("observe", Observe), ("context", ctypes.c_void_p)]


class Storage:
    def __init__(self, value):
        self.backing = (ctypes.c_uint64 * 16)()
        ctypes.memset(self.backing, 0xA5, ctypes.sizeof(self.backing))
        self.address = ctypes.addressof(self.backing) + 32
        ctypes.memmove(self.address, ctypes.byref(value), ctypes.sizeof(value))
        self.pointer = ctypes.cast(self.address, ctypes.POINTER(type(value)))

    def snapshot(self):
        return bytes(self.backing)


def selected_address(code, version):
    return 0x7E002010 + 2048 * (version // 65536 % 16) + 4 * (code // 8 % 8)


def stored_word(code, value, old_word):
    first = (code % 8) * 4
    result = 0
    for bit in range(32):
        retained = (old_word >> bit) & 1 if not first <= bit < first + 4 else 0
        supplied = (value >> (bit - first)) & 1 if bit >= first else 0
        result += (retained | supplied) * (2 ** bit)
    return result


class Call:
    names = ("request", "plan", "observer", "raw")

    def __init__(self, opaque=0xD3D3D3D3, code=0x5E, value=1,
                 version=0x40, old_word=0xA5A5A5A5, raw=SENTINEL):
        self.storage = {}
        self.events = []
        self.snapshots = []
        self.contexts = []
        self.context_words = []
        self.inspect_context = False

        def observe(context, event, address, word):
            self.events.append((event, address, word))
            self.snapshots.append(self.snapshot())
            self.contexts.append(context)
            if self.inspect_context:
                self.context_words.append(ctypes.cast(context, ctypes.POINTER(Word)).contents.value)

        self.callback = Observe(observe)
        address = selected_address(code, version)
        values = (Inputs(opaque, code, value), Plan(version, address, old_word, address),
                  Observer(self.callback, None), Word(raw))
        for name, item in zip(self.names, values):
            self.storage[name] = Storage(item)
        self.arguments = [self.storage[name].pointer for name in self.names]

    def object(self, name):
        return self.arguments[self.names.index(name)].contents

    def snapshot(self):
        return {name: storage.snapshot() for name, storage in self.storage.items()}

    def redirect(self, name, address):
        index = self.names.index(name)
        self.arguments[index] = ctypes.cast(address, type(self.arguments[index]))


class ServiceWordUpdateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("Service word tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="service-word-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "service_word_update.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            str(ROOT / "src/start4/service_word_update.c"), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.service_word_update
        cls.function.argtypes = [ctypes.POINTER(kind) for kind in (Inputs, Plan, Observer, Word)]
        cls.function.restype = ctypes.c_int
        path = ROOT / "tests/vectors/start4/service-word-update.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.cases = json.loads(path.read_text())["cases"]

    def run_call(self, call, status=OK, expected=None, raw=0):
        before = call.snapshot()
        if status == OK:
            context = call.object("observer").context
            if expected is None:
                request, plan = call.object("request"), call.object("plan")
                address = selected_address(request.code, plan.version)
                expected = [(VERSION, 0, plan.version), (READ, address, plan.old_word),
                            (WRITE, address, stored_word(request.code, request.value, plan.old_word))]
        self.assertEqual(self.function(*call.arguments), status)
        if status != OK:
            self.assertEqual(call.events, [])
            self.assertEqual(call.snapshot(), before)
            return
        self.assertEqual(call.events, expected)
        self.assertEqual(call.snapshots, [before] * 3)
        self.assertEqual(call.contexts, [context] * 3)
        self.assertEqual(call.object("raw").value, raw)
        result_address = ctypes.addressof(call.object("raw"))
        after = dict(before)
        for name, storage in call.storage.items():
            offset = result_address - ctypes.addressof(storage.backing)
            if 0 <= offset <= ctypes.sizeof(storage.backing) - 4:
                data = bytearray(after[name])
                data[offset:offset + 4] = raw.to_bytes(4, sys.byteorder)
                after[name] = bytes(data)
        self.assertEqual(call.snapshot(), after)

    def test_complete_public_fixtures(self):
        self.assertEqual(self.fixture_hash,
                         "416aeae16ca949d804a282a4d38c6797fb9fc27c41bbba4b2d5f5dfa3812ee7d")
        self.assertEqual(len(self.cases), 9)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                registers = case["setup"]["registers"]
                execution = case["execution"]
                self.assertEqual(len(execution["mmio_responses"]), 1)
                self.assertEqual(len(execution["mmio_write_addresses"]), 1)
                read = execution["mmio_responses"][0]
                call = Call(*(int(registers[f"r{index}"], 0) for index in range(3)),
                            int(execution["version_input"]["word"], 0),
                            int.from_bytes(bytes.fromhex(read["hex"]), "little"))
                call.object("plan").read_address = int(read["address"], 0)
                call.object("plan").write_address = int(execution["mmio_write_addresses"][0], 0)
                events = []
                for event in case["expected"]["events"]:
                    if event["kind"] == "version":
                        events.append((VERSION, 0, int(event["value"], 0)))
                    else:
                        kind = {"supplied_mmio_read": READ, "mmio_write": WRITE}[event["kind"]]
                        events.append((kind, int(event["address"], 0),
                                       int.from_bytes(bytes.fromhex(event["hex"]), "little")))
                self.run_call(call, expected=events, raw=int(case["expected"]["registers"]["r0"], 0))

    def test_every_bank_word_and_shift_with_full_width_values(self):
        values = (0, 0xF, 0x10, 0x80000001, WORD_MAX)
        randomizer = random.Random(0x7E002010)
        for bank, code, value in itertools.product(range(16), range(64), values):
            with self.subTest(bank=bank, code=code, value=value):
                self.run_call(Call(randomizer.getrandbits(32), code, value, bank << 16,
                                   randomizer.getrandbits(32)))

    def test_every_value_bit_survives_or_truncates_at_each_shift(self):
        for field, bit, old in itertools.product(range(8), range(32), (0, WORD_MAX, 0xA5A5A5A5)):
            with self.subTest(field=field, bit=bit, old=old):
                self.run_call(Call(code=field, value=1 << bit, old_word=old))

    def test_general_random_words(self):
        randomizer = random.Random(0xCEC006D0)
        for index in range(2048):
            with self.subTest(index=index):
                self.run_call(Call(*(randomizer.getrandbits(32) for _ in range(6))))

    def test_ignored_code_version_and_opaque_bits(self):
        for bank, code in itertools.product(range(16), range(64)):
            baseline = Call(0, code, 0xF0EDCBA9, bank << 16, 0x12345678)
            self.run_call(baseline)
            alias = Call(WORD_MAX, code | 0xFFFFFFC0, 0xF0EDCBA9,
                         (bank << 16) | 0xFFF0FFFF, 0x12345678)
            expected = [(VERSION, 0, alias.object("plan").version)] + baseline.events[1:]
            self.run_call(alias, expected=expected)

    def test_observer_can_inspect_incoming_result_through_context(self):
        for incoming in (0, 1, SENTINEL, WORD_MAX):
            call = Call(raw=incoming)
            call.object("observer").context = call.storage["raw"].address
            call.inspect_context = True
            self.run_call(call)
            self.assertEqual(call.context_words, [incoming] * 3)
        call = Call()
        call.object("observer").context = POINTER_MAX
        self.run_call(call)

    def test_missing_and_misaligned_objects(self):
        for name in Call.names:
            for missing in (True, False):
                with self.subTest(name=name, missing=missing):
                    call = Call()
                    call.redirect(name, None if missing else call.storage[name].address + 1)
                    self.run_call(call, INVALID)

    def test_complete_typed_spans_cannot_wrap(self):
        for name, kind in zip(Call.names, (Inputs, Plan, Observer, Word)):
            with self.subTest(name=name):
                call = Call()
                call.redirect(name, POINTER_MAX - ctypes.alignment(kind) + 1)
                self.run_call(call, BOUNDS)

    def test_all_object_pairs_reject_full_and_partial_overlap(self):
        for left, right in itertools.permutations(Call.names, 2):
            template = Call()
            left_size = ctypes.sizeof(template.object(left))
            right_type = type(template.object(right))
            alignment = ctypes.alignment(right_type)
            for offset in range(-ctypes.sizeof(right_type) + alignment, left_size, alignment):
                with self.subTest(left=left, right=right, offset=offset):
                    call = Call()
                    call.redirect(right, call.storage[left].address + offset)
                    self.run_call(call, OVERLAP)

    def test_adjacent_disjoint_objects_are_valid(self):
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

    def test_missing_observer_and_invalid_addresses_emit_nothing(self):
        call = Call()
        call.object("observer").observe = Observe()
        self.run_call(call, INVALID)
        for field in ("read_address", "write_address"):
            for wrong in (0, 1, 0x7E002018, 0x7E00201D, 0x7E009830, WORD_MAX):
                with self.subTest(field=field, wrong=wrong):
                    call = Call()
                    setattr(call.object("plan"), field, wrong)
                    self.run_call(call, INVALID)
        call = Call()
        call.object("plan").read_address = 0
        call.object("plan").write_address = 0
        self.run_call(call, INVALID)


if __name__ == "__main__":
    unittest.main()
