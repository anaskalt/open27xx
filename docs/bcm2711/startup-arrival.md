<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Conditional startup arrival

The source below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

The ELF entry at 0xCEC00200 selects a stack and return continuation, then
branches to the service initializer at 0xCEC002A0. A complete service return
to the primary continuation leads through three predecessor calls to the
initialization-table call at 0x0EC2CBC2, target 0x0EC3D740. This is a
conditional source route. No complete entry-to-initializer execution or
physical startup arrival is established by these source bindings.

## Source extent

The selected code contains 61 instructions in 204 bytes. The five data
ranges contain 48 original bytes. The service initializer and table parser
have separate contracts; their bodies are outside these selected ranges.

| Code range | Address | File offset | Bytes |
| --- | --- | --- | ---: |
| Entry and continuation selection | 0xCEC00200 | 0x7E0 | 92 |
| Primary prefix through parser call | 0x0EC2CB90 | 0x2C590 | 54 |
| First return-only predecessor | 0x0EC2FCCC | 0x2F6CC | 2 |
| Middle hook | 0x0EC36AEC | 0x364EC | 30 |
| Third return-only predecessor | 0x0EC2FCD0 | 0x2F6D0 | 2 |
| Selected callback | 0x0EC87EE8 | 0x878E8 | 12 |
| VERSION leaf and pointer getter | 0x0EC87F2E | 0x8792E | 12 |

| Data range | Address | File offset | Bytes |
| --- | --- | --- | ---: |
| Entry literals | 0xCEC00280 | 0x860 | 32 |
| Callback-table pointer | 0x0EE02C64 | 0x202644 | 4 |
| Callback slot | 0x0EDE886C | 0x1E824C | 4 |
| Optional progress pointer | 0x0EE055B0 | 0x204F90 | 4 |
| Progress word | 0xCEC02000 | 0x231AA0 | 4 |

## Entry selection

Let E denote the scalar VERSION result at 0xCEC00200. The test at
0xCEC00206 examines bit 16. It sets SR's low nibble to 0xA when that bit
is clear and to zero when it is set, preserving higher SR bits. No later
instruction in the selected entry range writes SR. In particular, the
comparisons at 0xCEC0020C, 0xCEC00216, 0xCEC00220 and 0xCEC0023C make
their branch decisions without replacing those flags.

The original literal words are:

| Address | Value | Use |
| --- | --- | --- |
| 0xCEC00280 | 0x00000400 | Fallback size |
| 0xCEC00284 | 0x00000400 | Subtraction from selected SP into r28 |
| 0xCEC00288 | 0x0EE33203 | First stack candidate |
| 0xCEC0028C | 0x0EE33A03 | Second stack candidate |
| 0xCEC00290 | 0x0EE04140 | GP |
| 0xCEC00294 | 0xCEC002A0 | Service initializer target |
| 0xCEC00298 | 0x0EC2CB90 | Primary continuation |
| 0xCEC0029C | 0x0EC2CC28 | Alternate continuation |

Both stack candidates differ from the sentinel value 3. The first two
comparisons therefore skip the first breakpoint and the fallback block.
The nonzero size word skips the remaining breakpoint. None of the three
breakpoint paths at 0xCEC00210, 0xCEC00224 and 0xCEC00240 is selected
with these original literals. Their software-interrupt semantics remain
outside the route described here.

The preserved bit-test condition selects r29, clears the chosen stack's low
two bits and selects the continuation placed in LR. At 0xCEC0025A:

| State | E bit 16 clear | E bit 16 set |
| --- | --- | --- |
| GP | 0x0EE04140 | 0x0EE04140 |
| SP | 0x0EE33200 | 0x0EE33A00 |
| r28 | 0x0EE32E00 | 0x0EE33600 |
| r29 | 0x00000000 | 0x00000001 |
| LR | 0x0EC2CB90 | 0x0EC2CC28 |
| Branch target | 0xCEC002A0 | 0xCEC002A0 |

The entry branches to the service initializer, with the selected later
continuation in LR. It does not directly branch to either continuation.
The alternate continuation's body is outside the selected source extent.

## Service return premise

The [service-initialization contract](service-initialization.md#general-conditional-input-domain)
requires its two VERSION observations at 0xCEC002A0 and 0xCEC002EA to
supply the same value V. Completion requires V & 0xFFFEFFF7 to be one of
0x04000162, 0x04000161, 0x04000160, 0x04000140 or 0x04000104, together
with the documented stack, original table-word and MMIO conditions.
Unsupported values do not have an accepted complete-return result.

Under that contract, the service body preserves GP, SP, r28 and r29 and
returns to its supplied LR. It sets SR to zero. The entry's bit-test flags
therefore do not survive this completed service return. The service writes
and constructed RTI frame remain subject to their separate pinned semantics.

E and V name separate observations. This source route does not establish
their equality, a concrete processor VERSION or physical service completion.
Primary continuation requires E bit 16 clear; it additionally requires the
service body to complete with its documented inputs and effects.

## Primary predecessor calls

The prefix at 0x0EC2CB90 calls the return-only bodies at 0x0EC2FCCC and
0x0EC2FCD0 around the middle hook at 0x0EC36AEC. The hook calls a getter
at 0x0EC87F32, which reads the contents of 0x0EE02C64. The original word
is 0x0EDE8854. Reading offset 0x18 from that table yields callback address
0x0EC87EE8 from 0x0EDE886C.

The hook calls that callback with r0=0. The callback calls the VERSION leaf
at 0x0EC87F2E, then returns H = (C >> 16) & 0xF, where C is that leaf's
unsigned scalar result. C is distinct from the entry observation E and the
paired service observations V. No actual value or cross-site consistency
is established for these observations.

If H is nonzero, the hook skips its optional progress store. If H is zero,
it reads GP+0x1470, which is 0x0EE055B0 for the selected GP. The original
word contains 0xCEC02000, so the hook writes 0x70736662 to the caller's
progress cell. This path has no separate null-pointer check. These effects
depend on the original pointer values and their storage remaining valid.

The primary prefix assigns r15=0xCEC02000. Its ordered four-byte progress
writes and following calls are:

| Store address in code | Value stored at 0xCEC02000 | Following call |
| --- | --- | --- |
| 0x0EC2CB9C | 0x68736D5F | 0x0EC2FCCC; returns to 0x0EC2CBA2 |
| 0x0EC2CBA8 | 0x68736F5F | 0x0EC36AEC; returns to 0x0EC2CBAE |
| 0x0EC36B06, only H=0 | 0x70736662 | Inside the middle hook |
| 0x0EC2CBB4 | 0x6873755F | 0x0EC2FCD0; returns to 0x0EC2CBBA |
| 0x0EC2CBC0 | 0x7063695F | 0x0EC3D740; return address 0x0EC2CBC6 |

The original progress word is 0x5F5F5F5F. The values and destinations above
are numeric memory effects; they do not assign a hardware meaning to the
cell or prove that the stores occur during physical startup.

## Stack and initializer entry

Let S be SP at the primary continuation. The middle hook saves
0x0EC2CBAE at S-4, then its callback saves 0x0EC36AF8 at S-8. The leaf
and getter do not extend the stack. The callback and hook read their saved
return addresses and restore their incoming SP. Those returns do not
restore LR as a register; the two saved words remain in memory afterward.

The selected predecessors preserve GP, r28, r29, r15 and SR. With the
accepted service return, original pointers and completed predecessor calls,
the direct call at 0x0EC2CBC2 establishes this state at 0x0EC3D740:

| Register or storage | Conditional value |
| --- | --- |
| GP | 0x0EE04140 |
| SP | 0x0EE33200 |
| LR | 0x0EC2CBC6 |
| r28, r29 | 0x0EE32E00, 0x00000000 |
| SR | 0x00000000 |
| r15 | 0xCEC02000 |
| r0 | 0x7063695F |
| r3 | 0x0EC87EE8 |
| r1, r2 when H=0 | 0x70736662, 0xCEC02000 |
| r1, r2 when H is nonzero | Preserved service-return values |
| S-4, S-8 | 0x0EC2CBAE, 0x0EC36AF8 |

The call itself replaces LR with 0x0EC2CBC6, independently of the LR
left by nested returns. r5 and the other ordinary registers retain their
service-return values except for the explicit changes above. This is a
source-derived conditional caller state, not an additional captured profile.

The original `.stack` interval is 0x0EE32A00–0x0EE331FF. With the primary
S=0x0EE33200, the eight-byte service frame and eight-byte predecessor stack
use fit within it. The [table initializer's 24-byte frame](startup-initialization.md#caller-state-and-stack)
occupies 0x0EE331E8–0x0EE331FF, below its second clearing interval starting
at 0x0EE33200. Its saves overwrite the predecessor words before their
restoration reads. These address relationships establish compatible numeric
geometry; they do not establish live allocation or hardware alias behavior.

## Pinned semantics and limits

Source interpretation uses Ghidra 12.2, `vc4:LE:32:default`, compiler
specification `default` and VideoCoreIV commit
`db09a308c2db6a31ba5e060e6b763713f77e4f7b`. The compiled `vc4.sla`
SHA-256 is `2303eea79ede697a37318068af1514de75ff64d9fcf2965623e2ab417e93bb56`.
The pinned [`data/languages/vc4.slaspec`](https://github.com/aleph-void/ghidra-videocore4/blob/db09a308c2db6a31ba5e060e6b763713f77e4f7b/data/languages/vc4.slaspec)
supplies the scalar branch, flag and stack semantics. VERSION remains an
explicit unresolved processor observation.

For every selected instruction, ProgramContext current/default/nondefault
values are null. The 32-bit `contextreg` disassembly default and detached
instruction context each contain eight zero mask/value bytes. A zero mask
denotes unknown context bits, not a known-zero CPU state. The source bytes,
original-file mappings and these input-context values are bound by the
[read-only inspector](../../tools/ghidra/InspectStartupInitialization.java).

The completed [original-table initialization calls](startup-initialization.md)
remain separate observations with synthetic callers. The source route above
does not extend those two caller profiles into a complete boot or general
parser contract. No post-initializer call, alternate-continuation body or
later driver dispatch is included in this source extent.

## Open questions

- Actual arrival. Establish the executed entry state, concrete VERSION
  observations and their consistency, the service return and original
  pointer preservation before claiming this caller state occurs on hardware.
- Storage and aliases. Establish live stack/progress backing and physical
  address visibility. The loader's address arithmetic alone does not prove
  equivalence between the 0x0EC00000 and 0xCEC00000 ranges.
- Later state lifetime. Trace subsequent callers, indirect writes and
  concurrent effects before treating the table initializer's zero at
  GP+0x3B484 as the value consumed during first open.
- Service delivery. Establish SWI entry, trap-frame production, dispatcher
  selection and return independently. Entry breakpoint paths and the
  standalone service initializer do not prove that transition.
