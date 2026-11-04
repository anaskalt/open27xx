# SDRAM initialization

The resource map below refers to `pieeprom-2026-10-30.bin` from raspberrypi/rpi-eeprom commit `236b4406753e604fde3315cb521a2f843c9f8f85`, SHA-256 `6abfaea480f93da47a790f89751ed45d3af6e88ee8fb337d4eb62ad125ca3e8a`. Offsets identify section headers in that image. Every listed section uses LZ4; each SHA-256 covers the complete decompressed resource and equals the digest stored in its section.

| Resource | Section offset | Decompressed size (bytes) | SHA-256 |
|---|---|---|---|
| `memsys00.bin` | 0x040518 | 20492 | `6dde761b7c678f96868a290526ab1e94325a1b50ebff55f7d242eebc7864d782` |
| `memsys01.bin` | 0x0436C8 | 20492 | `ae4ec3bf6c825194db9d8187a6a1259dde9afbc7fc5cc3b549160869a726e1af` |
| `memsys02.bin` | 0x0462B8 | 20492 | `6db139a4d842abcd1bcfbd7e8569100d022b72a13caea55e27c7f27a46f482fe` |
| `memsys03.bin` | 0x048B40 | 20492 | `e4aa04005b361338a4fac3716843816ddf86811aa0d601a7706eef4a27c246ef` |
| `memsys04.bin` | 0x04B238 | 20492 | `cb983d480b735691651927ff3706c0eb4e28cb08e5d67a5ca341fe4f6287aaca` |
| `memsys05.bin` | 0x04E0B0 | 20492 | `5542e200f91bd695d87b84616a55a0c637a7f144b200a45a3141e1d7754620ad` |
| `memsys06.bin` | 0x050EF0 | 20492 | `5f243c66c08868e66e0a9a80082181d3aae289881e2200fe0ccab4fb2e693c11` |
| `memsys07.bin` | 0x053A10 | 20492 | `4a33a96ee3a96bb39145d17e2cc7918eaa4a90d7d9c239d6cede4b258ad7fdd8` |
| `memsys08.bin` | 0x056960 | 20492 | `d18ee9cf804b90233d4dc93132727d576cacbf7557a2268af89d6885f7e9dcd4` |
| `mcb.bin` | 0x059260 | 12384 | `a615150a4a241a48eafa91be453b2790ba35f37a53d6652af1f1f8cf7f8178a6` |

## memsys00.bin–memsys08.bin

Reversing the bytes within each four-byte group, starting at resource offset 0x00, exposes the identifiers below. Offsets refer to this transformed view of each decompressed resource identified above. A byte at transformed offset `n` comes from original offset `(n & ~3) + 3 - (n & 3)`.

| Resource | `DPFE FW hph1_lpddr4` offset | `2.35.0.0` offset |
|---|---|---|
| `memsys00.bin` | 0x45B3 | 0x45C8 |
| `memsys01.bin` | 0x4355 | 0x436A |
| `memsys02.bin` | 0x4355 | 0x436A |
| `memsys03.bin` | 0x4358 | 0x436D |
| `memsys04.bin` | 0x4381 | 0x4396 |
| `memsys05.bin` | 0x4355 | 0x436A |
| `memsys06.bin` | 0x4375 | 0x438A |
| `memsys07.bin` | 0x4440 | 0x4455 |
| `memsys08.bin` | 0x4429 | 0x443E |

In the transformed `memsys00.bin`, `LPDDR4` occurs at 0x45DD and `LPDDR4X` at 0x4605. This byte transformation establishes the string representation, not the instruction set or the loader's transfer order.

Linux v6.12, [`drivers/memory/brcmstb_dpfe.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/memory/brcmstb_dpfe.c), describes a DDR PHY front end for Broadcom set-top-box SoCs with a DCPU inside the PHY. Its introductory comment specifies big-endian DCPU execution and little-endian host communication. The driver's `DPFE_BE_MAGIC` and `DPFE_LE_MAGIC` values are 0xFE1010FE and 0xFE0101FE. Neither byte sequence occurs in any of the nine complete decompressed memsys resources above, from offset 0x00 through 0x500B.

## mcb.bin

The decompressed `mcb.bin` identified above contains 5651 zero bytes among its 12384 bytes, from offset 0x00 through 0x305F. The host record layout and selection rules are described below.

## Host initialization path

The host behavior below refers to usbboot `2711/bootcode4.bin` from
commit `fdb604d018693465c9aa6ec69879df866d2820da`, SHA-256
`9e1b0b7df904a7fdc22e263d530c6e4c48921229631dd7ea2325271843996f6c`.
Addresses use the provisional `0x80000000` mapping; subtract that base
for file offsets. These observations cover VPU resource selection and
sequencing, not the execution of the PHY firmware.

The dispatcher at `0x80006FE8` uses the initialized flag at `gp + 0xB8`.
If it is already nonzero, the dispatcher returns 0 without loading a
resource. Otherwise it performs this sequence:

1. Prepare a destination descriptor through `0x800059A6` and load
   `mcb.bin` through `0x80007384`, with the expected digest at
   `0x8000B900`.
2. Call the MCB selector at `0x800054D4` with the loaded contents and
   length. A negative result stops the sequence.
3. Load `memsys00.bin` and request stage 0 through `0x80005988`.
4. For each following resource through `memsys08.bin`, load the resource,
   then call `0x80005A2C` for the preceding stage. A nonzero completion
   flag ends the stage-start loop; otherwise request the next stage
   through `0x80005988`.
5. Call `0x80005A2C` with stage index 8. On success, set `gp + 0xB8` to 1
   and return 0.

The memsys name-pointer table starts at `0x8000B800`; the expected-digest
array starts at `0x8000B920` with 32 bytes per entry. The dispatcher loads
the next resource before waiting for the previous stage. An early
completion response can therefore leave the next loaded resource
unused.

In `0x80006FE8`, a failed resource load selects result `0xFFFFFFFE` and
requests the failure-report path with code `0x31`. Failed MCB selection,
stage start or stage completion selects `0xFFFFFFFF`. The initialized
flag remains zero in the tested failures.

[sdram-sequence.json](../../tests/vectors/bootsys/sdram-sequence.json)
records eight cases covering the complete nine-stage request sequence,
early completion, the initialized fast path and each failure class.
The dispatcher, descriptor helpers and MCB selector execute. Resource
delivery and PHY start/completion use explicit literal responses. The
failure-report boundary returns in the test harness so the subsequent
status can be observed. These cases establish host ordering and error
propagation, not training success or the device failure handler.

## Configuration fields

In the pinned `bootcode4.bin`, the MCB selector at `0x800054D4` consumes
a configuration value obtained through `0x80006F2E`, or a resume/probe
path. The vectors supply a synthetic configuration at that boundary and
perform no OTP or memory-device reads.

| Configuration bits | Consumer | Meaning used by the selector |
|---|---|---|
| 2:0 and 5 | `0x80007EEE` | density code |
| 3 | `0x800054D4` | byte-mode flag |
| 4 | `0x800054D4` | dual-rank flag |
| 8:6 | `0x80007EE6` | part configuration |

The density decoder at `0x80007EEE` returns these values, expressed as
Gbit by the diagnostic at `0x800058AC`:

| Bits 2:0 | Bit 5 clear | Bit 5 set |
|---|---|---|
| 0, 1, 2 | 0 | 0 |
| 3 | 128 | 128 |
| 4 | 64 | 64 |
| 5 | 32 | 48 |
| 6 | 16 | 24 |
| 7 | 8 | 4 |

The encoder at `0x80007E62` takes dual rank, byte mode, density and part
configuration in `r0` through `r3`. It places the flags in bits 4 and 3,
masks the part field to three bits, and encodes the density above.
The 39 cases in
[sdram-config.json](../../tests/vectors/bootsys/sdram-config.json)
exercise density decoding, part extraction, encoding and speed selection
without substituted calls or device access.

## MCB records and selection

The MCB scanner at `0x800054D4` treats its contents as variable-length
records. The fields below are offsets from a record, not offsets from
the outer EEPROM section. The header is 80 bytes, followed by a count of
32-bit words.

| Record offset | Size (bytes) | Role in 0x800054D4 |
|---|---|---|
| 0x00 | 4 | copied to the selected header; not tested by the scanner |
| 0x04 | 4 | copied to `gp + 0xA4C` |
| 0x08 | 4 | rate to match |
| 0x0C | 4 | density to match |
| 0x10 | 4 | dual-rank value to match |
| 0x14 | 4 | byte-mode value to match |
| 0x18 | 4 | part configuration to match |
| 0x1C | 4 | termination setting to match |
| 0x20 | 4 | following word count |
| 0x24 | 44 | auxiliary data copied to `gp + 0x17A4` |
| 0x50 | count × 4 | words copied to `gp + 0x14A0` |

The scanner at `0x800054D4` requires matching configuration fields, a
nonzero count no greater than 152, and enough remaining bytes for the
words. It masks the supplied contents length down to a multiple of four.
A rejected record with a nonzero count advances by 80 plus four times
the count. A zero count ends the scan. On selection it also copies the
first 36 header bytes to the address held at `gp + 0x48` and returns 0.
No match returns `0xFFFFFFFF`.

The speed helper at `0x80005146` maps selectors 1 through 7 to 1350,
2160, 2400, 2667, 3200, 3733 and 4267 respectively. Selector 0 returns
zero, which disables rate matching in `0x800054D4`; the tested selector 8
also maps to zero. The rate diagnostic at `0x80005860` labels the value
in Mbps. The MCB selector accepts densities 4, 8, 16, 24, 32, 48 and 64;
the decoded density 128 reaches its unsupported-size failure path.

[mcb-selection.json](../../tests/vectors/bootsys/mcb-selection.json)
records fourteen cases: matching and nonmatching dimensions, unrestricted
rate, selection of a later record, zero/excessive counts, short contents,
the 152-word boundary and unsupported density. All records and copied
contents are synthetic. Configuration acquisition, board preparation and
diagnostic output are substituted. The comparison, bounds checks and
copy operations execute in `0x800054D4`.

## Execution boundaries

For the pinned `bootcode4.bin`, `0x80005988` passes the memsys data and
selected words to `0x80004F46`. Static references in that path reach
`0x7DC20000`; the completion path through `0x8000507E` reaches
`0x7DC30000`. These addresses locate the remaining device-specific work.
The tests stop at the start/completion call boundaries and do not provide
register values for those devices.

The fixtures initialize their declared synthetic memory in array order.
MCB and sequence cases first zero a synthetic global-state area, then
overlay the explicit pointers and configuration fields. The recorder
rejects uninitialized reads, undeclared memory writes, MMIO reads, vector
instructions and unsupported p-code operations. Recorded MMIO writes
in resource-hash cases do not imply a modeled device response.

## Open questions

- Configuration acquisition. Reproduce the resume and device-probe paths
  that supply density, rank, byte mode and termination settings to
  `0x800054D4`. Synthetic field matching does not establish their hardware
  origin or the policy for every board revision.
- PHY processor and instruction set. Establish the hardware destination of the memsys transfer and identify the receiving processor before applying the STB DCPU description to the BCM2711.
- PHY transfer and completion details. Trace the device register writes
  that load the resources, record byte order, and verify the hardware
  completion conditions where peripheral behavior is available.
- MCB field meanings beyond selection. Follow the consumers of the copied
  44-byte auxiliary area and word array before assigning PHY register
  meanings to them. The first header word is not a validated magic in
  the observed scanner.
