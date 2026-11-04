<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# ARM control requests

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. The contract covers
configuration-request construction at 0x0EC5EE2A and the software
start-request gate at 0x0EC5A81E, with explicit service replies.

These operations select request arguments and update software state. They
do not establish hardware register effects, clock or reset completion,
memory visibility, an ARM entry address or execution of an ARM core. The
[stub metadata contract](arm-handoff.md) prepares a separate buffer.

## Configuration inputs

In the identified `start4.elf`, function 0x0EC5EE2A returns without issuing
a request when the driver pointer at GP+0x1660 is zero. That path leaves
the incoming `r0` unchanged; its recorded zero is not a success status.
The remaining recorded cases supply a nonzero pointer, selection word
GP+0x1564 equal to 1 and the following routing state:

| GP-relative location | Size (bytes) | Supplied value or role |
|---|---:|---|
| 0x1660 | 4 | Driver table pointer, 0x0EDE54D4 |
| 0x1564 | 4 | Selection word, 1 |
| 0x19C8 | 4 | Driver handle, 0x61726D11 |
| 0x3B490 | 4 | Service index, 1 |
| 0xCC948 | 4 | Configuration word A |
| 0xCC934 | 4 | Configuration word B |
| 0xCCA24 | 4 | Configuration word C |
| 0xCCA1C | 4 | Configuration word D |

A, B, C and D name opaque cached words. The code tests each for zero;
the 16 recorded combinations supply each as 0 or 1. Neither configuration
key names nor hardware meanings are assigned to these words. The
selection-word-zero path inside 0x0EC5EE2A uses a different protocol and
is outside this configuration contract.

## Ordered configuration requests

The identified `start4.elf` function 0x0EC5EE2A issues six requests, plus
a seventh when D is nonzero. Each row gives the requested address, the
offset passed to the service boundary and the selected value. `OR` means
bitwise combination.

| Order | Requested address | Service offset | Value | Call site |
|---:|---|---|---|---|
| 1 | 0x7E00B41C | 0x41C | 0xA | 0x0EC5EE4A |
| 2 | 0x7E00B008 | 0x08 | 0x3030 | 0x0EC5EE5C |
| 3 | 0x7E00B000 | 0 | 0x1000 when A is zero, OR 0x400 when C is nonzero | 0x0EC5EE8E |
| 4 | 0x7E500200 | 0x4F5200 | 0x30 | 0x0EC5EEA0 |
| 5 | 0x7E500204 | 0x4F5204 | 0xF when B is nonzero, OR 0xFFFF0 when C is nonzero | 0x0EC5EEAA |
| 6 | 0x7E500220 | 0x4F5220 | 0x200, OR 0x10 when A is zero | 0x0EC5EEC0 |
| 7, if D is nonzero | 0x7E50020C | 0x4F520C | 0xF | 0x0EC5EED4 |

An absent conditional term contributes zero. For example, row 3 selects
0 when A is nonzero and C is zero. Row 5 selects 0 when both B and C
are zero. The requested address is a routing argument, not an observed
hardware write.

Wrapper 0x0ED6D2DA adds the caller's bank and offset, then subtracts
0x7E00B000. It dispatches through the supplied table's slot at offset
0x54 to driver 0x0EC534A2. With the supplied handle and selection word,
the driver calls exception wrapper 0x0ED65284 at 0x0EC534CA with these
register arguments:

| Register | Value at the boundary |
|---|---|
| `r0` | Service index from GP+0x3B490, supplied as 1 |
| `r1` | Selected request value |
| `r2` | Requested address minus 0x7E00B000 |
| `r3`, `r4`, `r5` | Zero |

The base fixture intercepts 0x0ED65284 and supplies zero without changing
memory. SWI and the service implementation do not execute. The real
configuration function, routing wrapper and ARM driver execute around
that boundary; all supplied configuration/routing fields remain unchanged
and SP is restored. The observed zero in `r0` does not establish hardware
success or a configuration error policy. This contract assumes callbacks
leave cached inputs unchanged during a call; callback mutations and
concurrent state changes are outside the recorded behavior.

## Start-request software state

The identified `start4.elf` function 0x0EC5A81E takes a handle in `r0`.
That argument is not a kernel address or ARM-stub entry point. The
function uses these fields:

| GP-relative location | Size (bytes) | Role in the tested function |
|---|---:|---|
| 0x3B470 | Opaque | Mutex object passed by address |
| 0x3B474 | 4 | Open-count word; must be nonzero |
| 0x3B478 | 4 | Opaque object passed to the resource request |
| 0x3B494 | 4 | Active word; must be zero before the request |
| 0x3B518 | 4 | Mapping-state marker; must be nonzero |

Under the supplied mutex replies, execution follows this sequence:

1. Call mutex-acquire boundary 0x0ED64D02 at 0x0EC5A82C with the mutex
   object's address, GP+0x3B470.
2. At 0x0EC5A830–0x0EC5A850, check the handle against 0x61726D11,
   then the open-count word, mapping-state marker and inactive state.
   A failed check selects return value 0xFFFFFFFF and skips the resource
   request without changing the supplied state.
3. If all checks pass, call 0x0ED7C9B0 at 0x0EC5A85C with the object
   from GP+0x3B478, logical resource 23, literal 1 and literal 1.
4. Preserve that call's result for return. If it is zero, write 1 to
   GP+0x3B494 at 0x0EC5A868. A nonzero result leaves the active word
   unchanged.
5. Call mutex-release boundary 0x0ED64D3A at 0x0EC5A86C with the same
   mutex object, then return the selected result at 0x0EC5A870.

The base fixture's mutex boundaries return zero without changing memory.
The resource boundary is also supplied: result 0 produces return 0 and active word 1;
result 7 produces return 7 and active word 0. It is not an executed
resource transition. The mutex-release boundary is called on every
recorded path, including an invalid handle, and does not replace the
selected return value. All other observed state remains unchanged and
SP is restored.

The software names describe the gates used by this function. A nonzero
mapping marker does not establish actual mapping or cache visibility. An
active word of 1 does not establish that an ARM core has started. The
opaque object and handle do not identify a physical reset vector.

The [resource-request contract](resource-request.md) follows the fixed
logical index 23 through record aggregation, dependency selection and
conditional check callbacks. It distinguishes completed software calls
from stops before unsupported operations.

## Callback return words

In the identified `start4.elf`, the service boundary at 0x0ED65284 returns
to 0x0EC534CE, which replaces `r0` with zero. The configuration caller
does not observe the service's returned word or stop the remaining
requests because of it. The no-driver path at 0x0EC5EE2A issues no call
and preserves its incoming `r0`, including the tested value 0x89ABCDEF.
Neither result defines a hardware-success status.

The start-request caller at 0x0EC5A81E does not test the returned `r0`
from mutex-acquire boundary 0x0ED64D02. It continues through the same
software gates. After the resource request, it retains that request's
result separately from the mutex-release return word. At 0x0EC5A870 it
places the selected result in `r0`. Nonzero mutex return words therefore
do not prevent the logical resource call or replace its result.

[arm-control-replies.json](../../tests/vectors/start4/arm-control-replies.json)
records 17 additional cases and 1477 scalar instructions:

| Group | Cases | Supplied return words | Observed behavior |
|---|---:|---|---|
| Six- and seven-request configuration paths | 6 | First service reply 7; last reply 0x80000000; or every reply 0xFFFFFFFF | Same complete request sequence and unchanged state; final `r0` is zero |
| Missing configuration driver | 1 | Incoming `r0` is 0x89ABCDEF | No call; `r0` remains 0x89ABCDEF |
| Resource results 0 and 7 | 6 | Acquire/release pairs (7, 0), (0, 0xFFFFFFFF), (7, 0x80000000) | Same gates and resource arguments; return 0 or 7 and active word 1 or 0, respectively |
| Each of the four gate rejections | 4 | Both mutex return words nonzero | No resource call; return 0xFFFFFFFF; unchanged state |

The configuration cases use A/B/C/D equal to 0000 or 1111. All request
arguments, call ordering, observed memory, restored SP and instruction
counts match their corresponding base cases. The missing-driver case
changes only the observed incoming and final `r0`. No reply changes memory.

These are raw return-register words supplied at explicit boundaries.
They are not measured service failures, lock-acquisition failures or
successful hardware operations. A portable implementation preserves the
complete configuration-request sequence and derives the start-request
result from the gates and resource reply. Callback memory effects, real
synchronization and hardware recovery remain outside this contract.

## Zero-selection boundary

One case enters the internal block at 0x0ED55648 in the identified
`start4.elf` with GP+0x1564 equal to zero. It stops at 0x0ED55688 after
three scalar instructions, before the unsupported VERSION instruction.
The selection word and SP remain unchanged and no service call occurs.
This is a branch-boundary observation, not a function return, a completed
resource callback or a tested alternative initialization path.

## Recorded cases and portable comparison

[arm-control.json](../../tests/vectors/start4/arm-control.json) contains
24 synthetic cases and 3452 scalar instructions. The unchanged
[scalar recorder](../../tools/ghidra/CaptureScalarVectors.java) executes
the cases with Ghidra 12.2 `EmulatorHelper`.

| Group | Cases | Scalar instructions | Observed output |
|---|---:|---:|---|
| A/B/C/D combinations | 16 | 3328 | Six or seven ordered service requests; unchanged supplied state |
| Missing driver | 1 | 4 | No request; unchanged supplied state |
| Start-request gates | 6 | 117 | Four gate rejections, resource result 0 and resource result 7 |
| Zero-selection boundary | 1 | 3 | Stop before VERSION; unchanged selection word |

Configuration case suffixes list A, B, C and D in that order. All memory
is explicitly supplied. The fixture uses synthetic GP 0xE4000000, stack
pointer 0x24010000 and return sentinel 0x24030000; these values are test
locations, not hardware placement requirements. No MMIO, exception
transition or ARM instruction executes.

For portable tests, represent the cached words as ordinary state fields.
Compare configuration callbacks by their service index, selected value,
relative offset and order. Check that a missing driver emits no request.
Represent mutex and resource calls as explicit callback boundaries, compare
their object identity and documented arguments, and compare the returned
status and active-state update. Keep those callbacks separate from actual
hardware operations. Incidental register contents and native stack
addresses do not define a portable application interface.

A host API must define pointer validity, ownership and valid callback
objects before accessing caller-owned state. Those host rules are distinct
from the returned register words above. The two fixtures cover zero and
nonzero service/mutex replies, and resource results 0 and 7. They do not
establish callback side effects, synchronization correctness or production
failure recovery.

## Open questions

- Configuration provenance. Trace the writers of the four cached words
  and the selection flag before mapping them to configuration keys or
  physical board properties.
- Service effects and failure handling. Verify the exception transition,
  service implementation and actual result semantics before connecting
  requests to hardware access or defining recovery behavior. Ignoring a
  supplied return word does not establish the operation's physical outcome.
- Resource transition. Connect the fixed [resource dependencies](resource-request.md)
  to clock-driver calls, required initial state and readback semantics
  before treating the logical request as an ARM release operation.
- Memory and entry. Connect loader buffers, address translation, mapping,
  cache visibility and reset-vector placement, then verify the complete
  handoff on hardware. The tested handle supplies no ARM PC.
