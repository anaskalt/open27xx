<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Service token lookup

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

Entry 0xCEC00D82 searches a fixed table of 42 numeric tokens for the incoming
32-bit word. It returns the matching index or 0xFFFFFFFF. It does not
dereference the query, invoke a table entry, write memory or call another
function. The body occupies 30 bytes at file offset 0x1362, with SHA-256
`d1c1c0e3ce71da2dbf2ac3cfd511439172d31136e91abdd81161509dfd64f68e`.

The complete source control flow defines the general behavior below.
Five recorded standalone calls check selected inputs. No portable API
or connected SWI call is specified here.

## Original token table

The table begins at B=0xCEC01B60, file offset 0x2140. It contains 42
little-endian 32-bit words and occupies 168 bytes through 0xCEC01C07.
Its SHA-256 is
`bf1e371e217c0090fe5493b0ba54f9507c59c7fcd80a13bd3537ed619e35512b`.
Entry i is at B+4i, file offset 0x2140+4i. The tokens below are complete
numeric address metadata for this file revision; they are not handler
implementations or inferred service names.

| Index | Word address | Token |
|---:|---|---|
| 0 | 0xCEC01B60 | 0xCEC00D82 |
| 1 | 0xCEC01B64 | 0xCEC00432 |
| 2 | 0xCEC01B68 | 0xCEC0043E |
| 3 | 0xCEC01B6C | 0xCEC00460 |
| 4 | 0xCEC01B70 | 0xCEC004AE |
| 5 | 0xCEC01B74 | 0xCEC0053A |
| 6 | 0xCEC01B78 | 0xCEC005A6 |
| 7 | 0xCEC01B7C | 0xCEC00680 |
| 8 | 0xCEC01B80 | 0xCEC00694 |
| 9 | 0xCEC01B84 | 0xCEC006A6 |
| 10 | 0xCEC01B88 | 0xCEC006D0 |
| 11 | 0xCEC01B8C | 0xCEC006DE |
| 12 | 0xCEC01B90 | 0xCEC006F6 |
| 13 | 0xCEC01B94 | 0xCEC00766 |
| 14 | 0xCEC01B98 | 0xCEC0077E |
| 15 | 0xCEC01B9C | 0xCEC0079E |
| 16 | 0xCEC01BA0 | 0xCEC007B4 |
| 17 | 0xCEC01BA4 | 0xCEC007B8 |
| 18 | 0xCEC01BA8 | 0xCEC007C4 |
| 19 | 0xCEC01BAC | 0xCEC00860 |
| 20 | 0xCEC01BB0 | 0xCEC0088E |
| 21 | 0xCEC01BB4 | 0xCEC0090C |
| 22 | 0xCEC01BB8 | 0xCEC00996 |
| 23 | 0xCEC01BBC | 0xCEC009C2 |
| 24 | 0xCEC01BC0 | 0xCEC00A4A |
| 25 | 0xCEC01BC4 | 0xCEC00A68 |
| 26 | 0xCEC01BC8 | 0xCEC00E16 |
| 27 | 0xCEC01BCC | 0xCEC00E40 |
| 28 | 0xCEC01BD0 | 0xCEC011A8 |
| 29 | 0xCEC01BD4 | 0xCEC011BE |
| 30 | 0xCEC01BD8 | 0xCEC011CA |
| 31 | 0xCEC01BDC | 0xCEC011E0 |
| 32 | 0xCEC01BE0 | 0xCEC01444 |
| 33 | 0xCEC01BE4 | 0xCEC01560 |
| 34 | 0xCEC01BE8 | 0xCEC016E4 |
| 35 | 0xCEC01BEC | 0xCEC01700 |
| 36 | 0xCEC01BF0 | 0xCEC01714 |
| 37 | 0xCEC01BF4 | 0xCEC01918 |
| 38 | 0xCEC01BF8 | 0xCEC01954 |
| 39 | 0xCEC01BFC | 0xCEC019EC |
| 40 | 0xCEC01C00 | 0xCEC01A74 |
| 41 | 0xCEC01C04 | 0xCEC01B20 |

All 42 words are distinct. The original imported `.secfns` block spans
exactly these 168 bytes, is initialized and readable/executable, and is
not writable. Before the recorded calls, its complete current bytes and
direct file mapping match the original ELF range, and its complete
original-file digest matches the firmware identity above. No synthetic
table, overlay or replacement token is supplied. This observation does
not establish a live device mapping or table lifetime.

## General scalar behavior

Incoming r0 supplies query Q, an arbitrary unsigned 32-bit word. Zero,
odd values and values differing only in a high address bit are permitted
queries. Comparison uses all 32 bits without alignment masking, tag
removal, address translation or pointer conversion.

The body examines words in increasing index order, starting at zero.
At 0xCEC00D8E it reads the current word and advances the table cursor by
4. The equality test at 0xCEC00D92 selects an immediate match. Otherwise
the index advances by one at 0xCEC00D96 and the next word is examined,
unless all 42 entries have been consumed. A match returns its index.
Exhaustion selects 0xFFFFFFFF at 0xCEC00D9A. Both paths select the raw
result at 0xCEC00D9C and return through incoming LR at 0xCEC00D9E.

The query is never used as a memory address or call target. Its numeric
value may coincide with an observed-memory address or another scalar
value without creating an access to that address. The table is fixed
original file data, not an additional caller-selected argument.

All table reads are four-byte aligned and remain within B through
B+167. The post-read cursor may equal B+168, but that one-past address
is not read. Index and cursor increments cannot overflow: the index
reaches at most 42, and the largest cursor is 0xCEC01C08. No loop
depends on external replies or mutable device state.

## Incoming state and observation bounds

Within this scalar contract, incoming r1 through r23, GP, SP, r27 through
r29 and SR may contain arbitrary 32-bit values. They do not select a
branch or provide table data. The body neither accesses stack memory
through SP nor uses GP-relative addressing. Supplied stack backing is
optional observation storage, not a frame consumed by this function.
Arbitrary incoming SP does not imply a valid physical processor stack.

Let L be the incoming LR. L is an even external completion address outside
the complete 30-byte body and the complete 168-byte table. It also lies
outside every declared observation span. Completion stops before any
instruction at L executes; no behavior after that transfer is included.

Every declared observation span must be nonwrapping, actually backed,
readable and disjoint from every other declared span, the entire source
body and the entire original table. Fixture setup must not overlay either
source range. These exclusions apply to whole spans even if a particular
query returns before reading the entire table. Initial observation bytes
are arbitrary and remain unchanged because the function writes no memory.
The table and original instructions remain stable throughout the call.
No external observer, interrupt arrival or concurrent write changes them.

These are bounded environmental premises. They do not restrict Q to the
five recorded values or claim that arbitrary supplied registers describe
an observed hardware state. The recorder's synthetic storage windows
remain a separate admission requirement for concrete replay requests.

## Complete result equations

Let T[i] be the word at table index i. For a matching query, j is its
index, with 0 through 41 inclusive. For an absent query, every table word
differs from Q. The complete final register effects are:

| Register | Match at j | No match |
|---|---|---|
| r0 | j | 0xFFFFFFFF |
| r1 | B+4(j+1) | B+168 = 0xCEC01C08 |
| r2 | 42 | 42 |
| r3 | j | 0xFFFFFFFF |
| r4 | T[j] = Q | T[41] = 0xCEC01B20 |
| PC | L | L |
| LR | Incoming L | Incoming L |
| r5 through r23, GP, SP, r27 through r29, SR | Incoming values | Incoming values |

No byte of ordinary RAM, original table data or MMIO is written. There
are no semantic provider events, subordinate calls or computational
function replies. In particular, this body does not store an index
through a caller output pointer.

For a match at j, there are j+1 table reads and 7+3j instructions.
For no match, there are 42 table reads and 132 instructions. The maximum
is therefore 132 instructions. These equations follow the complete
source path; the five native calls measure selected instances.

The pinned language is `vc4:LE:32:default` from
`aleph-void/ghidra-videocore4` revision
`db09a308c2db6a31ba5e060e6b763713f77e4f7b`, as listed in
[references](../references.md#open-source-projects). The installed
`data/languages/vc4.slaspec` SHA-256 is
`a3cc3f596d63a268440a659baa6fcf92e15900ec7ca1b8c2c733203d45236131`;
the compiled language SHA-256 is
`2303eea79ede697a37318068af1514de75ff64d9fcf2965623e2ab417e93bb56`.
The scalar comparisons branch on their own computed predicates and do
not read or update SR. No unsupported instruction or exception operation
is needed for this bounded lookup.

## Recorded cases and replay

[service-token-lookup.json](../../tests/vectors/start4/service-token-lookup.json)
contains the five complete calls. Its SHA-256 is
`0a50b8cbde34f021743ecd1a7965de3e8be193645be406b9cba0f411bb6d3f41`.
Only incoming register and observation-memory state is synthetic. The
original table supplies every token read.

| Case | Query Q | Incoming SR | Raw result | Instructions |
|---|---|---|---|---:|
| first-table-token | 0xCEC00D82 | 0x00000000 | 0 | 7 |
| first-open-service-token | 0xCEC006D0 | 0x400000A5 | 10 | 37 |
| last-table-token | 0xCEC01B20 | 0xFFFFFFFF | 41 | 130 |
| low-bit-difference | 0xCEC006D1 | 0x80000008 | 0xFFFFFFFF | 132 |
| high-address-bit-difference | 0x4EC006D0 | 0x1234567B | 0xFFFFFFFF | 132 |

Every call uses SP=0x24010000, L=0x24040000, 128 observed bytes at
0x2400FFC0 and a separate four-byte canary at 0xE40CB488. All 132 bytes
and all 32 ordinary registers are compared. The canary remains unchanged;
it is not a runtime index destination produced by this call.

Totals are 438 instructions, 160 compared register words, 660 observed
bytes and zero semantic events. Independently derived paths cover all
nine PCs and 30 bytes, with 138 table-word reads across the five calls.
The recorder exports final state, events and instruction totals, not
an executed-PC or memory-read trace. These five samples do not exhaust
the unsigned 32-bit query or incoming-state domain.

Use the imported program and versions in [headless analysis](../analysis.md),
with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0xCEC00D82 \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/service-token-lookup.json /work/analysis/service-token-lookup.json
cmp tests/vectors/start4/service-token-lookup.json /work/analysis/service-token-lookup.json
```

The original-table mapping and byte identity are observed before the
calls. No separate post-run table-digest observation is claimed.

Three controls reject a wrong source digest, a four-byte setup region
outside the synthetic windows and a one-instruction-short budget before
the last-token return at 0xCEC00D9E. Each yields its exact diagnostic and
no completed result artifact. Earlier setup initialization can precede
the storage rejection. The short-budget index is source-derived, not
an exported negative runtime count. Absent output does not imply rollback.

## Relationship to first open

The table at 0xCEC01B60 places this lookup body at service index zero.
The [driver initialization prefix](driver-initialization.md) passes
token 0xCEC006D0 to wrapper 0x0ED6529A and supplies GP+0xCB488 as an
output destination. The actual standalone lookup produces index 10
for that token. This fact does not establish that SWI0 at 0x0ED6528E
delivers the request, that the wrapper receives the result or that the
destination is written in the live initialization path.

The [service initializer](service-initialization.md) and
[service word update](service-word-update.md) remain separate evidence.
Neither this ordinary lookup return nor those standalone calls establish
the connected wrapper, trap frame, dispatcher, selected handler and
RTI transition. The opaque first-open word has a separate unresolved
runtime producer.

## Open questions

- Connected lookup. Establish SWI entry, dispatcher argument routing,
  trap-frame production and return before accepting the wrapper's
  service-index destination write or a complete driver initializer.
- Runtime table lifetime. Establish startup mapping, fixups and any
  subsequent writers before treating the original imported table as
  live hardware state. Other firmware revisions require their own
  table identity and behavior evidence.
- Remaining service tokens. Establish each body and its input/output
  contract before assigning functional names or invoking its token.
  A numeric table mapping does not prove a handler's behavior.
- Higher first-open state. Establish actual runtime index and opaque-word
  producers before using the lookup result as evidence of a completed
  first-open service call. No hardware effects are part of this lookup.
