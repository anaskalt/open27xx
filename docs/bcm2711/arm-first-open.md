<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# ARM callback registration and first-open returns

The behavior below belongs to `start4.elf` from firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Every firmware address below is a VPU virtual address in that file.

Three complete calls cover callback registration at 0x0ED651FC. Three
more enter first open at 0x0EC59D24, execute the real object registrar
and callback-registration helper, and return 0xFFFFFFFF when the selected
callback-table word is zero. These are complete returned paths with
explicit synthetic state and external results. They do not establish a
successful first open or live initialization.

| Site | File offset | Role |
|---|---|---|
| 0x0EC59D24 | 0x59724 | First-open entry |
| 0x0ED7C928 | 0x17C328 | Existing resource-object registrar |
| 0x0EC59DE0 | 0x597E0 | VERSION, bytes `E4 00`, destination r4 |
| 0x0EC59E12 | 0x59812 | Read 32 bits from 0x7E00B44C |
| 0x0ED651FC | 0x164BFC | Callback-registration entry, 90-byte body |

The callback-registration body SHA-256 is
`627eb3728a1478688db836ea65755283ec85298f5c3a23ac9284d9dbcfe9da77`.
Object registration is a different operation, specified in
[ARM object registration](arm-object.md).

## Selected callback-registration profiles

Entry 0x0ED651FC receives code 0x5E, new callback token 0x0EC5716E and a
nonnull old-callback output. It selects the word at
`GP + 0xE25C + 4 × 0x5E = GP + 0xE3D4` and compares it with default
token 0x0EC3EA48. The fixed profiles start with output 0xA5A5A5A5:

| Initial selected word | Final selected word | Final old-callback output | Raw return |
|---|---|---|---|
| 0 | 0 | 0 | 0xFFFFFFFF |
| 0x0EC3EA48 | 0x0EC5716E | 0 | 0 |
| 0x11223344 | 0x0EC5716E | 0x11223344 | 0 |

The operation follows this order:

1. Clear the old-callback output at 0x0ED6520A.
2. Load the selected word at 0x0ED65218.
3. For the default token, replace the selected word at 0x0ED6524C and
   return zero; the cleared output remains zero.
4. For zero, preserve the selected word and return 0xFFFFFFFF through
   0x0ED65252/0x0ED65254.
5. For 0x11223344, write that word to the output at 0x0ED65244, replace
   the selected word at 0x0ED6524C and return zero.

There are no external calls, MMIO accesses or handler invocations in
these profiles. Tokens are unsigned 32-bit identities, never host
pointers. Incoming r3 is overwritten with the code at 0x0ED651FE; it is
not a fourth defined argument. Null output, zero new callback, other
codes and other old tokens are outside this finite contract.

## First-open input profiles

Entry 0x0EC59D24 receives a parameter word 0x400, parameter byte 2 and a
nonnull handle output. The supplied GP is 0xE4000000. Common state is:

| Field | Address or extent | Initial value |
|---|---|---|
| Open count | GP+0x3B474 | 0 |
| Object output | GP+0x3B478 | 0xA5A5A5A5 |
| Capacity | GP+0x3B47C | 0xA5A5A5A5 |
| Configuration | GP+0x3B51C | 0xA5A5A5A5 |
| Configuration source | GP+0xCC93C | 0x12345678 |
| Record array | GP+0xDA4C4, 896 bytes | All zero |
| Selected callback word | GP+0xE3D4 | 0 |
| Old-callback output | GP+0x3B488 | 0xA5A5A5A5 |
| Handle output | Separate caller word | 0xA5A5A5A5 |

The record array is exactly the existing first-free-slot-0 profile in
`arm-object.md`, with fixed metadata `(0x0EC59E8C,0x158)`. No successful
earlier open, prior clearing routine or live table contents are inferred.

Only these paired branches are admitted:

| CPU word | Secondary word, GP+0xCC934 | Service index, GP+0x3B490 | Service value |
|---|---|---|---|
| 0x00000000 | Not consumed | 1 | 0x1230FC1B |
| 0x00000040 | 0 | Not consumed | No service call |
| 0x00000040 | 1 | 1 | 0x200 |

Each case supplies one MMIO response: read at PC 0x0EC59E12, address
0x7E00B44C, size 4, little-endian bytes `44 33 22 11`. The CPU word and
MMIO word 0x11223344 are explicit inputs, not hardware observations.
CPU bit 6 has no assigned BCM2711 meaning. No MMIO write occurs on these
returned paths. No native ELF-RAM cell is required.

## Joined first-open sequence

The real scalar sequence in the identified `start4.elf` is:

1. Acquire higher mutex GP+0x3B470 at 0x0EC59D88. Read count zero and
   store count one at 0x0EC59D92.
2. Call the existing object registrar at 0x0EC59DA6. It clears object
   output before acquiring its manager mutex, selects record 0, writes
   its fields and the object token, then emits its diagnostic and release.
3. Store capacity 0x400 at 0x0EC59DBE. At 0x0EC59DDE, store configuration
   from the supplied source word using
   `((word & 0xFFFF0FFF) & 0xFFF0001C) | 3 | 0xF000 | 0xC00`,
   which is 0x1230FC1B for this profile.
4. Observe the explicit VERSION result at 0x0EC59DE0. Its following bit
   test and optional secondary-word test select the table above. If
   required, call service 0x0ED65284 at 0x0EC59E04 with the service index,
   selected value and four zero words.
5. Read the supplied MMIO word at 0x0EC59E12.
6. At 0x0EC59E22, execute the real selected callback-registration
   operation with code 0x5E, token 0x0EC5716E and output GP+0x3B488.
   It clears that output and returns 0xFFFFFFFF for the selected zero
   table word. The preceding MMIO word is incidental incoming r3 and is
   overwritten inside this helper.
7. Copy the raw result at 0x0EC59E26. The nonzero branch at 0x0EC59E28
   reaches 0x0EC59E86, then the real epilogue at 0x0EC59E88. Return
   0xFFFFFFFF without reaching higher release at 0x0EC59E6E.

There is no rollback. Count remains one, object remains 0xE40DA4C4,
capacity remains 0x400 and configuration remains 0x1230FC1B. Record 0
contains self 0xE40DA4C4, index zero and the actual metadata pair; its
request and words at offsets 0x0C/0x10 remain zero. The callback word
stays zero, old-callback output becomes zero and handle output stays
0xA5A5A5A5. Other record bytes and declared state remain unchanged.

This raw return is not assigned a generic error-enum meaning. Missing
higher release is an observed call-order fact, not a statement about
physical lock ownership. The first-open helper does not write a valid
handle or enter the subsequent driver-success path.

## Portable operations and observations

Provide two separate complete operations: selected callback registration
and the three first-open profiles. The latter composes the existing
`arm_object_register` slot-0 behavior and the selected callback operation;
it must not replace either computation with a literal return provider.
Keep the existing `arm_object_reopen` and prefix-only evidence unchanged.

For callback registration, represent the fixed code/new-token inputs,
selected word, old-callback output and a separate raw-result destination.
Both state words and the result are required. The code/token and one of
the three paired initial states must pass preflight before clearing the
output. There are no observers. After the documented state writes,
publish the actual raw word to the separate result destination.

For first open, represent caller-owned count/object/capacity/configuration
state, the 896-byte record view, callback state/output, parameter values,
configuration source, CPU word, optional secondary/index inputs, handle
output, literal reply/read plans, observers and separate raw-result
destination. The records and metadata use the existing object contract's
opaque token base. Native addresses identify observations; they do not
become callable host addresses or host pointers.

The defined portable observations, in order, are:

| Observation | Defined inputs | Supplied result |
|---|---|---|
| Higher acquire, 0x0ED64D02 | Mutex token 0xE403B470 | 0 |
| Registrar acquire, 0x0ED64D02 | Mutex token 0xE40DA4C0 | 0 |
| Registrar diagnostic, 0x0ED17442 | `(0x4000,0x0ED7C990,0xE40DA4C4)` | 0 |
| Registrar release, 0x0ED64D3A | Mutex token 0xE40DA4C0 | 0 |
| VERSION | Site 0x0EC59DE0, destination r4, complete supplied CPU word | Instruction result, not a function reply |
| Conditional service, 0x0ED65284 | `(1,service_value,0,0,0,0)` | 0 |
| Supplied MMIO read | PC 0x0EC59E12, address 0x7E00B44C, size 4, word 0x11223344 | Explicit read result |

The logical function-reply plan has exactly four zero words when the
service is skipped, or five zero words when it runs. VERSION and MMIO
inputs are separate from that plan. The read plan contains exactly one
matching entry. All plans are known before execution. Observers receive
the prescribed inputs/results; they do not choose dynamic values. An
unused available observer is not an extra reply. No higher-release event
is synthesized, and no event replaces callback-table computation.

Only the listed semantic arguments are portable. The fixtures also
record six physical words at function boundaries, including incidental
register contents. VERSION instruction index 74 and native frame bytes
are recorder observations, not additional arguments or a host calling
convention.

Observer-visible ordering follows the original store/call sites:

| Observation | Visible state |
|---|---|
| Higher acquire | All incoming state, count 0 and object 0xA5A5A5A5 |
| Registrar acquire | Count 1, cleared object output, unchanged zero records; capacity/configuration still 0xA5A5A5A5 |
| Diagnostic and registrar release | Updated record 0 and object token; capacity/configuration still incoming |
| VERSION, service and MMIO read | Capacity 0x400 and configuration 0x1230FC1B; callback table zero and old-callback output still 0xA5A5A5A5 |

Every observer sees the incoming raw-result destination and unchanged
handle output. Only after the final MMIO observation and actual
callback-registration effects does the portable first-open operation
publish raw 0xFFFFFFFF. The raw-result destination is a host interface
choice; native firmware returns the word in r0. Intermediate visibility
uses static store/call ordering; the fixtures do not snapshot memory at
every observer or exercise callbacks that mutate it.

## Storage and preflight

Perform one complete read-only preflight before the first effect. It
covers every required pointer, full declared extent, address/size wrap,
pairwise overlap, exact paired input domain and every reachable observer
or planned reply/read. In first open this includes the nested slot-0
record domain, callback table/output and late VERSION/MMIO/service
premises before the higher acquire. A later nested validation failure
must not be discovered after count or object writes.

The record view needs at least 896 bytes; bytes after the 896-byte view
remain untouched, but the full declared extent participates in overlap
and wrap checks. Record bytes need no alignment. Typed parameter, state,
word, plan, observer and result objects require natural alignment.
Callers establish actual backing, writability and lifetime; preflight
cannot prove that arbitrary pointers address live allocations.

All supplied API objects and full declared spans remain disjoint,
including immutable inputs, reply arrays, read plans, observer
configuration, nested record storage, outputs and raw result. Optional
supplied-but-unused objects still contribute their spans to overlap and
wrap checks without content access. Null optional byte views require
zero extent. If fields are grouped in one typed object, unused members
are not read or numerically validated and remain unchanged, while the
whole object contributes its size to storage requirements.

The CPU-clear profile requires index 1 but does not read or validate the
secondary word. The CPU-set/secondary-zero profile requires secondary
zero but does not read or validate the index or require a service
observer. The CPU-set/secondary-one profile requires both secondary one
and index 1. These three pairings are not a Cartesian domain expansion.
Callback registration does not accept null outputs or new callback zero.

Host validation errors emit no observations and preserve every API
object, including the raw-result destination. Host statuses remain
distinct from firmware raw 0 and 0xFFFFFFFF. A completed first-open raw
0xFFFFFFFF is an accepted execution with the specified retained effects,
not a host validation error or request to roll back state.

Observers return normally, preserve API objects/arguments, avoid reentry
and concurrent mutation, and perform no hardware access. Read-only
context references may inspect state/results. Mutable bookkeeping and
indirectly writable storage remain disjoint from API objects. No pointer
is retained, allocated or freed. Dynamic provider returns, unexpected
exceptions and physical synchronization/device behavior have no policy
in this finite contract.

## Recorded cases and replay

The two public fixtures contain only synthetic state, declared external
inputs and observations:

| Fixture | SHA-256 |
|---|---|
| [arm-callback-registration.json](../../tests/vectors/start4/arm-callback-registration.json) | `60377c5327f87fb5f95ca4cbed0d438dae5a1d26731a0e02c398c6f00cad7250` |
| [arm-first-open.json](../../tests/vectors/start4/arm-first-open.json) | `937f35212d420b4c3918b661466d6144152c88ef2180c69da348a15208aa4ce9` |

| Case | Instructions | Ordered events |
|---|---:|---:|
| registration-zero | 16 | 0 |
| registration-default | 19 | 0 |
| registration-prior | 22 | 0 |
| first-open-cpu-clear | 111 | 7 |
| first-open-cpu-set-secondary-zero | 106 | 6 |
| first-open-cpu-set-secondary-one | 114 | 7 |

All six start at actual entries and return through real epilogues to an
external sentinel. They total 388 instructions, 192 observed register
words, 9760 observed bytes and 20 events. Every declared memory byte,
including full stack contents and guards, is compared. The three
first-open frames are newly formed by the real 32-byte caller save,
24-byte registrar save and 8-byte callback-helper save. SP and saved
registers restore; stack memory retains the saved values. These frames
are distinct from the older pre-VERSION prefix's internal return sentinel.

Use the imported program and versions in [headless analysis](../analysis.md),
with two unused output paths:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EC59D24 0x0ED7C928 0x0ED651FC \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/arm-callback-registration.json /work/analysis/arm-callback-registration.json \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/arm-first-open.json /work/analysis/arm-first-open.json
cmp tests/vectors/start4/arm-callback-registration.json /work/analysis/arm-callback-registration.json
cmp tests/vectors/start4/arm-first-open.json /work/analysis/arm-first-open.json
```

The unchanged recorders retain their separate memory policies. Clock
uses the [explicit VERSION contract](vpu-version.md) and its existing
strict MMIO/source/native-cell guards. No native cell is supplied here;
its original source and block checks still apply.

Missing registration table/output, missing consumed secondary/index,
missing or mismatched MMIO reply, extra MMIO or higher-release reply,
and absent VERSION plan must reject without an artifact. The standalone
registration controls also reject short table backing, an insufficient
step budget and unused replies. Such harness failures are not native raw
returns and do not define rollback behavior.

## Open questions

- Successful first open. Follow the real getter 0x0ED00582 and selected
  table slots 0x0C/0x14 after successful callback registration, preserving
  preceding MMIO/software writes and actual output handles. Inspect and
  execute those bodies before declaring external reply boundaries.
  The separate [bounded suspend registrar](suspend-registrar.md) composes
  tuple lookup, basename selection and bounded copy under supplied state
  and conditional IRQ/p16 observations. Its standalone return does not
  establish a complete first open.
- Runtime state acquisition. Establish the producer of the callback table,
  record clearing, count, configuration source and service index. Supplied
  zero/default tokens do not prove a live first-open state.
- Broader registration/open domains. Capture null output, zero callback,
  other codes/tokens/parameter shapes, occupied records and alternate
  replies before extending these six fixed profiles.
- Composition with higher start. Preserve the actual registrar metadata
  and retained request fields when joining to the
  [higher start contract](arm-start-composition.md). The table-zero open
  return does not provide a valid acquired handle for that route.
- Hardware behavior. Resolve physical VERSION, synchronization, MMIO and
  privileged-service semantics independently; none follows from a
  supplied word or a completed synthetic call.
