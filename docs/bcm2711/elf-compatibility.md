<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# ELF compatibility checks

The checks below belong to `bootmain` from raspberrypi/usbboot commit
`fdb604d018693465c9aa6ec69879df866d2820da`, SHA-256
`4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d`.
Addresses are ELF virtual addresses in that file. Its entry establishes
`gp = 0x000CB000` at 0x00080014. The contract covers the ordinary path in
completion handler 0x00086754, with `boot_load_flags` equal to zero and
explicitly supplied query results. It does not establish earlier file or
signature acceptance, physical state, segment placement or firmware entry.

## Metadata and sequence

In the identified `bootmain`, completion handler 0x00086754 performs these
operations before the segment-loader call:

1. At 0x00086758–0x0008677E, initialize a 16-byte metadata buffer from the
   four zero words at 0x000BDCE8, file offset 0x3DD68.
2. At 0x00086780, obtain the loaded image through descriptor helper
   0x000806E8. Call ELF-header validator 0x0008E2A2 at 0x0008678C.
3. At 0x0008679E, look up `.text.firmware_rev`. If found, copy 16 bytes
   into the local metadata buffer at 0x000867AC. Otherwise retain the
   defaults.
4. At 0x000867B0, inspect bit 0 of the word at GP+0x1674. The recorded
   cases supply zero and follow the checks below.
5. At 0x00086940–0x00086946, require both accumulated predicates to be
   nonzero. Success continues at 0x00086980; failure reaches 0x00086948.
6. On success, look up `.text.bootloader_state`, prepare its
   [state-pointer field](boot-information.md#state-pointer-field), process
   the fixup path and validate the ELF again. The segment-loader call
   occurs at 0x00086A90.

The descriptor at file offset 0x4085C names `boot_load_flags` and points to
0x000CC674, or GP+0x1674. The nonzero-flag path is outside this contract.
Compatibility requires supported firmware behavior; changing that flag is
not part of replacement acceptance.

Only the first little-endian metadata word, named `F` below, affects the
observed compatibility decisions. It contains feature bits. The remaining
three words are copied, but no use of them occurs before the segment-loader
call in this path. The predicates in local `r7` and `r6` describe platform
and boot-mode compatibility, respectively. They are not function return
values, and the rejected cases stop before error handling.

## Platform requirements

In the identified `bootmain`, every active row must succeed. GP-relative
words below are cached scalar inputs. Their physical meaning and acquisition
are not established by these checks. A required mask means all its bits must
be present in `F`.

| Condition | Required mask in `F` | Decision addresses |
|---|---|---|
| GP+0x2E8 equals 0x18 and GP+0x954 has bit 0x10 | 0x2000 | 0x000867C8–0x000867E4 |
| GP+0x2E8 equals 0x30 | 0x2000 | 0x000867E8–0x000867F6 |
| GP+0x938 has bit 0x02 | 0x03 | 0x000867FA–0x0008680E |
| VERSION predicate 0x000A76B0 returns nonzero | 0x01 | 0x00086812–0x00086820 |
| GP+0x300 is nonzero | 0x04 | 0x00086824–0x00086834 |
| GP+0x938 has bit 0x02 and GP+0x300 is nonzero | 0x08 | 0x00086838–0x00086852 |
| GP+0x938 has bit 0x04 | 0x40 | 0x00086856–0x0008687C |
| GP+0x938 has bit 0x04 and GP+0x2F8 equals 0x14 | 0x400 | 0x0008685E–0x0008686E |
| The platform object exists and its callback at offset 0xB8 returns 2 | 0x1000 | 0x0008687E–0x0008689E |

The paired 0x03 test rejects `F=1` and `F=2`. Combined conditions retain
each requirement: GP+0x938 bit 0x02 with nonzero GP+0x300 requires 0x0F;
GP+0x938 bit 0x04 with GP+0x2F8 equal to 0x14 requires 0x440. The first
two rows do not identify a live board's RAM capacity.

## Boot-mode requirements

In the identified `bootmain`, the mode is the byte at context offset 0x740,
read at 0x000868A2. These conditions accumulate in a separate predicate.
Platform compatibility alone does not satisfy them.

| Condition | Required mask in `F` | Decision addresses |
|---|---|---|
| Mode 2 and GP+0xA50 equals 2 | 0x80 | 0x000868A2–0x000868BE |
| Mode 0x10 | 0x200 | 0x000868D6–0x000868E4 |
| Mode 4 | 0x10 | 0x000868E8–0x000868F2 |
| Mode 5 | 0x20 | 0x000868F6–0x00086902 |
| Mode 6 | 0x100 | 0x00086906–0x00086912 |
| Mode 2 and GP+0xB50 is nonzero | 0x800 | 0x00086916–0x0008692C |

For modes other than 0x10, this path also calls 0x000A8788 at 0x000868C6.
The recorded cases supply zero at this boundary. Results for a nonzero
reply are outside this contract.

## Execution boundaries

[elf-compatibility.json](../../tests/vectors/bootmain/elf-compatibility.json)
contains 35 synthetic cases and 2171 scalar instructions recorded with
Ghidra 12.2 `EmulatorHelper`. Each enters the identified `bootmain` at
0x000867B0 with a supplied metadata buffer and stops at 0x00086980 or
0x00086948. Cases cover the individual masks, paired requirements and
unchanged context bytes. The fixture contains no ELF executable payload.

The cases supply three call boundaries:

| Call address | Supplied behavior | Limit |
|---|---|---|
| 0x000A76B0 | Return 0 or 1 | VERSION acquisition does not execute; no physical processor identity follows |
| 0x000A8788 | Return zero when called | The ordinary continuation is conditional on this reply; hardware security state and signature acceptance are not measured |
| 0x000A71DC | Record diagnostic arguments | Diagnostic output does not execute |

The platform callback executes normally. In the identified `bootmain`,
0x000A92D4 reads a supplied table pointer. Table 0x000BF2F8 has callback
0x00092252 in its slot at 0x000BF3B0. That callback reads the supplied byte
at GP+0x315. The cases exercise byte values 1 and 2 without assigning them
physical board identities. Diagnostics use the ordinary-path format
pointer 0x00086CB4; successful full-image cases also use 0x00086D48.

These observations are conditional on supplied cached state. They do not
execute VERSION, provisioning queries, storage completion, MMIO, cache
maintenance or firmware entry.

## Open-image observations

The [pinned host build](../../src/start4/README.md) produces an open image
of 36327 bytes with SHA-256
`f0cbcdeeab820ccff5829005a1c897e5b304f2b098494723bb4100fba96cde93`.
Its metadata is present:

| Section | File offset | Address | Size (bytes) | Four little-endian words |
|---|---|---|---:|---|
| `.text.bootloader_state` | 0x1000 | 0xC4000000 | 16 | 0x41545342, 0, 0, 0 |
| `.text.firmware_rev` | 0x1010 | 0xC4000010 | 16 | 3, 0, 0, 0 |

Six additional executions of the identified `bootmain` enter 0x00086754
with that exact image. They use `F=3`, `boot_load_flags=0`, mode 1,
GP+0x938 equal to 3, GP+0x2F8 equal to 0x14, GP+0x315 equal to 1 and
GP+0x2E8 equal to 0x20. GP+0x954, GP+0x300, GP+0xA50 and GP+0xB50 are
zero. Both supplied queries return zero unless the row changes one.
Fixup length at context offset 0xD4 and optional display/dump state are
zero. The loaded image starts at synthetic address 0x24080000.

| Change from supplied state | Platform predicate | Mode predicate | Observed stop |
|---|---:|---:|---|
| None | 1 | 1 | Before segment-loader call, 0x00086A90 |
| VERSION predicate returns 1 | 1 | 1 | Before segment-loader call, 0x00086A90 |
| GP+0x938 equals 6 | 0 | 1 | Incompatible branch, 0x00086948 |
| Mode equals 4 | 1 | 0 | Incompatible branch, 0x00086948 |
| GP+0x300 equals 1 | 0 | 1 | Incompatible branch, 0x00086948 |
| GP+0x2E8 equals 0x30 | 0 | 1 | Incompatible branch, 0x00086948 |

These six cases execute 4683 scalar instructions. The two successful
cases prepare segment-call arguments for image 0x24080000, length 36327
and entry-output pointer 0x2400FFDC. They change only the word at image
file offset 0x1004, from zero to 0x00040000. Every other image byte remains
unchanged. The four rejected cases preserve the entire image. None executes
the segment-loader call or firmware entry.

The feature word remains 3 in every case. Passing a compatibility check
does not establish the behavior represented by a feature bit. Additional
bits require corresponding firmware behavior and differential verification.
These supplied states do not establish compatibility across CM4 variants
or boot modes.

## Open questions

- Cached-state provenance. Trace the writers of the GP-relative fields and
  VERSION/platform queries, then compare their outputs on supported board
  configurations. The synthetic values do not identify a real board.
- Earlier file acceptance. Execute storage and signed/unsigned completion
  paths with their documented inputs before connecting this caller to a
  complete load result. A supplied query reply cannot establish trust policy.
- Feature behavior. Identify the runtime behavior associated with each
  required mask and test it before changing the open image's feature word.
- Complete handoff. Connect the compatibility and segment-placement checks
  to verified address mapping, cache visibility and entry-state preparation,
  then test the complete path on hardware.
