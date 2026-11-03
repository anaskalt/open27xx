# SPI EEPROM image

The BCM2711 bootloader is stored in a 512 KiB SPI EEPROM. The image, published as `pieeprom-*.bin` in rpi-eeprom, is a chain of sections. `tools/eeprom.py` lists, extracts and verifies them.

Offsets and sizes refer to `pieeprom-2026-10-30.bin` unless stated otherwise. `scripts/blobs.sha256` has its SHA-256.

## Sections

Each section starts with an 8-byte header:

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | magic, big-endian |
| 4 | 4 | payload length in bytes, big-endian |
| 8 | length | payload |

The next section starts at the following 8-byte boundary; the gap is filled with 0xFF. A magic of 0xFFFFFFFF ends the chain; `rpi-eeprom-config` also accepts 0x00000000. In released images the rest of the image is 0xFF, and `rpi-eeprom-config` reserves the last 4 KiB for the bootloader.

A magic is valid if `magic & 0xFFFFF00F == 0x55AAF00F`. Bits 4 to 11 give the section type:

| Magic | Type | Payload |
|---|---|---|
| 0x55AAF00F | bootcode | bootsys, see [bootsys.md](bootsys.md) |
| 0x55AAF11F | file | 12-byte name, 4 zero bytes, contents |
| 0x55AAF22F | plain | 16-byte name, contents |
| 0x55AAF33F | LZSS | 16-byte name, compressed contents, 32-byte SHA-256 of the contents |
| 0x55AAF44F | LZ4 | 16-byte name, LZ4 frame, 32-byte SHA-256 of the contents |
| 0x55AAFEEF | padding | 0xFF bytes |

Names are ASCII, padded with zero bytes. File sections hold the configuration and the key and signature slots, which `rpi-eeprom-config` rewrites in place.

## LZSS compression

Type 0x33 sections use a byte-oriented LZSS variant with a 256-byte window:

1. A flag byte describes the next eight items, least significant bit first.
2. A clear bit is a literal: one byte is copied to the output.
3. A set bit is a back-reference of two bytes, the distance minus one and the length minus one. The decoder copies that many bytes from that distance back in the window, one byte at a time, so the copy may overlap its own output.
4. The window is a ring buffer of the last 256 output bytes and starts zero-filled.
5. The stream ends when the input ends; unused flag bits are ignored.

Type 0x44 sections hold a standard LZ4 frame.

## Section map

Padding sections are omitted. The length column is the header field, which includes the name and, for compressed sections, the digest.

| Offset | Type | Name | Length | Contents |
|---|---|---|---|---|
| 0x000000 | bootcode | bootsys | 50930 | 50930 |
| 0x00C918 | LZ4 | `bootmain` | 211955 | 267042 |
| 0x040518–0x056960 | LZ4 | `memsys00.bin`–`memsys08.bin` | 9963–12706 | 20492 each |
| 0x059260 | LZ4 | `mcb.bin` | 1340 | 12384 |
| 0x0597A8 | LZSS | `vl805hub.bin` | 7028 | 9446 |
| 0x05B328 | LZSS | `vl805mcu.bin` | 60451 | 86680 |
| 0x069F58 | LZ4 | `logo.bin` | 2256 | 12844 |
| 0x06A830 | LZ4 | `font.bin` | 7422 | 27404 |
| 0x06C538 | file | `versioninfo` | 70 | 54 |
| 0x06C588 | file | `updatetime` | 24 | 8 |
| 0x06C600 | file | `pubkey.bin` | 528 | 512 |
| 0x06C900 | file | `cacert.der` | 2064 | 2048 |
| 0x06D200 | file | `bootconf.sig` | 1040 | 1024 |
| 0x06D700 | file | `bootconf.txt` | 95 | 79 |

The end marker, 0xFFFFFFFF, is at 0x06D768.

Resources:

- `bootmain`: the main bootloader stage, see [bootmain.md](bootmain.md).
- `memsys00.bin`–`memsys08.bin`, `mcb.bin`: SDRAM firmware and configuration, see [sdram.md](sdram.md).
- `vl805hub.bin`, `vl805mcu.bin`: firmware for the VL805 USB 3 controller of the Raspberry Pi 4 Model B and Raspberry Pi 400. The Compute Module 4 has no VL805.
- `logo.bin`, `font.bin`: Targa images for the HDMI diagnostics screen, 50 × 64 in 32-bit RGBA and 720 × 19 in 16-bit grayscale with alpha.

File sections:

- `versioninfo`: `VERSIONINFO 2026/10/30 23:20:35 13c4219f R 2711 MFG02`, terminated by a zero byte.
- `updatetime`: 8 bytes; the released image holds the little-endian words 0x00000000 and 0xFFFFFFFF.
- `pubkey.bin`, `cacert.der`, `bootconf.sig`: zero-filled slots for the customer public key, a CA certificate and the signature of the configuration.
- `bootconf.txt`: the default configuration.

```ini
[all]
BOOT_UART=0
WAKE_ON_GPIO=1
POWER_OFF_ON_HALT=0
NET_INSTALL_AT_POWER_ON=1
```

## Related formats

These come from the rpi-eeprom tools and have not been checked against the bootloader code:

- `pubkey.bin`: the RSA-2048 modulus (256 bytes) followed by the public exponent (8 bytes), both little-endian (`tools/rpi-bootloader-key-convert`).
- `bootconf.sig`: text lines with the SHA-256 of `bootconf.txt` in hex, `ts: <unix time>`, an optional `target-soc: <soc>` and `rsa2048: <signature in hex>`, where the signature is an RSA PKCS #1 v1.5 signature over SHA-256 (`rpi-eeprom-digest`).
- Self-update timestamp: `rpi-eeprom-config` writes the complement of the timestamp followed by the timestamp, both little-endian 32-bit words, into an `updatetime` section in the first 64 KiB of the image, or else into the last 8 bytes of the image.
- BCM2712 images are 2 MiB. Recent ones use an A/B layout: a 64 KiB read-only region, two 988 KiB partitions and two journal sections (`rpi-eeprom-config`).

## Image history

The pinned rpi-eeprom commit holds 120 BCM2711 images, 2019-07-15 to 2026-10-30; the images of 2020-09-02 and 2020-09-03 are identical. The changes to the section set:

| First image | Change |
|---|---|
| 2019-07-15 | bootsys, `memsys00.bin`–`memsys07.bin` as plain sections, `bootconf.txt` |
| 2019-09-06 | `mcb.bin` added |
| 2020-03-04 | all resources LZSS-compressed; `vl805hub.bin`, `vl805mcu.bin`, `logo.bin`, `font.bin` and `qrcode.bin` added |
| 2021-05-19 | `memsys08.bin`, `pubkey.bin` and `bootconf.sig` added |
| 2021-09-23 | `bootmain` added as a separate section |
| 2024-04-17 | `cacert.der` added |
| 2025-02-11 | `qrcode.bin` removed |
| 2025-09-22 | all resources except the VL805 firmware LZ4-compressed |
| 2026-05-17 | `updatetime` added |
| 2026-09-23 | `versioninfo` added |

`tools/eeprom.py verify` passes on all of them.

## Open questions

- Whether the BCM2711 bootloader reads the `updatetime` section, which lies outside the first 64 KiB, or the last 8 bytes of the image.
