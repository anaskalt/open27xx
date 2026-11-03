# bootmain

bootmain is the main bootloader stage. It reads the boot configuration, runs the boot modes and loads the VideoCore firmware.

bootmain is a compressed section of the EEPROM image: a separate section since 2021-09-23, LZSS-compressed until 2025-08-27 and LZ4-compressed since 2025-09-22. In `pieeprom-2026-10-30.bin` it is a 211955-byte section at 0x00C918 that decompresses to 267042 bytes. `bootfiles.bin` in usbboot carries the uncompressed file as `2711/bootmain`.

## ELF file

| Field | Value |
|---|---|
| Class | ELF32, little-endian |
| Machine | 137 (`readelf`: Broadcom VideoCore III processor) |
| Flags | 0x100 |
| Entry point | 0x00080000 |
| First segment | 0x00080000, 0x3F628 bytes, read, write and execute |
| Second segment | 0x000CB000, 0x1662 bytes in the file, 0xD2E4 in memory, read and write |
| Sections | 29; `.text` at 0x000800A0, 0x3CB60 bytes |
| Symbols | none |
| Linker | MetaWare Linker v5.6.19, from `.comment` |

The first segment holds `.crt`, `.text`, `.init`, `.fini`, `.initdat`, `.drivers`, `.rev`, `.rdata` and `.rsdata`. The second holds `.sdata`, `.sbss`, `.data_guarded`, `.data`, `.tls`, `.bss`, `.heap` and `.stack`.

The MetaWare toolchain is not the GNU toolchain for the VPU, so function prologues and the calling convention may differ from those of GCC builds.

## Function

- Configuration: the documented bootloader configuration keys, such as `BOOT_ORDER`, `BOOT_UART`, `PCIE_PROBE`, `SD_BOOT_MAX_RETRIES`, `USB_MSD_STARTUP_DELAY` and `NET_INSTALL_ENABLED`, appear as strings.
- Boot modes: SD and eMMC, USB mass storage, NVMe, network boot over TFTP and HTTP, and USB device boot with rpiboot. A log line reports the boot mode, partition, build timestamp, serial number and board revision.
- Secure boot: when it is enabled, bootmain loads `boot.img`, a FAT ramdisk, and verifies it against `boot.sig` with the customer key (chain-of-trust diagram). Otherwise it loads `start4.elf` and `fixup4.dat` from the boot partition.
- Cryptography: Mbed TLS, recognizable from source paths for `ecdsa.c`, `pkparse.c`, `x509.c` and `x509_crt.c`.
- Memory test: its log messages report the failing address with the expected and the read value.

`firmware-2711/release-notes.md` in rpi-eeprom lists the changes in every release. Comparing two consecutive images locates the code of a change.

## Open questions

- Calling convention and register usage of the MetaWare toolchain.
