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
or a general initialization-table API. The broader caller-state domain below
follows from the fixed source semantics; the two calls remain its concrete
execution witnesses.

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

## General conditional input domain

The same fixed path admits every 32-bit value for incoming r0 through r23,
r27 through r29 and SR under the pinned semantics. GP remains 0x0EE04140,
the entry remains 0x0EC3D740, and the source and table retain the exact
original bytes above. This domain does not accept another table, version,
destination or decoder context.

Let S and L be incoming SP and LR. The stack has ordinary byte storage
containing the full interval [S-24, S). S is four-byte aligned and at least
24; its frame arithmetic does not wrap. The complete declared stack span
is disjoint from the three destination allocations, the four code ranges
and the table. Destination and stack bytes may vary independently and need
not be uniform or nonzero. Source/table bytes and all storage remain free
from concurrent modification through return. The portable policy below
further restricts L and validates the host storage.

The source establishes independence from those incoming values as follows:

1. At 0x0EC3D740, the entry saves incoming LR and r6 through r9 before
   reusing them. At 0x0EC3D742 and 0x0EC3D74E, GP alone determines the
   bound 0x0EDD7894 and table base 0x0EDD7870. Incoming r0 through r5 are
   overwritten before they can affect this path.
2. At 0x0EC3D754 through 0x0EC3D786, the original signature/version bytes
   determine the comparison operands. Each of the four comparisons that
   writes SR replaces all four low bits before any following SR-dependent
   branch. The last SR writer compares version 2 with 3 at 0x0EC3D782. It sets
   Z=0, N=1, C=1 and V=0 while preserving the upper 28 bits. Later
   comparisons and loop conditions use temporary values without changing SR.
3. At 0x0EC3D7B2 through 0x0EC3D7F4, the original records supply every
   cursor, destination and signed length. The fixed negative records do not
   select the indirect-call path. Each fill receives a positive byte count
   of at least eight; its destination and byte count are multiples of four.
   Alignment and tail-byte paths are therefore skipped. After k word stores,
   the fill's pointer is destination+4k and its remaining count is byte count-4k.
   At byte count/4 stores, the pointer reaches the allocation end and the
   remaining count is zero.
   None of these intervals wraps. No destination byte is loaded.
4. The original zero pair selects completion. Every stack load at
   0x0EC3D77C reads a word already saved by the entry. The separate
   destinations cannot overwrite those saved words. No other initial
   stack byte is consumed. Registers r10 through r23 and r27 through
   r29 are untouched by the selected instructions.

The resulting state relation is:

| Output | Value |
| --- | --- |
| All three destination allocations | Every byte zero |
| r0, r1, r2, r4 | 0x00000000 |
| r3 | 0x0EF2A858 |
| r5 | 0x0EDD7870 |
| r6 through r23, GP, SP, r27 through r29 | Incoming values |
| LR | 0x0EC3D77A |
| SR | `(incoming SR & 0xFFFFFFF0) \| 0x00000006` |
| PC | L |

The five retained stack words contain incoming LR/r6/r7/r8/r9 at
S-4/S-8/S-12/S-16/S-20 respectively, in little-endian order. Every other
declared stack byte remains unchanged, including the reserved four bytes
at S-24. The saved 20 bytes must be separate from the destination writes
to restore arbitrary incoming registers. Excluding the entire declared
stack span also preserves arbitrary prefix, suffix and reserved bytes.
The final PC is a data result at the return boundary; no instruction at L
is fetched by this contract.

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

## Portable API

`startup_initialization_run(input, destinations, stack, result)` operates
on caller-owned storage for the fixed original table. Its validation and
output-publication rules are host policy, not additional vendor behavior.

All four object pointers are required and naturally aligned. Input contains
31 incoming scalar register words: r0 through r23, GP, SP, LR, r27 through
r29 and SR. Entry PC is implicit. GP must be 0x0EE04140. Other register
values follow the general conditional domain above. There is no VERSION,
source-table or record input.

`destinations` contains exactly three mutable byte-span descriptors, in
original table order. Each descriptor contains a byte pointer and length.
Their required lengths are 2352, 2048 and 1011288 bytes, respectively.
The numeric VPU addresses are the fixed allocation starts above and are
not caller-supplied fields. All three byte pointers are required, including
when a malformed descriptor has length zero. Byte storage need not have
host alignment. Adjacent buffers are permitted; intersecting buffers are not.

`stack` contains a mutable byte pointer, length and numeric VPU start
address. Its byte pointer is required and needs no host alignment. Length
is at most UINT32_MAX. The exclusive virtual end may equal 2^32 but may not
exceed it. SP must be four-byte aligned and at least 24, and [SP-24, SP)
must fit within the span. The entire virtual span excludes all three
destination allocations, four code ranges and the 36-byte table listed
above. Half-open ranges that meet only at an endpoint do not overlap.

LR must be even and outside the entire virtual stack span and all those
fixed destination, code and table ranges. These are conservative host
stop-token checks. The vendor body saves the supplied word and returns
through it without performing these validations; this interface does not
define execution at the return target.

Every full host pointer-plus-length must fit uintptr_t. The following host
spans are pairwise disjoint: input, the complete destinations descriptor
object, the stack descriptor, all three complete destination byte spans,
the complete declared stack byte span and result. Input and descriptors
remain immutable. All checks finish before any store. Numeric VPU addresses
and register values never become host pointers.

Result contains all 31 final scalar register words and final PC, with the
values in the state relation above. Success returns
`STARTUP_INITIALIZATION_OK` (0), separately from the final r0 word.
Success changes only the three complete destination buffers, the five saved
stack words and result. It preserves every other
stack byte and publishes result after the memory effects. The API does not
expose intermediate state, an event stream, instruction counts, callbacks
or physical store timing.

| Host status | Rejected condition |
| --- | --- |
| `STARTUP_INITIALIZATION_INVALID` | Null required object or byte pointer, typed-object misalignment, SP below 24 or not four-byte aligned, or odd LR |
| `STARTUP_INITIALIZATION_UNSUPPORTED` | GP differs from 0x0EE04140 |
| `STARTUP_INITIALIZATION_BOUNDS` | Host or virtual span wrap, stack length above UINT32_MAX, wrong destination length, or frame outside the stack span |
| `STARTUP_INITIALIZATION_OVERLAP` | Intersecting host spans, stack intersection with a fixed destination/code/table range, or LR inside the stack or a forbidden fixed range |

If several conditions fail, any applicable error may be returned. Rejection
leaves every supplied byte and object unchanged. This preflight policy does
not reproduce partial effects of unsupported vendor paths: the vendor
stores its frame before checking the table header and provides no matching
rollback guarantee.

Callers provide actual backing, readable input/descriptors and stack,
writable stack/destination bytes and result, and lifetime through return.
Integer checks cannot establish allocation validity. No supplied storage
is concurrently accessed during
the call. No pointer is retained, allocated or freed. The operation performs
no hardware access, INI parsing for other records, address fixups or service
transition.

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
