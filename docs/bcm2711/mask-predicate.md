<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Mask predicate and scalar word-pair shift

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

The predicate at 0x0ED00640 tests one selected bit in two software mask
words. It calls the actual word-pair shift at 0x0EC2FCAA. The complete
control flow defines general scalar behavior; 28 complete native calls
check selected paths and boundary values, not a whitelist of valid inputs.

| Entry | File offset | Bytes | Operation |
|---|---|---:|---|
| 0x0ED00640 | 0x100040 | 62 | Conditional mask predicate |
| 0x0EC2FCAA | 0x2F6AA | 34 | Shift a low/high word pair |

Their body SHA-256 values, in table order, are
`0c1433dd61defbd4b5ac1f56c3632f304270ca2a660ae19c255894931e4ea6b6`
and `909ff622e25407183e41aea206267e8b99ec97c2f0d56ccaedefa5d4611b0cfb`.

## Conditional mask predicate

The predicate accepts any unsigned 32-bit code C. Unsigned comparisons at
0x0ED00644 and 0x0ED0064A select these routes:

| Code | Mask access | Raw result |
|---|---|---|
| C below 0x40 or at least 0x80 | None; no shift helper call | 0 |
| 0x40 through 0x7F | Read both words after the actual shift helper | 1 if bit C-0x40 is set, otherwise 0 |

For an in-range code, the call at 0x0ED00658 shifts low word 1 and high
word 0 by C-0x40. That count always lies from zero through 63. The predicate
then reads the high mask at GP+0xCB49C at 0x0ED0065C and the low mask at
GP+0xCB498 at 0x0ED00662. It intersects the two shifted words with the
corresponding mask words and tests whether either intersection is nonzero.
Both masks are read even when the selected bit belongs to only one half.
No mask byte changes. Raw zero does not distinguish an out-of-range code
from an in-range code whose selected bit is clear.

The portable operation receives C by value, an optional immutable mask
byte view and a required separate 32-bit raw-result destination. The view
starts at original GP+0xCB498: low little-endian word at offset zero,
high little-endian word at offset four. Mask words and unused bytes are
arbitrary. Accept the following conditional storage domain:

- In-range C requires a present view containing at least 8 bytes. Read high
  then low using byte-wise little-endian access. No host word alignment is
  required for the byte storage.
- Outside the interval, a null view descriptor or null bytes with zero
  extent is valid. A supplied unused view may have any extent from zero
  through 0xFFFFFFFF bytes. Its contents are not read, including when its
  extent is less than eight bytes.
- Every supplied descriptor and nonempty declared span passes the storage
  checks below, whether its contents are used or not. Null bytes with a
  nonzero extent are invalid. A nonnull byte pointer with zero extent has
  no byte span. All declared extents are at most 0xFFFFFFFF.

The complete source mask view, including every unused tail byte, remains
unchanged on success. Publish raw zero or one only after computation
finishes. The portable predicate executes the shared word-pair shift
computation with inputs (1, 0, C-0x40); it does not accept a supplied shift
reply or maintain a separate lookup table of the recorded cases.

## Logical 64-bit domain

Entry 0x0EC2FCAA receives low word L, high word H and count N in r0, r1
and r2. Its returned low/high pair is in r0/r1. Both input words are
arbitrary unsigned 32-bit values. The body has no data-memory access,
stack frame or subordinate call and returns through its incoming LR.

For N from zero through 63, the result is a logical left shift of the
64-bit pair, with overflow beyond bit 63 discarded. Let U(x) mean reduction
modulo 2^32. All right shifts below are logical:

| Count | Low result | High result |
|---|---|---|
| 0 | L | H |
| 1 through 31 | U(L << N) | U(H << N) OR (L >> (32-N)) |
| 32 through 63 | 0 | U(L << (N-32)) |

This is the only count interval reached by the mask predicate. Neither
the general predicate domain nor its callers require an extended count.

## General pinned scalar domain

The same body has a defined pinned scalar result for every unsigned
32-bit N. It does not clamp counts at 64. This separate domain describes
the compiled semantics used by the pinned VideoCoreIV extension in
[headless analysis](../analysis.md); it does not define the result of an
out-of-range shift in the C language or establish physical ISA behavior.

Let T = U(N-32), K = N AND 31 and J = U(32-N) AND 31. Interpret every
intermediate arithmetic result as an unsigned 32-bit word. The complete
piecewise result is:

| Condition, in order | Low result | High result |
|---|---|---|
| T below 0x80000000 | 0 | U(L << (T AND 31)) |
| Otherwise, N equals zero | L | H |
| Otherwise | U(L << K) | U(H << K) OR (L >> J) |

The first row covers N from 32 through 0x8000001F. The remaining rows
cover N from zero through 31 and from 0x80000020 through 0xFFFFFFFF.
The branch at 0x0EC2FCB0 tests the sign of the wrapped 32-bit subtraction;
the unsigned T comparison above expresses that test without converting an
out-of-range unsigned value to a host signed type.

At 0x0EC2FCB4, 0x0EC2FCC2, 0x0EC2FCC4 and 0x0EC2FCC6, the compiled
scalar operations explicitly retain only five count bits before a 32-bit
left or logical right shift. The pinned VideoCoreIV
[`data/languages/vc4.slaspec` scalar shift definitions](https://github.com/aleph-void/ghidra-videocore4/blob/db09a308c2db6a31ba5e060e6b763713f77e4f7b/data/languages/vc4.slaspec#L1149-L1158)
apply that count mask. Thus every subshift in the table is from
zero through 31. Wrapping subtraction, explicit count masking and unsigned
word operations define the whole domain without signed overflow or a host
shift of 32 or more. The last row uses the original L for both contributions;
the shifted low result must not replace it in the high-word calculation.

The portable word-pair operation receives L, H and N by value and a
required result object containing separate 32-bit low and high words.
It accepts every possible word and count under the storage rules below.
Publish both words only after computing the pair in private temporaries.
Do not reduce N to six bits, return zero for all counts at least 64 or
restrict the extended domain to the seven recorded examples. Reuse this
same computation from the predicate. Native scratch registers, comparison
flags, GP, LR and stack residue are not additional portable outputs.

## Whole-call host preflight

Before reading mask contents or writing any result, validate all required
output objects, nonnull supplied descriptors, typed alignment, declared
extents, pointer-plus-size arithmetic and overlap. A predicate mask view is
required only for in-range C; its contents have no numeric restrictions.
All shift inputs and predicate codes are valid unsigned 32-bit values.
There is no event plan, observer, external reply or provider to validate.

Typed result objects and nonnull view descriptors require natural host
alignment. Their full host spans must not wrap. A supplied descriptor,
its entire declared byte span and the result object must be pairwise
disjoint, including unused byte-view tails and the out-of-range route.
Check fixed object spans before reading their fields and the byte span
before reading its contents. By-value scalar inputs introduce no separate
caller storage span. Byte storage may be unaligned; the native recorded
cases use aligned words, so unaligned access is a portable storage rule.

The caller supplies actual backing, readability, output writability and
lifetime. Integer span checks do not establish allocation validity.
Descriptors and mask bytes remain immutable throughout the operation,
with no concurrent modification. Original firmware addresses never become
host addresses. No pointer is retained, allocated or freed.

All host errors leave every supplied byte and result object unchanged,
with no intermediate result publication or external effect. Use separate
host status categories for invalid arguments, bounds and overlapping
spans. These are distinct from a completed predicate result of zero or one
and from either returned shift word. A native recorder rejection can occur
after register or frame effects and does not establish rollback behavior.

## Caller state and composition limits

The two masks correspond to original addresses 0x0EECF5D8 and 0x0EECF5DC
for GP 0x0EE04140. They occupy non-file-backed memory. The
[driver-open callback](driver-open-masks.md) at 0x0ED0067E can copy an
explicit pair there; a null incoming source skips that copy. The predicate
does not call that callback, construct masks or establish their lifetime.
Both mask words in this contract are explicit software inputs.

The caller at 0x0ED0070A passes its incoming code to the predicate. For
the recorded first-open inputs, that code is 0x5E. A nonzero predicate
result selects the caller's early raw-one return; a clear bit permits the
later service route. General mask membership is not evidence that a service
completed, a callback ran or an opaque output was produced. The full
standalone calls here require a supplied ordinary caller return address,
and the predicate requires its real four-byte saved-return frame.

## Recorded calls and replay

[mask-predicate.json](../../tests/vectors/start4/mask-predicate.json)
contains the 28 complete synthetic calls, SHA-256
`56db3bb0eae86cdfb5ee7eb6cca01969ba43878e6dcc649de2661a0e1450b4c7`.
All registers, masks, stack and guard bytes are synthetic inputs.

| Group | Calls | Inputs |
|---|---:|---|
| Predicate outside interval | 5 | Codes 0, 0x3F, 0x80, 0x80000000, 0xFFFFFFFF; no mask backing |
| Predicate selected bit | 8 | Codes 0x40, 0x5F, 0x60, 0x7F; selected bit clear or set |
| Ordinary direct shift | 8 | Counts 0, 1, 31, 32, 33, 63; mixed, zero and all-one words |
| Extended direct shift | 7 | Counts 64, 65, 0x7FFFFFFF, 0x80000000, 0x8000001F, 0x80000020, 0xFFFFFFFF |

Set cases contain only the selected mask bit; clear cases contain every
other bit. The mixed shift input is L=0x89ABCDEF, H=0x76543210. Extended
examples distinguish the pinned operation from a six-bit count reduction:

| N | Low result | High result |
|---|---|---|
| 64 | 0 | 0x89ABCDEF |
| 65 | 0 | 0x13579BDE |
| 0x7FFFFFFF | 0 | 0x80000000 |
| 0x80000000 | 0 | 0x89ABCDEF |
| 0x8000001F | 0 | 0x80000000 |
| 0x80000020 | 0x89ABCDEF | 0xFFFFFFFF |
| 0xFFFFFFFF | 0x80000000 | 0x44D5E6F7 |

The calls total 398 instructions, 896 compared register words, 2880
observed bytes and zero ordered events. Each starts with a fresh 96-byte
stack view and returns naturally to 0x24040000 with SP 0x24010000 restored
or untouched. Predicate calls retain their actual four-byte saved-return
residue; direct shifts preserve every declared stack byte. Both masks and
all guards remain unchanged. The comparison includes ordinary registers,
upper SR bits, computed flags and every declared byte.

Independent source-derived paths visit all 37 PCs covering 96 bytes. The
runtime recorder compares final state and step totals; it does not export
a PC or memory-access trace. These finite examples do not exhaust all
code, mask, word and count values in the source-derived scalar domain.

Use the imported program and versions in [headless analysis](../analysis.md),
with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0ED00640 0x0EC2FCAA \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/mask-predicate.json /work/analysis/mask-predicate.json
cmp tests/vectors/start4/mask-predicate.json /work/analysis/mask-predicate.json
```

The fixture has no IRQ, p16, VERSION, MMIO, SWI, RTI or computational stubs.
Four controls reject missing high-mask backing at 0x0ED0065C, missing
low-mask backing at 0x0ED00662, missing saved-return storage at 0x0ED00640
and a short budget before the helper return at 0x0EC2FCCA. Each produces
no result artifact. Guard rejection does not imply absence of earlier
emulated effects.

## Open questions

- Runtime mask state. Establish startup ordering and subsequent mask
  updates before treating supplied words as live startup state. The recorded
  [initialization prefix](driver-initialization.md) clears both masks before
  its first SWI, but does not establish live startup ordering or subsequent
  mask writes. The optional copy remains a separate producer path.
- Physical extended-count semantics. Compare the four variable-shift
  sites and signed-wrap boundary with authoritative scalar ISA evidence
  or a separate permitted hardware observation before making a hardware
  claim beyond the pinned compiled behavior.
- Later service and opaque output. Resolve the caller's exception and
  service transition, together with the opaque-word producer, before
  claiming a successful first open. This predicate has no such effects.
