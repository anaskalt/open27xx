<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Lower memory span

The standard firmware pair connects the bootmain ARM split field to the
byte-count input of the [memory-bank serializer](memory-layout.md). Its
fixup stream changes two bound immediates. The difference between the two
results supplies the lower span through the caller transfers below.
This numerical relationship does not establish usable RAM, physical
ownership, reservations or a complete device-tree update.

## Source identities

| File | Repository and commit | Bytes | SHA-256 |
|---|---|---:|---|
| `start4.elf` | `raspberrypi/firmware` `ab5c7f86283ceb58b7adb269cae1d16092a31bf6` | 2303104 | `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb` |
| `fixup4.dat` | Same firmware commit | 5512 | `349d772e90351c4012d9b631f64ee9f0bc7587b44c8da97ef0d8994fabd0ea87` |
| `bootmain` | `raspberrypi/usbboot` `fdb604d018693465c9aa6ec69879df866d2820da` | 267042 | `4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d` |

Start4 addresses below refer to the first row; bootmain addresses refer
to the third. File offsets start at zero. The observations apply to this
standard pair. Other variants and overridden pairs require separate checks.

## Original bounds and byte count

In the identified `start4.elf`, helpers 0x0EC5ABF6 and 0x0EC5ABFE each
return GP plus a 32-bit immediate. Arithmetic wraps modulo 2^32.

| Helper | Immediate file offset | Original immediate | Result with GP = 0x0EE04140 |
|---|---|---|---|
| 0x0EC5ABF6 | 0x0005A5F8 | 0xF91FBEC0 | 0x08000000 |
| 0x0EC5ABFE | 0x0005A600 | 0xF11FBEC0 | 0x00000000 |

Startup function 0x0EC593C4 calls these helpers at 0x0EC593CE and
0x0EC593D4, saving their results in `r8` and `r7`. At 0x0EC59532 it
subtracts the second from the first modulo 2^32. The unmodified image
therefore supplies a difference of 134217728 bytes for these constants.
The paired fixup changes those constants before the eventual runtime use.
The original difference is not a general memory-size constant.

The recorded prefix executes both complete helpers with original GP and
with supplied GP 0x24020000. The second case returns 0x1D21BEC0 and
0x1521BEC0, again differing by 134217728 bytes. The larger startup body
between the prefix and subtraction is not executed in these cases.

## Paired fixup arithmetic

The identified `fixup4.dat` contains 5282 first-list patches and three
second-list patches. Both lists end at the complete ELF length of
2303104 bytes. Exactly three records intersect the two helper instructions:

| List | Stream offset | ELF file offset | Original address | Effect |
|---:|---|---|---|---|
| 0 | 0x00000102 | 0x0005A5FA | 0x0EC5ABFA | Subtract first adjustment from the first immediate's high halfword |
| 0 | 0x00000106 | 0x0005A602 | 0x0EC5AC02 | Subtract first adjustment from the second immediate's high halfword |
| 1 | 0x00001578 | 0x0005A5FA | 0x0EC5ABFA | Add second adjustment to the first immediate's high halfword |

The [fixup format](start4.md#fixup-stream) applies each operation modulo
65536 to the selected halfword. The common low halfword remains 0xBEC0.
Bootmain 0x000869CA–0x00086A18 forms the two adjustments from context
size fields measured in MiB:

| Adjustment | Formula |
|---|---|
| `D_total` | 16 × (final total − reference total) |
| `D_arm` | 16 × (final ARM − reference ARM) |

After the paired operations, the two high halfwords are
`(0xF91F − D_total + D_arm) mod 65536` and
`(0xF11F − D_total) mod 65536`. Both helpers add the same runtime GP.
Their difference is therefore
`(134217728 + D_arm × 65536) mod 2^32`.
The common GP and total adjustment cancel.

The standard pair's reference ARM field is 128 MiB. Under the accepted
adjustment formula, the difference equals
`final_arm_mib × 1048576` modulo 2^32. Within the documented
[bootmain split window](bootmain.md#firmware-and-fixup-selection), capped
at 1024 MiB, that byte count does not wrap. This relationship is conditional
on the paired fixup being applied; the caller's reference-size checks still
apply. It does not replace the separately derived
[total capacity](memory-capacity.md).

For example, synthetic final total/ARM fields of 1024/948 MiB give
994050048 bytes. Fields of 1024/1008 give 1056964608 bytes; 512/256 give
268435456 bytes. These are arithmetic examples, not measured allocations.

## Offline fixup observations

Two complete-pair observations execute the identified bootmain function
0x000811C6 on an offline copy of the paired ELF and stream. Each call
takes 69554 scalar instructions. All image bytes, image guards, stream
bytes and adjustment words are checked. The table extracts the GP word
at ELF file offset 0x00000870 and the two immediate fields from those
outputs, then evaluates their numerical difference.

| Adjustments total/ARM | GP word | First immediate | Second immediate | Evaluated difference |
|---|---|---|---|---:|
| 0, 0 | 0x0EE04140 | 0xF91FBEC0 | 0xF11FBEC0 | 134217728 bytes |
| 0x100, 0x80 | 0x0FE04140 | 0xF89FBEC0 | 0xF01FBEC0 | 142606336 bytes |

The complete output-image SHA-256 values are respectively
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb` and
`f3fdec4ea23dd5a4686adb774415d887a7473f50dc5294cccf67b8506f1d653c`.
The latter difference is 136 MiB: an 8 MiB ARM-field increase remains,
while the 16 MiB total relocation cancels. The relocated start4 instructions
are not executed in these observations. These complete-pair observations
are separate from the synthetic transport fixtures below; no complete
firmware image is included in those fixtures.

## Explicit argument transfers

In the identified `start4.elf`, the following call sites and explicit
register/stack transfers carry the numerical difference toward the
serializer. Each stack offset is relative to its own post-prologue SP.

| Caller | Transfer | Next call |
|---|---|---|
| 0x0EC593C4 | Difference in `r0` at 0x0EC59532 | 0x0ED13224 at 0x0EC59536 |
| 0x0ED13224 | Save incoming `r0` in `r7` at 0x0ED13226; copy to `r1` at 0x0ED13250 | 0x0ED14134 at 0x0ED13252 |
| 0x0ED14134 | Store incoming `r1` at SP+0x30 at 0x0ED14146; reload at 0x0ED14578 | 0x0EC54FD0 at 0x0ED14580 |
| 0x0EC54FD0 | Store incoming `r1` at SP+0x38 at 0x0EC54FE0; reload at 0x0EC56452 | 0x0EC57248 at 0x0EC56456 |
| 0x0EC57248 | Save incoming `r1` in `r9` at 0x0EC57252; copy to serializer `r3` at 0x0EC57510 | 0x0ECB2A50 at 0x0EC57518 |

These are explicit instruction transfers and bounded execution results.
The intervening callees and branch conditions of the complete startup,
loader and constructor are not executed by the transport fixtures.
Preservation through every omitted call and complete runtime reachability
remain separate questions.

The serializer consumes `r3` as an unsigned byte count and truncates it
to MiB for the first tuple. Its `r4` total-capacity input already uses MiB
and arrives by the separate cache path. The transport cases preserve
fractional-MiB values unchanged at serializer entry; they do not perform
that later truncation. The [serializer fixtures](memory-layout.md#recorded-cases-and-replay)
cover the truncation separately.

## Synthetic transport cases

[memory-span.json](../../tests/vectors/start4/memory-span.json) contains
27 cases and 197 scalar instructions. It includes supplied registers,
synthetic stack bytes, exact stopping addresses and complete observations.
Its SHA-256 is
`f3a6f58c3bdea570d9cb2641d52745acdfe42c1c579e73c88c7b78dc7d47c1f8`.

| Group | Cases | Entry | Stop before | Instructions per case |
|---|---:|---|---|---:|
| Original bound prefix | 2 | 0x0EC593C4 | 0x0EC593DA | 11 |
| Difference into wrapper | 5 | 0x0EC59532 | 0x0ED1322A | 5 |
| Wrapper into loader prologue | 5 | 0x0ED1324E | 0x0ED14148 | 9 |
| Loader into parent prologue | 5 | 0x0ED14578 | 0x0EC54FE2 | 10 |
| Parent into constructor prologue | 5 | 0x0EC56452 | 0x0EC57254 | 7 |
| Constructor into serializer entry | 5 | 0x0EC57510 | 0x0ECB2A50 | 4 |

The five transport groups each use byte values 0, 1, 1048575, 305419896
and 4294967295. The last subtraction case supplies upper 0 and lower 1,
so its result wraps to 4294967295. These are numerical words, not validated
physical ranges. The final group holds total capacity at an independent
8192 MiB while varying the byte span.

Each case supplies SP = 0x24010000 and 1792 stack bytes from 0x2400FA00
through 0x240100FF. The observations cover all 48384 bytes across the
27 cases and all 297 listed register results. Saved-register words and
explicit stores match exactly. Bytes outside those stores remain unchanged,
including the caller's source word. The six groups leave SP below its input
by 64, 12, 580, 388, 1316 and zero bytes respectively; the stopped prologues
have not returned. The last group writes no memory.

There are no stubs or MMIO events. The supplied base pointers are moved
or saved without dereferencing their pointed-to contents. Alias acquisition,
complete loader calls, property insertion and reservation updates remain
outside these cases.

## Replay

Use the imported program and versions from [headless analysis](../analysis.md).
Run from the repository root with an unused output path. Instruction
preparation changes transient metadata only; the original source bytes
and scalar instruction semantics remain unchanged.

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EC593C4 0x0EC5ABF6 0x0EC5ABFE 0x0EC59532 \
  0x0ED13224 0x0ED1324E 0x0ED14134 0x0ED14578 \
  0x0EC54FD0 0x0EC56452 0x0EC57248 0x0EC57510 \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/memory-span.json \
  /work/analysis/memory-span.json
cmp tests/vectors/start4/memory-span.json /work/analysis/memory-span.json
```

Compare the complete JSON, including instruction counts, all observed
registers and every memory byte. The recorder rejects unknown reads,
undeclared writes, altered instruction bytes and unsupported operations.

Two separate missing-state probes confirm those boundaries. Omitting the
source word at SP+0x38 causes an uninitialized 4-byte read at 0x24010038
by instruction 0x0EC56452. Supplying that word without stack backing causes
an undeclared 4-byte write at 0x2400FFFC by instruction 0x0EC57248.
Neither produces a result artifact. These are recorder failures, not
vendor error returns or evidence of a checked stack interface.

## Open questions

- Composed transport. Execute the intervening calls and branch conditions
  before claiming complete preservation or reachability from startup to
  the serializer. The bounded prologue and call-site slices do not establish
  those omitted effects.
- Runtime placement. Check relocated execution, aliases, reservations and
  later consumers before assigning physical ownership to a lower span or
  to the serializer's emitted tuples.
- Other firmware pairs. Locate and check the corresponding helper fields,
  references and paired fixup intersections before extending this arithmetic
  to cut-down, debug, extended or overridden firmware pairs.
