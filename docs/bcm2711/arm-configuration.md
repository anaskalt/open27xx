<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# ARM configuration control

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Every firmware address below is a VPU virtual address in that file.

Entry 0x0EC59EBE changes a cached configuration bit and conditionally
issues a service request. Its 86-byte body starts at file offset 0x598BE.
Driver table 0x0EDE54D4 slot 0x30 contains this entry at file offset
0x1E4EE4. The two complete calls use an explicit CPU instruction-result
input, literal mutex/service replies and declared state. They establish
software ordering and returns, without assigning physical meaning to
CPU bit 6, a hardware identity, synchronization or service effects.

## Paired input profiles

The identified `start4.elf` entry receives `(handle, control)`. Both
supported profiles supply handle 0x61726D11, control 1 and initial
configuration 0x1230FC1B. The following differences are paired; they are
not independent dimensions of a larger input matrix.

| Profile | Supplied VERSION word | Service-index state | Literal replies |
|---|---|---|---|
| CPU bit clear | 0x00000000 | Index 1 | Acquire 0, service 7, release 0 |
| CPU bit set | 0x00000040 | Not read or declared | Acquire 0, release 0 |

These words are synthetic inputs. No default or actual CM4 VERSION word
is defined. The configuration value is a recorded output of the separate
[first-open prefix](arm-object.md#first-open-observation-and-runtime-gap).
That prefix does not complete initialization or prove this call's runtime
reachability. No earlier stack frame is reused by these complete calls.

The body uses these GP-relative locations:

| Location | Size (bytes) | Use |
|---|---:|---|
| 0x3B470 | Opaque | Mutex token for acquire and release |
| 0x3B51C | 4 | Configuration word, read and written before VERSION |
| 0x3B490 | 4 | Service index, read only when CPU bit 6 is clear |

The fixture uses GP 0xE4000000. Mutex token 0xE403B470 is an opaque
32-bit identity in a portable interface, separate from host storage.
The body does not read a mapping table, marker, open count or resource
record on these paths. That does not establish acquisition of those
objects or completion of [mapping-table preparation](arm-mapping.md).

Other handles, control values, initial configurations, CPU words, service
indexes and reply plans are outside this helper's finite domain. In
particular, the earlier zero-handle native return is not a supported
portable profile here. A host validation error must not manufacture
vendor raw 0xFFFFFFFF. The earlier control-zero prefix likewise does not
establish a complete control-zero operation.

## Native operation order

For entry 0x0EC59EBE in the identified `start4.elf`:

1. Save the actual call frame and acquire at 0x0EC59ECE through boundary
   0x0ED64D02, passing the mutex token. Handle comparison follows at
   0x0EC59ED2–0x0EC59ED8. Both supported inputs match.
2. Read configuration at 0x0EC59EE2. With control 1, set its bit 6 at
   0x0EC59EE4 and store at 0x0EC59EEC. The complete new value is
   0x1230FC5B. Other bits remain unchanged.
3. Observe VERSION at 0x0EC59EEE, file offset 0x598EE, destination r2.
   The [explicit instruction-result contract](vpu-version.md) supplies
   the complete declared word. The native instruction continues normally;
   no function return or subsequent computation is substituted.
4. Test CPU-word bit 6 at 0x0EC59EF0. For word zero, read service index
   at 0x0EC59EF4 and the stored configuration at 0x0EC59EFC. Call
   0x0ED65284 from 0x0EC59F04 with `(1,0x1230FC5B,0,0,0,0)`.
   Supplied word 0x40 skips the index read and service call entirely.
5. Select raw zero at 0x0EC59F08. The supplied service reply 7 does not
   affect that selection. Release through 0x0ED64D3A at 0x0EC59F0C,
   move the selected result to r0 at 0x0EC59F10, and execute the real
   epilogue at 0x0EC59F12.

The two uses of bit 6 are distinct: control 1 changes the cached
configuration, then the supplied CPU word selects the service path.
The recorded result is raw zero for both profiles; it does not establish
that a physical configuration was applied.

## Portable observations

Represent the operation with caller-owned configuration state, the
fixed handle/control parameters, explicit CPU word, optional service-index
input, an immutable literal-reply plan, observer configuration and a
separate raw-result destination. Native code addresses may identify event
kinds; they are opaque identities, not callable host addresses.

The semantic event order and defined inputs are:

| Event | Defined observation | Literal reply |
|---|---|---|
| Acquire | Mutex token 0xE403B470 | 0 |
| VERSION | Site 0x0EC59EEE, destination r2, complete supplied word | Not a function reply |
| Service, CPU-bit-clear profile only | Index 1, configuration 0x1230FC5B, four zero words | 7 |
| Release | Mutex token 0xE403B470 | 0 |

The native fixture's function events contain six physical register words.
Only the mutex token is a defined acquire/release argument here; the
remaining register values are incidental observations. The six service
words are defined arguments. VERSION is an instruction-result event,
not a mutex/service callback. The portable helper must emit it after the
configuration write and before any service event.

Observers see the initial configuration at acquire and the new
configuration at VERSION, service and release. The raw-result destination
retains its incoming contents through every observer and is written with
zero only after release. The native return is a register value; this
separate result destination and its storage rules are host API choices.
The callback-visible sequence follows the native store/call positions; the
fixture records event arguments and final memory, not per-event memory
snapshots.

The entire literal-reply plan is known before execution. Observers report
the declared replies; they do not choose them. The clear profile consumes
acquire, service and release replies in that order; the set profile
consumes only acquire and release. Extra logical reply entries are host
validation errors; an available but unused observer is not an extra reply.
VERSION's word comes from the separate
immutable input. Dynamic provider returns, missing replies discovered
after a state write, callback mutation and failure rollback have no
supported policy in this contract.

## Storage and preflight

Before any observer or state/result write, validate required pointers,
full declared extents, address/size wrap, pairwise overlap, the exact
paired profile and every reachable observer and reply. Require writable
configuration and raw-result storage for both profiles. Require the
service-index input and service observation only for the clear profile.
Do not require an unused service provider or read its numeric index on
the set profile.

The interface may group fields into a typed state object. Any grouped
member unused by the selected profile is not read or numerically
validated and remains unchanged. The whole object still contributes
its declared size to backing, alignment and overlap requirements. This
is a host representation rule, not an additional native input profile.

All supplied objects remain disjoint, including parameter/state views,
CPU/reply-plan storage, observer configuration, service-index storage
and result storage. An optional supplied-but-unused object still
contributes its full declared span to wrap/overlap preflight without
content access. A null optional byte view must have zero extent. Typed
objects require their natural alignment. Callers establish actual
backing, writability, alignment and lifetime; preflight cannot prove
that a pointer is backed by a live allocation.

Observers return normally, preserve all API objects, and do not reenter,
perform hardware access or introduce concurrent mutation. They may inspect
API state/result objects through read-only context references. Mutable
bookkeeping and indirectly writable storage remain disjoint from API
objects. A single observer may handle multiple semantic event kinds, but
all reachable observations must be available before the first effect.

Host validation failure emits no events and preserves configuration,
unused state and all outputs, including the raw-result destination.
Use host statuses distinct from firmware raw words. For accepted inputs,
perform the state update and observations in the documented order, then
publish raw zero after release.

## Recorded cases and replay

[arm-configuration.json](../../tests/vectors/start4/arm-configuration.json)
contains the two complete synthetic calls and their observed state.
Its SHA-256 is
`510e76f733805e52eab9343b776531616cac97ba4acedbf93589ce26d0f0cd9c`.

| Case | Instructions | Ordered events |
|---|---:|---:|
| control-version-bit-clear | 30 | 4 |
| control-version-bit-set | 23 | 3 |

Both start at the actual function entry and return to external sentinel
0x24040000. The real prologue and epilogue use a 20-byte frame and restore
the saved registers. SP returns to 0x24010000 and LR ends at 0x0EC59F10.
The fixture compares
all 32 named register words per case, 2236 bytes across both cases,
including the full declared stack and state guards, and every event.
VERSION appears at zero-based ordinary instruction index 15 in each call.
These emulator register/stack observations are not a portable calling
convention or a requirement to reproduce native scratch registers.

Use the pinned import and versions in [headless analysis](../analysis.md)
and a recorder that implements the [VERSION input contract](vpu-version.md).
Keep the output path unused:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EC59EBE \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/arm-configuration.json \
  /work/analysis/arm-configuration-recorded.json
```

The bit-set case declares neither service-index backing nor a service
reply. An unexpected service path therefore cannot be hidden by supplied
memory or an extra reply. Removing configuration/index backing or a
required acquire/service/release reply fails. Adding an unconsumed
service reply on the skip path also fails. Omitting the VERSION plan
retains the existing rejection; stopping before its declared site fails
the unused-site check. Require the individual diagnostic and absent
output artifact; a headless process exit code alone is insufficient.

## Open questions

- Other input profiles. Capture complete calls for another control word,
  initial configuration, CPU word, handle or reply plan before extending
  the paired portable domain. A prefix or arbitrary host error is not a
  complete vendor result.
- Live CPU identity and CPU bit 6. Establish an authoritative scalar
  specification or separately approved observation; the supplied words
  cannot determine either.
- Runtime acquisition and physical configuration. Complete first open and
  establish its remaining MMIO, registration and callback state before
  connecting these calls to live startup. The software return and service
  event do not prove synchronization, mapping application or ARM execution.
