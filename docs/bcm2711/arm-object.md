<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# ARM object registration and repeated open

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Every firmware address below is a VPU virtual address in that file.

Registrar 0x0ED7C928 produces a resource-object identity used by the
[resource manager](resource-request.md). ARM driver table 0x0EDE54D4
slot 0x0C selects open entry 0x0EC59D24; its pointer word is at file
offset 0x1E4EC0. That entry calls the registrar at 0x0EC59DA6 on first
open. Six complete synthetic calls cover registration and one repeated
open. A seventh case stops during first open, before `VERSION`; it is
not a completed initialization or a portable partial-open operation.

## Record storage and fixed profiles

In the identified `start4.elf`, the registrar scans 32 records at
GP+0xDA4C4 with a 28-byte stride. The manager mutex identity is GP+0xDA4C0.
Registration uses these little-endian fields:

| Record offset | Size (bytes) | Registration behavior |
|---|---:|---|
| 0x00 | 4 | Zero means free; selection stores the record's own identity |
| 0x04 | 4 | Store the selected index |
| 0x08 | 4 | Preserve the logical request word |
| 0x0C, 0x10 | 4 each | Preserve both words |
| 0x14, 0x18 | 4 each | Store the two incoming metadata words |

The actual ARM caller supplies metadata 0x0EC59E8C and 0x158. These are
opaque words in this contract. The registrar stores them without following
the first word as a pointer. Its output is a four-byte object identity.

The fixtures use GP 0xE4000000, so the array's logical base is 0xE40DA4C4
and record `i` has identity `0xE40DA4C4 + 28 × i`. A host implementation
uses these identities as unsigned 32-bit tokens, separate from the host
address backing its 896-byte record array. The fixed registration profiles
are:

| Profile | Initial array |
|---|---|
| First free record 0 | All 896 bytes zero |
| First free record 1 | Record 0 has self identity 0xE40DA4C4; every other byte is zero |
| Full array | Each record has its own identity at 0x00 and index at 0x04; all remaining fields are zero |
| Free record with retained fields | Record 0 words are `(0,0x55667788,0x11223344,0xAABBCCDD,0x89ABCDEF,0xDEADBEEF,0x76543210)`; the other 31 records are zero |
| Absent output | The native output argument is null; no array or output storage is accessed |

For every present-output profile, the incoming output word is 0xA5A5A5A5
and metadata is the fixed pair above. These paired profiles do not admit
arbitrary occupied-record contents, free indexes, metadata or mutations.
A nonzero self word is treated as occupied, without checking ownership
or membership. Registration is not validation of the other record fields.

## Registration sequence

For 0x0ED7C928 in the identified `start4.elf`:

1. If the output argument is null, return raw 0xFFFFFFFF through
   0x0ED7C95E/0x0ED7C98A. No diagnostic or mutex boundary executes.
2. Otherwise clear the output at 0x0ED7C936, then acquire the manager
   mutex at 0x0ED7C940. The acquire observer sees output zero and the
   unchanged input records.
3. Examine record self words in increasing index order at
   0x0ED7C94C–0x0ED7C958. Select the first zero self word.
4. For that record, store self at 0x0ED7C962, index at 0x0ED7C968,
   metadata at 0x0ED7C96E/0x0ED7C970 and its identity to the caller's
   output at 0x0ED7C972. Call the diagnostic at 0x0ED7C974 afterward.
5. Release at 0x0ED7C986 and return raw zero. If the scan instead finds
   all 32 occupied, output stays zero, no diagnostic executes, release
   occurs at 0x0ED7C980 and the returned word is 0xFFFFFFFF.

All other record bytes are preserved. In the retained-field profile,
0x11223344, 0xAABBCCDD and 0x89ABCDEF survive at offsets 0x08–0x10;
the index and old metadata are replaced. No clearing of the request word
can be inferred from a successful registration.

Every external reply in these profiles is literal zero and has no memory
effects. The defined portable boundary arguments are:

| Boundary | Identity | Defined arguments |
|---|---|---|
| Acquire | 0x0ED64D02 | Manager mutex token 0xE40DA4C0 |
| Diagnostic | 0x0ED17442 | `(0x4000,0x0ED7C990,selected_record_identity)` |
| Release | 0x0ED64D3A | Manager mutex token 0xE40DA4C0 |

Format, function and mutex identities are opaque tokens. Each fixture event
also captures six physical argument registers; extra register contents do
not define extra portable arguments. Observers receive the prescribed
zero reply as an observation and do not choose a dynamic return value.
Actual synchronization and diagnostic rendering are outside the contract.

## Complete repeated-open profile

The identified `start4.elf` entry 0x0EC59D24 accepts a parameter block
whose first word is 0x400 and byte at offset 4 is 2, plus a nonnull handle
output. The complete repeated-open fixture supplies:

| Field | Initial word | Final word |
|---|---|---|
| Open count, GP+0x3B474 | 1 | 2 |
| Resource object, GP+0x3B478 | 0x11223344 | Unchanged |
| Handle output | 0xA5A5A5A5 | 0x61726D11 |
| Raw return | No incoming result premise | 0 |

The entry validates the fixed parameter shape, acquires the higher mutex
GP+0x3B470 at 0x0EC59D88, reads old count at 0x0EC59D8C and stores old+1
at 0x0EC59D92. Nonzero old count takes 0x0EC59D94 directly to the release
at 0x0EC59E6E. Handle store 0x0EC59E80 follows that release. The actual
epilogue returns zero and restores the saved frame.

Acquire sees count 1 and the incoming handle-output word. Release sees
count 2 and the still-unchanged handle output. The object is neither read
nor validated on this path. No record array or first-open configuration
is required; no registrar, diagnostic, `VERSION`, MMIO or privileged
service executes. The portable mutex argument is only token 0xE403B470.
The fixture's other five physical argument registers are incidental.

This is one complete call with supplied prior count 1. It does not prove
that the prior open completed, support arbitrary count values, acquire a
real object, or validate the supplied object identity. Null handle output,
other parameter shapes and nonzero external replies are not added to this
finite repeated-open domain.

## First-open observation and runtime gap

The first-open prefix starts at the same actual 0x0EC59D24 entry with
old count zero and the fixed parameter block. It increments count to one
and executes the real registrar with output GP+0x3B478, metadata
0x0EC59E8C and 0x158. The first free record is supplied as slot 0.
Both the higher and manager acquisitions execute; only their actual
external bodies receive zero replies.

After the registrar returns zero, store 0x0EC59DBE writes 0x400 to
GP+0x3B47C. Store 0x0EC59DDE writes 0x1230FC1B to GP+0x3B51C from the
supplied GP+0xCC93C word 0x12345678:

`((word & 0xFFFF0FFF) & 0xFFF0001C) | 3 | 0xF000 | 0xC00`.

The recorded execution stops before `VERSION` at 0x0EC59DE0. The handle
output remains 0xA5A5A5A5, the higher mutex has not been released and the
32-byte higher frame remains. The zero register word at this stop is not
a completed open return. The recorder seeds incoming LR with the internal
stop; that saved frame is not a natural complete caller frame. No portable
partial-first-open API, normal cleanup after the stop or architecture
result is defined by this observation.

The [higher start composition](arm-start-composition.md) supplies an
already matching record-0 binding, count 1, mapping marker 1 and active
word zero. The registrar explains one conditional source of the binding,
but it also writes metadata absent from that composition's unused-zero
record profile. Those contracts and fixtures remain unchanged. Registering
then starting requires a separately verified domain that preserves the
actual metadata and prior request words. First-free-slot order, earlier
array clearing, completed open, mapping/entry preparation and lifetime
remain unresolved runtime inputs.

## Portable storage and preflight

Registration and repeated open are separate complete operations. The
first-open prefix is evidence only. For registration, represent output
presence explicitly, keep a caller-owned 896-byte record view, the
four-byte object-output token and a separate raw-result word. The token
base and metadata pair are the fixed values above. A represented absent
output selects the vendor-null case; it is distinct from a missing host
pointer needed for a present-output operation.

The absent-output profile needs no record view or object-output storage
and emits no calls. A separate final raw-result destination is still
required by the host interface. It must not silently treat a missing host
result pointer as a valid vendor-null call. For present output, preflight
requires the record view, its full declared extent and separate output
storage before clearing anything.

Repeated open owns the count update and handle-output store. Represent
the supplied count and opaque object word as caller-owned state, with
separate parameter values, handle output and raw result. Its fixed profile
requires count 1, object word 0x11223344, parameter word 0x400, byte 2 and
incoming handle output 0xA5A5A5A5. The object word stays unchanged and is
never followed as a host pointer.

Before any callback or state/output write, validate required pointers,
declared lengths, address/size wrap, pairwise overlap, the exact applicable
profile and all reachable observers. Full-array registration needs acquire
and release but no diagnostic; null-output registration needs none. A
successful selected-slot profile needs all three. Repeated open needs only
its higher acquire/release. The literal replies are fixed zero; callbacks
that choose other replies or mutate state have no supported policy here.

Host validation failure emits no calls and preserves all state and output,
including the raw-result destination. Use host statuses distinct from the
actual returned 0 or 0xFFFFFFFF. All declared API objects and extents,
including provider configuration and result storage, remain disjoint.
Callers establish actual backing, suitable alignment, writability and
lifetime; preflight cannot prove these properties. Observer bookkeeping
and indirectly referenced storage remain separate. Observers return
normally, preserve API objects, avoid reentry/concurrent mutation and
perform no hardware access.

For accepted inputs, perform the documented effects in order. Registration
diagnostic/release observations see the completed record and object-output
writes. Repeated-open release precedes the handle store. Store the final
host raw-result word only after the last release, or directly for the
no-call null-output case. The raw-result destination is a host API choice;
native register/stack observations are not its calling convention.

## Recorded cases and replay

The [arm-object.json](../../tests/vectors/start4/arm-object.json) fixture is
synthetic state, explicit replies and observed results. Its SHA-256 is
`58d5c7c36b8bda0a402a975900a985f32cc39daad6b8beb0c91541b5c66e6d0b`.

| Case | Kind | Instructions | External events |
|---|---|---:|---:|
| register-slot0 | Complete | 30 | 3 |
| register-slot1 | Complete | 35 | 3 |
| register-full | Complete | 182 | 2 |
| register-stale-fields | Complete | 30 | 3 |
| register-null-output | Complete | 10 | 0 |
| repeated-open | Complete | 35 | 2 |
| first-open-before-version | Prefix | 74 | 4 |

The six complete calls total 322 instructions and 13 events; the prefix
adds 74 and four. All seven compare 5752 specified bytes, every ordered
boundary event and 24 observed registers per case. Every declared
non-stack byte and two 64-byte stack-edge guards are observed. Interior
saved-stack bytes are not sampled. Complete calls restore SP; the prefix
retains SP minus 32. Ordinary write ordering follows the cited store/call
instructions, not a full memory snapshot at every callback.

Use the imported program and versions in [headless analysis](../analysis.md).
Run from the repository root with a fresh output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EC59D24 0x0ED7C928 0x0EC59C22 \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/arm-object.json /work/analysis/arm-object.json
cmp tests/vectors/start4/arm-object.json /work/analysis/arm-object.json
```

The third preparation entry is retained in the replay recipe; no fixture
executes the mapping routine 0x0EC59C22. The unchanged scripts preserve
firmware bytes and reject missing state, undeclared writes, exhausted or
unused replies and unsupported operations.

Missing array or output backing fails at 0x0ED7C952 or 0x0ED7C936.
Missing count/configuration fails at 0x0EC59D8C or 0x0EC59DB0. An extra
diagnostic reply on the repeat and an exhausted registrar-release reply
also fail. Moving the prefix stop past `VERSION` fails before executing
0x0EC59DE0. Its diagnostic says `vector instruction` because the recorder
rejects mnemonics beginning with `v`; this is not an ISA classification
of `VERSION`. Require the individual diagnostic and absent result file;
headless launcher exit zero alone does not establish a successful capture.

## Open questions

- First-open continuation. Establish the architecture input and following
  service, interrupt-registration and MMIO behavior before claiming a
  complete initialization. Do not invent a `VERSION` result.
- Runtime records. Trace earlier clearing, allocation order, lifetime and
  release/reuse before choosing a live record or assuming request words
  start at zero. Preserve the actual registration metadata when composing.
- Mapping and entry. Execute the relevant producer and apply/visibility
  paths before treating the higher mapping marker as initialized state
  or evidence of an ARM mapping, entry address or release.
- Wider inputs. Capture other parameter/count/record/reply profiles and
  exceptional/concurrent behavior separately before extending these fixed
  complete operations. No hardware completion follows from raw zero.
