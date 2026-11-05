<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Original-table startup initialization

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

Entry 0x0EC3D740 clears three original ELF allocations when called with
GP 0x0EE04140 and the unchanged initialization table at 0x0EDD7870.
Two complete calls with different caller registers, stacks and memory poisons
clear all 1015688 destination bytes and return through the saved caller
address. These calls establish the fixed original-table behavior under the
pinned Ghidra semantics below. They do not establish actual startup arrival
or a general initialization-table API.

## Source ranges and table

The complete selected instruction ranges contain 244 bytes at 75 instruction
sites. Each call executes 55 of those sites. Code and table bytes retain
their original file values before and after both calls.

| Range | Address | File offset | Bytes |
| --- | --- | --- | ---: |
| Initializer | 0x0EC3D740 | 0x3D140 | 182 |
| Completion return | 0x0EC3D7F6 | 0x3D1F6 | 2 |
| Scalar fill entry | 0x0ED1FDF0 | 0x11F7F0 | 4 |
| Scalar fill body | 0x0ED1FE14 | 0x11F814 | 56 |
| Initialization table | 0x0EDD7870 | 0x1D7270 | 36 |

The table begins with the three-byte identifier `INI`, followed by the
numeric version byte 0x02. The version is not an ASCII digit. Each following
record has a 32-bit destination and a signed 32-bit length, in little-endian
order. The recorded version-2 path reads these original records:

| Table offset | Record address | Destination | Signed length |
| --- | --- | --- | ---: |
| 0x04 | 0x0EDD7874 | 0x0EE056A0 | -2352 |
| 0x0C | 0x0EDD787C | 0x0EE33200 | -2048 |
| 0x14 | 0x0EDD7884 | 0x0EE33A00 | -1011288 |
| 0x1C | 0x0EDD788C | 0x00000000 | 0 |

For each negative length, the initializer supplies the destination, zero
fill value and negated byte count to 0x0ED1FDF0. The three fills run in table
order. The final zero-length, zero-destination pair ends this traversal.
No positive-length record or alternate version executes in these calls.

## Destination effects

The three records cover complete original allocations. Their program headers
have zero file size, read/write flags and alignment 32; their section headers
have type `SHT_NOBITS`. Header offsets describe metadata, not stored BSS bytes.

| Allocation | PT_LOAD index | Section index | Start | End, exclusive | Bytes |
| --- | ---: | ---: | --- | --- | ---: |
| First | 13 | 29 | 0x0EE056A0 | 0x0EE05FD0 | 2352 |
| Second | 17 | 34 | 0x0EE33200 | 0x0EE33A00 | 2048 |
| Third | 18 | 35 | 0x0EE33A00 | 0x0EF2A858 | 1011288 |

Each call starts with every destination byte explicitly set to its nonzero
poison. The fill body at 0x0ED1FE14 writes successive four-byte zero words;
its stores at 0x0ED1FE36 cover each destination byte exactly once. The three
regions receive 588, 512 and 252822 stores respectively. No runtime read
from these allocations occurs.

Complete final scans and hashes agree with zero-filled regions of the
declared sizes. All three nonzero-byte counts are zero. The code, table and
decoder transport bytes remain unchanged, and the original ProgramDB
allocations remain uninitialized. The clearing occurs in the disposable
emulator state used for each call.

## Caller state and stack

The two caller profiles supply all 32 registers. For ordinary numbered
register `ri`, the first profile uses 0x11110000 + `i` times 0x101 and the
second uses 0xEEEE0000 + `i` times 0x303. This covers `r0` through `r23` and
`r27` through `r29`. The named registers use the explicit values below.

| Input | First profile | Second profile |
| --- | --- | --- |
| GP | 0x0EE04140 | 0x0EE04140 |
| SP | 0x24010080 | 0x24010280 |
| LR and unmapped return address | 0x24000000 | 0x24000004 |
| SR | 0x13579BDA | 0xA5A5A5A5 |
| PC | 0x0EC3D740 | 0x0EC3D740 |
| Stack byte fill | 0x3C | 0xC3 |
| Destination byte poison | 0xA5 | 0x5A |

Let S denote the supplied SP. Each stack observation covers 128 bytes from
S-64 through S+63. The lowest SP is S-24. The pinned multi-register semantics
produce this retained frame:

| Address | Bytes | Final content |
| --- | ---: | --- |
| S-24 | 4 | Original poison; reserved local word remains untouched |
| S-20 | 4 | Incoming r9 |
| S-16 | 4 | Incoming r8 |
| S-12 | 4 | Incoming r7 |
| S-8 | 4 | Incoming r6 |
| S-4 | 4 | Incoming LR |

The five stack writes occur in the order LR, r6, r7, r8, r9. The final
restoration reads r9, r8, r7, r6 and the saved return address in that order.
The return at 0x0EC3D77C consumes the last word as its target and restores
SP to S. All 104 guard bytes outside the frame and the four-byte reserved
word retain their original poison. The complete 128-byte observations match
these effects, including all 108 untouched bytes.

The complete final register state is:

| Register | First profile | Second profile |
| --- | --- | --- |
| r0, r1, r2, r4 | 0x00000000 | 0x00000000 |
| r3 | 0x0EF2A858 | 0x0EF2A858 |
| r5 | 0x0EDD7870 | 0x0EDD7870 |
| r6 through r23 | Incoming values | Incoming values |
| GP | 0x0EE04140 | 0x0EE04140 |
| SP | 0x24010080 | 0x24010280 |
| LR | 0x0EC3D77A | 0x0EC3D77A |
| r27 through r29 | Incoming values | Incoming values |
| SR | 0x13579BD6 | 0xA5A5A5A6 |
| PC | 0x24000000 | 0x24000004 |

These are two complete caller profiles, not a proof for arbitrary register,
stack or destination inputs. The stack ordering follows the pinned
VideoCoreIV [`data/languages/vc4.slaspec` multi-register definitions](https://github.com/aleph-void/ghidra-videocore4/blob/db09a308c2db6a31ba5e060e6b763713f77e4f7b/data/languages/vc4.slaspec#L730-L813).

## Calls and counts

The helper calls and returns execute normally. Each fill enters
0x0ED1FDF0 from 0x0EC3D7F0, reaches the body at 0x0ED1FE14 and returns to
0x0EC3D7F4. After the terminator, the completion call at 0x0EC3D776 enters
0x0EC3D7F6 and returns to 0x0EC3D77A. The outer return at 0x0EC3D77C then
reaches the incoming-LR address without fetching it. The three fill calls,
three fill returns, completion call/return and outer return account for
nine recorded control transfers per profile.

| Observation per call | Operations | Bytes |
| --- | ---: | ---: |
| Completed instructions | 507943 | — |
| Table reads | 13 | 37 |
| Stack reads | 5 | 20 |
| Destination writes | 253922 | 1015688 |
| Stack writes | 5 | 20 |
| Total runtime data accesses | 253945 | 1015765 |

Table reads cover all 36 bytes; the version byte at table offset 0x03 is
read twice. Runtime writes cover only the three destinations and the five
saved stack words. Per-PC instruction counts, per-region access counts,
complete byte-coverage sets and ordered data-access digests match the
independent predictions for both profiles. Decoder reads, initial seeding
and final observation reads are separate from these runtime totals.

## Processor semantics and observation scope

The calls use Ghidra 12.2, language `vc4:LE:32:default`, compiler
specification `default`, and VideoCoreIV commit
`db09a308c2db6a31ba5e060e6b763713f77e4f7b`. The compiled `vc4.sla` SHA-256 is
`2303eea79ede697a37318068af1514de75ff64d9fcf2965623e2ab417e93bb56`.
All 75 selected instructions match the independently specified byte and
compiled p-code bindings. No instruction, source-table value, helper result
or return register is substituted.

The 32-bit decoder context register is `contextreg`. ProgramContext current,
default and nondefault values are null. The disassembly default and detached
instruction contexts have eight zero mask/value bytes. Existing listing
contexts are null or have the same eight zero bytes. Each fresh emulator's
context is null before seeding and the first step; after each step it has
eight zero mask/value bytes. Both complete calls preserve this recorded
policy, including per-PC repetition counts.

A zero context mask marks unknown bits. It does not assert a zero CPU state.
Decoder-local parser scratch is separate from these input-context values.
The observed stack and register effects apply to this pinned decoding
condition; they do not establish physical multi-register instruction order.

The [startup observation tool](../startup-zero-observations.md) defines the
exact request, source/allocation checks, finite limits, complete memory
scans and separate runtime/decoder accounting. Whole-file source, loaded
API, installed processor and recorder digests bind both calls. Independent
comparison covers every final register, stack byte, destination scan,
instruction count, selected byte/p-code binding and runtime access digest.

## Relation to first-open state

With the supplied GP, GP+0x3B484 is 0x0EE3F5C4, offset 0xBBC4 within the
third destination. Its four bytes are zero at both recorded returns.
This establishes a covering clear for that word in these original-table
calls. The [driver initialization prefix](driver-initialization.md) still
does not produce a service index through its unresolved SWI path.

The opaque first-open word's later value requires the actual invocation
order, intervening writes and address mapping. The observed clear alone
does not supply a live first-open handle or complete the service lifecycle.

## Open questions

- Startup arrival and lifetime. The [conditional source route](startup-arrival.md)
  derives a primary caller with GP 0x0EE04140 and SP 0x0EE33200 after a
  complete service return. Establish actual VERSION observations, execution
  and subsequent writes before assigning these zeros to later first-open state.
- Fixup-adjusted addresses. Compare the parser with admitted adjusted
  tables and destination mappings before extending the original-address
  result to other memory splits or aliases.
- Other table paths. Execute positive-length records, other INI versions,
  malformed headers and alternative termination states before defining a
  general parser or copy contract.
- Physical stack behavior. Resolve the multi-register ordering against an
  independent instruction oracle or approved hardware observation before
  treating the pinned scalar semantics as a physical ISA result.
- Service transition. Establish SWI delivery, trap-frame production,
  dispatcher selection and return separately; these initializer calls
  execute no such transition.
