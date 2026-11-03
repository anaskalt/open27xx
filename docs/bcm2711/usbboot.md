# USB boot and recovery.bin

When nRPIBOOT is held low, the Compute Module 4 boot ROM enters USB device mode. The host tool rpiboot from usbboot then sends a loader that carries the same signature footer as bootsys. For bootloader updates that loader is `recovery.bin`.

## recovery.bin

- 83842 bytes of raw VPU code with the bootsys footer: 83558 signed bytes, key index 1 ([bootsys.md](bootsys.md)).
- `firmware-2711/default/recovery.bin` and `firmware-2711/latest/recovery.bin` in rpi-eeprom are the same file. usbboot reaches it through symlinks as `recovery/bootcode4.bin` and `secure-boot-recovery/bootcode4.bin`.
- Like bootsys it starts with 0x200 zero bytes, and its first 22 bytes of code at 0x200 match those of bootsys. Comparing the two locates shared code: start-up, UART and SHA-256.
- Its log messages cover an SD host driver; reading, erasing, writing and verifying the bootloader EEPROM and the VL805 EEPROM; EEPROM write protection; and a check of the RSA key stored in the EEPROM.

## Update flow

`recovery/update-pieeprom.sh` in usbboot builds `pieeprom.bin` from `pieeprom.original.bin` and `boot.conf`. `rpiboot -d recovery` sends `recovery.bin` as `bootcode4.bin`; `recovery.bin` then requests `pieeprom.bin` over USB and writes it to the SPI EEPROM. On a Raspberry Pi 4 Model B the same file runs from an SD card to update the bootloader.

## Host side

`main.c` in usbboot (Apache-2.0) implements the host side of the USB protocol and documents the requests that `recovery.bin` and bootmain send in USB device mode.
