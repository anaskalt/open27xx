<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Memory bank serialization

The behavior below belongs to `start4.elf` from `raspberrypi/firmware`
commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Serializer 0x0ECB2A50 emits ordered base/size tuples from supplied numeric
inputs. Its real scalar encoding helpers execute in every recorded case.

These tuples are candidate memory-property bytes. Their values do not
establish physical RAM, usable ownership, reserved ranges or a safe payload
placement. The [capacity calculation](memory-capacity.md) and the
[boot-information parser](boot-information.md) are separate contracts.
The caller observations below stop before device-tree insertion.

## Inputs

The identified serializer at 0x0ECB2A50 consumes these inputs:

| Input | Vendor location | Meaning within this contract |
|---|---|---|
| Output | `r0` | Writable byte buffer |
| Address cells | `r1` | 1 or 2 cells per base |
| Size cells | `r2` | 1 or 2 cells per size |
| Lower span | `r3` | Supplied unsigned byte count |
| Total | `r4` | Supplied count in MiB for additional tuples |
| Control word | GP+0xCC948 | Zero/nonzero choice of the ordinary cutoff |
| Cached record | Lookup of tag 0x52455642 | Absent, or a supplied record with words at offsets 0x80 and 0x88 |

Total, lower span, record words and control word are independent inputs.
Each is represented by an unsigned 32-bit word; total uses MiB and the
lower span uses bytes.
The fixture field `hole_flag` represents the numeric control word; its
name does not identify the purpose or owner of a gap. No relationship to
a particular board or VPU allocation is assumed.

The real lookup at 0x0EC642FC calls the real parser at 0x0EC644E0.
Recorded state supplies completion 1 and the cached record pointer.
The source-pointer word points to undeclared synthetic memory, which is
not dereferenced on this completed-parser path. No record allocation,
source copy, service substitution or MMIO occurs.

The word at record offset 0x88 is a numeric selector. Only bit 4 of the
word at offset 0x80 selects its special branch. These field meanings do
not identify a memory type, rank, channel or physical board. The record's
declared length does not establish accessible backing for either word.

## Ordered tuples

All base and size values in this section are MiB. The identified serializer
first emits `(0, lower_span_bytes >> 20)`. Fractional MiB are discarded.
A lower span of zero still produces a zero-size tuple; it does not suppress
the first tuple or return an empty payload.

| Supplied lower span (bytes) | Encoded first size (bytes) |
|---:|---:|
| 0, 1 or 1048575 | 0 |
| 1048576 or 1048577 | 1048576 |
| 994124613 | 994050048 |

Let T be the supplied total MiB. The serializer appends the following
tuples in table order within the selected branch. It does not merge them
with the first tuple.

| Branch | Predicate | Base (MiB) | Size (MiB) |
|---|---|---:|---:|
| Ordinary | T > 1024 | 1024 | min(T, C) − 1024 |
| Ordinary | T > 4096 | 4096 | T − 4096 |
| Selector 24, record flag bit 4 set | T > 1024 | 1024 | min(T, 1536) − 1024 |
| Selector 24, record flag bit 4 set | T > 1536 | 2048 | min(T, 3072) − 1536 |
| Selector 48, record flag bit 4 set | T > 1024 | 1024 | min(T, 3072) − 1024 |
| Selector 48, record flag bit 4 set | T > 3072 | 4096 | min(T, 6144) − 3072 |

For the ordinary branch, C is 4032 when GP+0xCC948 is zero and 4096 when
it is nonzero. An absent record, another selector word, or either special
selector with bit 4 clear selects that ordinary branch. The selector word
is compared in full. Other bits of the record's flag word do not replace
the bit-4 test.

The special gates occur at 0x0ECB2A98–0x0ECB2AAA and
0x0ECB2B12–0x0ECB2B24. The ordinary path is at
0x0ECB2B7E–0x0ECB2BC4. The special branches stop after their two possible
additional tuples: totals above 3072 or 6144 MiB respectively do not
append another range. The control word changes only the ordinary cutoff.

For ordinary T = 8192, lower span 994050048 bytes and control zero,
the tuples are `(0, 948)`, `(1024, 3008)` and `(4096, 4096)` MiB before
cell-size splitting. With the same total and lower span, selector 24 and
record flag bit 4 produce `(0, 948)`, `(1024, 512)` and `(2048, 1536)`.
These are synthetic examples of clipping and numeric gaps, not verified
physical bank assignments.

## Big-endian cells

The identified pair encoder at 0x0EC44AEE calls field encoder 0x0EC44B42
and byte writer 0x0ECA314E. They emit each tuple's base first, followed
by its size. Each cell occupies 4 bytes in big-endian order.

For a field value M in MiB:

| Cell count | Cells in output order |
|---:|---|
| 1 | Low 32 bits of (M × 1048576) |
| 2 | M shifted right by 12; then its low 12 bits shifted left by 20 |

Two cells therefore encode the 64-bit byte value, high cell before low
cell. One-cell encoding retains only the low 32 bits. Recorded
one-address-cell cases keep every base below 4096 MiB. Truncating a higher
base is not an accepted placement policy.

When the size-cell count is one and a tuple size is at least 4096 MiB,
0x0EC44AFA–0x0EC44B26 emits a 2048 MiB part, advances the base by
2048 MiB and subtracts 2048 MiB from the remaining size. It repeats while
the remaining size is at least 4096 MiB, then emits the final remainder.
The split parts keep their original position in the tuple order.
Two-size-cell encoding does not split tuples this way.

For example, base 4096 MiB and size 4096 MiB become two tuples of size
2048 MiB at bases 4096 and 6144 MiB when the size uses one cell. With two
size cells they remain one tuple. Zero-size tuples still occupy the normal
number of cells.

The serializer returns the number of bytes written. Each emitted tuple
occupies `4 × (address_cells + size_cells)` bytes. The return value includes
every split part. Output bytes after that returned extent remain unchanged
in the recorded cases. There is no output-buffer length argument or advance
capacity check in this vendor interface.

## Cached-capacity caller slices

Four cases connect the identified getter 0x0EC63578 to the serializer.
They enter at 0x0EC574E0 or 0x0EC574E8 and stop before 0x0EC5752A.
They are internal slices, not complete calls to the surrounding
device-tree constructor.

The getter reads cached MiB at GP+0x3B8B0. The unrestricted slice uses
that value; the limited slice takes the smaller of it and the supplied
nonzero limit in `r7`. Both raise the result to at least 128 MiB, store
it at context offset 0x08, then pass it as T to the serializer. This does
not raise or otherwise replace the independently supplied lower span.

| Case | Cached MiB | Supplied limit MiB | T passed to serializer |
|---|---:|---:|---:|
| Unrestricted | 8192 | — | 8192 |
| Minimum | 64 | — | 128 |
| Smaller limit | 8192 | 2048 | 2048 |
| Larger limit | 2048 | 8192 | 2048 |

The output buffer is supplied at SP+0x2BC. After the serializer returns,
the slice stores these little-endian words in the supplied descriptor:

| Descriptor offset | Value |
|---|---|
| 0x24 | Supplied property-name pointer |
| 0x28 | Returned payload length in bytes |
| 0x2C | Output-buffer pointer |

The property-name pointer is stored without being dereferenced. All other
observed context and descriptor bytes remain unchanged. The preceding
branch at 0x0EC574D4 selects unrestricted or limited behavior from
GP+0xCCC74; the fixtures enter after that choice. Earlier property lookups,
default cell-count selection and lower-span acquisition are not executed.
Later property insertion, reservation updates and complete tree mutation
are outside these slices.

## Host representation and bounds

A portable serializer can accept ordinary numeric inputs and either
decoded record words or an explicitly absent record. It must preserve the
numeric branch choices, tuple order, low-span truncation, splitting and
exact output bytes above. Keep the caller's capacity normalization separate
from the complete serializer: the direct cases include T = 0 without
applying the caller's minimum.

The supported host comparison domain is T from 0 through 16384 MiB,
an unsigned 32-bit lower-span byte count, and address/size cell counts of
1 or 2. Record and control words retain their full unsigned 32-bit values.
The 16384 MiB bound is a host comparison limit, not a recovered vendor
check or a physical hardware maximum. It also contains every arithmetic
result of the separate byte-capacity helper. Extending the supported range
requires additional documented evidence and tests.

Require valid caller-owned output storage and sufficient capacity before
writing. Check the encoded extent without overflowing. For one address
cell, every emitted base must fit below 4096 MiB, including bases advanced
by size splitting. Apply this condition to the selected tuples, not merely
to T: special branches use different clipping and bases. Wrapped high bases
remain outside the host comparison contract even though the vendor's
one-cell field encoding retains only low bits.

If record words are read from a byte buffer, require an independently valid
extent of at least 140 bytes for offset 0x88; the record's own length word
is insufficient. An absent record requires no such read. Prevent overlap
between mutable output and input record/state storage. These are host
preconditions, not vendor error codes or recovered validation behavior.
No vendor rejection of unsupported cell counts or larger totals is asserted.

General overflow behavior and physical validity remain separate. Validate
physical-bank bounds, overlap and ownership before treating serialized
values as an actual memory map. Neither total capacity nor a returned
payload length proves that an address can be used safely.

For portable comparison, map the synthetic output pointer to a test-owned
byte array and compare the returned length, every output byte and unchanged
tail/guards. Record pointers and GP-relative locations are fixture storage,
not a host ABI. Compare the four caller slices separately if a host wrapper
also implements the stated normalization and descriptor stores.

## Recorded cases and replay

[memory-layout.json](../../tests/vectors/start4/memory-layout.json)
contains 48 synthetic cases and 13275 scalar instructions:

| Group | Cases | Scope |
|---|---:|---|
| Direct serializer | 44 | Complete calls to 0x0ECB2A50, including real lookup and cell encoding |
| Unrestricted caller | 2 | Internal slice at 0x0EC574E0, including the 128 MiB minimum |
| Limited caller | 2 | Internal slice at 0x0EC574E8 with limits below and above capacity |

The inner pair and field encoders execute within these cases; they are not
separate standalone-entry captures. Ordinary thresholds include 1024,
4032 and 4096 MiB. Special branches cover their clipping boundaries and
record-selection alternatives. Address/size cell combinations are 1/1,
1/2, 2/1 and 2/2; the long 2/1 case exercises repeated splitting with
T = 16384 MiB. Zero and fractional-MiB lower spans are included.

All cases have zero substituted calls and zero MMIO events. Synthetic GP
is 0x24020000 and SP is 0x24010000. Direct output starts at 0x24001010;
caller output starts at 0x240102BC. Each payload has 512 backed bytes and
16-byte guards on both sides. All observed input, cache, record, context
and descriptor bytes are checked, and SP is restored. These are test
locations and access extents, not physical placement requirements.

Use the imported program and versions from [headless analysis](../analysis.md).
Both public preparation and recording tools are unchanged:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0ECB2A50 0x0EC44AEE 0x0EC44B42 0x0ECA314E \
  0x0EC642FC 0x0EC644E0 0x0EC63578 0x0EC574E0 0x0EC574E8 \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/memory-layout.json \
  /work/analysis/memory-layout.json
```

The output path must not exist. Compare the entire recorded JSON, including
all memory observations, returned lengths and instruction counts. The
recorder rejects unknown reads, undeclared writes, changed instruction
bytes and unsupported operations.

Two separate short-backing probes establish access boundaries. A
16-byte-only payload faults on a byte write at 0x24001020 by instruction
0x0ECA3156. A present record without offset-0x88 backing faults on a
4-byte read at 0x24004098 by instruction 0x0ECB2A9C. Neither creates a
result artifact. These are recorder faults, not vendor error returns or
proof of a safe short-buffer interface.

## Open questions

- Lower-span provenance. Trace the surrounding constructor's second
  argument and establish its relation to the separately documented
  [bootmain ARM/GPU split](bootmain.md#firmware-and-fixup-selection).
  No transport from that split is assumed here.
- Record and control-word provenance. Identify the producers of record
  words 0x80/0x88 and GP+0xCC948, including their lifetime after import and
  relocation, before assigning hardware meanings to their values.
- Physical banks and retained ranges. Establish addresses, aliases, actual
  gaps and ownership of VPU code/heap/stack, mailbox storage and boot state
  before allocating ARM payloads from these tuples.
- Complete device tree. Execute property insertion, reservation updates and
  later mutation separately, then check the resulting tree and Linux boot.
  The descriptor-store slices alone do not establish those results.
