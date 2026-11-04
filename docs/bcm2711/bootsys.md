# bootsys

bootsys is the first EEPROM stage in raspberrypi/usbboot
`docs/secure-boot-chain-of-trust-2711.pdf`, page 1, at commit
`fdb604d018693465c9aa6ec69879df866d2820da`. The diagram describes the
secure-boot chain; it does not establish the behavior of every boot mode.

All binary offsets below refer to `2711/bootcode4.bin` from that commit's
`firmware/bootfiles.bin`: 50930 bytes, SHA-256
`9e1b0b7df904a7fdc22e263d530c6e4c48921229631dd7ea2325271843996f6c`.
These bytes equal the first section payload at EEPROM offset `0x000008` in
`pieeprom-2026-10-30.bin`, identified in [vendor-files.md](vendor-files.md).

## Layout

| Offset | Size (bytes) | Contents |
|---|---|---|
| 0x0000 | 512 | zero bytes |
| 0x0200 | 50134 | body, including the digests below |
| 0xC5D6 | 284 | footer |

## Resource digests

Each location contains the 32-byte SHA-256 of the named decompressed section
of `pieeprom-2026-10-30.bin`. The digest also equals the final 32 bytes of
that compressed section. Section locations are in [eeprom.md](eeprom.md).

| Offset in bootsys | Resource |
|---|---|
| 0xB8C0 | `logo.bin` |
| 0xB8E0 | `font.bin` |
| 0xB900 | `mcb.bin` |
| 0xB920 | `memsys00.bin` |
| 0xB940 | `memsys01.bin` |
| 0xB960 | `memsys02.bin` |
| 0xB980 | `memsys03.bin` |
| 0xB9A0 | `memsys04.bin` |
| 0xB9C0 | `memsys05.bin` |
| 0xB9E0 | `memsys06.bin` |
| 0xBA00 | `memsys07.bin` |
| 0xBA20 | `memsys08.bin` |
| 0xBBA8 | `bootmain` |

Digest equality establishes the stored values. It does not establish which
execution paths check them or how a mismatch is handled.

## Footer

The field boundaries follow librerpi/rpi-tools `signing-tool/docs.txt` at
commit `a700385d9b1c2f93d755d4455792ce7b08f90ede`. The first two fields are
checked directly in `bootcode4.bin`; the cryptographic interpretation is
from that source.

| Offset in bootsys | Size (bytes) | Field |
|---|---|---|
| 0xC5D6 | 4 | body length, little-endian: 50646 |
| 0xC5DA | 4 | key index, little-endian: 1 |
| 0xC5DE | 256 | RSA signature field |
| 0xC6DE | 20 | legacy checksum field |

The body length equals the file size minus 284. The matching footer
boundaries in `recovery.bin` are listed in [usbboot.md](usbboot.md).

## Documented role

The pinned usbboot chain-of-trust diagram assigns these operations to
bootsys: checking the customer public-key digest, verifying the EEPROM
configuration, and loading bootmain and resources while checking embedded
hashes. These are the vendor's description of secure boot, not execution
results for the pinned `bootcode4.bin`.

## Open questions

- Load address and entry point. The 512 zero bytes at `0x0000` do not
  establish either. Resolve the absolute references in the body starting
  at `0x0200`, then validate a candidate memory map in emulation.
- Digest verification. Trace references to `0xB8C0`–`0xBA20` and `0xBBA8`;
  compare the result for an unchanged resource and a one-byte mismatch in
  emulated input.
- Footer checks with secure boot disabled. Obtain a vendor specification
  for the relevant ROM revision. The secure-boot diagram alone does not
  determine which footer fields the ROM checks in that mode.
- SDRAM and configuration flow. Identify the callers that consume the
  resource names and configuration before assigning initialization order
  or rejection behavior to this build.
