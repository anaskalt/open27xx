<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# ARM mapping-table preparation

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Every firmware address below is a VPU virtual address in that file.

Entry 0x0EC59C22 prepares a 64-entry software table and its marker.
Its body spans 258 bytes at file offset 0x59622. Driver table 0x0EDE54D4
slot 0x14 contains that entry at file offset 0x1E4EC8. The twelve complete
calls below use fixed synthetic state and supplied external replies. They
do not establish physical mappings, cache visibility or ARM execution.

## Inputs and finite profiles

The identified `start4.elf` entry receives `(handle, offset, base, length)`.
Offset, base and length name 32-bit arithmetic operands, not validated
host pointers or ownership of physical memory. The matching handle word
is 0x61726D11. The body uses these GP-relative fields:

| Location | Size (bytes) | Use |
|---|---:|---|
| 0x3B470 | Opaque | Higher mutex identity passed to acquire/release |
| 0x3B494 | 4 | Active-state gate |
| 0x3B47C | 4 | Capacity word used to form bound and step |
| 0x3B498 | 128 | 64 little-endian halfwords |
| 0x3B518 | 4 | Table-initialization marker |
| 0x1564 | 4 | Selection word for the optional service call |
| 0x3B48C | 4 | Service index on selection zero |

The fixture uses GP 0xE4000000. Mutex identity 0xE403B470 and table
identity 0xE403B498 remain opaque 32-bit tokens in the portable contract;
they are separate from addresses of host storage. In particular, numeric
base 0x7E000000 is never dereferenced by the recorded body.

The following paired profiles are the entire supported input domain.
An omitted native field is not read on that profile. It is not an
additional free-value dimension. The invalid-handle profile supplies
handle zero; every other profile supplies 0x61726D11.

| Profile | Offset | Base | Length | Required state |
|---|---|---|---|---|
| Invalid handle | 0 | 0x7E000000 | 0x01000000 | None |
| Active | 0 | 0x7E000000 | 0x01000000 | Active 1 |
| Range exceeded | 0x40000000 | 0x7E000000 | 0x01000000 | Active 0, capacity 0x400 |
| Zero length | 0 | 0x7E000000 | 0 | Active 0, capacity 0x400 |
| Unaligned length | 0 | 0x7E000000 | 1 | Active 0, capacity 0x400 |
| Zero base | 0 | 0 | 0x01000000 | Active 0, capacity 0x400 |
| Unaligned base | 0 | 0x7E000001 | 0x01000000 | Active 0, capacity 0x400 |
| Unaligned offset | 1 | 0x7E000000 | 0x01000000 | Active 0, capacity 0x400 |
| Fresh table | 0 | 0x7E000000 | 0x01000000 | Fresh table state below |
| Repeat last entry | 0x3F000000 | 0x40000000 | 0x01000000 | Completed fresh state below |
| Selection zero | 0 | 0x7E000000 | 0x01000000 | Fresh state, selection 0, service index 1 |
| Wrapped table index | 0xFF000000 | 0x7E000000 | 0x01000000 | Fresh table state below |

Fresh table state means active 0, capacity 0x400, marker 0, selection 1
and 128 explicitly supplied bytes alternating 0xA5, 0x5A. The selection-zero
profile changes only selection and adds service index 1. Completed fresh
state means the actual fresh call's output: marker 1 and 64 halfwords
0x03F0, with active, capacity and selection unchanged. The repeat starts
with that state and a fresh call frame. Other table patterns, capacities,
active/marker/selection values, lengths, indexes and combinations are
outside these finite profiles.

No open-count or resource-object word is read on these paths. That fact
does not establish that open completed or that the handle, capacity and
mapping state were acquired at runtime.

## Ordered arithmetic and table effects

For 0x0EC59C22 in the identified `start4.elf`:

1. Compare the handle at 0x0EC59C24–0x0EC59C36. The supplied zero
   handle returns raw 0xFFFFFFFF without a boundary call or GP-state read.
2. For the matching handle, acquire the higher mutex at 0x0EC59C48,
   then read active at 0x0EC59C4C. Supplied active 1 releases at
   0x0EC59C54 and returns raw 0xFFFFFFFE at 0x0EC59C58.
3. With active zero, 0x0EC59C5E–0x0EC59C6A forms `bound` by shifting
   capacity left 20 with 32-bit truncation, then forms `step` by shifting
   that result right six. Fixed capacity 0x400 gives bound 0x40000000
   and step 0x01000000. Compute offset+length modulo 2^32. Reject if
   this unsigned sum exceeds bound or length is zero.
4. Check the unsigned remainder of length divided by step, reject base
   zero, then check base and offset remainders in that order. Calls at
   0x0EC59C76, 0x0EC59C86 and 0x0EC59C92 execute helper 0x0EC2FBCE,
   12 bytes at file offset 0x2F5CE. Its result is dividend minus unsigned
   quotient times divisor. No remainder result is supplied externally.
   A failed range, zero or remainder check releases at 0x0EC59C9C
   and returns raw 0xFFFFFFFD at 0x0EC59CA0.
5. Read marker at 0x0EC59CA6. If zero, fill every table halfword with
   the low 16 bits of `base >> 21` at 0x0EC59CBE/0x0EC59CC2, then
   store marker 1 at 0x0EC59CC8. Marker 1 skips that fill.
6. Start position at zero. While unsigned position is less than length,
   calculate index as `((position + offset) modulo 2^32) / step` and
   value as the low 16 bits of `((position + base) modulo 2^32) >> 21`.
   Index below 64 stores the halfword at 0x0EC59CD8 and advances
   position by step. Index at least 64 releases at 0x0EC59CF6 and
   returns raw 0xFFFFFFFC at 0x0EC59CFA, preserving preceding writes.
7. After the update loop, read selection at 0x0EC59CFE. Selection 1
   skips the service. Selection 0 calls 0x0ED65284 at 0x0EC59D16
   with `(service_index, table_identity, 0, 0, 0, 0)`. The recorded
   profile supplies raw 7 without memory effects. Release the mutex
   at 0x0EC59D1C, then return raw zero from 0x0EC59D20.

Every successful recorded call performs exactly one update iteration.
The 64-entry initial fill is a separate loop. The described loop arithmetic
does not enlarge the input domain to general multi-entry updates or other
capacities. Every admitted divisor is nonzero. The returned words are raw
results, without an inferred error enumeration or hardware-success meaning.

## State continuity and retained failure writes

In the identified `start4.elf`, the fresh profile fills all entries with
0x03F0, sets marker 1 and writes entry 0 with the same 0x03F0 value.
The repeat carries the actual fresh output, skips initialization and
writes entry 63 as 0x0200. All other entries and supplied fields remain
unchanged. Its request state is derived from the earlier output, not from
concatenating two expected event streams.

The wrapped-index profile adds 0xFF000000 and 0x01000000 modulo 2^32,
giving zero. The initial bound check therefore passes. The fill and marker
store execute before index 255 fails the later index check. Raw result
0xFFFFFFFC leaves all 64 entries at 0x03F0 and marker 1; there is no
rollback. A marker of 1 alone does not prove normal completion of this
call. The profile establishes this arithmetic path, not its use at startup.

## Boundary arguments and visible order

All mutex replies are literal zero. The selection-zero service reply is
literal 7. Each preserves memory and every register other than the supplied
raw return. These bodies do not execute in the fixtures.

| Boundary | Function identity | Portable argument words | Supplied reply |
|---|---|---|---|
| Acquire | 0x0ED64D02 | Mutex token 0xE403B470 | 0 |
| Release | 0x0ED64D3A | Mutex token 0xE403B470 | 0 |
| Selection-zero service | 0x0ED65284 | `(1,0xE403B498,0,0,0,0)` | 7 |

Only the mutex token is a defined argument to acquire/release. Their
remaining five recorded physical registers are incidental. Function and
table identities are opaque tokens, not host call targets or memory
addresses to dereference. The service's six words are defined arguments.
Its supplied 7 neither establishes an error enum nor propagates to the
final raw result, which the body explicitly sets to zero.

Acquire observes the incoming state. Active/range/remainder rejection
releases with state unchanged. Fresh/repeated completion releases after
the table and marker updates. The wrapped-index release also observes
the completed initial fill and marker 1, despite its later raw failure.
On selection zero, the service observes the completed table/marker before
the final release. Ordinary store order follows the cited instructions;
the recorder captures final memory and ordered boundaries, not a memory
snapshot at each call or a per-store event stream.

## Portable representation and host preflight

Provide one complete table-preparation operation with the four argument
words, caller-owned state appropriate to the selected profile, an optional
128-byte table view, observers and a separate raw-result destination.
State may group required words in a typed object; the presence of a host
object is separate from the numeric firmware handle and identity tokens.
Keep table entries little-endian and preserve every byte except the
documented table/marker stores. Do not retain pointers between calls.
Unused members of a grouped state object are neither read nor validated
as numeric premises and remain unchanged. The supplied object's full
size still participates in storage validation. This is a host layout
rule, not an additional native input profile.

The invalid-handle profile needs no state, table or observers, but still
needs the argument record and raw-result destination. It represents numeric
handle zero, not a missing required host pointer. The active profile needs
only active state and acquire/release observers. The six range/zero/alignment
profiles need active and capacity plus those observers. The four table
profiles need active, capacity, marker, selection, the complete 128-byte
table and acquire/release. Only selection zero requires a service index
and service observer. Fields absent from a profile are not accessed and
must not be required as evidence of initialization.

Before any observer, state write or result write, validate required host
pointers, declared storage lengths, host-address span overflow, pairwise
overlap of distinct passed storage objects, the exact paired profile and
all reachable observers. Validate the full table extent when present,
including the repeat's 64 initial values. The wrapped numeric offset is a
supported input word; it is not a host-address span overflow and must not
be rejected by substituting wider arithmetic for the vendor's 32-bit sum.

Optional state, table or provider-plan objects supplied on a path that
does not use them still contribute their complete declared spans to
overflow/overlap checks, without reading their contents. A null table
pointer requires zero declared extent. A used table view covers at least
128 bytes; only those 128 bytes are content inputs and may be updated.
Larger declared extents participate in overlap checks and remain preserved
beyond the table. The byte-table view may be unaligned. Typed argument,
state, provider and result objects require their type's alignment before
content access. For a grouped state, validate the whole object extent,
including members unused by the selected profile.

The argument/provider/result objects and complete declared state/table
storage extents must be disjoint. Fields within one state object belong
to that one extent. Callers establish actual backing, alignment, writable
output/state storage and lifetime; preflight cannot prove these properties.
Observers may read the supplied state but must preserve it, the arguments,
raw-result storage and provider configuration. Their mutable bookkeeping
storage must be separate. Require normal return, no reentry, no concurrent
mutation and no hardware access.

The reply plan is fixed before execution: zero for both mutex boundaries
and 7 for the sole service profile. Observers receive these values as
observations and do not choose dynamic replies. Unconstrained providers,
callback failures and alternate service/mutex words have no policy in this
contract. Arithmetic and table updates remain owned by the operation,
rather than supplied as computational callback results.

Host validation failure emits no calls and leaves all state and outputs,
including the raw-result destination, unchanged. Return a host status
distinct from the firmware result. A valid wrapped-index profile completes
the host operation with raw 0xFFFFFFFC and retained table writes; it is
not a host preflight failure. For all admitted profiles, store the host
raw-result word after the final release, or directly on the no-call
invalid-handle path. That output placement is a host API choice; native
register and stack observations do not define its host calling convention.

## Recorded cases and replay

The exact [arm-mapping.json](../../tests/vectors/start4/arm-mapping.json)
fixture has SHA-256
`b4d23a356284c0e7f088815079712b7e0d87a3ea1a6358d0e85561aa146866de`.
All twelve calls start at 0x0EC59C22 and finish at the external sentinel
0x24040000 after their actual prologue and epilogue. They restore SP
0x24010000 and the observed saved registers. No internal prefix or saved
frame transplant is included.

| Case | Raw result | Instructions | Boundary events |
|---|---|---:|---:|
| invalid-handle | 0xFFFFFFFF | 9 | 0 |
| active | 0xFFFFFFFE | 19 | 2 |
| range-exceeded | 0xFFFFFFFD | 24 | 2 |
| zero-length | 0xFFFFFFFD | 25 | 2 |
| length-unaligned | 0xFFFFFFFD | 34 | 2 |
| zero-base | 0xFFFFFFFD | 35 | 2 |
| base-unaligned | 0xFFFFFFFD | 44 | 2 |
| offset-unaligned | 0xFFFFFFFD | 53 | 2 |
| fresh-table | 0 | 201 | 2 |
| repeat-last-entry | 0 | 67 | 2 |
| selection-zero-service-seven | 0 | 208 | 3 |
| wrapped-index-outside-table | 0xFFFFFFFC | 196 | 2 |

The complete fixture totals 915 instructions and 23 boundary events.
It compares 2216 specified bytes and 24 observed register words per case,
including every declared non-stack byte and two 64-byte stack-edge guards.
Interior saved-stack bytes are not sampled. All writes are to declared
synthetic RAM; no MMIO read or write occurs. These counts describe the
fixed observations, not all-input or whole-firmware coverage.

Use the imported program and versions in [headless analysis](../analysis.md).
Run from the repository root with a fresh output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EC59C22 0x0EC2FBCE \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/arm-mapping.json /work/analysis/arm-mapping.json
cmp tests/vectors/start4/arm-mapping.json /work/analysis/arm-mapping.json
```

The unchanged decoder prepares only the producer and actual remainder
helper. The recorder preserves source bytes and rejects missing state,
undeclared writes, unsupported operations and exhausted or unused replies.
No computation body is replaced. The exact fixture also permits checking
the carried state directly:

```python
import json
from pathlib import Path

cases = json.loads(Path("/work/analysis/arm-mapping.json").read_text())["cases"]
by_id = {case["id"]: case for case in cases}
prior = {
    region["address"]: region["hex"]
    for region in by_id["fresh-table"]["expected"]["memory"]
}
for region in by_id["repeat-last-entry"]["setup"]["memory"]:
    if region["address"] != "0x2400FC00":
        assert region["hex"] == prior[region["address"]]
```

Omitting active, capacity, marker or selection fails at 0x0EC59C4C,
0x0EC59C5E, 0x0EC59CA6 or 0x0EC59CFE respectively. Missing table
backing rejects the two-byte write at 0xE403B498. Adding a service reply
to selection 1 or removing its release reply also fails. Require each
individual diagnostic and absent output; a zero headless exit alone does
not establish a successful capture. These recorder rejections are distinct
from the portable host preflight policy.

## Runtime connection

The [object/open contract](arm-object.md) records capacity 0x400 stored
at 0x0EC59DBE before an unresolved first-open `VERSION`. Static caller
0x0EC5A664 also reaches `VERSION` at 0x0EC5A6DE before selecting later
mapping calls. The static instruction sequence prepares a 16-MiB length;
one conditional branch supplies base 0x7E000000, while others call
0x0EC2FDF0 to derive a base. None of those architecture choices is
executed by this fixture.

The [higher start composition](arm-start-composition.md) still supplies
its marker, binding, open-count and active-state premises. Preparing this
table does not change that contract or connect the two calls into a
verified startup path.

## Open questions

- Application and visibility. Caller site 0x0EC5A740 invokes driver slot
  0x30 with `(handle,1)`; the raw word at file offset 0x1E4EE4 selects
  0x0EC59EBE. Establish that body and its dependencies before assigning
  mapping-application or cache-visibility effects to the prepared table.
- Initialization and architecture. Complete the first-open and caller
  architecture boundaries with verified inputs before treating capacity,
  handle, descriptor selection or table state as live startup state.
- Wider inputs. Capture other capacities, table patterns and multi-entry
  updates separately before broadening these paired profiles. Establish
  exceptional service and synchronization behavior before admitting
  dynamic replies or concurrent mutations.
- ARM handoff. Connect entry-address preparation, required memory visibility
  and actual release separately; software table values and raw zero do
  not establish ARM execution.
