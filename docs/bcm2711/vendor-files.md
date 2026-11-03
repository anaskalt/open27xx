# Vendor files

The BCM2711 firmware is published in three repositories. None of them contains source code for the VideoCore stages. `scripts/fetch-blobs.sh` downloads the files below at pinned commits into `blobs/`, and `scripts/blobs.sha256` lists their SHA-256 digests.

| Repository | Pinned commit | Relevant content | License of the firmware |
|---|---|---|---|
| raspberrypi/rpi-eeprom | 236b4406753e604fde3315cb521a2f843c9f8f85 | `firmware-2711/`: EEPROM images and `recovery.bin`; `rpi-eeprom-config`, `rpi-eeprom-digest`, `tools/` | custom, binary only; the scripts are BSD-3-Clause |
| raspberrypi/usbboot | fdb604d018693465c9aa6ec69879df866d2820da | `firmware/bootfiles.bin`, rpiboot, `docs/` | `LICENSE.firmware`, binary only; rpiboot is Apache-2.0 |
| raspberrypi/firmware | ab5c7f86283ceb58b7adb269cae1d16092a31bf6 | `boot/start4*.elf`, `boot/fixup4*.dat` | `boot/LICENCE.broadcom`, binary only |

The firmware licenses allow redistribution in binary form without modification, for use with Raspberry Pi devices. open27xx does not redistribute any of these files.

## Pinned files

Paths are relative to `blobs/bcm2711/`.

| File | Source | Size |
|---|---|---|
| `pieeprom-2026-10-30.bin` | rpi-eeprom `firmware-2711/default/` | 524288 |
| `recovery.bin` | rpi-eeprom `firmware-2711/default/` | 83842 |
| `bootfiles.bin` | usbboot `firmware/` | 1525760 |
| `bootfiles/2711/bootcode4.bin` | extracted from `bootfiles.bin` | 50930 |
| `bootfiles/2711/bootmain` | extracted from `bootfiles.bin` | 267042 |
| `start4.elf` | firmware `boot/` | 2303104 |
| `start4x.elf` | firmware `boot/` | 3050408 |
| `start4cd.elf` | firmware `boot/` | 845820 |
| `start4db.elf` | firmware `boot/` | 3800296 |
| `fixup4.dat` | firmware `boot/` | 5512 |
| `fixup4x.dat` | firmware `boot/` | 8501 |
| `fixup4cd.dat` | firmware `boot/` | 3285 |
| `fixup4db.dat` | firmware `boot/` | 8501 |

`bootfiles.bin` is a tar archive. Its `2711/` directory holds the EEPROM components uncompressed: `bootcode4.bin` equals EEPROM section 0, and `bootmain`, `memsys00.bin`–`memsys08.bin`, `mcb.bin`, `logo.bin` and `font.bin` equal the decompressed sections. The VL805 firmware is not included.

`scripts/fetch-blobs.sh --all` also copies every published BCM2711 image of the pinned rpi-eeprom commit to `blobs/bcm2711/history/`.

## Symlinks

- rpi-eeprom: `firmware-2711/beta` and `firmware-2711/stable` point to `latest/`, `firmware-2711/critical` to `default/`.
- usbboot: `firmware/2711/pieeprom.bin` and `firmware/2711/recovery.bin` point into the rpi-eeprom submodule (`latest/`). `recovery/bootcode4.bin` and `secure-boot-recovery/bootcode4.bin` point to `firmware/2711/recovery.bin`. `eeprom-erase/bootcode4.bin` points to `firmware/2711/bootcode4.bin`, which does not exist at the pinned commit.
