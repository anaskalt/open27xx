<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Memory capacity calculation

The scalar behavior below belongs to `start4.elf` from
`raspberrypi/firmware` commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`,
SHA-256 `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Entry 0x0ECC3E60 converts supplied byte-service replies into a size in MiB
and a separate class. Its capacity helper starts at 0x0ED6B440.

The contract covers the nonzero GP+0x1564 path with diagnostic byte
GP+0xCCDB8 equal to zero. It does not establish physical capacity,
usable banks, reserved ranges, initialization order or payload placement.
The [boot-information parser](boot-information.md) has a separate contract;
its record copies do not supply a memory-map interpretation.

The [memory-bank serializer](memory-layout.md) consumes a supplied capacity
and separate lower-span and record inputs. Its encoded tuples still require
independent validation of physical mapping and ownership.

## Indexed byte service

In the identified `start4.elf`, helper 0x0ED6B440 calls boundary
0x0ED6B4C6 eight times. Arguments are `(selector, first index, second index)`:

| Order | Selector | First index | Second index |
|---:|---:|---:|---:|
| 1 | 5 | 0 | 0 |
| 2 | 8 | 0 | 0 |
| 3 | 5 | 1 | 0 |
| 4 | 8 | 1 | 0 |
| 5 | 5 | 0 | 1 |
| 6 | 8 | 0 | 1 |
| 7 | 5 | 1 | 1 |
| 8 | 8 | 1 | 1 |

Each reply is an unsigned byte, 0 through 255. The complete order executes
even when a reply does not participate in the calculation below. The
recorded boundary returns each supplied byte in `r0` without changing
memory. No reply is interpreted as an error code.

Only the first three recorded argument words define this service input.
The recorder also logs `r3`–`r5`; those words are incidental register state,
not additional callback arguments or portable comparison requirements.

Boundary 0x0ED6B4C6 contains hardware accesses and is entirely substituted
in the tests. The substitutions do not execute hardware polling or acquire
actual module identifiers. A portable interface can supply these bytes
through a callback with the three arguments above. Callback context is
caller-owned and remains valid throughout both passes.

## One capacity pass

All operations in this section execute in the identified `start4.elf`
at 0x0ED6B472–0x0ED6B4C4. Let A be the selector-8 reply with both
indices zero. Its bits 5:2 select a base count:

| A bits 5:2 | Base count |
|---:|---:|
| 0 | 4 |
| 1 | 6 |
| 2 | 8 |
| 3 | 12 |
| 4 | 16 |
| 5 | 24 |
| 6 | 32 |
| 7–15 | 8 |

The multiplier starts at 1. It becomes 2 when both of these comparisons
match at 0x0ED6B4A4–0x0ED6B4B6:

- Selector 5 at indices `(0,0)` equals selector 5 at `(1,0)`.
- Selector 8 at indices `(0,0)` equals selector 8 at `(1,0)`.

These comparisons use the complete reply bytes. Bits 1:0 of A do not
select the base count, but they can affect the selector-8 equality and
therefore the multiplier. At 0x0ED6B4B8–0x0ED6B4BE, the multiplier doubles
again only when A bits 7:6 equal 1. Values 0, 2 and 3 do not double it.

The helper returns base count times multiplier. All four calls whose
second index is 1 still occur, although their replies do not enter this
calculation. The count ranges from 4 through 128 for byte replies; not
every integer in that interval is a possible result. It is an intermediate
numeric count, not a list of memory banks or a decoded rank/channel layout.

## Two passes and outputs

The identified `start4.elf` entry 0x0ECC3E60 receives a writable output
word. It writes 256 at 0x0ECC3E6A before testing GP+0x1564. On the supported
nonzero path it performs two complete capacity passes at 0x0ECC3E76 and
0x0ECC3E7C, giving 16 byte-service calls in the order above repeated twice.

The first count determines the final output size: multiply it by 128 and
store that number of MiB at 0x0ECC3EEE. The second count determines the
returned class through 0x0ECC3E80–0x0ECC3EEA:

| Second count | Returned class |
|---:|---:|
| 4 | 1 |
| 8 | 2 |
| 16 | 3 |
| 32 | 4 |
| 64 | 5 |
| 128 | 6 |
| Other counts | 7 |

Class 7 is a numeric result, not an established error status. Distinct
counts can produce class 7. Recorded stable replies yield 1536, 3072 and
6144 MiB with that class. The class alone cannot reconstruct the size.

The MiB count fits in an unsigned 32-bit word for all byte replies.
A byte-size conversion needs wider arithmetic: the maximum synthetic
result is 16384 MiB. That bound is arithmetic, not a supported-board claim.

The two passes are separate observations. The `different-two-samples`
case supplies first count 8 and second count 32; the result is 1024 MiB
and class 4. Combining or caching the service replies across the passes
would change this behavior. No stability guarantee is assumed.

The final MiB store occurs after both passes. The output word contains
256 between its initial and final stores. Supported callbacks return
normally and preserve the output and configuration. They may update their
own separately owned context, such as a reply cursor. Failure, reentry,
concurrent output/configuration mutation and diagnostic callback behavior
are outside the supported comparison.

## Bounded cache stores

Four cases enter the identified `start4.elf` at internal block 0x0EC62714
and stop before 0x0EC62786. They are not complete initializer calls. The
prior revision gates and setup are supplied:

| Input | Supplied value |
|---|---|
| `r6`, revision word | 0x00D03140 |
| `r8` | Pointer to nonzero GP+0x1564 |
| `r11` | Cache base corresponding to GP+0x3B890 |
| `r12` | 0 |
| Cache word at offset 0x08 | 0x00D03140 |

The block executes the two-pass helper with its output at SP+0x0C.
It updates these cache fields at 0x0EC6273C–0x0EC62784:

| Cache offset | Size (bytes) | Value in the four recorded cases |
|---|---:|---|
| 0x08 | 4 | Previous word with bits 22:20 replaced by class bits 2:0 |
| 0x1C | 1 | 0x14 |
| 0x1D | 1 | 0 |
| 0x1E | 1 | 3 |
| 0x1F | 1 | Returned class |
| 0x20 | 4 | Size in MiB from the first pass |
| 0x24 | 1 | 0 |
| 0x28 | 4 | Updated word from offset 0x08 |

Words use little-endian representation. These cases supply stable byte
replies yielding 1024, 2048, 4096 and 8192 MiB. All other bytes in the
observed 64-byte cache remain unchanged. The standalone output buffer is
untouched by these cases; the helper uses the stack-local output instead.
Neither the supplied revision word nor these numeric sizes identifies a
tested physical board. General neighboring-field derivation and the
remaining initializer are outside these four observations.

## Host representation and comparison

Represent the byte service as an ordered callback or explicit sequence of
byte replies. Preserve all 16 requests, including the unused replies, and
keep the two observations separate. An unsigned-byte callback return type
matches the established input range. No truncation or failure convention
for wider callback results is established.

A host operation requires a valid writable 32-bit output object and a
valid callback before any write or call. Define their ownership, lifetime,
alignment and nonoverlap with mutable callback context. These are host
preconditions, not vendor checks or vendor return codes. The supported
callback must not change the output or reenter the operation. Keep host
validation outcomes separate from the raw class result.

For the cache-slice comparison, use a byte buffer with at least 44
accessible bytes and preserve its unwritten bytes. A test should include
the complete 64-byte observed region and its guards. The fixed neighboring
values above belong only to the supplied revision/context; they do not
define a general board-initialization function. A portable implementation
of the complete helper can compare the 24 standalone cases independently
of those four internal slices.

## Recorded cases and replay

[memory-capacity.json](../../tests/vectors/start4/memory-capacity.json)
contains 28 synthetic cases, 5260 scalar instructions and 448 byte-service
events. The 24 complete calls to 0x0ECC3E60 cover every base selector, both
equality conditions, upper fields 0/1/2/3, low-bit behavior and divergent
observations. Four additional cases cover the internal cache stores.
The inner capacity helper executes twice within each case; it is not
captured as a separate standalone entry.

The fixture uses synthetic GP 0x24020000, stack pointer 0x24010000 and
return sentinel 0x24030000. Cache cases instead stop at 0x0EC62786. These
addresses are test storage, not a runtime memory layout. All backing bytes
are explicit; no MMIO instruction, acquisition leaf or ARM code executes.

Use the imported program and versions from [headless analysis](../analysis.md).
The explicit decode helper defines instruction metadata where automatic
analysis misses scalar switch arms. It does not change firmware bytes or
relax the recorder's memory, instruction or unsupported-operation checks.

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0ECC3E60 0x0ED6B440 0x0EC62714 \
  0x0ED6B488 0x0ED6B48C 0x0ED6B490 \
  0x0ED6B494 0x0ED6B498 0x0ED6B49C \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/memory-capacity.json \
  /work/analysis/memory-capacity.json
```

The output path must not exist. Compare the complete recorded JSON,
including every event, observed byte and instruction count. The strict
missing-flag boundary is an uninitialized 4-byte read of GP+0x1564 at
instruction 0x0ECC3E6E;
it is not a vendor error return or an acquisition result.

## Separate bootmain window

In `bootmain` from `raspberrypi/usbboot` commit
`fdb604d018693465c9aa6ec69879df866d2820da`, SHA-256
`4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d`,
the size input at GP+0x2EC is capped at 1024 MiB by
0x000AD57E–0x000AD58A. The [firmware-pair selection](bootmain.md#firmware-and-fixup-selection)
stores reference and final ARM/GPU split fields at context offsets
0x13C–0x14C. [Fixup processing](start4.md#fixup-stream) consumes their
differences. Those fields describe a bounded split window; they are not
a complete physical RAM-bank map. This is separate static context for the
start4 scalar cases, not an executed acquisition or ownership proof.

## Open questions

- Acquisition and path selection. Establish the byte service's physical
  meaning, ready-bit behavior and GP+0x1564 provenance before connecting
  the callback to hardware. Check observation stability independently.
- Usable memory and reservations. Trace consumers that form bank bases,
  holes and retained VPU/boot-information/mailbox ranges before assigning
  ARM-owned addresses or placing a stub, kernel, device tree or initramfs.
- Cache initialization. Execute the earlier gates and later consumers with
  explicit state before generalizing the four internal cache-store cases.
- Other paths. Record the zero GP+0x1564 path and enabled diagnostics before
  adding them to the portable behavioral contract.
