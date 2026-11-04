# Architecture

open27xx develops open boot firmware for Broadcom BCM27xx SoCs. The first
target is the BCM2711 on the Compute Module 4. File identities and source
versions are in [bcm2711/vendor-files.md](bcm2711/vendor-files.md).

## Boot chain

raspberrypi/usbboot `docs/secure-boot-chain-of-trust-2711.pdf`, page 1, at
commit `fdb604d018693465c9aa6ec69879df866d2820da` describes the secure-boot
chain below. It assigns signature verification to the ROM, embedded
resource-hash checks to bootsys and signed `boot.img` verification to
bootmain. This is the vendor's documented design. The per-stage documents
distinguish reproduced scalar checks from untested hardware trust policy
and complete boot behavior.

```mermaid
flowchart LR
  ROM["Boot ROM"] --> BS["bootsys"]
  BS --> BM["bootmain"]
  BM --> IMG["boot.img"]
  IMG --> S4["start.elf + fixup.dat"]
  S4 --> ARM["ARM kernel"]
```

The available file evidence covers these parts of that design:

| Component | Pinned-file observation | Details |
|---|---|---|
| bootsys | `pieeprom-2026-10-30.bin` payload at `0x000008` equals usbboot `2711/bootcode4.bin`; its `0xBBA8` field equals the decompressed bootmain SHA-256 | [bootsys.md](bcm2711/bootsys.md) |
| bootmain | `pieeprom-2026-10-30.bin` section at `0x00C918` decompresses to usbboot `2711/bootmain` | [eeprom.md](bcm2711/eeprom.md), [bootmain.md](bcm2711/bootmain.md) |
| SDRAM resources | `pieeprom-2026-10-30.bin` sections from `0x040518` through `0x059260` contain `memsys00.bin`–`memsys08.bin` and `mcb.bin` | [sdram.md](bcm2711/sdram.md) |
| `start4*.elf`, `fixup4*.dat` | files in raspberrypi/firmware `boot/` at commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`; whole-file identities cover bytes from `0x000000`; ELF fields are listed in start4.md | [start4.md](bcm2711/start4.md) |
| recovery | `recovery.bin` from the pinned rpi-eeprom commit has a 284-byte footer at `0x14666` | [usbboot.md](bcm2711/usbboot.md) |

The linked documents provide the SHA-256 identities, exact layouts and
unresolved behavior. Stored hashes, filenames and diagnostic text alone
do not prove control flow or acceptance of replacement firmware.

## Replacement plan

| Component | Deliverable | Verification |
|---|---|---|
| EEPROM image | list, extract, verify and rebuild with `tools/eeprom.py` | byte-identical round trip of every pinned image |
| `start4.elf` | VPU firmware built with vc4-toolchain | Linux boots on a Compute Module 4; mailbox replies match the reference firmware |
| bootmain | portable C library for configuration, boot-mode selection and file loading | equivalent results in emulation |
| bootsys, SDRAM | documentation of SDRAM initialization | register sequences and resource selection checked in emulation |

These are completion criteria. The host tool supports listing, extraction,
digest checks and rebuilding. The [VPU build](../src/start4/README.md)
produces a bring-up image and a separate ARM entry stub. ARM handoff, Linux
file loading and mailbox compatibility remain unimplemented.

## Verification

Compare formats byte for byte. Compare functions with identical inputs in
the Ghidra p-code emulator where instruction semantics are supported.
Compare boot behavior through UART output, mailbox replies and the boot
result on a Compute Module 4. Binary identity is not a requirement for
replacement firmware; observable behavior is.

All implementation follows the clean-room process in
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Code map

| Path | Contents |
|---|---|
| `docs/` | per-SoC documentation and references |
| `tools/` | host tools |
| `tests/` | synthetic unit tests and integration tests on pinned vendor files |
| `scripts/` | fetch and verify pinned vendor files |
| `src/start4/` | pinned VPU bring-up and separate ARM entry stub builds |

Firmware sources go to `src/`, one directory per stage. Vendor binaries,
extracted files and disassembly are excluded from the repository.

## Open questions

- Normal boot without secure boot. Establish the file-loading and
  validation paths in the pinned bootmain before claiming which
  replacement formats it accepts. The [ordinary ELF compatibility
  checks](bcm2711/elf-compatibility.md) cover supplied state before segment
  loading; connect them to storage completion and entry preparation in
  emulation.
- ARM handoff. Identify the entry address, memory layout and register state
  established by the pinned `start4.elf`; reproduce those observations in
  emulation before defining the replacement's handoff contract. The
  [control-request checks](bcm2711/arm-control.md) cover software decisions
  with supplied replies, not a complete hardware transition.
  The [resource-request contract](bcm2711/resource-request.md) specifies
  fixed logical-index dependencies and conditional software call outcomes.
  The [fixed resource composition](bcm2711/resource-composition.md) joins
  two clock requests and selected body operations under explicit state
  and readback premises; it does not establish a complete ARM launch.
  The [higher start composition](bcm2711/arm-start-composition.md) connects
  that route to 0x0EC5A81E with supplied successful gates and a record-0
  object binding; its active flag remains a software result.
  The [first clock composition](bcm2711/clock-composition.md) specifies
  the initialized request at 0x0ED55EFA in the pinned `start4.elf`, with
  actual source, native-word and divider bodies under finite supplied
  read plans. Initialization and physical completion remain unresolved.
