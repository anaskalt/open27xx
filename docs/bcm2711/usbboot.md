# USB boot and recovery.bin

raspberrypi/usbboot `Readme.md`, section "Compute Module 4", at commit
`fdb604d018693465c9aa6ec69879df866d2820da` documents the nRPIBOOT selection of
ROM USB boot. Its `recovery/README.md` describes `recovery.bin` as the
bootloader EEPROM update loader. These are documented hardware functions;
the byte checks below do not exercise them.

## recovery.bin

The file is `firmware-2711/default/recovery.bin` from raspberrypi/rpi-eeprom
commit `236b4406753e604fde3315cb521a2f843c9f8f85`: 83842 bytes, SHA-256
`d2496ef5dd106f250197f1cdf9fc2eecda90acdc0fc420a63b20940c06130ce1`.
`firmware-2711/latest/recovery.bin` at the same commit is byte-identical.
The commit identifies this sample; no build date is inferred from its name.

| File offset | Size (bytes) | Observation |
|---|---|---|
| 0x00000 | 512 | zero bytes |
| 0x00200 | 22 | equals `bootcode4.bin` at `0x0200`, identified in [bootsys.md](bootsys.md) |
| 0x14666 | 4 | little-endian body length: 83558 |
| 0x1466A | 4 | little-endian key index: 1 |
| 0x1466E | 256 | RSA signature field in the documented footer layout |
| 0x1476E | 20 | legacy checksum field in the documented footer layout |

The 284-byte footer follows the field layout cited in
[bootsys.md](bootsys.md). Equality of the 22 body bytes does not identify
shared UART, hashing or initialization functions.

## Host side

At the pinned usbboot commit, `recovery/bootcode4.bin` and
`secure-boot-recovery/bootcode4.bin` point to
`firmware/2711/recovery.bin`. That path points into the rpi-eeprom submodule.
[vendor-files.md](vendor-files.md) records the repository paths.

`recovery/update-pieeprom.sh` delegates to `tools/update-pieeprom.sh`.
The latter defaults to `pieeprom.original.bin` and `boot.conf` as inputs,
and produces `pieeprom.bin` and `pieeprom.sig`. This describes host file
preparation; it does not verify the device-side update sequence.

The Apache-2.0 source in usbboot `main.c` implements the rpiboot host.
Device-side request handling in the pinned `recovery.bin` needs separate
verification.

## Open questions

- USB request sequence. Identify the request handlers in the body at
  `0x00200`–`0x14665` and compare emulated requests with usbboot `main.c`.
- EEPROM update behavior. Trace the load, validation and write paths in
  the same body and test them against an emulated EEPROM. String presence
  or host-side filenames do not establish write order or failure behavior.
