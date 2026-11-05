# Startup zero observations

`tools/ghidra/CaptureStartupZero.java` records two isolated calls of the startup
initializer in `start4.elf`, firmware revision
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
The entry is 0x0EC3D740 and GP is 0x0EE04140. Inputs are synthetic caller
registers and memory poisons. These observations do not establish startup
arrival state or hardware behavior.

The script requires Ghidra 12.2, `vc4:LE:32:default`, the default compiler
specification and the eight installed processor files identified in its
`MODULE` map. It resolves the loaded SLA path and checks every file digest.
The general scalar and clock capture scripts retain their existing behavior.

## Source and memory admission

The script verifies the complete original FileBytes digest, ELF32 header,
program and section header tables, exact original/current source equality
and direct source mappings. Each destination must have its original
uninitialized, readable/writable, nonexecuting, ordinary RAM block.
An initialized, mapped, overlay, absent or differently bounded block fails
admission. The script does not create instructions or change ProgramDB.

All addresses and offsets below refer to the file and revision above.

| Source | Address | File offset | Bytes |
| --- | --- | --- | ---: |
| Initializer | 0x0EC3D740 | 0x3D140 | 182 |
| Completion return | 0x0EC3D7F6 | 0x3D1F6 | 2 |
| Fill entry | 0x0ED1FDF0 | 0x11F7F0 | 4 |
| Fill body | 0x0ED1FE14 | 0x11F814 | 56 |
| Table | 0x0EDD7870 | 0x1D7270 | 36 |

The 244 instruction bytes decode into exactly 75 detached instruction sites.
The decoder may read transport bytes through 0x0EC3D7FD, 0x0ED1FDF7 and
0x0ED1FE51 in the corresponding source spans. These 16 additional bytes have
separate original-file digest bindings and never become execution targets or
runtime data merely because the decoder can read them.

| Destination | PT_LOAD index | NOBITS index | Start | Bytes |
| --- | ---: | ---: | --- | ---: |
| `bss_0` | 13 | 29 | 0x0EE056A0 | 2352 |
| `bss_1` | 17 | 34 | 0x0EE33200 | 2048 |
| `bss_2` | 18 | 35 | 0x0EE33A00 | 1011288 |

Each destination has zero file payload, flags RW and alignment 32.
Their 1015688 bytes receive synthetic poison in disposable emulator memory.
The original blocks remain uninitialized. Header file offsets are metadata;
they do not identify file-backed BSS bytes.

## Request

The script takes a UTF-8 request filename and a new output filename.
The request is at most 16384 bytes. Unknown or duplicate members fail.

| Member | Value |
| --- | --- |
| `schema_version` | Integer `1` |
| `source_sha256` | Complete source digest above |
| `tool_sha256` | SHA-256 of `CaptureStartupZero.java` |
| `helper_sha256` | SHA-256 of sibling `StartupZeroObservations.java` |
| `profiles` | Exactly `poison-a`, then `poison-b` |

Each profile has exactly `id`, `registers`, `stack`, `bss_poison` and
`return_sentinel`. The stack object has exactly `start`, `size` and `fill`.
All words use `0x` followed by eight uppercase hexadecimal digits. Fill
values use two lowercase hexadecimal digits. All 32 registers are required:
`r0` through `r23`, `gp`, `sp`, `lr`, `r27` through `r29`, `sr`, `pc`.

| Input | `poison-a` | `poison-b` |
| --- | --- | --- |
| Ordinary register number `i` | 0x11110000 + `i` × 0x101 | 0xEEEE0000 + `i` × 0x303 |
| GP | 0x0EE04140 | 0x0EE04140 |
| SP | 0x24010080 | 0x24010280 |
| LR and return sentinel | 0x24000000 | 0x24000004 |
| SR | 0x13579BDA | 0xA5A5A5A5 |
| PC | 0x0EC3D740 | 0x0EC3D740 |
| Stack start | 0x24010040 | 0x24010240 |
| Stack size | 128 | 128 |
| Stack fill | `3c` | `c3` |
| BSS poison | `a5` | `5a` |

The named GP/SP/LR/SR/PC values override their ordinary register numbers.
`expectedProfile()` constructs this exact schema for callers and host tests.
The request contains no expected outputs, operation plan, substitutions,
source patches or decoder-context values.

## Execution and accounting

Each profile uses a fresh EmulatorHelper. Seeding occurs while idle and
every seeded byte is read back and hashed before execution. Uninitialized
or unknown accesses fail through a rejecting memory fault handler.

MemoryAccessFilter callbacks distinguish `INSTRUCTION_DECODE` from `EXECUTE`.
Decoder reads must stay inside the current site's bound transport envelope.
Runtime reads must fit wholly within one table, BSS or stack span. Runtime
writes must fit wholly within one BSS or stack span. An access crossing the
adjacent `bss_1`/`bss_2` boundary fails. Idle setup, byte checks and final
observations do not enter either runtime stream.

The callbacks occur after the underlying memory access. A rejected access
invalidates the disposable case; it does not establish that the access was
prevented. No partial case is emitted as successful evidence.

Each step checks the selected PC and original instruction bytes. The bound
initializer instruction at 0x0EC3D77C must execute its actual RETURN and reach
the profile's sentinel. Calls, fills and completion returns execute normally.
The script does not repair result registers or memory.

Each case has ceilings of 600000 instructions, 600000 runtime RAM operations
and 8388608 runtime bytes. Decoder transport independently has the same
operation and byte ceilings. These are resource limits, not expected counts.
Coverage uses one bit per byte, least significant bit first, padded with
zero bytes to `ceil(region_size / 8)`. Read coverage, write coverage and
duplicate read/written-byte totals accompany per-region/PC/kind/width counts.

## Canonical streams

SHA-256 starts with ASCII `open27xx-startup-data-v1` and one NUL byte for
runtime data, or `open27xx-startup-decode-v1` and one NUL byte for decoder
transport. Each stream has an independent zero-based ordinal. Each event
appends these fields without padding:

| Field | Encoding |
| --- | --- |
| Ordinal | Unsigned 64-bit little-endian |
| Current instruction PC | Unsigned 32-bit little-endian |
| Kind | One byte: read 0, write 1 |
| Memory address | Unsigned 32-bit little-endian |
| Width | Unsigned 32-bit little-endian |
| Observed value | Exactly `width` bytes in memory order |

The fixed header is 21 bytes. Counts and byte totals accompany the digest;
the output contains no array proportional to the number of stores.

The detached p-code digest starts with ASCII `open27xx-startup-pcode-v1`
and NUL. Each operation appends its opcode and input count as 32-bit
little-endian integers, then its output followed by its inputs. Each node
starts with a presence byte. A present node appends its address-space UTF-8
name length as 32-bit little-endian, the name bytes, its offset as 64-bit
little-endian and its size as 32-bit little-endian.

## Context and output

Each context value is JSON `null` or an object containing `register`,
`bit_length` and `mask_value_bytes`. The last field is lowercase hex from
Ghidra RegisterValue.toBytes(): the mask half followed by the value half.
A zero mask is unknown state; it does not assert a numeric zero value.
No context setter is called.

Production admission requires `contextreg`, 32 bits. ProgramContext current,
default and nondefault getters must return null at every source address.
The disassembly default and detached instruction context must contain eight
zero mask/value bytes. An existing listing instruction's context may be null
or the same eight zero bytes. Fresh emulator context must be null before
seeding and before the first step. After each step and before subsequent
steps, it must contain eight zero bytes. Both halves are checked: a zero
mask with a nonzero stored value fails. Decoder-local parser scratch is
distinct from these instruction input-context getters.

Site evidence includes listing presence, ProgramContext current/default/
nondefault values, the disassembly default and detached context. Each case
records emulator context before seeding, before the first step and after
return. Per-PC before/after tuples retain repetition counts, with at most
two tuples per site. Emulator context describes the previous parsed
instruction and feeds the next decode; it is not an architectural register.

Final observations scan every BSS byte in chunks of at most 65536 bytes.
Each region reports the actual SHA-256, an independently generated zero-byte
SHA-256, all-zero status, nonzero-byte count and first nonzero offset or null.
The complete 128-byte stack and all 32 registers are retained. The script
checks all source bytes and ProgramDB listing/context snapshots afterward.

The complete two-case output is at most 1048576 UTF-8 bytes and is written
once with CREATE_NEW. `capture_completed` describes normal capture
completion. `expected_result_comparison` remains `not_performed`; an
independent comparison decides whether observed results match predictions.
After request, tool and module admission, a failed attempt writes a bounded
`<output>.failure.json` with source,
request, tool/module bindings and its diagnostic.

## Host checks

Set `OPEN27XX_GHIDRA_HOME` and `JAVA_HOME`, then run:

```sh
python3 -m unittest tests.test_startup_zero_observations
```

The tests use a synthetic ELF, ordinary uninitialized ProgramDB storage,
source-owned x86 instructions and actual EmulatorHelper callbacks. They do
not execute vendor instructions or alter the installed processor files.
