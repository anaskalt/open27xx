#!/bin/sh
# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Fetch the vendor firmware used for analysis and tests into blobs/.
# The files come from the upstream repositories at pinned commits and are
# checked against scripts/blobs.sha256. They are not part of this repository.
#
# Usage: fetch-blobs.sh [--all]
#   --all  also copy every published BCM2711 EEPROM image to
#          blobs/bcm2711/history/

set -eu

case ${1:-} in
  "") all=0 ;;
  --all) all=1 ;;
  *) echo "usage: $0 [--all]" >&2; exit 2 ;;
esac

root=$(cd "$(dirname "$0")/.." && pwd)
dst=$root/blobs/bcm2711
cache=$root/blobs/.cache

# Upstream commits, pinned on 2026-11-03.
rpi_eeprom=236b4406753e604fde3315cb521a2f843c9f8f85
usbboot=fdb604d018693465c9aa6ec69879df866d2820da
firmware=ab5c7f86283ceb58b7adb269cae1d16092a31bf6

fetch() { # repository commit
  dir=$cache/$1
  if [ ! -d "$dir/.git" ]; then
    git init -q "$dir"
    git -C "$dir" remote add origin "https://github.com/raspberrypi/$1.git"
  fi
  git -C "$dir" fetch -q --depth 1 --filter=blob:none origin "$2"
}

get() { # repository commit path
  git -C "$cache/$1" show "$2:$3" > "$dst/$(basename "$3")"
}

mkdir -p "$dst" "$cache"
fetch rpi-eeprom "$rpi_eeprom"
fetch usbboot "$usbboot"
fetch firmware "$firmware"

get rpi-eeprom "$rpi_eeprom" firmware-2711/default/pieeprom-2026-10-30.bin
get rpi-eeprom "$rpi_eeprom" firmware-2711/default/recovery.bin
get usbboot "$usbboot" firmware/bootfiles.bin
for f in start4.elf start4x.elf start4cd.elf start4db.elf \
  fixup4.dat fixup4x.dat fixup4cd.dat fixup4db.dat; do
  get firmware "$firmware" "boot/$f"
done

# bootfiles.bin is a tar archive of the uncompressed EEPROM components.
rm -rf "$dst/bootfiles"
mkdir "$dst/bootfiles"
tar -xf "$dst/bootfiles.bin" --no-same-owner -C "$dst/bootfiles" 2711

"$root/scripts/verify-blobs.sh"

if [ "$all" = 1 ]; then
  repo=$cache/rpi-eeprom
  git -C "$repo" sparse-checkout set --no-cone '/firmware-2711/**/pieeprom-*.bin'
  git -C "$repo" checkout -q --detach "$rpi_eeprom"
  rm -rf "$dst/history"
  mkdir "$dst/history"
  find "$repo/firmware-2711" -type f -name 'pieeprom-*.bin' \
    -exec cp {} "$dst/history/" \;
  echo "blobs: $(find "$dst/history" -type f | wc -l | tr -d ' ') images in blobs/bcm2711/history"
fi
