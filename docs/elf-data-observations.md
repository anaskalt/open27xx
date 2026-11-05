<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Source-backed ELF data observations

`CaptureClockVectors.java` accepts an optional `execution.elf_data` plan
for initialized data in the original ELF file. The plan authorizes exact
scalar memory accesses and records their actual bytes. It supplies no
replacement data, arithmetic result, register value or control transfer.
Requests without this option retain the existing memory rules.

The implementation is in
[`ElfDataObservations.java`](../tools/ghidra/ElfDataObservations.java).
The [host tests](../tests/ElfDataObservationsTest.java) use a synthetic ELF
file, real Ghidra `ProgramDB`, `FileBytes` and memory blocks, and decoded
scalar instructions. They do not require vendor firmware.

## Request fields

`execution.elf_data` contains exactly two nonempty arrays: `regions` and
`operations`. Each region contains these fields:

| Field | Type | Meaning |
|---|---|---|
| `address` | Hex string | Start address in the program's ordinary `ram` space |
| `size` | Integer | Complete region size, from 1 through 1048576 bytes |
| `file_offset` | Hex string | Offset in the original complete ELF file |
| `sha256` | String | SHA-256 of the original bytes in this region |

Each operation contains exactly these fields:

| Field | Type | Meaning |
|---|---|---|
| `kind` | String | `read` or `write` |
| `pc` | Hex string | Address of the actual scalar instruction |
| `address` | Hex string | Exact data-access address |
| `size` | Integer | Exact access width, from 1 through 1048576 bytes |

Address and offset strings have `0x` followed by exactly eight hexadecimal
digits. Digests have exactly 64 lowercase hexadecimal digits. Sizes are
positive integral JSON numbers without an exponent. Address and file
extents must fit within the unsigned 32-bit interval. Instruction PCs
must be even. Unknown fields and supplied `hex`, `fill` or value fields
in the plan are rejected.

The host fixture uses this plan for its two scalar memory instructions:

```json
{
  "elf_data": {
    "regions": [
      {
        "address": "0x10002000",
        "size": 8,
        "file_offset": "0x00000200",
        "sha256": "9e8376b4aa602de084708bf231f7ab5bd700e3d623bcf47a3851ce49cbe46f08"
      }
    ],
    "operations": [
      {
        "kind": "read",
        "pc": "0x10001000",
        "address": "0x10002004",
        "size": 4
      },
      {
        "kind": "write",
        "pc": "0x10001002",
        "address": "0x10002000",
        "size": 4
      }
    ]
  }
}
```

The region's eight initial bytes are all `0x90`. The plan carries their
digest; the recorder obtains the bytes from the original program file.
It does not write them into program memory or overlay caller bytes into
the emulator.

## Admission

The complete plan and every final memory observation are checked before
the case executes its first original instruction.

1. The program must be an ELF file with the requested source SHA-256.
   Each complete region must fit inside one initialized, readable,
   writable, nonexecuting normal memory block. Overlay address spaces,
   bit mappings and byte mappings are excluded.
2. One direct file-source mapping must cover the whole region. Both
   endpoints must match the declared original-file offset and a contiguous
   one-to-one mapping. Embedded-file origins and ranges crossing distinct
   source mappings are excluded.
3. The SHA-256 of the complete original `FileBytes` source must equal the
   request's file digest. Original region bytes must match their region
   digest and the current program bytes. A modified database region or an
   unrelated loaded file cannot substitute for the original source.
4. Regions must be disjoint and must not intersect instructions, supplied
   memory, stub entries or declared VERSION/IRQ sites. The synthetic
   windows, MMIO window and separately admitted clock cell retain their
   own policies and cannot be declared as ELF data.
5. Each planned operation must fit wholly inside one region. Every
   region must occur in the plan. The PC must identify initialized,
   readable, executable instruction bytes with a concrete RAM LOAD or
   STORE of the stated width. A supplied function-reply site is excluded.
   The actual address is checked during execution; an opcode alone does
   not prove the address it will access.
6. Every region must have exactly one complete final observation in
   `expected.memory`, using the existing `address` and `hex` fields.
   Partial, repeated, missing and undeclared source observations fail.
   Synthetic observations must still lie in the declared setup storage;
   a stub-only storage declaration does not authorize them.

The ordinary instruction-byte, vector, unsupported-operation, VERSION,
IRQ, MMIO and synthetic-memory guards remain active. The option does not
permit caller overlays of source data, arbitrary writes to ELF storage
or changes to executable bytes.

## Ordered observations

Original scalar accesses consume one shared read/write cursor. An access
intersecting a declared ELF region must match the next operation's kind,
PC, address and width exactly. A cross-boundary, reordered, exhausted or
unexpected access fails. All planned accesses must occur before the case
can finish. Other existing memory policies remain in force.

Each access appends an event to the recorder's existing event array:

| Field | Meaning |
|---|---|
| `kind` | `elf_data_read` or `elf_data_write` |
| `pc` | Executing original instruction |
| `address` | Actual access address |
| `hex` | Actual accessed bytes in memory order |
| `operation_index` | Zero-based index in the declared access plan |
| `step` | Number of original instructions completed before this instruction |

Events observe the emulator's data. They do not compare against or inject
an arithmetic result. Stub assignments, MMIO injection and final memory
reads do not consume the ELF-data plan. The final memory records contain
the emulator's actual bytes after the ordinary source instructions finish.
The recorder never changes the Ghidra program's stored bytes.

## Host checks

Set `OPEN27XX_GHIDRA_HOME` to the installed Ghidra directory and `JAVA_HOME`
to its supported JDK, then run:

```sh
python3 -m unittest \
  tests.test_elf_data_observations \
  tests.test_clock_version \
  tests.test_scalar_version \
  tests.test_irq_p16
```

The ELF-data checks cover parser bounds, source identity, original-file
digests, current-byte equality, real file mappings, block permissions,
instruction overlaps, final-observation admission and ordered runtime
events. The existing VERSION and IRQ checks cover requests without the
new option. Recorded firmware comparisons require their own pinned source,
input and expected-state fixtures.

## Open questions

- Physical storage and exception behavior. These observations establish
  only conditional scalar execution in the pinned interpreter. Hardware
  evidence or an independently justified architecture contract is needed
  for privilege, aliasing, interrupt delivery or device effects.
- Other recorder entry points. Only `CaptureClockVectors.java` accepts
  this option. Supporting another recorder requires the same complete
  admission and access-order checks plus legacy-output regression evidence.
