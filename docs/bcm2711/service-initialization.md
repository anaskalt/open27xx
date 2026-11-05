<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Service initialization and constructed return frame

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

Entry 0xCEC002A0 selects an address from VERSION, writes a fixed table base
and checks five normalized VERSION values. One branch also updates an
original ELF table word and performs three ordered MMIO writes. Both
branches construct a return frame with ordinary stores, then complete
through the installed RTI semantics at 0xCEC00D80. Five recorded standalone
calls cover the five comparisons and both branches.

This is distinct from the [driver initializer](driver-initialization.md)
at 0x0ED005BC. It does not complete that initializer's lookup, produce a
service index or execute the first-open service wrapper. No portable
initialization API is specified here.

| Entry | File offset | Bytes | Role |
|---|---|---:|---|
| 0xCEC002A0 | 0x880 | 96 | VERSION selection and validation |
| 0xCEC00DD0 | 0x13B0 | 70 | Original table-word update and three writes |
| 0xCEC00D76 | 0x1356 | 12 | Frame construction and RTI |

Body SHA-256 values, in table order, are
`61d2a307b9a2ffd623a8ae8ee8b5dd2c0b90b7d71c0ea48aa76a94218720e00e`,
`3c41d835b703416a0e4f9ac4087df7a07c508d0bc20bdde6565f63cd9c3f564e`
and `34ebd6e0275337356f519b4ada42c86ad4076786edbe73132310ca1b4145cff6`.

## General conditional input domain

The [VERSION observation](vpu-version.md) supplies the same unsigned
32-bit word V at 0xCEC002A0 and 0xCEC002EA. Define N as V with bits 16 and
3 cleared, or `V & 0xFFFEFFF7`. Complete return requires N to equal one
of the following values, in the comparison order shown:

| Comparison index k | N | Comparison address |
|---:|---|---|
| 0 | 0x04000162 | 0xCEC002C0 |
| 1 | 0x04000161 | 0xCEC002C8 |
| 2 | 0x04000160 | 0xCEC002D0 |
| 3 | 0x04000140 | 0xCEC002D8 |
| 4 | 0x04000104 | 0xCEC002E0 |

Each N permits both values of bits 16 and 3, so this condition describes
20 distinct VERSION words. Bit 16 selects the two paths; bit 3 affects
neither path nor stored data. All other bits participate in the equality
checks. All 20 words follow the complete finite source control flow.
A changing VERSION between the two sites is outside this contract.

An unsupported N still permits the first VERSION observation and table-base
write before reaching BKPT at 0xCEC002E8. The recorder rejects its unsupported
operation before executing it. There is no accepted return or rollback
contract for that branch.

Let S be the incoming SP and L the incoming LR. S is four-byte aligned and
at least 8, with eight readable and writable RAM bytes immediately below
it. The declared stack span contains S-8 through S-1 and must not wrap.
The entire declared span and L exclude all of these fixed regions on both
branches, including regions that the selected branch otherwise leaves unused:

- All three complete source byte ranges in the first table.
- The four-byte ELF word at 0xCEC01E80.
- All four MMIO word spans: four bytes each at 0x7E002030, 0x7E002830,
  0x7EE0003C and 0x7EE00040.

Initial stack contents are arbitrary: every read follows the call's own
write. Bytes outside S-8 through S-1 remain unchanged. L is even and also
lies outside the entire declared stack span. Completion stops before any
instruction at L executes.
Initial r0 through r23, GP, r27 through r29 and SR may contain arbitrary
32-bit values. Their values neither select another path nor supply the
frame contents, except that L supplies its return-address word. The call
does not dereference GP or any incoming general-register pointer.

These storage and incoming-state generalizations follow the actual read,
write and branch dependencies. The five native profiles use S=0x24010000,
L=0x24040000 and 128 stack bytes; they do not dynamically exhaust the
general domain. Readability, writability, lifetime and separation from
unrelated state are explicit environmental premises, not inferred live
hardware properties.

The source table word is fixed to the original ELF state below. Arbitrary
initial words, an already-updated table, concurrent modifications and
repeated initialization of live storage are outside the recorded domain.
The scalar OR operation sets bit 0 without changing the other bits, but
that arithmetic fact is not evidence of those alternative initial states.

## Ordered effects

At 0xCEC002BA the first write stores 0xCEC01E00. Its address is 0x7E002030
when V bit 16 is clear, or 0x7E002830 when that bit is set. This write
precedes all five VERSION comparisons. The second VERSION observation
occurs only after a comparison matches.

For bit 16 clear, the complete observable sequence is:

| Order | Kind | Source address | Address or word |
|---:|---|---|---|
| 1 | VERSION observation | 0xCEC002A0 | V |
| 2 | MMIO write | 0xCEC002BA | 0xCEC01E00 to 0x7E002030 |
| 3 | VERSION observation | 0xCEC002EA | V |
| 4 | Original ELF word read | 0xCEC00DDC | 0xCEC00DA0 from 0xCEC01E80 |
| 5 | ELF word write | 0xCEC00DE2 | 0xCEC00DA1 to 0xCEC01E80 |
| 6 | MMIO write | 0xCEC00DF6 | 0x0EC00000 to 0x7EE0003C |
| 7 | MMIO write | 0xCEC00E02 | 0x0EC01FFF to 0x7EE00040 |
| 8 | MMIO write | 0xCEC00E0C | 0x0EC00001 to 0x7EE0003C |

For bit 16 set, only the first three events occur, with the first write
address changed to 0x7E002830. The call does not access the ELF word or
the two addresses in the final three rows.

The ELF word at 0xCEC01E80 has file offset 0x660 and size 4. Its initial
word is 0xCEC00DA0, with SHA-256
`fabeeb78a36193b6aebc55fd2e1654b76fb9f134526b8cdc8c20bc3c43a60f69`.
It lies 128 bytes into the 512-byte initialized readable/writable,
nonexecuting segment at 0xCEC01E00, file offset 0x5E0. The segment's
SHA-256 is `26c2f537974bcf011ec71a7639e51de5aca63d544cd62eb8f59da859114cd5b3`.
The update changes only bit 0 of that one word. No caller-supplied overlay
or function reply produces either its initial value or its update.

The three final MMIO values follow fixed unsigned scalar arithmetic from
0xCEC00000: the low 28 bits form 0x0EC00000, adding 0x1FFF forms
0x0EC01FFF, and setting bit 0 of the first value forms 0x0EC00001. No
MMIO read or read-modify-write operation occurs. Address names, device
meaning, table-tag interpretation and effects on physical memory remain
unresolved. These numeric observations alone do not identify hardware
register semantics.

## Actual frame and pinned completion

Both paths reach 0xCEC00D76 with the original L in LR. The bit-16-clear
path first stores L at S-4 and reads it back at 0xCEC002F4 and 0xCEC002F6;
the stack returns to S before the later frame construction. That path
also retains L in r5 while performing its table and MMIO updates.

At 0xCEC00D78 the body stores L at S-4. At 0xCEC00D7C it stores zero at
S-8. SP then equals S-8. The resulting frame is:

| Address | Size | Value |
|---|---:|---|
| S-8 | 4 | Zero status word |
| S-4 | 4 | Incoming L |

The installed scalar RTI semantics at 0xCEC00D80 read the status word,
advance SP by 4, read the return address, advance SP by 4, assign SR and
transfer to that return address. The actual preceding instructions
produce both words. No exception frame, replacement return value or
instruction bypass supplies them.

The pinned `aleph-void/ghidra-videocore4` revision
`db09a308c2db6a31ba5e060e6b763713f77e4f7b`,
[`data/languages/vc4.slaspec`](https://github.com/aleph-void/ghidra-videocore4/blob/db09a308c2db6a31ba5e060e6b763713f77e4f7b/data/languages/vc4.slaspec#L496-L504),
defines these concrete loads, stack advances and transfer. Its status
packing/unpacking macros at lines 299 through 305 have empty bodies.
The installed specification SHA-256 is
`a3cc3f596d63a268440a659baa6fcf92e15900ec7ca1b8c2c733203d45236131`;
the compiled language SHA-256 is
`2303eea79ede697a37318068af1514de75ff64d9fcf2965623e2ab417e93bb56`.
This completion is confined to that pinned execution semantics. It does
not establish physical privilege, interrupt delivery or stack banking.

On completion, SP=S, LR=L, PC=L, SR=0 and r0=0. Other changed scalar
registers are:

| Register | V bit 16 clear | V bit 16 set |
|---|---|---|
| r1 | 0x7EE0003C | 0x7E002830 |
| r2 | 0x7EE00040 | 0xCEC01E00 |
| r5 | L | Incoming value |

All remaining ordinary registers retain their incoming values. The last
eight stack bytes retain the frame words after SP is restored. The initial
SR is not restored; the frame deliberately contains zero. Incoming flags
do not change the sequence: each conditional branch uses flags written
by its own preceding test or comparison.

There are no data-dependent loops. For comparison index k, the
bit-16-clear path takes 42+2k instructions and the bit-16-set path takes
18+2k. Those formulas derive from the complete source paths; the fixture
measures five selected totals.

## Caller and remaining first-open boundary

The original entry path at 0xCEC00252 loads the initializer target from
literal 0xCEC00294. It selects LR from its earlier startup state before
branching at 0xCEC0025A. The standalone calls explicitly supply L and
the initial registers instead of claiming that this startup path ran.

The updated word names the dispatcher at 0xCEC00DA0 with its low bit set.
The [service word update](service-word-update.md) separately describes
that dispatcher's static service table and selected handler. Neither the
table update nor this constructed RTI return proves that SWI0 at
0x0ED6528E produces a compatible trap frame, selects this word or reaches
the dispatcher. The dispatcher has a different RTI site, 0xCEC00DCA.

This body does not address the driver-control span at GP+0xCB480 or the
opaque first-open word at GP+0x3B484 through GP. It contains no GP-relative
initialization of a service-index lookup result or opaque handle. In the
recorded profiles, the independent four-byte canary at GP+0x3B484 remains
unchanged.

## Recorded cases and replay

[service-initialization.json](../../tests/vectors/start4/service-initialization.json)
contains the five complete calls. Its SHA-256 is
`2389936e44ae2b6deed89aff710b35cf6a801b50a7f756fd5d2f131c898b21d2`.
Caller register/stack state and VERSION observations are synthetic.
The initial ELF word is original file-backed data, not synthetic input.
No computational stubs or MMIO read replies occur.

| Case | V | Incoming SR | Instructions | Events |
|---|---|---|---:|---:|
| first-version-primary | 0x04000162 | 0x00000000 | 42 | 8 |
| second-version-secondary-bit3 | 0x04010169 | 0x400000A5 | 20 | 3 |
| third-version-primary-bit3 | 0x04000168 | 0xFFFFFFFF | 46 | 8 |
| fourth-version-secondary | 0x04010140 | 0x80000008 | 24 | 3 |
| fifth-version-primary | 0x0400010C | 0x1234567B | 50 | 8 |

Totals are 182 instructions, 160 compared register words, 672 observed
bytes and 30 events. All 128 stack bytes per call, the four-byte independent
canary and each complete accessed ELF word are compared. The independently
derived paths visit 52 PCs covering 176 bytes. The recorder exports final
state, ordered semantic events and instruction totals, not a full PC trace.
These finite calls do not exhaust the general VERSION or incoming-state
domain.

Use the imported program and versions in [headless analysis](../analysis.md),
with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0xCEC002A0 0xCEC00DD0 0xCEC00D76 \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/service-initialization.json /work/analysis/service-initialization.json
cmp tests/vectors/start4/service-initialization.json /work/analysis/service-initialization.json
```

The [ELF data observation contract](../elf-data-observations.md) requires
the complete original-file digest, exact direct file mapping, unchanged
current bytes, initialized readable/writable nonexecuting storage and
complete final-region observation before execution. Its ordered accesses
observe the actual source read and write; they do not supply replacement
data. Original instruction-byte and unsupported-operation guards remain.
The two VERSION sites use their shared immutable word. No IRQ/p16 plan
is needed by these paths.

Four controls reject a wrong original-region digest, an incomplete final
region observation, reversed source-access order at 0xCEC00DDC and an
unsupported VERSION reaching BKPT at 0xCEC002E8. Each produces no completed
result artifact. The two runtime rejections can follow earlier MMIO or
stack writes; absent output does not imply rollback. Their instruction
indices are source-derived, not exported negative runtime counters.

## Open questions

- Physical RTI semantics. Establish privilege, status packing, interrupt
  and stack-bank behavior from authoritative processor documentation or
  separately approved hardware observations. The installed scalar
  semantics and its constructed-frame result do not settle those facts.
- SWI composition. Establish trap-frame production, vector selection,
  low-bit interpretation and dispatcher return before joining this setup
  to the service wrapper and higher first-open success path.
- MMIO purpose and VERSION values. Bind the numeric writes and actual
  processor observations to an authoritative device definition before
  assigning physical register names or hardware initialization success.
- Runtime arrival and lifetime. Establish startup invocation, mapping and
  subsequent writes before treating the updated table word as live state.
  The five calls all start from the original ELF word; an already-updated
  word and repeated live initialization require separate evidence.
- Driver index and opaque word. Establish their actual producers and
  intervening state. This initializer has no GP-relative producer for either;
  the [driver initialization prefix](driver-initialization.md) still stops
  before the first lookup SWI.
