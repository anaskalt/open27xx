<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Suspend software helpers

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

Three scalar helpers provide tuple lookup, byte-string length and bounded
copy. The complete source control flow and its arithmetic bounds define
the general behavior below.
Twenty synthetic complete calls check selected paths through those bodies;
they are examples within the domain, not lists of accepted input values.
No helper invokes a callback, accesses MMIO or changes interrupt state.

| Entry | File offset | Bytes | Role |
|---|---|---:|---|
| 0x0EDA6DA6 | 0x1A67A6 | 56 | First matching tuple index |
| 0x0ED7B898 | 0x17B298 | 20 | First-NUL byte length |
| 0x0EDA6698 | 0x1A6098 | 50 | Bounded copy at supplied offset |
| 0x0ED1FC44 | 0x11F644 | 26 | Actual nested byte search |

The three helper body SHA-256 values, in table order, are
`b90c37610d2ee716a14992aa6921c2c7b3b43cb4980597eed335694340dc763f`,
`c85a19fdd3bbc4f626669e6beb908b68517bddaa7ebe818529b19b3d0059f7a2`
and `62333498488e247fba9ae17a8bf7a6ec22faded1328c94b5cf279d689cbd75a3`.
The byte-search body SHA-256 is
`d84528413d76061ee04f5ccb0e11f2838df33a50675b2c4d52dc53698498edf3`.

The suspend registrar at 0x0EDA7260 calls lookup at 0x0EDA72A0, length
at 0x0EDA72B6 and copy at 0x0EDA72F2. These calls occur after the registrar's
interrupt boundary at 0x0EDA7270. Standalone helper completion does not
establish a complete registrar or [first open](arm-first-open.md).

## Tuple lookup

Entry 0x0EDA6DA6 receives three unsigned 32-bit keys. It loads an object
pointer through GP+0x14E4 and a signed 32-bit count at object+0xB5C.
For count at most zero, it returns raw 0xFFFFFFFF without reading records.
For positive count, it examines indices from zero to count-1 in order.

The original object layout and portable record view have different origins:

| Field for index i | Original location | Portable location |
|---|---|---|
| First key, unsigned byte | object+0x1C+36i | records+36i |
| Second key, little-endian word | object+0x20+36i | records+36i+4 |
| Third key, little-endian word | object+0x24+36i | records+36i+8 |

The portable byte view starts at original object+0x1C, not at the original
object base. Each portable record occupies 36 bytes. Only its byte at
offset zero and words at offsets 4 and 8 participate. Padding and all
other bytes remain unchanged and need no particular value.

The first key compares as a full word against the zero-extended byte.
For example, 0x101 does not match byte 1. The second comparison runs only
after the first matches; the third runs only after both match. Return
the first matching index. If none matches, return raw 0xFFFFFFFF.
Duplicate tuples therefore select the earlier record. Callback-like
word values are opaque identities; no pointer dereference or call follows.

The helper itself has no 40-record clamp. The separate registrar tests
its count against 40 at 0x0EDA7288 before reaching this helper. That caller
guard is not an extra comparison in the lookup operation.

The portable operation receives count, the three keys, a declared record
byte view and a required separate 32-bit raw-result destination. Accept
arbitrary keys and field values under these storage bounds:

- Count is any signed 32-bit value. A nonpositive count needs no record
  contents; a null view with zero extent is valid.
- For positive count n, the record view contains at least 36n bytes.
  Compute the extent without overflow and require 36n at most 0xFFFFFFFF.
  This also keeps every successful index representable as a signed word.
- The last consumed word ends at byte `(n-1)*36+12` relative to this
  view. The full 36n-byte view includes its remaining unused record bytes.
  Relative to the original object, the last consumed word ends at
  `36n+4`; those origins must not be interchanged.
- Every supplied view, including an unused view for nonpositive count,
  satisfies the shared span rules below. Unused contents are not read.

The operation leaves records unchanged and publishes the raw index or
0xFFFFFFFF only after lookup completes. A missing host argument or invalid
extent is a host validation error, distinct from a completed no-match result.

## Byte-string length

Entry 0x0ED7B898 calls 0x0ED1FC44 with target byte zero and search count
0x7FFFFFFF, then subtracts the original pointer from the returned pointer.
For a terminated, nonwrapping source span within that bound, the result
is the number of bytes before the first NUL. Bytes have no character
encoding interpretation; values 0x80 through 0xFF are ordinary nonzero
bytes. Bytes after the first NUL do not contribute and are not read.

The portable operation receives a required source byte view and a separate
32-bit length destination. Its declared source extent is from 1 through
0x7FFFFFFF bytes, with a NUL inside that extent. The resulting length L is
from zero through 0x7FFFFFFE. Content before the NUL is arbitrary. This
bound ensures that the nested search reaches the NUL before exhausting
its count; the count-exhausted return has a different meaning and is
outside this string-length contract.

The source remains unchanged. A missing NUL in the declared extent is
host invalidity, not a permitted out-of-range read or a synthetic length.
Do not use an unbounded host string routine to establish this precondition.

## Bounded copy

Entry 0x0EDA6698 receives destination, source, unsigned 32-bit capacity C
and unsigned 32-bit offset O. It uses the same source and termination
rules as length. Let L be the full length of that source.

When O is below C, copy `min(L,C-O-1)` bytes from the source to destination
starting at offset O, then write one NUL. The first NUL or the last available
destination byte stops copying. Bytes before O and after the terminator
remain unchanged. Capacity one and offset zero write only the terminator.

When O is at least C, perform no destination access. In both cases, the
actual source body calls the real length helper at 0x0EDA66C2 and returns
`(L+O) mod 2^32` at 0x0EDA66C6. The result is neither the number of copied
bytes nor an error flag. A truncation still returns the full source length
plus offset. Arithmetic wrap of this raw return is intentional.

The portable operation receives both declared byte views, C, O and a
required separate raw-result destination. Source and destination are
disjoint. The destination extent is at most 0xFFFFFFFF bytes and at least
C. A null destination with zero extent is accepted only when C is zero.
All 32-bit offsets are accepted, including 0xFFFFFFFF. If O is at least
C, never form destination+O: that pointer is unnecessary and may be outside
the supplied object even though the completed no-write operation is valid.

For O below C, all writes fit the declared destination because the last
written byte is at most C-1. Required source termination and the full
source extent remain the same for a truncated copy or zero capacity.
Destination truncation does not limit the final length calculation.

Use the shared portable byte-length computation for the final result.
No literal length, reply provider or computational callback replaces it.
The whole copy operation validates the nested length premises before any
destination write; a late nested validation failure must not leave a
partially changed destination. The preflight may share its read-only
source scan with execution. This implementation choice does not change
the copied bytes or returned word.

## Loop bounds from source

At 0x0EDA6DB6 the lookup rejects nonpositive signed count before entering
the loop. For a positive count n, its index starts at zero, increments
by one at 0x0EDA6DD6 and continues only while the signed index is below n.
The 36n extent bound prevents the index product from wrapping and keeps
the index below 0x80000000 throughout. The byte load at 0x0EDA6DC2
zero-extends its field before the full-word equality at 0x0EDA6DC6.
The declared nonwrapping view covers every selected field address.

For length L, the byte search consumes L+1 positions, including the NUL.
The source bound gives `L+1 <= 0x7FFFFFFF`. Its remaining count is still
positive at the comparison at 0x0ED1FC4A before the terminating byte read,
so the exhausted-count branch is unreachable under this contract.

Copy tests unsigned O against C at 0x0EDA669C. If O is below C, the
remaining data capacity C-O-1 is a nonnegative 32-bit value. Each copied
byte advances both cursors once; the first NUL or last available byte
stops the loop at 0x0EDA66BA. The full destination span and source-NUL
bound cover both cursor paths without address wrap. These control-flow
and arithmetic arguments support the general bounded behavior. The
separate matrix below records which finite inputs have executed natively.

## Shared storage and preflight

These host interfaces express the scalar computation over explicit
caller-owned storage. Original GP, object, stack, callback tokens and
return addresses do not become callable host addresses. The native
mapping assumes that its 32-bit source/object/destination address
calculations do not wrap. The portable interface uses bounded object
offsets and checks the full host spans rather than recreating a wrapped
VPU address space.

All byte-view extents are at most 0xFFFFFFFF. Check extent arithmetic,
pointer-plus-extent overflow and pairwise overlap before reading contents.
For positive lookup count, check multiplication by 36 before forming a
record offset. Byte views need no alignment. Typed view descriptors,
parameter structures and 32-bit result objects require natural alignment.
The native fixtures use aligned record words and unaligned source and
destination bytes; unaligned host record views are a portable storage
requirement, not an additional native observation.

Every supplied API object and full declared view is disjoint from every
other object/view, including immutable inputs, unused views, source,
destination and result. Zero-length views have no byte span. A null view
must have zero extent and satisfy its operation-specific rule. Declared
tails participate in wrap and overlap checks even when their contents
are unused. The caller supplies actual backing, readability, writability
where required and lifetime; arithmetic preflight cannot prove that an
arbitrary pointer names a live allocation.

Run one complete read-only preflight before the first observable effect.
It covers every required pointer, extent, count/product, scalar domain,
alignment, overlap and source-termination requirement. For copy, this
includes the final full-length calculation and destination capacity even
when no destination write will occur. Do not validate inputs by comparing
them with the fixture strings or tuple values.

On host invalidity, emit no events and preserve all API objects, source,
records, destination and the separate result word. On accepted execution,
publish the native raw result after the documented computation and writes.
Host status is distinct from raw 0, 0xFFFFFFFF and a wrapped copy result.
There are no observers, mutable providers or other external effects.
No pointer is retained, allocated or freed. Concurrent mutation and
overlapping-storage behavior are outside this contract.

## Recorded cases and replay

[suspend-helpers.json](../../tests/vectors/start4/suspend-helpers.json)
contains the same 20 complete calls with explicit synthetic storage and
no external replies. Its SHA-256 is
`6c7f1850c4877b2aaea02c2f44f7b64b636fe8ad4e11792b4063884f5c3e2339`.

| Operation | Dynamically checked inputs | Calls | Instructions |
|---|---|---:|---:|
| Lookup | Counts 0, -1 and 4; first/last match; three mismatch gates; absence; wide first key; duplicate tuples | 7 | 162 |
| Length | Empty, byte 0x80, mixed-separator path, first NUL before trailing data | 4 | 184 |
| Copy | Zero capacity; offset equal/above capacity; capacity one; empty/full/truncated source; nonzero offset; returned-word wrap | 9 | 778 |

The 20 calls total 1124 instructions, 640 observed scalar register words,
4100 observed bytes and zero events. Every declared memory byte is
compared, including destination tails, padding, guards and stack residue.
All prologues execute from their actual entries. All epilogues return
naturally to an external sentinel with SP restored; no internal stop is
counted as a completed call. Lookup uses a 16-byte frame, length an 8-byte
frame, and copy its own 8-byte frame plus the nested length's 8-byte frame.
These native frames and incidental registers are observations, not host
API parameters or a required calling convention.

Across the four bodies, the independently derived case paths visit 55
instruction addresses covering 150 bytes. The only decoded instruction
outside those paths is the byte-search count-exhausted zero return at
0x0ED1FC5A. The runtime recorder compares final state and instruction
counts; it does not export an executed-PC trace. The general behavior
above follows the complete scalar control flow under its stated bounds;
this finite matrix does not exhaust all strings, keys, counts or capacities.

Use the imported program and versions in [headless analysis](../analysis.md),
with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EDA6DA6 0x0ED7B898 0x0EDA6698 0x0ED1FC44 \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/suspend-helpers.json /work/analysis/suspend-helpers.json
cmp tests/vectors/start4/suspend-helpers.json /work/analysis/suspend-helpers.json
```

The unchanged recorder rejects a missing object pointer at 0x0EDA6DAA,
missing count at 0x0EDA6DB0, a source read beyond the declared NUL-less
span at 0x0ED1FC52, an undeclared destination write at 0x0EDA66BE and a
one-instruction short length budget at 0x0ED7B8AA. Each control produces
no artifact. Recorder rejection is distinct from the portable preflight's
unchanged-state host error; native execution has already formed frames
when such a recorder failure occurs.

## Open questions

- Larger boundaries. Add separately predicted cases for count/product
  limits, long strings and extreme capacity/offset pairings to expand
  dynamic coverage. The current 20 cases do not dynamically test the
  maximum supported extents or every negative count.
- Byte-search exhaustion. Specify and capture direct bounded-search
  inputs before exposing 0x0ED1FC44 as a general separate operation.
- Overlap and wrapping native addresses. Inspect and capture those
  behaviors before extending the disjoint, nonwrapping storage domain.
- Runtime state and complete registration. Establish object initialization,
  record lifetime and interrupt-boundary semantics before composing a
  full suspend registrar. The original GP+0x14E4 pointer and synthetic
  record contents do not establish live initialization or callback effects.
