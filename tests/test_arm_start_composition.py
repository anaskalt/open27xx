# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare whole ARM start calls and evidence-only lower-return prefixes."""

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

from tests import test_arm_control as arm
from tests import test_clock_composition as clock
from tests import test_clock_driver as driver
from tests import test_clock_request as manager
from tests import test_resource_composition as lower

ROOT = Path(__file__).resolve().parents[1]
Word = driver.Word
OK, INVALID, UNSUPPORTED, BOUNDS, OVERLAP = 0, -1, -2, -3, -4
OBJECT_INDICES = (0, 1, 2, 4, 5, 7, 8, 9, 10, 11, 13, 14)


class Inputs(ctypes.Structure):
    _fields_ = [("handle", Word), ("mutex_identity", Word), ("resource", lower.Inputs)]


class Plan(ctypes.Structure):
    _fields_ = [("resource", lower.Plan), ("acquire", lower.Provider),
                ("release", lower.Provider), ("context", ctypes.c_void_p)]


class Result(ctypes.Structure):
    _fields_ = [("resource", lower.Result), ("higher_raw", Word)]


class Request(lower.Request):
    def __init__(self, case):
        gp = int(case["setup"]["registers"]["gp"], 0)
        get = lambda offset: driver.fixture_word(case, "setup", gp + offset)
        super().__init__(case, identity=get(0x3B478), scratch_address=0x2400FF78)
        self.higher_inputs = Inputs(int(case["setup"]["registers"]["r0"], 0),
                                    gp + 0x3B470, self.inputs)
        self.inputs = self.higher_inputs.resource
        self.higher_plan = Plan(self.plan, self.provider, self.provider,
                                ctypes.addressof(self.bookkeeping))
        self.plan = self.higher_plan.resource
        self.guards["start"] = driver.guarded(arm.StartState(*(get(offset) for offset in
            (0x3B474, 0x3B518, 0x3B494, 0x3B478))))
        self.start = self.guards["start"].value
        self.guards["result"] = driver.guarded(Result(self.result.contents, driver.SENTINEL))
        self.result = driver.value_pointer(self.guards["result"])

    def arguments(self):
        arguments = super().arguments()
        arguments[0] = ctypes.byref(self.higher_inputs)
        arguments[12] = ctypes.byref(self.higher_plan)
        arguments.insert(1, ctypes.byref(self.start))
        return arguments

    def storage(self):
        return tuple(bytes(value) for value in (self.higher_inputs, self.higher_plan,
                     *self.arrays, *self.guards.values()))


class ArmStartCompositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise RuntimeError("ARM-start composition tests require a host C compiler; set CC")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="arm-start-composition-", dir=build)
        cls.addClassCleanup(temporary.cleanup)
        library = Path(temporary.name) / "arm_start_composition.so"
        subprocess.run(compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-ffreestanding", "-fno-builtin", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            *(str(ROOT / "src/start4" / name) for name in
              ("arm_start_composition.c", "resource_composition.c", "clock_composition.c",
               "clock_driver.c", "arm_control.c")), "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(library))
        cls.function = cls.library.arm_start_composition_execute
        cls.function.argtypes = [ctypes.POINTER(Inputs), ctypes.POINTER(arm.StartState),
            manager.BytePointer, ctypes.c_size_t, ctypes.POINTER(lower.State), manager.BytePointer,
            ctypes.c_size_t, ctypes.POINTER(manager.State), ctypes.POINTER(driver.SourceState),
            ctypes.POINTER(driver.DividerState), driver.WordPointer, manager.BytePointer,
            ctypes.c_size_t, ctypes.POINTER(Plan), ctypes.POINTER(Result)]
        cls.function.restype = ctypes.c_int
        cls.cases = json.loads((ROOT / "tests/vectors/start4/arm-start-composition.json").read_text())["cases"]

    def request(self, index=0):
        return Request(self.cases[index])

    def run_request(self, request, status=OK, arguments=None):
        before = request.storage()
        self.assertEqual(self.function(*(request.arguments() if arguments is None else arguments)), status)
        if status != OK:
            self.assertEqual(request.storage(), before)
            self.assertEqual(request.events, [])
        else:
            self.assertEqual(request.storage()[:7], before[:7])
        for storage in request.guards.values():
            self.assertEqual((storage.before, storage.after), (0x713AC924713AC924, 0x57DDEF8357DDEF83))
        for name, offset in (("records", 896), ("manager", 1156), ("scratch", 8)):
            self.assertEqual(bytes(getattr(request, name)[offset:]), b"\x53" * 16)
        self.assertEqual(request.contexts, [ctypes.addressof(request.bookkeeping)] * len(request.events))
        self.assertEqual(request.bookkeeping.value, len(request.events))
        self.assertTrue(all(snapshot["result"] == bytes([0xA5]) * ctypes.sizeof(Result)
                            for snapshot in request.snapshots))

    def compare_memory(self, case, snapshot):
        resource = lower.State.from_buffer_copy(snapshot["resource"])
        state = manager.State.from_buffer_copy(snapshot["state"])
        source = driver.SourceState.from_buffer_copy(snapshot["source"])
        divider = driver.DividerState.from_buffer_copy(snapshot["divider"])
        start = arm.StartState.from_buffer_copy(snapshot["start"])
        patches = {0xE40DA4C4: snapshot["records"][:896],
            0xE40DA98C: resource.held.to_bytes(4, "little"),
            0x24020010: resource.aggregate.to_bytes(4, "little"),
            0xE40D33FC: resource.prehook.to_bytes(4, "little"),
            0xE403E810: snapshot["manager"][:1156], 0xE400184C: state.initialized.to_bytes(4, "little"),
            0xE40D1B88: bytes(state.descriptor_miss),
            0xE40D1BE4: state.divider_miss.to_bytes(4, "little"),
            0xE40D1BE0: state.source_miss.to_bytes(4, "little"),
            0xE403E6AC: source.marker.to_bytes(4, "little"),
            0xE403E6B0: source.requested.to_bytes(8, "little"),
            0xE403E4A8: source.cached.to_bytes(8, "little"),
            0xE403E72C: divider.marker.to_bytes(4, "little"),
            0xE403E730: divider.count.to_bytes(4, "little"),
            0x0EE056B0: snapshot["cell"], 0x2400FF78: snapshot["scratch"][:8],
            0xE403B474: start.open_count.to_bytes(4, "little"),
            0xE403B518: start.mapping_marker.to_bytes(4, "little"),
            0xE403B494: start.active.to_bytes(4, "little"),
            0xE403B478: start.resource_object.to_bytes(4, "little")}
        for region in case["expected"]["memory"]:
            address = int(region["address"], 0)
            expected = bytes.fromhex(region["hex"])
            actual = bytearray(driver.fixture_bytes(case, "setup", address, len(expected)))
            for field, value in patches.items():
                if address <= field and field + len(value) <= address + len(actual):
                    actual[field - address:field - address + len(value)] = value
            self.assertEqual(actual, expected, f"{case['id']}: {address:#x}")

    def test_complete_calls_and_lower_return_prefixes(self):
        path = ROOT / "tests/vectors/start4/arm-start-composition.json"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "07f454c21c78b6302929e1aa5d086dc123cf3bbbd5920eacfc4dd47dc8820c98")
        for index in range(2):
            case, prefix = self.cases[index], self.cases[index + 2]
            request = self.request(index)
            initial = request.snapshot()
            self.run_request(request)
            self.assertEqual(request.events, list(map(lower.event_projection, case["expected"]["events"])))
            self.assertEqual(request.events[:-1],
                             list(map(lower.event_projection, prefix["expected"]["events"])))
            self.compare_memory(case, request.snapshot())
            self.compare_memory(prefix, request.snapshots[-2])
            self.assertEqual(request.snapshots[0], initial)
            for snapshot in request.snapshots[:-1]:
                self.assertEqual(snapshot["start"], initial["start"])
            released = request.snapshots[-1]
            self.assertEqual(arm.StartState.from_buffer_copy(released["start"]).active, 1)
            for field in request.guards.keys() - {"start", "result"}:
                self.assertEqual(released[field], request.snapshots[-2][field])
            result = request.result.contents
            self.assertEqual(result.resource.resource_raw, int(prefix["expected"]["registers"]["r0"], 0))
            self.assertEqual(result.higher_raw, int(case["expected"]["registers"]["r0"], 0))
            self.assertEqual(tuple(getattr(result.resource.first_clock, field) for field, _ in clock.Result._fields_),
                             (4 if index else 0, 0, 0, 0))
            self.assertEqual((result.resource.repeated_word_raw, result.resource.repeated_manager_raw), (0, 0))
            for kind, count in ((driver.MMIO_READ, 2064 if index else 65), (driver.MMIO_WRITE, 58),
                                (driver.NATIVE_READ, 6), (driver.NATIVE_WRITE, 2), ("boundary", 25)):
                self.assertEqual(sum(event[0] == kind for event in request.events), count)

    def test_required_objects_and_every_reachable_observer(self):
        for index in OBJECT_INDICES:
            request = self.request()
            arguments = request.arguments()
            arguments[index] = None
            self.run_request(request, INVALID, arguments)
        for higher in (False, True):
            for name in (("acquire", "release") if higher else ("acquire", "release", "diagnostic", "service")):
                request = self.request()
                setattr(request.higher_plan if higher else request.plan, name, lower.Provider())
                self.run_request(request, INVALID)
        for name in ("acquire", "release", "diagnostic"):
            request = self.request()
            setattr(request.plan.clock, name, manager.Provider())
            self.run_request(request, INVALID)
        request = self.request()
        request.plan.clock.word.observe = driver.Observe()
        self.run_request(request, INVALID)
        for index in range(5):
            request = self.request()
            request.plans()[index].observer.observe = driver.Observe()
            self.run_request(request, INVALID)
            request = self.request()
            request.plans()[index].reads = ctypes.POINTER(driver.Read)()
            self.run_request(request, INVALID)

    def test_all_object_and_read_array_pairs_are_disjoint(self):
        for left, right in itertools.combinations(OBJECT_INDICES, 2):
            request = self.request()
            arguments = request.arguments()
            arguments[right] = ctypes.cast(arguments[left], self.function.argtypes[right])
            self.run_request(request, OVERLAP, arguments)
        for plan_index in range(5):
            for object_index in OBJECT_INDICES:
                request = self.request()
                request.plans()[plan_index].reads = ctypes.cast(request.arguments()[object_index],
                                                               ctypes.POINTER(driver.Read))
                self.run_request(request, OVERLAP)
        for left, right in itertools.combinations(range(5), 2):
            request = self.request()
            request.plans()[right].reads = request.plans()[left].reads
            self.run_request(request, OVERLAP)

    def test_declared_tails_short_buffers_and_address_size_overflow(self):
        maximum = ctypes.c_size_t(-1).value
        for index in OBJECT_INDICES:
            request = self.request()
            arguments = request.arguments()
            arguments[index] = ctypes.cast(maximum - 1, self.function.argtypes[index])
            self.run_request(request, BOUNDS, arguments)
        for span, length, minimum in ((2, 3, 896), (5, 6, 1156), (11, 12, 8)):
            for size in (0, minimum - 1, maximum):
                request = self.request()
                arguments = request.arguments()
                arguments[length] = size
                self.run_request(request, BOUNDS, arguments)
            for target in [index for index in OBJECT_INDICES if index != span] + list(range(20, 25)):
                request = self.request()
                arguments = request.arguments()
                pointer = ctypes.cast(arguments[span], ctypes.c_void_p).value + minimum
                if target >= 20:
                    request.plans()[target - 20].reads = ctypes.cast(pointer, ctypes.POINTER(driver.Read))
                else:
                    arguments[target] = ctypes.cast(pointer, self.function.argtypes[target])
                self.run_request(request, OVERLAP, arguments)
        for index in range(5):
            request = self.request()
            request.plans()[index].count = maximum // ctypes.sizeof(driver.Read) + 1
            self.run_request(request, BOUNDS)
            request = self.request()
            request.plans()[index].reads = ctypes.cast(maximum - 3, ctypes.POINTER(driver.Read))
            self.run_request(request, BOUNDS)

    def test_all_lower_plans_are_checked_before_higher_acquisition(self):
        for case_index in range(2):
            request = self.request(case_index)
            for reads in request.arrays:
                for index in range(len(reads)):
                    for field in ("address", "word"):
                        original = getattr(reads[index], field)
                        setattr(reads[index], field, original ^ 0x80000000)
                        self.run_request(request, UNSUPPORTED)
                        setattr(reads[index], field, original)
            for index in range(5):
                request = self.request(case_index)
                request.plans()[index].count = 0
                self.run_request(request, BOUNDS)
                request = self.request(case_index)
                request.plans()[index].count -= 1
                self.run_request(request, UNSUPPORTED if index == 0 and case_index else BOUNDS)
                request = self.request(case_index)
                reads = request.arrays[index]
                extra = (driver.Read * (len(reads) + 1))(*reads, driver.Read(0, 0))
                request.plans()[index].reads, request.plans()[index].count = extra, len(extra)
                self.run_request(request, UNSUPPORTED)

    def test_exact_higher_gates_binding_and_distinct_mutexes(self):
        for name in ("open_count", "mapping_marker", "active", "resource_object"):
            for value in (0, 1, 2, 0xFFFFFFFF):
                request = self.request()
                if value == getattr(request.start, name):
                    continue
                setattr(request.start, name, value)
                self.run_request(request, UNSUPPORTED)
        for value in (0, 1, 0x61726D10, 0xFFFFFFFF):
            request = self.request()
            request.higher_inputs.handle = value
            self.run_request(request, UNSUPPORTED)
        for index in range(4):
            request = self.request()
            request.higher_inputs.mutex_identity = (request.inputs.request.mutex_identity,
                request.inputs.outer_mutex, request.inputs.resource_mutex,
                request.inputs.clock.request.mutex_identity)[index]
            self.run_request(request, UNSUPPORTED)
        request = self.request()
        request.start.resource_object = request.inputs.request.identity = 0
        request.records[:4] = bytes(4)
        self.run_request(request, UNSUPPORTED)

    def test_full_width_tokens_do_not_become_native_addresses(self):
        for token in (1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFC, 0xFFFFFFFF):
            request = self.request()
            request.start.resource_object = request.inputs.request.identity = token
            request.records[:4] = token.to_bytes(4, "little")
            request.higher_inputs.mutex_identity = token
            self.run_request(request)
            self.assertEqual(request.start.resource_object, token)
            self.assertEqual(request.start.active, 1)
            self.assertEqual(request.events[0][2], (token,))
            self.assertEqual(request.events[1][2][2], token)

    def test_fixed_lower_state_and_repeated_call_rejection(self):
        lower.ResourceCompositionTest.test_fixed_inputs_records_and_state(self)
        lower.ResourceCompositionTest.test_entire_first_clock_profile_is_checked_before_resource_effects(self)


if __name__ == "__main__":
    unittest.main()
