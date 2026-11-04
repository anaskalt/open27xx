# bootmain

`bootmain` is an ELF resource in `pieeprom-2026-10-30.bin` from raspberrypi/rpi-eeprom commit `236b4406753e604fde3315cb521a2f843c9f8f85`. The image SHA-256 is `6abfaea480f93da47a790f89751ed45d3af6e88ee8fb337d4eb62ad125ca3e8a`. Its LZ4 section starts at image offset 0x00C918, has a 211955-byte payload and decompresses to 267042 bytes.

The decompressed file has SHA-256 `4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d`. File offsets below refer to that file. Function and data addresses are ELF virtual addresses. It matches `2711/bootmain` in usbboot's pinned `firmware/bootfiles.bin` byte for byte; the archive identity is in [vendor-files.md](vendor-files.md). The section header and compression layout are in [eeprom.md](eeprom.md).

## ELF file

Fields follow the [ELF header specification](https://gabi.xinuos.com/elf/02-eheader.html).

| Field | File offset | Value |
|---|---|---|
| Class and byte order | 0x04–0x05 | ELF32, little-endian |
| Object type | 0x10 | 2, executable |
| Machine | 0x12 | 137 |
| Entry point | 0x18 | 0x00080000 |
| Program header table | 0x1C, 0x2A–0x2D | 0x34; two entries of 32 bytes |
| Section header table | 0x20, 0x2E–0x31 | 0x040E9A; 29 entries of 40 bytes |
| Flags | 0x24 | 0x100 |
| Linker identification in `.comment` | 0x040D22 | `MetaWare Linker v5.6.19` |

Both [program headers](https://gabi.xinuos.com/elf/07-pheader.html) have type `PT_LOAD`. Their virtual and physical address fields are equal.

| Header offset | Contents offset | Address | File size (bytes) | Memory size (bytes) | Flags |
|---|---|---|---|---|---|
| 0x34 | 0x80 | 0x00080000 | 259624 | 259624 | read, write, execute |
| 0x54 | 0x03F6C0 | 0x000CB000 | 5730 | 53988 | read, write |

The `.text` section header at 0x040EEA specifies file offset 0x120, address 0x000800A0 and size 248672 bytes. The section header table contains no `SHT_SYMTAB`, `SHT_DYNSYM` or `SHT_DYNAMIC` entry. These are [ELF section types](https://gabi.xinuos.com/elf/03-sheader.html); their absence does not identify library functions or establish the calling convention.

## Scalar execution evidence

The behavior below refers to `bootmain` from raspberrypi/usbboot commit `fdb604d018693465c9aa6ec69879df866d2820da`, SHA-256 `4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d`. Entry code at 0x00080014 establishes `gp = 0x000CB000`. The [scalar calling convention](abi.md) defines the register arguments used below.

The JSON files in [tests/vectors/bootmain](../../tests/vectors/bootmain/) contain synthetic memory, register inputs, execution boundaries and observations from Ghidra 12.2 `EmulatorHelper`. [CaptureScalarVectors.java](../../tools/ghidra/CaptureScalarVectors.java) records the cases. Uninitialized reads, writes outside declared memory, vector instructions and unsupported p-code operations fail execution. A stub records its arguments and applies only the reply listed in the fixture. Device outcomes do not follow from these replies.

## Configuration parser

In the identified `bootmain`, 0x00089128 consumes a text buffer through a stateful parser; 0x00088ADE finishes the pending assignment. Key lookup at 0x000890A8 uses case-sensitive comparison. Assignment at 0x00088A32 uses a table of 12-byte entries.

| Entry offset | Size (bytes) | Meaning |
|---|---|---|
| 0x00 | 4 | NUL-terminated key pointer |
| 0x04 | 4 | Destination pointer |
| 0x08 | 2 | String capacity, including NUL |
| 0x0A | 1 | Type: 0 signed integer, 1 unsigned integer, 2 string |
| 0x0B | 1 | Unset flag; cleared when a nonempty value is committed |

Selected entries in the identified `bootmain`:

| Key | Table address | Destination | Type |
|---|---|---|---|
| `SD_BOOT_MAX_RETRIES` | 0x000CC320 | 0x000CB564 | signed integer |
| `BOOT_UART` | 0x000CC398 | 0x000CB544 | unsigned integer |
| `BOOT_ORDER` | 0x000CC44C | 0x000CB600 | unsigned integer |
| `TFTP_PREFIX_STR` | 0x000CC464 | 0x000CB624 | string, 128-byte capacity |

[config.json](../../tests/vectors/bootmain/config.json) exercises 0x00089128 with a synthetic three-entry table. Its ten cases establish the following behavior:

- Spaces around a key and `=`, CR/LF line endings and `#` comments are accepted.
- A later assignment replaces an earlier value. An unknown key or a differently cased key leaves the destination unchanged.
- `0xf41` produces 0x00000F41; `-1` produces 0xFFFFFFFF in a signed destination. `010` produces decimal 10. The tested nonnumeric value produces zero.
- A string destination with capacity 8 receives at most seven characters followed by NUL.
- `[none]` disables assignments; `[all]` enables them again. Section handling is at 0x00088AF4.

The fixture texts end with a completed line and comment. They do not establish end-of-file behavior for a pending value, include-file handling or board-dependent filters.

## BOOT_ORDER and boot modes

In the identified `bootmain`, 0x00084D04 consumes the low nibble of the remaining order at boot-context offset 0x73C. In the normal state it shifts that word right by four bits, moves the previous mode to offset 0x741, stores the selected mode at 0x740 and clears the attempt counter at 0x748. [boot-order.json](../../tests/vectors/bootmain/boot-order.json) covers six orders, including 0x00000F41: SD is selected first and 0x000000F4 remains.

The mode-name function at 0x000833D0 and dispatcher at 0x00085148 identify these values in the same file:

| Value | Name | Dispatcher behavior |
|---|---|---|
| 0x0 | `SD` | Waits for SD insertion, then selects 0x1 |
| 0x1 | `SD` | Copies the retry limit at 0x000CB564 |
| 0x2 | `NETWORK` | Copies the retry limit at 0x000CB560 |
| 0x3 | `RPIBOOT` | Copies the retry limit at 0x000CB574 |
| 0x4 | `USB-MSD` | Sets the retry limit to 128 |
| 0x5 | `BCM-USB-MSD` | Sets the retry limit to 128 |
| 0x6 | `NVME` | Sets the retry limit to 1 |
| 0x7 | `HTTP` | Sets the retry limit to 0 |
| 0xE | `STOP` | Calls the stop path at 0x000A7388 with argument 4 |
| 0xF | `RESTART` | Reloads the configured order and dispatches again |

The same name table identifies internal modes 0x10 as `RAMDISK` and 0x20 as `NET-INSTALL`. These values cannot be single nibbles in `BOOT_ORDER`.

[boot-dispatch.json](../../tests/vectors/bootmain/boot-dispatch.json) executes ten dispatcher cases with watchdog, device-control and diagnostic calls intercepted. The retry counts above are observed at context offset 0x744. The 0xF case reloads the synthetic configured order, selects USB-MSD and increments the restart count at offset 0x74C. An unrecognized nibble 0x8 falls back to SD. The stop case records the request; it does not execute a hardware stop.

Eligibility at 0x00094E4C precedes device operation. [boot-mode.json](../../tests/vectors/bootmain/boot-mode.json) supplies board-type value 0x14 at `gp + 0x2F8` and explicit configuration globals. In these cases modes 0x0–0x6, 0xE and 0xF pass; 0x7 requires a nonzero word at `gp + 0x890`. With boot-reason word `gp + 0xA60` equal to 7, the tested 0x1 case fails while 0x3 and 0xE pass. This predicate is not a complete validity check for arbitrary mode numbers. Order filtering at 0x000888C0 retains eligible nibbles in their original order.

## Firmware and fixup selection

In the identified `bootmain`, 0x000AD57A selects descriptor pointers and memory sizes. With argument `r1 = 1`, it uses the BCM2711 file pairs below. Each descriptor occupies 16 bytes; its first word points to the filename.

| Selection | Firmware descriptor | Fixup descriptor | Files |
|---|---|---|---|
| Standard | 0x000CBE30 | 0x000CBE40 | `start4.elf`, `fixup4.dat` |
| Cut-down | 0x000CBEB0 | 0x000CBEC0 | `start4cd.elf`, `fixup4cd.dat` |
| Debug | 0x000CBEF0 | 0x000CBF00 | `start4db.elf`, `fixup4db.dat` |
| Extended | 0x000CBF30 | 0x000CBF40 | `start4x.elf`, `fixup4x.dat` |

The resulting pointers go to context offsets 0x114 and 0x118. The internal memory-size fields count units of 1048576 bytes. [firmware-pair.json](../../tests/vectors/bootmain/firmware-pair.json) records these six cases; the table converts the fields to byte sizes.

| Case | Input total (bytes) | Selected pair | Final total (bytes) | ARM (bytes) | GPU (bytes) |
|---|---|---|---|---|---|
| Default allocation | 1073741824 | Standard | 1073741824 | 994050048 | 79691776 |
| Explicit GPU allocation | 1073741824 | Cut-down | 1063256064 | 1046478848 | 16777216 |
| Extended flag | 1073741824 | Extended | 1073741824 | 1006632960 | 67108864 |
| Debug flag | 1073741824 | Debug | 1073741824 | 1006632960 | 67108864 |
| Smaller input memory | 268435456 | Standard | 268435456 | 201326592 | 67108864 |
| USB-MSD mode | 1073741824 | Standard | 1072693248 | 993001472 | 79691776 |

The same function uses context offsets 0x13C and 0x140 as fixup reference sizes: 268435456 bytes total and 134217728 bytes ARM for the standard, debug and extended cases; 268435456 bytes total and 251658240 bytes ARM for cut-down. Final ARM, total and GPU sizes occupy offsets 0x144, 0x148 and 0x14C. The [fixup operations](start4.md#fixup-stream) consume these values.

## File loading sequence

The identified `bootmain` uses these stages for the selected firmware pair:

1. 0x00086FC8 chooses a firmware candidate and calls 0x00086E14 to submit its file request.
2. Completion handler 0x00085748 accepts a successful file event and calls 0x00086FA6 to request the selected fixup file.
3. Completion handler 0x000857A8 continues to 0x00086754 even when the fixup is missing or empty.
4. 0x00086754 checks the ELF header, examines compatibility sections, applies a supplied fixup, checks the header again and calls the segment loader at 0x0008E1EA. The segment and fixup details are in [start4.md](start4.md#loading-by-bootmain).

At 0x00086E14, context offsets 0x10C and 0x110 retain the file and optional signature descriptors. The request object at context offset 0x124 receives filename pointers at offsets 0x94 and 0xA0 and eight buffer pointers at 0xB4. Buffer lengths are reset before submission. Event 0x16 requests an ordinary file, 0x18 a signature-aware file and 0x1A the alternate signature-aware path selected by a nonzero fifth argument.

[file-request.json](../../tests/vectors/bootmain/file-request.json) records `start4.elf`, `fixup4.dat` and both `boot.img` request forms. Calls to the event scheduler at 0x000AE1FC and callback installer at 0x000AE3B2 are intercepted after their arguments are recorded. These cases establish request construction, not storage-driver behavior or file contents.

## boot.img selection

In the identified `bootmain`, 0x00084412 selects the image and signature descriptors at context offsets 0x194 and 0x198. The ordinary pair is `boot.img`/`boot.sig`, at 0x000CC010/0x000CC020. The alternate pair is `tryboot.img`/`tryboot.sig`, at 0x000CC030/0x000CC040.

The alternate pair is selected when bit 0 of `gp + 0x944` is set, bit 1 is clear and the current mode is not 0x20. Otherwise the ordinary pair is selected. If the security-state query at 0x000A8788 returns zero, the signature descriptor is cleared except in modes 0x7 and 0x20. [boot-image.json](../../tests/vectors/bootmain/boot-image.json) records all these decisions with an explicit substituted query result. It does not establish how hardware provisioning produces that result.

Request setup at 0x000872BC passes the selected pair to 0x00086E14. [boot-image-complete.json](../../tests/vectors/bootmain/boot-image-complete.json) executes completion handler 0x00085CC8 for events 0x17, 0x19 and 0x1B with a successful request status. The handler changes the current mode to 0x10 (`RAMDISK`), retains the previous mode, clears the retry count and requests block-device event 0x46. It retains a positive partition number and maps a negative number to zero. Event 0x1B also sets the word at `gp + 0xCAC` to one. A fourth case supplies failure status 0x0C and records the request to advance the boot path without entering RAMDISK. Scheduler and next-path calls are intercepted; image mounting and storage behavior remain outside these fixtures.

## Signature files and verification boundaries

In the identified `bootmain`, buffer descriptors used by 0x000A8024 and 0x000A886C contain five 32-bit words: magic 0x42554646, data pointer, current length, capacity and an auxiliary word initialized to zero by 0x0008823E. The descriptor check at 0x000881B0 requires a nonnull data pointer, positive capacity and length no greater than capacity.

Signature-file parser 0x000A8024 accepts an optional 32-byte digest destination, 256-byte RSA destination, timestamp output and target-SoC output. When requested, the digest comes from 64 hexadecimal characters at the start of the input. Newline-delimited metadata uses the prefixes `ts: `, `rsa2048: ` and `target-soc: `. The timestamp defaults to zero; target SoC defaults to decimal 2711. The target parser accepts 2711 or 2712 and stores zero for the tested unrecognized value. A malformed requested digest or truncated RSA encoding returns 0xFFFFFFFF.

[signature-file.json](../../tests/vectors/bootmain/signature-file.json) covers digest parsing, timestamp/SoC metadata and malformed input. [signature-hex.json](../../tests/vectors/bootmain/signature-hex.json) executes helper 0x000A7DB6 with mixed-case hexadecimal, invalid characters, short input, short output and a zero-byte request. It resets the output length before decoding; an invalid later character preserves bytes already decoded. Diagnostic calls are intercepted in the file-parser cases.

File-completion function 0x0008FE8C, in state 2, calls 0x000A686C to compute SHA-256 over the completed buffer list and compares the result with the parsed digest. [file-digest.json](../../tests/vectors/bootmain/file-digest.json) records matching and mismatched three-byte payloads with the RSA-required field clear. A match resets the verification state to zero. A mismatch clears the tested payload and sets request status 0x0C. These cases execute the hash and comparison; only completion scheduling and diagnostics are intercepted. The watchdog write at 0x7E100024 is recorded in emulator memory.

Verification wrapper 0x000A886C requires a 256-byte signature descriptor and a 264-byte public-key descriptor. [signature-boundary.json](../../tests/vectors/bootmain/signature-boundary.json) records rejection of shorter and longer descriptors with return 0xFFFFFFFF. Their payload pointers are uninitialized and never read. No key or valid signature payload appears in these fixtures.

The wrapper calls 0x000AB04C for the accepted-length path. The RSA/SHA-256 entry points, PKCS#1 v1.5 encoding and Mbed TLS lineage are documented in [abi.md](abi.md#library-entry-points). Scalar execution of verifier 0x0009C0B2 with a fresh synthetic RSA-2048 key and a valid PKCS#1 v1.5/SHA-256 signature returns zero. Changing one digest byte returns 0xFFFFBC80, the encoding-comparison failure. Both cases execute the vendor modular arithmetic and allocator without substituted calls. The public fixtures above contain no key or valid signature payload and cover framing, digest comparison and invalid-argument behavior. None of these checks establishes hardware trust policy.

## Open questions

- Configuration edge cases. Execute pending end-of-file assignments, include directives, overflow boundaries and board-dependent sections through their callers before extending the parser contract beyond the recorded cases.
- Device boot paths. Record SD, USB, network, NVMe and HTTP state-machine completions, timeout handling and retry exhaustion with controlled device responses. The current dispatch fixtures stop at device boundaries.
- Hardware trust policy. Establish the allowed security-state transitions and certificate/key selection from documented provisioning and approved hardware observations; the image-selection fixture supplies the query result explicitly.
- Complete load and handoff. Exercise compatibility checks, storage completion, cache handling and entry-state preparation together before treating the scalar helper fixtures as a complete firmware boot.
