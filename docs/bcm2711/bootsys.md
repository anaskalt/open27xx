# bootsys

bootsys is the first stage that the boot ROM loads from the SPI EEPROM. It is raw VPU code without an ELF header, followed by a signature footer. The name comes from the BCM2711 chain-of-trust diagram in usbboot (`docs/secure-boot-chain-of-trust-2711.pdf`).

bootsys is section 0 of the EEPROM image (magic 0x55AAF00F). `bootfiles.bin` in usbboot carries the same bytes as `2711/bootcode4.bin`.

Offsets refer to the bootsys of `pieeprom-2026-10-30.bin`, 50930 bytes.

## Layout

| Offset | Size | Contents |
|---|---|---|
| 0x0000 | 0x200 | zero bytes |
| 0x0200 | 0xC3D6 | code and data, including the digest table |
| 0xC5D6 | 0x11C | footer |

Digest table, 32 bytes per entry:

| Offset | SHA-256 of |
|---|---|
| 0xB8C0 | `logo.bin` |
| 0xB8E0 | `font.bin` |
| 0xB900 | `mcb.bin` |
| 0xB920–0xBA20 | `memsys00.bin`–`memsys08.bin` |
| 0xBA40 | `vl805hub.bin` |
| 0xBA60 | `vl805mcu.bin` |
| 0xBBA8 | `bootmain` |

Each digest covers the decompressed contents and equals the digest stored in the section itself. Older images do not cover every resource: images from 2020-03-04 to 2020-07-06 carry none of these digests, images up to 2021-04-29 lack the VL805 digests, and images from 2024-04-17 to 2024-12-07 lack the digest of `qrcode.bin`.

## Footer

| Offset in footer | Size | Field |
|---|---|---|
| 0 | 4 | length of the signed data, little-endian: 50646, the section size minus 284 |
| 4 | 4 | key index, little-endian |
| 8 | 256 | RSA-2048 signature |
| 264 | 20 | legacy checksum |

The layout matches `signing-tool/docs.txt` in librerpi/rpi-tools. `tools/rpi-sign-bootcode` in rpi-eeprom computes the legacy checksum as an HMAC-SHA1. `recovery.bin` uses the same footer.

The key index selects a public key in the boot ROM. The chain-of-trust diagram lists key 0 as the development key, key 1 as the secure key and keys 2 and 3 as reserved, and states that old and beta bootloaders are signed with the development key. Published images use index 0 up to 2022-01-20, both indexes from 2022-01-25 to 2023-01-04, and index 1 from 2023-01-11 onward.

## Function

From the chain-of-trust diagram: when secure boot is enabled, bootsys verifies the customer public key against its digest in OTP. It then loads bootmain and the resources into RAM and checks them against the digest table.

From its log messages:

- SDRAM initialization: bootsys selects a memsys and MCB configuration by density, rank count, part configuration and on-die termination, and reports the DDR rate. See [sdram.md](sdram.md).
- OTP anti-rollback: a bootloader revision below the minimum in OTP is rejected.
- EEPROM configuration: bootsys reads it before loading bootmain.
- Network install: a path and a download host name are present as strings.

bootsys contains a SHA-256 implementation: the first initial hash word, 0x6A09E667, is stored little-endian at 0x4C84, and the round constants start at 0xB5A0.

## Open questions

- Load address and entry point. The 0x200 zero bytes fit the layout used by librerpi for VPU code, where a 128-entry vector table at the base address precedes the entry point at base + 0x200. With a base of 0x80000000 the entry point would be 0x80000200. Absolute addresses in the code would confirm it.
- Which check the boot ROM applies when secure boot is disabled: the RSA signature, the HMAC-SHA1 checksum or both.
