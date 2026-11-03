# SDRAM initialization

bootsys initializes SDRAM with two kinds of resource from the EEPROM image, `memsys00.bin`–`memsys08.bin` and `mcb.bin`, and checks each one against its digest table before use ([bootsys.md](bootsys.md)).

## memsys00.bin–memsys08.bin

Nine files of 20492 bytes each in `pieeprom-2026-10-30.bin`. They are stored as big-endian 32-bit words: text becomes readable after reversing the byte order of every word. The text includes a firmware name and version, `DPFE FW hph1_lpddr4` and `2.35.0.0`, messages about LPDDR4 and LPDDR4X byte mode, ZQ calibration and mode-register writes, and an exception handler message.

DPFE is the name of the DDR PHY front end in Broadcom set-top-box SoCs, where the firmware runs on a separate processor in the PHY, the DCPU. The Linux driver `drivers/memory/brcmstb_dpfe.c` states that the DCPU always runs big-endian and describes its mailbox to the host. The firmware image headers that the driver recognizes, 0xFE0101FE and 0xFE1010FE, do not occur in these files.

## mcb.bin

12384 bytes in `pieeprom-2026-10-30.bin`, 45.6 % of them zero. The file has grown in steps from 3836 bytes in `pieeprom-2019-09-06.bin`. bootsys reports the MCB that it selects together with the memsys configuration.

## Open questions

- How density, rank count, part configuration and on-die termination map to the nine memsys files and to entries in `mcb.bin`.
- The instruction set of the DCPU.
- The register sequence that loads the PHY firmware and starts training.
