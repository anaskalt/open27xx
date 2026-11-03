# start4.elf and fixup4.dat

`start4.elf` is the VideoCore firmware of the BCM2711. bootmain loads it together with its fixup file from the boot partition. `start4.elf` reads `config.txt`, loads the device tree, the kernel and the initramfs, starts the Cortex-A72 cores through the armstub and serves the mailbox property interface to Linux.

## Variants

| File | Size | Use |
|---|---|---|
| `start4.elf` | 2303104 | standard |
| `start4x.elf` | 3050408 | extended, with codecs and camera support |
| `start4cd.elf` | 845820 | cut-down, selected by `gpu_mem=16` |
| `start4db.elf` | 3800296 | debug |

Each variant pairs with the `fixup4*.dat` of the same suffix (`start_file` and `fixup_file` in the `config.txt` documentation). Sizes are those of the pinned raspberrypi/firmware commit.

## ELF file

| Field | Value |
|---|---|
| Machine | 137, flags 0x100 |
| Entry point | 0xCEC00200, in `.crypto` |
| Symbols | none |
| Linker | MetaWare Linker v5.6.19 |
| Build | `VC_BUILD_ID_VERSION` 13c4219f16dbe58c5b9946086b474baf572512bb, branch `bcm2711_2`, 2 Nov 2026 |

The short hash 13c4219f also appears in the `versioninfo` section of `pieeprom-2026-10-30.bin`: the bootloader and the firmware are built from the same source tree.

| Section | Address | Size | Notes |
|---|---|---|---|
| `.crypto` | 0xCEC00200 | 0x1960 | executable, holds the entry point |
| `.secfns` | 0xCEC01B60 | 0xA8 | |
| `.isr_vectors` | 0xCEC01E00 | 0x200 | 128 vectors of 4 bytes |
| `.text` | 0x0EC02800 | 0x1D5004 | |
| `.rdata` | 0x0EDD78C0 | 0x2A240 | constants and strings |
| `.data` | 0x0EE05FE0 | 0x2C88F | |
| `.bss` | 0x0EE33A00 | 0xF6E58 | |

Other sections include `.init.vchiq_services`, `.init_mmal_ril_parameter_table`, `.init.vc_debug_sym`, `.text.bootloader_state`, `.text.firmware_rev`, `.drivers`, `.modules`, `.stack` and `.stack2`.

`start4db.elf` has the same sections and many more strings: 23922 strings of eight or more printable characters, against 9296 in `start4.elf`.

## Runtime

The firmware runs on ThreadX with the VCOS abstraction layer; source paths under `vcfw/rtos/threadx` and `interface/vcos/threadx` remain in the binary. The VCOS and VCHIQ interfaces are public in raspberrypi/userland. Linux lists the mailbox property tags in `include/soc/bcm2835/raspberrypi-firmware.h`.

## Replacement

Without secure boot bootmain loads `start4.elf` without verification, so a replacement runs on unmodified hardware. The replacement starts from the `rpi4-start4` project of librerpi/lk-overlay (GPL-2.0-or-later), open VPU firmware for this SoC. It has to:

- bring up the UART and the clocks;
- load the kernel, the device tree and the initramfs, and start the Cortex-A72 cores through the armstub;
- answer the mailbox property tags that Linux uses with the same values as the vendor firmware.

## Open questions

- The two address ranges. 0x0Exxxxxx and 0xCExxxxxx are probably two VPU aliases of the same memory with different cache behavior; the legacy bus view in the BCM2711 peripherals datasheet shows such aliases.
- The format of `fixup4.dat`. The documentation of the boot folder describes the fixup files as linker files that pair with the `start*.elf` files. Comparing `fixup4.dat` with `fixup4x.dat` against the section addresses of the two ELF files should show the structure.
