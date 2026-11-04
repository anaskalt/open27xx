# bootmain

`bootmain` is an ELF resource in `pieeprom-2026-10-30.bin` from raspberrypi/rpi-eeprom commit `236b4406753e604fde3315cb521a2f843c9f8f85`. The image SHA-256 is `6abfaea480f93da47a790f89751ed45d3af6e88ee8fb337d4eb62ad125ca3e8a`. Its LZ4 section starts at image offset 0x00C918, has a 211955-byte payload and decompresses to 267042 bytes.

The decompressed file has SHA-256 `4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d`. All offsets below refer to that file. It matches `2711/bootmain` in usbboot's pinned `firmware/bootfiles.bin` byte for byte; the archive identity is in [vendor-files.md](vendor-files.md). The section header and compression layout are in [eeprom.md](eeprom.md).

## ELF file

Fields follow the [ELF header specification](https://gabi.xinuos.com/elf/02-eheader.html).

| Field | File offset | Value |
|---|---|---|
| Class and byte order | 0x04–0x05 | ELF32, little-endian |
| Object type | 0x10 | 2, executable |
| Machine | 0x12 | 137 |
| Entry point | 0x18 | 0x00080000 |
| Program header table | 0x1C, 0x2A–0x2D | 0x34; two entries of 32 bytes |
| Section header table | 0x20, 0x2E–0x31 | 0x040E9A; 29 entries of 40 bytes |
| Flags | 0x24 | 0x100 |
| Linker identification in `.comment` | 0x040D22 | `MetaWare Linker v5.6.19` |

Both [program headers](https://gabi.xinuos.com/elf/07-pheader.html) have type `PT_LOAD`. Their virtual and physical address fields are equal.

| Header offset | Contents offset | Address | File size (bytes) | Memory size (bytes) | Flags |
|---|---|---|---|---|---|
| 0x34 | 0x80 | 0x00080000 | 259624 | 259624 | read, write, execute |
| 0x54 | 0x03F6C0 | 0x000CB000 | 5730 | 53988 | read, write |

The `.text` section header at 0x040EEA specifies file offset 0x120, address 0x000800A0 and size 248672 bytes. The section header table contains no `SHT_SYMTAB`, `SHT_DYNSYM` or `SHT_DYNAMIC` entry. These are [ELF section types](https://gabi.xinuos.com/elf/03-sheader.html); their absence does not identify library functions or establish the calling convention.

## String locations

The following names occur in the decompressed file. Their presence locates data for further analysis; it does not establish which execution paths use it.

| String | File offset |
|---|---|
| `BOOT_ORDER` | 0x03D0C8 |
| `BOOT_UART` | 0x03CFAC |
| `PCIE_PROBE` | 0x03CFB8 |
| `SD_BOOT_MAX_RETRIES` | 0x03CEE0 |
| `USB_MSD_STARTUP_DELAY` | 0x03D020 |
| `NET_INSTALL_ENABLED` | 0x03CEF4 |
| `start4.elf` | 0x03D284 |
| `fixup4.dat` | 0x03D290 |
| `boot.img` | 0x03D418, 0x03D433 |
| `boot.sig` | 0x03D424, 0x03D43F |
| `ecdsa.c` | 0x01647B |
| `pkparse.c` | 0x026643 |
| `x509.c` | 0x01EB77 |
| `x509_crt.c` | 0x038FAF |

## Open questions

- Calling convention and register usage. Inspect function entry and return sequences and verify argument and result locations with scalar functions in emulation.
- Configuration parsing and boot-mode selection. Trace references to the configuration strings above and record inputs and outputs for the selected handlers in emulation.
- Firmware loading and validation. Trace references to the four file names above and document the selected files, memory destinations and validation results for each supported boot path.
- Cryptographic library and version. Follow references to the source-file names above and compare the identified behavior with public library APIs before assigning an implementation or version.
