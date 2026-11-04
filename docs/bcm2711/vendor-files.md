# Vendor files

The firmware inputs come from these pinned repositories. The commits are
the source versions for every file and repository path listed below.

| Repository | Pinned commit | Source paths | License files |
|---|---|---|---|
| raspberrypi/rpi-eeprom | `236b4406753e604fde3315cb521a2f843c9f8f85` | `firmware-2711/`, `rpi-eeprom-config` | `LICENSE`: custom firmware terms; BSD-3-Clause scripts |
| raspberrypi/usbboot | `fdb604d018693465c9aa6ec69879df866d2820da` | `firmware/bootfiles.bin`, `main.c`, `docs/` | `LICENSE.firmware`; `LICENSE` for Apache-2.0 host code |
| raspberrypi/firmware | `ab5c7f86283ceb58b7adb269cae1d16092a31bf6` | `boot/start4*.elf`, `boot/fixup4*.dat` | `boot/LICENCE.broadcom` |

The firmware terms permit binary redistribution without modification,
subject to device-use and notice conditions. The exact license files are
linked in [references.md](../references.md). open27xx does not redistribute
the firmware inputs.

## Pinned files

`scripts/fetch-blobs.sh` downloads into `blobs/` and checks
`scripts/blobs.sha256`. Local paths below are relative to `blobs/bcm2711/`.
Sizes cover the complete file starting at offset `0x000000` and are in bytes.

| File | Upstream source | Size (bytes) | SHA-256 |
|---|---|---|---|
| `pieeprom-2026-10-30.bin` | rpi-eeprom `firmware-2711/default/` | 524288 | `6abfaea480f93da47a790f89751ed45d3af6e88ee8fb337d4eb62ad125ca3e8a` |
| `recovery.bin` | rpi-eeprom `firmware-2711/default/` | 83842 | `d2496ef5dd106f250197f1cdf9fc2eecda90acdc0fc420a63b20940c06130ce1` |
| `bootfiles.bin` | usbboot `firmware/` | 1525760 | `c51ef4d816bc2968ca5eef215ca58ce8e2cd4d68d75eae58b4d450f1b5d3d2a6` |
| `bootfiles/2711/bootcode4.bin` | usbboot tar member `2711/bootcode4.bin` | 50930 | `9e1b0b7df904a7fdc22e263d530c6e4c48921229631dd7ea2325271843996f6c` |
| `bootfiles/2711/bootmain` | usbboot tar member `2711/bootmain` | 267042 | `4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d` |
| `start4.elf` | firmware `boot/` | 2303104 | `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb` |
| `start4x.elf` | firmware `boot/` | 3050408 | `d4e146d37e34287845a3e391bde7ba5b3454f55d2adce0d918d17951e8ef0723` |
| `start4cd.elf` | firmware `boot/` | 845820 | `425a48668f0290ed602de49e639a811ed5c2bc8fd8019e8924b94eda0782f41a` |
| `start4db.elf` | firmware `boot/` | 3800296 | `3913b5cdb36562b5c5daf996c201599cfcdfbc89d139169b0b26ae75f73a74bb` |
| `fixup4.dat` | firmware `boot/` | 5512 | `349d772e90351c4012d9b631f64ee9f0bc7587b44c8da97ef0d8994fabd0ea87` |
| `fixup4x.dat` | firmware `boot/` | 8501 | `50f96c4a6e7e91316918360705dcb82428b4fdfeb2bbc981736918ae4ea778e7` |
| `fixup4cd.dat` | firmware `boot/` | 3285 | `e9a32849bdd970240b2366f7ae6f8249d4af53284bf4e40092cb19d73f573632` |
| `fixup4db.dat` | firmware `boot/` | 8501 | `ea83348db4390d81afcb4ea7e187223d3edbb8ce0860ff7a570086b50c5d88b8` |

## Archive members

`bootfiles.bin` is a tar archive. At the offsets below, the `2711/` members
equal the decoded sections of `pieeprom-2026-10-30.bin`. For
`bootcode4.bin`, the comparison uses the uncompressed section payload at
EEPROM offset `0x000008`. For the other members, it uses the decompressed
contents after removing the name and digest fields. The section offsets
are listed in [eeprom.md](eeprom.md).

| Member | Data offset in `bootfiles.bin` | Size (bytes) |
|---|---|---|
| `2711/memsys06.bin` | 0x400 | 20492 |
| `2711/mcb.bin` | 0x5800 | 12384 |
| `2711/memsys01.bin` | 0x8C00 | 20492 |
| `2711/memsys08.bin` | 0xE000 | 20492 |
| `2711/font.bin` | 0x13400 | 27404 |
| `2711/memsys00.bin` | 0x1A200 | 20492 |
| `2711/memsys07.bin` | 0x1F600 | 20492 |
| `2711/memsys04.bin` | 0x24A00 | 20492 |
| `2711/memsys03.bin` | 0x29E00 | 20492 |
| `2711/bootmain` | 0x2F200 | 267042 |
| `2711/logo.bin` | 0x70800 | 12844 |
| `2711/memsys02.bin` | 0x73E00 | 20492 |
| `2711/memsys05.bin` | 0x79200 | 20492 |
| `2711/bootcode4.bin` | 0x7E600 | 50930 |

## Image catalog

`scripts/fetch-blobs.sh --all` copies the BCM2711 EEPROM images from the
pinned rpi-eeprom `firmware-2711/` tree into `blobs/bcm2711/history/`.
There are 120 distinct filenames, from `pieeprom-2019-07-15.bin` through
`pieeprom-2026-10-30.bin`. A filename count is not a unique-content count:
`pieeprom-2020-09-02.bin` and `pieeprom-2020-09-03.bin` have the same complete
file SHA-256, `87efba8547f725a799e1e6ed66f1e801b5e41533cbf837daeff91e1aa653ec18`.

## Repository symlinks

These are repository metadata at the pinned commits, not runtime paths
inside firmware.

| Repository | Path | Target |
|---|---|---|
| rpi-eeprom | `firmware-2711/beta` | `latest/` |
| rpi-eeprom | `firmware-2711/stable` | `latest/` |
| rpi-eeprom | `firmware-2711/critical` | `default/` |
| usbboot | `firmware/2711/pieeprom.bin` | `../../rpi-eeprom/firmware-2711/latest/pieeprom-2026-10-30.bin` |
| usbboot | `firmware/2711/recovery.bin` | `../../rpi-eeprom/firmware-2711/latest/recovery.bin` |
| usbboot | `recovery/bootcode4.bin` | `../firmware/2711/recovery.bin` |
| usbboot | `secure-boot-recovery/bootcode4.bin` | `../firmware/2711/recovery.bin` |
| usbboot | `eeprom-erase/bootcode4.bin` | `../firmware/2711/bootcode4.bin` |
