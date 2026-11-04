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

The decompressed `mcb.bin` identified above contains 5651 zero bytes among its 12384 bytes, from offset 0x00 through 0x305F. Its record layout and selection rules remain unresolved.

## Open questions

- Resource selection. Trace the bootsys paths that select memsys and MCB data; record how density, rank count, part configuration and termination affect the selected resource and offset.
- PHY processor and instruction set. Establish the hardware destination of the memsys transfer and identify the receiving processor before applying the STB DCPU description to the BCM2711.
- Transfer format and initialization sequence. Trace the host writes that load the PHY resources, record byte order and register addresses, and verify the sequence and completion conditions in emulation where peripheral behavior is available.
- MCB layout. Trace reads from `mcb.bin` and correlate offsets with resource-selection inputs before assigning field meanings or record sizes.
