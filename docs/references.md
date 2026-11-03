# References

## Vendor documentation and tools

| Source | Content |
|---|---|
| [Raspberry Pi 4 Boot Security](https://pip.raspberrypi.com/categories/685-whitepapers-app-notes/documents/RP-004651-WP/Raspberry-Pi-4-Boot-Security.pdf) | secure boot on the BCM2711 |
| [Chain of trust, BCM2711](https://github.com/raspberrypi/usbboot/blob/master/docs/secure-boot-chain-of-trust-2711.pdf) | stage names, ROM keys, what each stage verifies |
| [usbboot `docs/secure-boot.md`](https://github.com/raspberrypi/usbboot/blob/master/docs/secure-boot.md) | secure-boot provisioning |
| [rpiboot `main.c`](https://github.com/raspberrypi/usbboot/blob/master/main.c) | host side of USB boot (Apache-2.0) |
| [`rpi-eeprom-config`](https://github.com/raspberrypi/rpi-eeprom/blob/master/rpi-eeprom-config) | EEPROM sections, file slots, A/B layout (BSD-3-Clause) |
| [`rpi-eeprom-digest`](https://github.com/raspberrypi/rpi-eeprom/blob/master/rpi-eeprom-digest) | `.sig` file format |
| [rpi-eeprom `tools/`](https://github.com/raspberrypi/rpi-eeprom/tree/master/tools) | public key conversion, bootcode signing |
| [Release notes, BCM2711](https://github.com/raspberrypi/rpi-eeprom/blob/master/firmware-2711/release-notes.md) | changes in every bootloader release |
| [Bootloader configuration](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#raspberry-pi-bootloader-configuration) | configuration keys |
| [Compute Module hardware](https://www.raspberrypi.com/documentation/computers/compute-module.html) | rpiboot and the bootloader on the Compute Module 4 |
| [`config.txt`: `start_file`, `fixup_file`](https://www.raspberrypi.com/documentation/computers/config_txt.html#start_file-fixup_file) | firmware variants |
| [BCM2711 ARM Peripherals](https://datasheets.raspberrypi.com/bcm2711/bcm2711-peripherals.pdf) | memory map and ARM-side peripherals |
| [Mailbox property interface](https://github.com/raspberrypi/firmware/wiki/Mailbox-property-interface) | firmware property tags |
| [raspberrypi/utils](https://github.com/raspberrypi/utils) | `vcmailbox`, raw mailbox requests from Linux |
| [armstubs](https://github.com/raspberrypi/tools/tree/master/armstubs) | ARM entry code (BSD-3-Clause) |
| [raspberrypi/userland](https://github.com/raspberrypi/userland) | VCOS and VCHIQ interfaces |

## Open-source projects

| Source | Content |
|---|---|
| [aleph-void/ghidra-videocore4](https://github.com/aleph-void/ghidra-videocore4) | Ghidra processor module for the VideoCore IV VPU |
| [librerpi/lk-overlay](https://github.com/librerpi/lk-overlay) | open VPU firmware, including the `rpi4-start4` project (GPL-2.0-or-later) |
| [librerpi/rpi-tools](https://github.com/librerpi/rpi-tools) | `signing-tool/docs.txt` (footer layout), `eeprom-v2` (section types) |
| [christinaa/rpi-open-firmware](https://github.com/christinaa/rpi-open-firmware) | open bootcode for the VideoCore IV (BCM2835 to BCM2837) |
| [hermanhermitage/videocoreiv](https://github.com/hermanhermitage/videocoreiv) | VPU instruction set and memory map |
| [itszor/vc4-toolchain](https://github.com/itszor/vc4-toolchain) | binutils, GCC and newlib for the VPU |
| [Linux `brcmstb_dpfe.c`](https://github.com/torvalds/linux/blob/master/drivers/memory/brcmstb_dpfe.c) | DPFE and DCPU of Broadcom set-top-box SoCs |
| [Linux `raspberrypi-firmware.h`](https://github.com/torvalds/linux/blob/master/include/soc/bcm2835/raspberrypi-firmware.h) | mailbox property tags |
| [Mbed TLS](https://github.com/Mbed-TLS/mbedtls) | cryptographic library used by bootmain |
| [LZ4 frame format](https://github.com/lz4/lz4/blob/dev/doc/lz4_Frame_format.md) | type 0x44 sections |

## Research

| Source | Content |
|---|---|
| [jonatron: pivolt](https://jonatron.github.io/randomstuff/pivolt/) | analysis of the BCM2712 bootmain with Ghidra |
| [cmdly/openVC02](https://gitlab.com/cmdly/openVC02) | emulation and scripted analysis of VideoCore II (BCM2722) firmware |
| [info-beamer/rpi-eeprom-tools](https://github.com/info-beamer/rpi-eeprom-tools) | independent EEPROM image tools; no license |
| [Petr Tesarik: Raspberry Pi 4 boot sequence](https://hackaday.io/page/6372-raspberry-pi-4-boot-sequence) | boot ROM behavior, OTP rows |
| [raspberrypi/firmware#1169](https://github.com/raspberrypi/firmware/issues/1169) | OTP rows on the Raspberry Pi 4 |

## Naming

| Source | Content |
|---|---|
| [Raspberry Pi trademark rules](https://www.raspberrypi.com/trademark-rules/) | use of the Raspberry Pi name |
