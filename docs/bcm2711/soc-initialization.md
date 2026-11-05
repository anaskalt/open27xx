<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Conditional SoC initialization

The source below belongs to `boot/start4.elf` from raspberrypi/firmware
commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

Entry 0x0EC6221C selects flag, classification, control and mode values from
two conditional VERSION observations and one conditional peripheral read.
The state relation below requires the diagnostic byte at GP+0xCCDB8 to
remain between 0 and 3. This excludes all five calls to 0x0EDA5E7E.
The relation follows from the bound scalar semantics under the storage
and observation conditions below.

## Source extent

The selected code contains 81 instruction sites in 268 bytes. A separate
74-byte range contains the selection table. Within these ranges, the file
offset is the virtual address minus 0x0EC00600.

| Range | Address | File offset | Bytes |
| --- | --- | --- | ---: |
| Entry and selection prefix | 0x0EC6221C | 0x61C1C | 22 |
| Recognized-value paths | 0x0EC6227C | 0x61C7C | 182 |
| Default path and shared return | 0x0EC62332 | 0x61D32 | 64 |
| Selection table | 0x0EC62232 | 0x61C32 | 74 |

Every direct branch target and every table target lies within these code
ranges. The calls at 0x0EC622BE, 0x0EC622E0, 0x0EC62302, 0x0EC62326 and
0x0EC62362 target 0x0EDA5E7E, whose body is outside this extent. The return
at 0x0EC62370 obtains its destination from the saved stack word.

## Conditional inputs and storage

Let L denote the diagnostic byte, Q the incoming control word, S the
incoming SP and Rn the incoming value of register rn. The external
observations have independent values:

| Input | Observation address / file offset | Width | Consumption |
| --- | --- | ---: | --- |
| V1 | VERSION at 0x0EC6221E / 0x61C1E, destination r4 | 32 bits | Once on every path |
| V2 | VERSION at 0x0EC62332 / 0x61D32, destination r2 | 32 bits | Once on the default path only |
| M | Read at 0x0EC6230E / 0x61D0E from 0x7E0000B4 | 32 bits | Once on a recognized-value path only |

V1, V2 and M each range over all 32-bit words. V2 is not inferred from V1.
The VERSION observations supply only their named destination registers.
The peripheral observation supplies the declared read result. Other side
effects of those observations are outside this conditional relation.

GP locates the fields in the [guarded storage layout](#guarded-ordinary-storage).
Their names describe numeric roles in this routine; they do not assign a
hardware meaning to individual flags or control bits. The surrounding
buffer guards and descriptors belong to the portable interface.

All ordinary words use little-endian byte order. The four flag words,
classification byte, completion word, mode word and Q may contain arbitrary
initial values. The default path does not read Q. L is 0, 1, 2 or 3 and
remains stable throughout the call. Each diagnostic load zero-extends L;
the comparisons at 0x0EC622AE, 0x0EC622D0, 0x0EC622F0, 0x0EC62316 and
0x0EC62350 therefore select the paths that skip external calls.

S is four-byte aligned and at least 24. Ordinary readable and writable
storage covers [S-24, S), with no address wrap. The frame, GP-relative
fields, watched word, fixed code/table and peripheral observation are
disjoint. Any declared guard storage is also disjoint from the frame and
other writable fields. Source/table bytes remain immutable, and ordinary
storage has no concurrent modification through return.

General incoming scalar values, including SR and the saved registers, are
otherwise independent. The final PC is the saved incoming LR value. This
contract ends at that return boundary and does not fetch an instruction
from the returned address. Host storage validation and a portable calling
interface are separate from these source-derived effects.

## Selection table

At 0x0EC62220, r1 becomes zero. The arithmetic at 0x0EC62222 computes
u = (V1 - 0x04000160) modulo 2^32. The unsigned comparison at 0x0EC62228
admits u from 0 through 36. All other values branch directly to 0x0EC62332
without a table read.

The selector at 0x0EC62230 reads a signed little-endian 16-bit entry from
0x0EC62232 + 2u. Its target is 0x0EC62232 plus twice that entry. The target
base is the beginning of the table, not the selected entry's address.

| V1 | Signed entry | Destination | Ordered four-byte stores of 1, relative to GP |
| --- | ---: | --- | --- |
| 0x04000160, 0x04000161 | 37 | 0x0EC6227C | 0x1564 |
| 0x04000162 | 39 | 0x0EC62280 | 0x1568, 0x1564 |
| 0x04000170, 0x04000180 through 0x04000183 | 41 | 0x0EC62284 | 0x16E4, 0x1568, 0x1564 |
| 0x04000184 | 43 | 0x0EC62288 | 0x16E8, 0x16E4, 0x1568, 0x1564 |
| 0x04000163 through 0x0400016F, 0x04000171 through 0x0400017F | 128 | 0x0EC62332 | None |

The nine values in the first four rows select recognized-value paths.
The remaining 28 table entries and every input outside the table interval
select the default path. The full 32-bit comparison admits no high-bit
aliases of the recognized values.

The selected stores occur at 0x0EC6228A, 0x0EC6228E, 0x0EC62292 and
0x0EC62296. Each overwrites its entire word with 1. No path clears an
unselected flag; its incoming value remains unchanged under the storage
conditions above.

## Ordered ordinary-memory effects

The frame save precedes V1 and the selection described above. On a
recognized-value path, the flag stores precede these operations:

| Order | Code address / file offset | Data operation |
| ---: | --- | --- |
| 1 | 0x0EC622A0 / 0x61CA0 | Read L from GP+0xCCDB8 |
| 2 | 0x0EC622AA / 0x61CAA | Write byte 3 at GP+0x3B8AE |
| 3 | 0x0EC622CA / 0x61CCA | Read Q from GP+0x3B924 |
| 4 | 0x0EC622CE / 0x61CCE | Write Q OR 0x01000000 at GP+0x3B924 |
| 5 | 0x0EC622EE / 0x61CEE | Write Q OR 0x05000000 at GP+0x3B924 |
| 6 | 0x0EC62306 / 0x61D06 | Write 0x000037F5 at GP+0x3B92C |
| 7 | 0x0EC6230E / 0x61D0E | Read M from 0x7E0000B4 |
| 8, only M bit 0 set | 0x0EC62314 / 0x61D14 | Read L again from GP+0xCCDB8 |
| 9, only M bit 0 set | 0x0EC6232A / 0x61D2A | Read the current control word at GP+0x3B924 |
| 10, only M bit 0 set | 0x0EC6232E / 0x61D2E | Write Q OR 0x07000000 at GP+0x3B924 |
| 11 | 0x0EC6236E / 0x61D6E | Write 1 at GP+0x3B894 |

All writes in this table except the classification byte have width four.
The control masks preserve every other bit of Q. Both initial control
writes occur even when Q already contains the selected bits. If M bit 0
is clear, the second diagnostic read, final control read and third control
write are absent.

The default path observes V2 at 0x0EC62332 and defines
b = (V2 >> 6) AND 1. Its ordinary-memory operations are:

| Order | Code address / file offset | Data operation |
| ---: | --- | --- |
| 1 | 0x0EC62334 / 0x61D34 | Read L from GP+0xCCDB8 |
| 2 | 0x0EC6234A / 0x61D4A | Write byte b at GP+0x3B8AE |
| 3 | 0x0EC62366 / 0x61D66 | Write 0x00007FF5 at GP+0x3B92C |
| 4 | 0x0EC6236E / 0x61D6E | Write 1 at GP+0x3B894 |

The default path performs no peripheral read and writes neither Q nor
the four flag words. Both paths then restore the saved frame and return.
The frame and listed ordinary fields contain all direct writes in the
conditional domain. The watched word at GP+0x3B484 remains unchanged
because it is disjoint from those writes. No GP-relative store targets
GP+0x1560 or the diagnostic byte.

For GP 0x0EE04140, the watched word is 0x0EE3F5C4 and the diagnostic byte
is 0x0EED0EF8. The [original-table initializer](startup-initialization.md)
clears storage containing the watched word. This routine's conditional
preservation does not establish its value before or after intervening
startup calls.

## Frame and scalar state

Under the pinned semantics, the entry at 0x0EC6221C saves six four-byte
words and lowers SP by 24:

| Store order | Address | Saved value |
| ---: | --- | --- |
| 1 | S-4 | Incoming LR |
| 2 | S-8 | R6 |
| 3 | S-12 | R7 |
| 4 | S-16 | R8 |
| 5 | S-20 | R9 |
| 6 | S-24 | R10 |

The return at 0x0EC62370 reads these words in reverse order. It restores
r10 through r6, raises SP to S and uses the final word as PC. It does not
erase the saved bytes. Every declared stack byte outside [S-24, S) remains
unchanged under the nonoverlap conditions.

The complete final scalar relation is:

| Register | Recognized, M bit 0 clear | Recognized, M bit 0 set | Default |
| --- | --- | --- | --- |
| r0 | R0 | Q OR 0x07000000 | R0 |
| r1 | M | M | b |
| r2 | L | L | V2 |
| r3 | 0x7E000080 | 0x7E000080 | R3 |
| r4 | u | L | u |
| r5 | R5 | R5 | L |
| r6 through r23, GP, r27 through r29 | Incoming values | Incoming values | Incoming values |
| SP | S | S | S |
| LR | Incoming LR | Incoming LR | Incoming LR |
| SR | `(incoming SR & 0xFFFFFFF0) \| 0x0000000A` | `incoming SR & 0xFFFFFFF0` | `(incoming SR & 0xFFFFFFF0) \| (b == 0 ? 0x0000000A : 0)` |
| PC | Incoming LR | Incoming LR | Incoming LR |

The selection and diagnostic comparisons do not replace SR. The bit tests
at 0x0EC62310 and 0x0EC6233A replace SR bits 3 through 0 with 0xA when
the tested bit is clear and with zero when it is set. SR bits 31 through 4
remain unchanged. The full M word survives in r1, although only bit 0
selects the additional control update.

## Processor semantics and scope

Source interpretation uses Ghidra 12.2, language `vc4:LE:32:default`,
compiler specification `default` and VideoCoreIV commit
`db09a308c2db6a31ba5e060e6b763713f77e4f7b`. The compiled `vc4.sla` SHA-256 is
`2303eea79ede697a37318068af1514de75ff64d9fcf2965623e2ab417e93bb56`.
The pinned aleph-void/ghidra-videocore4 `data/languages/vc4.slaspec` source
defines the scalar, VERSION and multi-register semantics. The firmware and
processor sources appear in [references](../references.md).

For all 81 selected sites, ProgramContext current, default and nondefault
values are null. The disassembly default and detached instruction context
each contain eight zero mask/value bytes for the 32-bit `contextreg`.
A zero mask denotes unknown bits, not a known zero processor state.

The pinned multi-register definition uses incoming `storesp` and `mspoff`
context fields. The bound entry semantics contain the six frame writes
listed above, without an additional SP-value store. These are conditional
scalar semantics; they do not establish physical multi-register ordering
or the architecture's missing context state. No physical VERSION value,
peripheral value or complete startup execution follows from this relation.

## Verification

All 50 calls in a synthetic comparison return naturally. Their observed
results match the conditional relation for 1600 register and PC values,
11200 ordinary memory and stack bytes, and 991 ordered data accesses.
The comparison covers all 37 table selectors, the nine recognized
selectors again with M bit 0 set,
and four direct-default selectors. Every call compares all 31 scalar words
and PC, all 96 ordinary bytes, and a 128-byte declared stack containing the
24-byte frame. The calls execute 1214 instruction steps across 56 distinct
sites occupying 178 code bytes. Conditional VERSION/MMIO consumption also
matches. The observation record SHA-256 is
`09fe4dde72e03823adc3b4d527cde867ef716928f4f2cb8b548c48c8d6062617`.
These are finite cases with L from 0 through 3 and synthetic independent
VERSION/MMIO values under the pinned scalar semantics; the source decoder
context mask remains unknown. They establish no physical observations,
diagnostic-callee behavior or portable C equivalence.

## Portable API

`soc_initialization_run(input, observations, memory, stack, result)` operates
on caller-owned ordinary storage. Its validation and output-publication
rules are host policy, not additional vendor behavior. The interface uses
the scalar-state and byte-span conventions of
[startup initialization](startup-initialization.md#portable-api):

| Type | Fields |
| --- | --- |
| `struct soc_initialization_registers` | `uint32_t r[24]`, then `uint32_t gp`, `sp`, `lr`, `r27`, `r28`, `r29`, `sr` |
| `struct soc_initialization_observations` | `uint32_t version1`, `enum soc_initialization_followup kind`, `uint32_t word` |
| `struct soc_initialization_buffer` | `uint8_t *bytes`, `size_t length` |
| `struct soc_initialization_memory` | `struct soc_initialization_buffer buffers[SOC_INITIALIZATION_REGIONS]` |
| `struct soc_initialization_stack` | `uint8_t *bytes`, `size_t length`, `uint32_t address` |
| `struct soc_initialization_result` | `struct soc_initialization_registers registers`, `uint32_t pc` |

`SOC_INITIALIZATION_REGIONS` is 7. The function returns
`enum soc_initialization_status`. Its first four parameters point to const
objects of the corresponding types; `input` points directly to the scalar
register structure. `result` points to a mutable result object. Const
descriptors still describe mutable byte storage where specified below.
Entry PC is implicit. No source bytes, selection table, instruction stream
or arbitrary address map are inputs.

All five object pointers and all eight byte pointers are required. Typed
objects require natural host alignment; byte storage needs no host
alignment. All 31 incoming scalar words are supplied explicitly. No saved
register, flag, control value or guard is implicitly zero. GP must be
four-byte aligned as a portable host restriction; this does not assert that
the vendor checks GP or rejects physical unaligned access. SP and LR follow
the address rules below.

### Supplied observations

`version1` supplies V1. `enum soc_initialization_followup` has two values:
`SOC_INITIALIZATION_VERSION2` (0) and `SOC_INITIALIZATION_MMIO` (1). The
recognized selectors in the selection table require the MMIO tag and use
`word` as M. Every other V1 requires the VERSION2 tag and uses `word` as an
independent V2. Each word accepts all 32-bit values. An unknown tag or a
valid tag for the wrong path is invalid input.

Exactly one follow-up word is present. There is no unused third input to
read, validate or replace with a default. The source consumption is the
one V1 observation and the one selected follow-up listed above. The
function executes no VERSION instruction, peripheral read or callback.
Reading or copying immutable host input is not a hardware observation;
the interface does not promise a trace of host loads.

### Guarded ordinary storage

`enum soc_initialization_region` uses the indices in this table. Each
numeric VPU start is incoming GP plus the listed offset; callers do not
supply a second address. Field offsets in the last column are relative
to the buffer start.

| Index and enum member | GP-relative start | Exact bytes | Fields |
| --- | --- | ---: | --- |
| 0, `SOC_INITIALIZATION_FLAGS_A` | 0x1560 | 16 | Four-byte first flag at 4 and second flag at 8 |
| 1, `SOC_INITIALIZATION_FLAGS_B` | 0x16E0 | 16 | Four-byte third flag at 4 and fourth flag at 8 |
| 2, `SOC_INITIALIZATION_COMPLETION` | 0x3B890 | 12 | Four-byte completion word at 4 |
| 3, `SOC_INITIALIZATION_CLASSIFICATION` | 0x3B8AC | 8 | Classification byte at 2 |
| 4, `SOC_INITIALIZATION_CONTROL_MODE` | 0x3B920 | 20 | Four-byte Q at 4 and four-byte mode at 12 |
| 5, `SOC_INITIALIZATION_DIAGNOSTIC` | 0xCCDB4 | 12 | Read-only L at 4 |
| 6, `SOC_INITIALIZATION_WATCHED` | 0x3B480 | 12 | Read-only four-byte watched word at 4 |

The seven declared buffers total 96 bytes. Each length must equal its table
value; smaller and larger spans are rejected. A byte pointer remains
required even when a malformed descriptor has zero length. L must be
0, 1, 2 or 3; the other 95 bytes have arbitrary initial values. Only the
fields selected by the source relation may change. All other bytes remain
unchanged, including GP+0x1560 and the complete diagnostic and watched
buffers. The default path requires no Q content read for validation or
execution. Little-endian transfers are independent of host byte order.

### Addresses and host spans

Every full GP-relative range must fit in the 32-bit address space without
wrapping; its exclusive end may equal 2^32. `stack` declares a mutable byte
span beginning at its numeric `address`. Its length is at most UINT32_MAX,
and its exclusive virtual end may equal 2^32 but may not exceed it. S must
be four-byte aligned and at least 24. The entire frame [S-24, S) must fit
inside the declared span. Extra stack guard bytes are permitted.

All seven complete GP-relative spans and the entire declared stack span
must be pairwise disjoint. Each also excludes both fixed intervals:

| Fixed range | Half-open address interval | Bytes |
| --- | --- | ---: |
| Selected source and selection table | [0x0EC6221C, 0x0EC62372) | 342 |
| Supplied peripheral-read cell | [0x7E0000B4, 0x7E0000B8) | 4 |

The source interval is the exact union of the selected code and table;
no later byte is included. The peripheral exclusion is the single read
cell, not an inferred wider aperture. Both exclusions apply on both paths.

LR must be even and outside all seven ordinary spans, the entire stack
span and both fixed intervals. These are conservative host stop-token
checks. The body at 0x0EC62370 returns through saved incoming LR, and the
interface does not fetch or execute there. Half-open intervals that meet
only at an endpoint are disjoint. No numeric address or scalar word
becomes a host pointer.

Each complete host pointer-plus-length must fit uintptr_t. All 13 full
host spans are pairwise disjoint: the five typed objects, seven ordinary
buffers and entire stack byte span. All object padding belongs to its
span. Read-only inputs and diagnostic/watched buffers receive no overlap
exemption. Adjacent spans are permitted. Host-span checks are separate
from the VPU-address checks.

Required pointers, typed alignment and typed host spans are checked before
reading typed objects. Descriptor contents establish the byte spans.
Their lengths, host arithmetic and disjointness, all virtual arithmetic,
the frame and LR exclusions, GP alignment, the observation tag and L range
are validated before any output store. L is read only after its descriptor
and full span pass the storage checks. Validation requires no content read
from an unselected flag, guard or watched word.

### Results and rejection

Success returns `SOC_INITIALIZATION_OK` (0), separately from final r0.
Result contains exactly the 31 scalar words and PC in the state table.
Only selected ordinary fields, the 24 frame bytes and result may change.
Every other declared byte is preserved. Result publication follows ordinary
data and frame stores. Input registers, observations and descriptors remain
immutable.

The ordered native intermediate writes remain part of the source behavior
above. The portable operation specifies the resulting ordinary-storage
state. It exposes no intermediate-state observer, event stream, instruction
count, callback or physical store timing. Host stores are not a substitute
for the source-access trace when comparing native observation order.
Volatile storage, MMIO and concurrent observers are outside this interface.

| Host status | Value | Rejected condition |
| --- | ---: | --- |
| `SOC_INITIALIZATION_INVALID` | -1 | Null required object or byte pointer; typed-object misalignment; GP or SP not four-byte aligned; SP below 24; odd LR; unknown or path-inconsistent observation tag |
| `SOC_INITIALIZATION_UNSUPPORTED` | -2 | Diagnostic byte L greater than 3 |
| `SOC_INITIALIZATION_BOUNDS` | -3 | Host or virtual span wrap; stack length above UINT32_MAX; wrong ordinary-buffer length; frame outside the declared stack span |
| `SOC_INITIALIZATION_OVERLAP` | -4 | Intersecting full host spans; intersecting ordinary/stack virtual spans; an ordinary or stack span intersecting a fixed interval; LR inside any ordinary, stack or fixed interval |

If several conditions fail, any applicable error may be returned. Rejection
preserves every supplied byte and object, including result, and publishes
no partial scalar state. Preflight invokes no external code or hardware.
This atomic rejection is host policy. The vendor entry at 0x0EC6221C writes
its frame before selection and provides no matching rollback guarantee for
unsupported diagnostic paths.

Callers provide actual backing, readability, writable result and frame,
and writability of the ordinary fields changed by the selected path.
All storage remains valid through return and has no concurrent access.
Integer span checks cannot establish allocation validity. The function
allocates, frees and retains no storage. It performs no physical hardware
initialization and establishes no startup arrival, live allocation
lifetime or later preservation of the watched word.

## Open questions

- Diagnostic calls. Establish the effects and return behavior of
  0x0EDA5E7E before extending the domain to L of 4 or more. The five call
  sites may expose changed registers or memory; their effects cannot be
  replaced by an assumed empty call.
- Physical observations. Establish actual VERSION values and any
  cross-site relationship, the meaning and read effects of 0x7E0000B4,
  and physical address visibility before applying synthetic inputs to
  hardware initialization.
- Stack semantics. Resolve the incoming decoder context and multi-register
  save/restore order against an independent instruction oracle or an
  approved hardware observation before claiming physical equivalence.
- Startup state and lifetime. Establish the calling route, L at entry,
  valid storage and intervening writes before applying this preservation
  result to the watched first-open word. The earlier clear alone does not
  establish those premises or preservation across later callbacks.
