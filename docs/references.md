# References

## Vendor documentation and tools

| Source | Content |
|---|---|
| [Raspberry Pi 4 Boot Security](https://pip.raspberrypi.com/categories/685-whitepapers-app-notes/documents/RP-004651-WP/Raspberry-Pi-4-Boot-Security.pdf) | secure boot on the BCM2711 |
| [Chain of trust, BCM2711](https://github.com/raspberrypi/usbboot/blob/fdb604d018693465c9aa6ec69879df866d2820da/docs/secure-boot-chain-of-trust-2711.pdf) | stage names, ROM keys, what each stage verifies |
| [usbboot `docs/secure-boot.md`](https://github.com/raspberrypi/usbboot/blob/fdb604d018693465c9aa6ec69879df866d2820da/docs/secure-boot.md) | secure-boot provisioning |
| [usbboot `Readme.md`](https://github.com/raspberrypi/usbboot/blob/fdb604d018693465c9aa6ec69879df866d2820da/Readme.md) | CM4 USB boot selection and host usage |
| [usbboot `recovery/README.md`](https://github.com/raspberrypi/usbboot/blob/fdb604d018693465c9aa6ec69879df866d2820da/recovery/README.md) | recovery loader workflow |
| [usbboot `tools/update-pieeprom.sh`](https://github.com/raspberrypi/usbboot/blob/fdb604d018693465c9aa6ec69879df866d2820da/tools/update-pieeprom.sh) | host EEPROM image preparation |
| [rpiboot `main.c`](https://github.com/raspberrypi/usbboot/blob/fdb604d018693465c9aa6ec69879df866d2820da/main.c) | host side of USB boot (Apache-2.0) |
| [`rpi-eeprom-config`](https://github.com/raspberrypi/rpi-eeprom/blob/236b4406753e604fde3315cb521a2f843c9f8f85/rpi-eeprom-config) | EEPROM sections, file slots, A/B layout (BSD-3-Clause) |
| [`rpi-eeprom-digest`](https://github.com/raspberrypi/rpi-eeprom/blob/236b4406753e604fde3315cb521a2f843c9f8f85/rpi-eeprom-digest) | `.sig` file format |
| [rpi-eeprom `LICENSE`](https://github.com/raspberrypi/rpi-eeprom/blob/236b4406753e604fde3315cb521a2f843c9f8f85/LICENSE) | script and firmware license terms |
| [usbboot `LICENSE.firmware`](https://github.com/raspberrypi/usbboot/blob/fdb604d018693465c9aa6ec69879df866d2820da/LICENSE.firmware) | boot archive firmware terms |
| [usbboot `firmware/bootfiles.bin`](https://github.com/raspberrypi/usbboot/blob/fdb604d018693465c9aa6ec69879df866d2820da/firmware/bootfiles.bin) | pinned archive containing `2711/bootmain`; [file identities](bcm2711/vendor-files.md) and [ordinary ELF compatibility checks](bcm2711/elf-compatibility.md) |
| [firmware `boot/LICENCE.broadcom`](https://github.com/raspberrypi/firmware/blob/ab5c7f86283ceb58b7adb269cae1d16092a31bf6/boot/LICENCE.broadcom) | start and fixup firmware terms |
| [firmware `boot/start4.elf`](https://github.com/raspberrypi/firmware/blob/ab5c7f86283ceb58b7adb269cae1d16092a31bf6/boot/start4.elf) | pinned VPU firmware for the [ARM control requests](bcm2711/arm-control.md), [stub metadata](bcm2711/arm-handoff.md), [boot-information](bcm2711/boot-information.md), [memory-capacity](bcm2711/memory-capacity.md) and [memory-bank serialization](bcm2711/memory-layout.md) contracts |
| [Release notes, BCM2711](https://github.com/raspberrypi/rpi-eeprom/blob/236b4406753e604fde3315cb521a2f843c9f8f85/firmware-2711/release-notes.md) | changes in every bootloader release |
| [Bootloader configuration](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#raspberry-pi-bootloader-configuration) | configuration keys |
| [Compute Module hardware](https://www.raspberrypi.com/documentation/computers/compute-module.html) | rpiboot and the bootloader on the Compute Module 4 |
| [raspberrypi/documentation `computers/config_txt/boot.adoc`](https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/computers/config_txt/boot.adoc) | `start_file`, `fixup_file` and firmware variants |
| [BCM2711 ARM Peripherals](https://datasheets.raspberrypi.org/bcm2711/bcm2711-peripherals.pdf) | release 4, build 2022-01-18 (`cfcff44-clean`); memory map, ARM-side peripherals and general-purpose clock password fields; [source identity](bcm2711/clocks.md#source-identities) |
| [Mailbox property interface](https://github.com/raspberrypi/firmware/wiki/Mailbox-property-interface) | firmware property tags |
| [raspberrypi/utils](https://github.com/raspberrypi/utils) | `vcmailbox`, raw mailbox requests from Linux |
| [armstubs](https://github.com/raspberrypi/tools/tree/master/armstubs) | ARM entry code (BSD-3-Clause) |
| [raspberrypi/userland](https://github.com/raspberrypi/userland) | VCOS and VCHIQ interfaces |

## Open-source projects

| Source | Content |
|---|---|
| [aleph-void/ghidra-videocore4 `README.md`](https://github.com/aleph-void/ghidra-videocore4/blob/db09a308c2db6a31ba5e060e6b763713f77e4f7b/README.md) | VideoCoreIV ghidra-rare-v1.0.0; ELF recognition and scalar/vector support |
| [aleph-void/ghidra-videocore4 `data/languages/vc4.cspec`](https://github.com/aleph-void/ghidra-videocore4/blob/db09a308c2db6a31ba5e060e6b763713f77e4f7b/data/languages/vc4.cspec) | compiler specification used for scalar calling-convention comparison |
| [librerpi/lk-overlay](https://github.com/librerpi/lk-overlay) | open VPU firmware, including the `rpi4-start4` project (GPL-2.0-or-later) |
| [lk-overlay `project/rpi4-start4.mk`](https://github.com/librerpi/lk-overlay/blob/50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c/project/rpi4-start4.mk), [`README.md`](https://github.com/librerpi/lk-overlay/blob/50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c/README.md) | pinned VPU project and license declaration |
| [lk-overlay `platform/bcm28xx/start4/start4.c`](https://github.com/librerpi/lk-overlay/blob/50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c/platform/bcm28xx/start4/start4.c), [`platform/bcm28xx/start.ld`](https://github.com/librerpi/lk-overlay/blob/50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c/platform/bcm28xx/start.ld) | open loader metadata and VPU link region |
| [lk-overlay `platform/bcm28xx/arm/arm.c`](https://github.com/librerpi/lk-overlay/blob/50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c/platform/bcm28xx/arm/arm.c), [`app/linux-bootloader/loader.c`](https://github.com/librerpi/lk-overlay/blob/50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c/app/linux-bootloader/loader.c), [`app/mailbox-property-server/server.c`](https://github.com/librerpi/lk-overlay/blob/50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c/app/mailbox-property-server/server.c) | earlier-board ARM loader and limited property server; BCM2711 implementation gaps |
| [librerpi/lk `LICENSE`](https://github.com/librerpi/lk/blob/2770b28104c15e52555a45143836c9c82945d740/LICENSE) | pinned LK core license; retain individual source notices |
| [lk-overlay `platform/bcm28xx/rules.mk`](https://github.com/librerpi/lk-overlay/blob/50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c/platform/bcm28xx/rules.mk), [LK `kernel/novm/novm.c`](https://github.com/librerpi/lk/blob/2770b28104c15e52555a45143836c9c82945d740/kernel/novm/novm.c) | allocator size defaults and calculation used by the VPU build |
| [raspberrypi/tools `armstubs/armstub8.S`](https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/armstub8.S), [`armstubs/Makefile`](https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/Makefile) | pinned BSD-3-Clause ARM entry stub and BCM2711/GIC build variant |
| [librerpi/rpi-tools `signing-tool/docs.txt`](https://github.com/librerpi/rpi-tools/blob/a700385d9b1c2f93d755d4455792ce7b08f90ede/signing-tool/docs.txt) | footer field layout |
| [christinaa/rpi-open-firmware](https://github.com/christinaa/rpi-open-firmware) | open bootcode for the VideoCore IV (BCM2835 to BCM2837) |
| [hermanhermitage/videocoreiv](https://github.com/hermanhermitage/videocoreiv) | VPU instruction set and memory map |
| [itszor/vc4-toolchain](https://github.com/itszor/vc4-toolchain) | binutils, GCC and newlib for the VPU |
| [vc4-toolchain `2f57f093`](https://github.com/itszor/vc4-toolchain/tree/2f57f093ef6bc77470152f00e98f38843e8fbbc3), [binutils-vc4 `708acc85`](https://github.com/puppeh/binutils-vc4/tree/708acc851880dbeda1dd18aca4fd0a95b2573b36), [gcc-vc4 `0fe4b838`](https://github.com/puppeh/gcc-vc4/tree/0fe4b83897341742f9df65797474cb0feab4b377), [newlib-vc4 `89abe4a5`](https://github.com/puppeh/newlib-vc4/tree/89abe4a5263d216e923fbbc80495743ff269a510), [resim `cdc7808c`](https://github.com/puppeh/resim/tree/cdc7808ceb7ba4ac00d0d08ca646b58615059150) | VPU compiler source pins for the start4 host build |
| [Linux `brcmstb_dpfe.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/memory/brcmstb_dpfe.c) | DPFE and DCPU of Broadcom set-top-box SoCs |
| [Linux `drivers/clk/bcm/clk-bcm2835.c`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c) | v6.12 PLLB register fields, channel operations and BCM2711 analog-control differences |
| [Linux `arch/arm/boot/dts/broadcom/bcm283x.dtsi`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm/boot/dts/broadcom/bcm283x.dtsi), [`bcm2711.dtsi`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm/boot/dts/broadcom/bcm2711.dtsi) | v6.12 CPRMAN register base and BCM2711 driver selection; [clock-register reference](bcm2711/clocks.md) |
| [Linux `raspberrypi-firmware.h`](https://github.com/torvalds/linux/blob/master/include/soc/bcm2835/raspberrypi-firmware.h) | mailbox property tags |
| [Mbed TLS](https://github.com/Mbed-TLS/mbedtls) | cryptographic library source and API reference |
| [Mbed TLS 2.28.10 `library/sha256.c`](https://github.com/Mbed-TLS/mbedtls/blob/2fc8413bfcb51354c8e679141b17b3f1a5942561/library/sha256.c) | SHA-224 and SHA-256 implementation used for comparison |
| [Mbed TLS 2.28.10 `library/rsa.c`](https://github.com/Mbed-TLS/mbedtls/blob/2fc8413bfcb51354c8e679141b17b3f1a5942561/library/rsa.c), [`include/mbedtls/rsa.h`](https://github.com/Mbed-TLS/mbedtls/blob/2fc8413bfcb51354c8e679141b17b3f1a5942561/include/mbedtls/rsa.h) | RSA API, control flow and error codes used for comparison |
| [LZ4 frame format](https://github.com/lz4/lz4/blob/dev/doc/lz4_Frame_format.md) | type 0x44 sections |

## File formats

| Source | Content |
|---|---|
| [System V ABI: ELF header](https://gabi.xinuos.com/elf/02-eheader.html) | ELF identity and header fields |
| [System V ABI: section header](https://gabi.xinuos.com/elf/03-sheader.html) | section offsets, types and flags |
| [System V ABI: program header](https://gabi.xinuos.com/elf/07-pheader.html) | loadable segments and memory sizes |

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
