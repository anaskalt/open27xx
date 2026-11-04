# start4.elf and fixup4.dat

The files below come from `boot/` in raspberrypi/firmware commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`. Sizes cover each complete file from offset 0x00; SHA-256 identifies the bytes used throughout this document.

| File | Size (bytes) | SHA-256 |
|---|---|---|
| `start4.elf` | 2303104 | `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb` |
| `start4x.elf` | 3050408 | `d4e146d37e34287845a3e391bde7ba5b3454f55d2adce0d918d17951e8ef0723` |
| `start4cd.elf` | 845820 | `425a48668f0290ed602de49e639a811ed5c2bc8fd8019e8924b94eda0782f41a` |
| `start4db.elf` | 3800296 | `3913b5cdb36562b5c5daf996c201599cfcdfbc89d139169b0b26ae75f73a74bb` |
| `fixup4.dat` | 5512 | `349d772e90351c4012d9b631f64ee9f0bc7587b44c8da97ef0d8994fabd0ea87` |
| `fixup4x.dat` | 8501 | `50f96c4a6e7e91316918360705dcb82428b4fdfeb2bbc981736918ae4ea778e7` |
| `fixup4cd.dat` | 3285 | `e9a32849bdd970240b2366f7ae6f8249d4af53284bf4e40092cb19d73f573632` |
| `fixup4db.dat` | 8501 | `ea83348db4390d81afcb4ea7e187223d3edbb8ce0860ff7a570086b50c5d88b8` |

raspberrypi/documentation, [`documentation/asciidoc/computers/config_txt/boot.adoc`](https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/computers/config_txt/boot.adoc), defines `start_file` as the VideoCore firmware file and `fixup_file` as its matching memory fixup file. It requires a matched pair and specifies `gpu_mem=16` to select cut-down firmware.

## ELF file

All offsets and addresses in this section refer to `start4.elf` identified above. Fields follow the [ELF header specification](https://gabi.xinuos.com/elf/02-eheader.html).

| Field | File offset | Value |
|---|---|---|
| Class and byte order | 0x04–0x05 | ELF32, little-endian |
| Object type | 0x10 | 2, executable |
| Machine | 0x12 | 137 |
| Entry point | 0x18 | 0xCEC00200 |
| Program header table | 0x1C, 0x2A–0x2D | 0x34; 21 entries of 32 bytes |
| Section header table | 0x20, 0x2E–0x31 | 0x231D50; 46 entries of 40 bytes |
| Flags | 0x24 | 0x100 |
| Linker identification in `.comment` | 0x231B98 | `MetaWare Linker v5.6.19` |

Selected [section headers](https://gabi.xinuos.com/elf/03-sheader.html):

| Section | Header offset | Contents offset | Address | Size (bytes) |
|---|---|---|---|---|
| `.crypto` | 0x232368 | 0x0007E0 | 0xCEC00200 | 6496 |
| `.secfns` | 0x232390 | 0x002140 | 0xCEC01B60 | 168 |
| `.isr_vectors` | 0x2323B8 | 0x0005E0 | 0xCEC01E00 | 512 |
| `.text` | 0x231D78 | 0x002200 | 0x0EC02800 | 1921028 |
| `.rdata` | 0x231E18 | 0x1D72A0 | 0x0EDD78C0 | 172608 |
| `.data` | 0x232200 | 0x205080 | 0x0EE05FE0 | 182415 |
| `.bss` | 0x2322C8 | none (`SHT_NOBITS`) | 0x0EE33A00 | 1011288 |

The entry point equals the start address of `.crypto`, whose section flags include `SHF_EXECINSTR`. The section header table contains no `SHT_SYMTAB`, `SHT_DYNSYM` or `SHT_DYNAMIC` entry.

## Build and runtime identifiers

These strings occur in `start4.elf` identified above:

| Identifier | File offset |
|---|---|
| `VC_BUILD_ID_VERSION` | 0x1A55C4 |
| `13c4219f16dbe58c5b9946086b474baf572512bb` | 0x1A55D9, 0x201284 |
| `bcm2711_2` | 0x1A5570, 0x201234 |
| `Nov  2 2026` | 0x1A554E, 0x1DA669, 0x201240 |
| `vcfw/rtos/threadx` | 0x1176A7 |
| `interface/vcos/threadx` | 0x1A44A3, 0x1A52B3 |
| `config.txt` | 0x05F7A8, 0x113A86, 0x1D7850 |

## Replacement target

The replacement must initialize UART and clocks, load the kernel, device tree and initramfs, start the Cortex-A72 cores through an armstub, and answer the mailbox property requests needed by Linux. Acceptance requires matching mailbox replies and a recorded boot to Linux userspace on the CM4.

## Open questions

- Address aliases and cache behavior. Establish how the 0x0EC00000 and 0xCEC00000 ranges map to memory by checking the VPU memory map and the loader's address handling.
- Fixup format. Compare the eight files identified above, match fixup entries to ELF section and segment addresses, and test each inferred operation against the loader in emulation.
- Runtime initialization. Trace references to the ThreadX, VCOS and `config.txt` strings before assigning scheduler behavior or a configuration-loading sequence to this build.
- Firmware handoff. Record the entry registers, memory layout and required bootloader state for this build through loader analysis and emulation before defining the replacement entry contract.
