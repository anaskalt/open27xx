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

## Loading by bootmain

The loader behavior in this section belongs to `bootmain` from raspberrypi/usbboot commit `fdb604d018693465c9aa6ec69879df866d2820da`, SHA-256 `4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d`. Loader addresses are ELF virtual addresses in that file. The [firmware selection and file requests](bootmain.md#firmware-and-fixup-selection) precede these operations.

The completion path at 0x00086754 validates the image with 0x0008E2A2, looks up `.text.firmware_rev` and `.text.bootloader_state` through 0x0008E19C, processes an available fixup and validates the result again. It then calls 0x0008E1EA to place segments in memory. [elf-section.json](../../tests/vectors/bootmain/elf-section.json) records successful and missing section-name lookups using a synthetic section table.

The [ELF compatibility contract](elf-compatibility.md) describes the feature
word checks between metadata lookup and segment loading. Its 35 synthetic
cases cover ordinary-path decisions with supplied state. Six additional
open-image observations stop at rejection or before the segment-loader
call; they do not establish earlier security acceptance or complete boot.

The [boot-information contract](boot-information.md) describes the state-pointer
store in `.text.bootloader_state` and the supplied-record parser in `start4.elf`.
Its vectors cover copy bounds, cached records and allocation zeroing. Record
production and complete platform initialization remain outside that contract.

In `start4.elf` identified above, the
[original-table startup initializer](startup-initialization.md) clears three
complete ELF allocations through two recorded calls at 0x0EC3D740.
The calls retain the original table and addresses; actual startup arrival,
later state lifetime and other table paths remain outside that result.
The [conditional startup route](startup-arrival.md) binds the selected
`start4.elf` entry, service continuation and predecessor hook without
claiming a complete execution of that route.

### Header checks

In the identified `bootmain`, 0x0008E2A2 takes the image pointer in `r0` and byte length in `r1`. It returns zero for the accepted header and 0xFFFFFFFF for a rejected header. [elf-header.json](../../tests/vectors/bootmain/elf-header.json) records ten cases.

| Field or condition | Required value |
|---|---|
| Image pointer alignment | Multiple of 4 bytes |
| `EI_CLASS` at 0x04 | 1, ELF32 |
| `EI_DATA` at 0x05 | 1, little-endian |
| `e_type` at 0x10 | 2 |
| `e_machine` at 0x12 | 137 |
| `e_phnum` at 0x2C | Nonzero |
| Program-header table extent | No later than image end |
| Section-header table extent | No later than image end |

The helper uses the entry sizes stored in the header for those extent calculations. It does not check the ELF magic in the first four bytes; the `elf-header-magic-unchecked` case retains a zero result after those bytes change. These are the checks of this helper, not a complete ELF validity contract.

### Segment placement

In the identified `bootmain`, 0x0008E1EA takes the image in `r0` and an entry-output pointer in `r2`. For each nonzero program-header type, it forms the destination from `p_vaddr | 0xC0000000`, copies `p_filesz` bytes from the image's `p_offset`, then clears the remaining bytes when `p_memsz` exceeds `p_filesz`. A zero program-header type is skipped. On success it writes `e_entry` to the output pointer and returns zero.

[elf-segments.json](../../tests/vectors/bootmain/elf-segments.json) executes the actual copy and clear routines for five synthetic images. The cases cover a copied segment with a zero-filled tail, a zero-only segment, a skipped type-zero header, a nonzero type other than `PT_LOAD`, and two segments. Destination 0xE4008000 is explicitly initialized emulator memory; the fixtures do not model hardware cache aliases.

The `start4.elf` file identified at the top of this document has `.text` address 0x0EC02800 and entry 0xCEC00200. The loader's OR operation places the former at 0xCEC02800. The scalar fixtures establish address formation and data placement; they do not execute the firmware entry or cache maintenance.

## Fixup stream

In the identified `bootmain`, 0x00081294 checks fixup endpoints and 0x000811C6 applies the fixups. Both receive the firmware start, firmware end and fixup-stream pointers in `r0`, `r1` and `r2`. Application additionally receives a pointer to two 32-bit adjustments in `r3`.

A stream contains two consecutive lists. Each list starts with a position two bytes before the firmware image. A record advances that position and selects the operation below. Multi-byte deltas use little-endian byte order.

| First byte | Following bytes | Position increment | Operation before the endpoint |
|---|---|---|---|
| 0x02–0xFF | none | Twice the first byte minus two | Add the list adjustment |
| 0x01 | 24-bit unsigned delta | Twice the delta | Add the list adjustment |
| 0x00 | 24-bit unsigned delta | Twice the delta | Subtract the list adjustment |

A position equal to the firmware end terminates the current list without modifying a word. The validator returns zero if a position passes the end and one after both lists terminate exactly at the end. Application reads the selected 16-bit word, adds or subtracts the selected adjustment and writes the low 16 bits. The position resets before the second list; it uses the second adjustment.

[fixup-validate.json](../../tests/vectors/bootmain/fixup-validate.json) records empty lists, short and extended deltas, a subtract marker and an overshoot. [fixup-apply.json](../../tests/vectors/bootmain/fixup-apply.json) records positive, negative and wrapping 16-bit updates. The functions have no fixup-stream length argument; each fixture explicitly supplies every byte read.

The caller at 0x00086754 keeps memory-size fields in units of 1048576 bytes. The first adjustment is 16 times the difference between the final and reference total-size fields; the second uses the final and reference ARM-size fields. The standard pair uses reference sizes of 268435456 bytes total and 134217728 bytes ARM; the cut-down pair uses 268435456 bytes total and 251658240 bytes ARM. The caller applies a supplied fixup only when the final sizes are no smaller than the corresponding references.

For the four pairs from raspberrypi/firmware commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, identified by SHA-256 above, decoding from fixup-file offset 0x00 consumes the complete file and both lists terminate at the paired ELF size:

| Fixup file | First-list patches | Second-list patches | Firmware endpoint (bytes) |
|---|---|---|---|
| `fixup4.dat` | 5282 | 3 | 2303104 |
| `fixup4x.dat` | 8199 | 3 | 3050408 |
| `fixup4cd.dat` | 3139 | 3 | 845820 |
| `fixup4db.dat` | 8199 | 3 | 3800296 |

Each first list contains six subtract operations. The second lists contain only add operations. These counts describe the pinned files; they are not constants of the stream format.

The [lower-span contract](memory-span.md) identifies the standard pair's
fixup intersections with two bound fields. Their difference retains the
ARM-size adjustment while the common total adjustment cancels. Separate
synthetic slices record the explicit byte-argument transfers toward the
memory-bank serializer; complete startup and usable RAM remain unverified.

## Replacement file selection

The following contract covers `bootmain` from raspberrypi/usbboot commit `fdb604d018693465c9aa6ec69879df866d2820da`, SHA-256 `4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d`. It establishes filename selection and the zero-length fixup path, without executing the complete firmware acceptance or handoff sequence.

The case-sensitive configuration keys `fixup_file` and `start_file` have table entries at 0x000CC1F0 and 0x000CC1FC. Both string destinations have capacity 256 bytes. Selector 0x000AD57A copies nonempty overrides into separate filename buffers, limits the copy to 255 bytes and writes a terminating NUL.

[loader-overrides.json](../../tests/vectors/bootmain/loader-overrides.json) records two selector cases. Both select `open27xx.elf` from `start_file`. An empty `fixup_file` leaves the standard `fixup4.dat` descriptor at 0x000CBE40 selected. A nonempty `fixup_file=open27xx-none.dat` selects the override descriptor at 0x000CBF50. An empty value therefore does not disable the default fixup request. The explicit-name case establishes only which name is requested; it does not establish whether that file exists on a boot partition.

Three more cases execute fixup completion handler 0x000857A8 for event 0x17:

| Request status | Device timeout result | Observed continuation |
|---|---|---|
| 0 | Not queried | Calls firmware finalizer 0x00086754 |
| 4 | 0 | Reports the missing/empty file and calls the finalizer |
| 4 | 1 | Advances the boot path without calling the finalizer |

The request status and device timeout result are synthetic inputs. The finalizer and next-path calls are recorded boundaries. These cases establish callback decisions, not filesystem or device behavior.

Inside finalizer 0x00086754, the fragment at 0x000869C2 reads the fixup buffer length at context offset 0xD4. The sixth case supplies zero length and reaches 0x00086A6C in two instructions, without reading a fixup pointer or modifying the image. That destination begins the post-fixup ELF validation path. This fragment starts after earlier compatibility checks and stops before later validation and loading.

A replacement that needs no memory fixup must therefore avoid selecting a nonempty vendor fixup payload. The recorded cases support an explicit filename override and the zero-length continuation, while leaving complete ELF acceptance, signature policy and entry execution unproven.

## Replacement target

The replacement must initialize UART and clocks, load the kernel, device tree and initramfs, start the Cortex-A72 cores through an armstub, and answer the mailbox property requests needed by Linux. Acceptance requires matching mailbox replies and a recorded boot to Linux userspace on the CM4.

The [BCM2711 clock-register reference](clocks.md) lists PLLB addresses,
fields and applicability from pinned public sources. It leaves initial
clock state and a complete ARM release sequence unresolved.

The [memory-capacity calculation](memory-capacity.md) derives a MiB count
and a separate class from supplied service bytes. Physical banks and
reserved ranges remain prerequisites for payload placement.

The [memory-bank serialization contract](memory-layout.md) covers candidate
memory-property bytes and bounded descriptor stores. It does not establish
physical ownership or complete device-tree mutation.

The [host build](../../src/start4/README.md) provides a pinned unsigned VPU
bring-up image and a separate BCM2711 ARM entry stub. It does not yet
implement the ARM release, Linux file-loading or mailbox paths. A
successful host build does not establish those runtime requirements.

The [ARM stub metadata contract](arm-handoff.md) specifies the four
little-endian fields used to pass caller-supplied DTB and kernel values.
Its synthetic vectors cover buffer preparation, without establishing
ARM address placement, cache visibility or core release.

The [ARM control-request contract](arm-control.md) covers configuration
arguments and software start-request gates with supplied service replies.
It keeps logical requests separate from hardware effects and ARM execution.

The [ARM object contract](arm-object.md) specifies registration at
0x0ED7C928 and a complete repeated open at 0x0EC59D24. Its separate
first-open prefix stops before `VERSION` and does not prove runtime
initialization or ownership.

The [callback registration and first-open returns](arm-first-open.md) cover
three fixed callback-table states and three complete first-open returns
with a zero selected table word. They do not establish successful open.

The [ARM configuration-control contract](arm-configuration.md) covers complete
slot-0x30 calls at 0x0EC59EBE with explicit CPU inputs and ordered service
observations. It does not establish the physical effect of those requests.

The [ARM mapping-table contract](arm-mapping.md) covers preparation at
0x0EC59C22 with twelve complete synthetic calls, actual repeated state
and retained stores on one raw-failure path. Table preparation remains
separate from mapping application, visibility and physical ARM release.

The [resource-request contract](resource-request.md) covers fixed logical
index 23, record aggregation, dependency order and conditional check
callbacks. Its complete calls and bounded prefixes use explicit software
state and callback replies.
The [complete resource composition](resource-composition.md) records two
clock requests in persistent state and the selected control phases, while
keeping the higher ARM wrapper and physical completion outside its scope.
The [higher start composition](arm-start-composition.md) joins that route
to the software gate at 0x0EC5A81E with explicit object binding and separate
lower/higher raw-zero results. Physical ARM launch remains unresolved.

The [fixed clock-request contract](clock-request.md) specifies software
planning, cache changes and notification outcomes for clock 0x30 and
requested value 600000000, with explicit driver boundaries. The
[fixed programming callback contract](clock-driver.md) describes the three
selected bodies under supplied read plans and native-word state.

## Restoring the boot partition

Before an approved hardware test, make an offline copy of the complete
known-working boot partition, including hidden files, `config.txt`, all
firmware/fixup pairs, kernel, device trees, overlays and initramfs. Keep
the backup on separate storage and record file sizes and SHA-256 values.
Use a separate test medium where the board configuration permits it.

The restoration sequence is:

1. Remove power from the CM4 and disconnect the test medium.
2. Attach the medium to the maintenance host and identify its boot
   partition. For soldered eMMC, use the board's approved read/write
   storage-access procedure after power is removed; do not change the
   SPI EEPROM or OTP configuration.
3. Restore the complete boot-partition file tree from the saved copy.
   Remove files added for the test so that the restored tree matches
   the backup, including the original firmware selection in `config.txt`.
4. Verify every restored file against the saved sizes and SHA-256 values.
   Unmount the medium cleanly.
5. Reconnect the original boot medium and board connections. After approval
   for the restoration boot, capture the UART log and verify the original
   Linux userspace returns.

This procedure has not been tested on hardware. The host build can
[stage a candidate configuration](../../src/start4/README.md#host-staging)
using the bounded file-selection contract above. Complete loader
acceptance and VPU entry execution remain unverified. A vendor fixup
stream must not be applied to an unrelated open ELF.

## Open questions

- Address aliases and cache behavior. Establish how the 0x0EC00000 and 0xCEC00000 ranges map to memory by checking the VPU memory map and the loader's address handling.
- Fixup bounds and compatibility. Test malformed/truncated streams with explicit host-side bounds and execute the caller across every supported memory split before defining a complete replacement loader contract.
- Runtime initialization. Trace references to the ThreadX, VCOS and `config.txt` strings before assigning scheduler behavior or a configuration-loading sequence to this build.
- Firmware handoff. The [conditional startup route](startup-arrival.md) resolves selected source dependencies. Record actual entry registers, memory layout and required bootloader state before defining the replacement entry contract.
