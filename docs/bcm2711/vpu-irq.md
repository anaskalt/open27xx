<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Conditional VPU IRQ and p16 observations

`execution.irq_p16` is a pending opt-in interface for
`CaptureScalarVectors.java` and `CaptureClockVectors.java`. Neither recorder
implements it yet. DI still rejects under the existing instruction policy.
The examples below describe the host interface, not recorded native fixtures.

The interface records DI's interrupt-disable request, supplies each declared
p16 read result and observes natural p16 writes. It assumes no asynchronous
interrupt arrives during the captured interval. It does not implement a
physical interrupt controller or shared mutex. The interpreter retains the
pinned instruction calculations and ordinary control flow.

## Source and instruction binding

The inspected native sites belong to `start4.elf`, firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, size 2303104 bytes,
SHA-256 `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Use Ghidra 12.2, language `vc4:LE:32:default`, compiler specification
`default` and VideoCoreIV commit
`db09a308c2db6a31ba5e060e6b763713f77e4f7b`, as in
[headless analysis](../analysis.md).

| Instruction address | File offset | Original bytes in file order | Binding |
|---|---|---|---|
| 0x0EDA7270 | 0x1A6C70 | `05 00` | DI |
| 0x0EDA7272 | 0x1A6C72 | `20 CC 10 00` | p16 read into r0 |
| 0x0EDA728C | 0x1A6C8C | `10 CC 02 00` | r2 written to p16 |
| 0x0EDA7310 | 0x1A6D10 | `10 CC 05 00` | r5 written to p16 |
| 0x0ED0071A | 0x10011A | `05 00` | DI |
| 0x0ED0071C | 0x10011C | `21 CC 10 00` | p16 read into r1 |
| 0x0ED0073E | 0x10013E | `10 CC 02 00` | r2 written to p16 |

These are inspected instruction bindings, not executed continuations.
They are evidence profiles, not a firmware-address allowlist for the
generic interface. Every other explicit site must satisfy the same complete
byte, operand and compiled-operation binding before use.

DI has length 2 and natural fallthrough PC+2. Its compiled p-code contains
exactly these five operations, in order:

| Operation | Required inputs and output |
|---|---|
| `INT_AND` | 4-byte SR at register offset 0x78 and 4-byte constant 0xBFFFFFFF; output 4-byte unique offset 0x8300 |
| `INT_ZEXT` | 1-byte constant zero; output 4-byte unique offset 0x8400 |
| `INT_LEFT` | Unique 0x8400 and 4-byte constant 0x1E; output 4-byte unique offset 0x8500 |
| `INT_OR` | Unique 0x8300 and unique 0x8500; output 4-byte SR at register offset 0x78 |
| `CALLOTHER` | One 4-byte constant selector 0x4, operation name `irq_disable`; no explicit arguments or output |

The first four operations clear SR bit 30 and preserve every other SR bit.
The final operation is an unresolved external request. Matching only the
mnemonic, selector or final SR value is insufficient; require the entire
compiled shape and its exact data flow.

A p16 move has length 4 and natural fallthrough PC+4. Its sole compiled
operation is a 4-byte `COPY`; p16 is register offset 0x240. For a read into
`rn`, the two little-endian halfwords are `0xCC20 | n` and 0x0010, with
output register offset `4 * n`. For a write from `rn`, the halfwords are
0xCC10 and `n`, with input at that ordinary register offset. Only n=0
through 23 is admitted. No extra operation, special register, partial
register access or alternate processor-control register is allowed.

The pinned `vc4.sla` SHA-256 is
`2303eea79ede697a37318068af1514de75ff64d9fcf2965623e2ab417e93bb56`;
`vc4.slaspec` is
`a3cc3f596d63a268440a659baa6fcf92e15900ec7ca1b8c2c733203d45236131`.
A different compiled shape requires separate validation and a contract
update, not a broader instruction allowlist.

## Public source limits

The following sources support the narrow interface distinction. Exact pins
and paths are also in [references](../references.md).

- VideoCoreIV `data/languages/vc4.slaspec:462–480` defines processor-control
  moves as assignments and DI as an SR update followed by `irq_disable`.
  It does not model a shared p16 read side effect or interrupt delivery.
- resim `libresim/src/videocore/VideoCoreIVExecute.hpp:448–456`, commit
  `cdc7808ceb7ba4ac00d0d08ca646b58615059150`, updates SR bit 30 for its
  opcode-4/5 handlers. The scalar32 decoder does not implement the p16
  moves. It is not an independent mutex or interrupt-delivery oracle.
- LK `arch/vpu/include/arch/arch_ops.h` and `arch_atomic.h`, commit
  `50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c`, use DI/EI and SR bit 30,
  loop on p16 until a zero read, and write zero to release. This source
  does not establish every p16 write value or BCM2711 ordering effect.
- The VideoCore IV programmer manual, wiki commit
  `0cb0ea6271a191e8e1900de7b67928f3070c75fe`, describes p16–p31 as shared
  single-bit mutexes and names p16 PRSPINL. It attributes that description
  to a Broadcom driver header and identifies its own work as independent
  research.
- The historical `broadcom/hardware_vc4.h` mirror at
  `christinaa/rpi-open-firmware` commit
  `02275a1bf046dc4a81a68640999ea4ac6126cc5f` contains the same description
  in its Broadcom-attributed 2006 header. It refers to a P-Reg Semaphore
  specification but does not supply that specification or a BCM2711
  validation. Its source SHA-256 is
  `c6087fd3605826c9601065313ba7a544be64bbb2d03cfee72acaf42b81d3ff19`.

The pinned `start4.elf` loop at 0x0EDA7272 repeats while its read result
is nonzero. Its exits at 0x0EDA728C and 0x0EDA7310 write the saved SR word
to p16, followed by separate SR restores. Recording that full word does
not establish the physical effect of the write. In particular, the LK
zero-write protocol does not prove the effect of every saved SR value.

## Input schema

Add this optional member to a case's existing `execution` object:

```json
"irq_p16": {
  "interrupt_arrivals": "none",
  "operations": [
    { "kind": "di", "pc": "0x00100000" },
    {
      "kind": "p16_read", "pc": "0x00100002",
      "destination": "r0", "value": "0x00000001"
    },
    {
      "kind": "p16_read", "pc": "0x00100002",
      "destination": "r0", "value": "0x00000000"
    },
    { "kind": "p16_write", "pc": "0x0010000A", "source": "r5" }
  ]
}
```

These addresses illustrate a synthetic instruction program with a repeated
read. They are not native firmware addresses or an executable fixture.

| Member | Requirement |
|---|---|
| `irq_p16` | Optional object; if present, exactly `interrupt_arrivals` and `operations` |
| `interrupt_arrivals` | Required string, exactly `none` |
| `operations` | Nonempty ordered array of actual instruction occurrences; length no greater than the positive instruction step limit |
| DI occurrence | Exactly `kind: "di"` and `pc` |
| Read occurrence | Exactly `kind: "p16_read"`, `pc`, `destination` and `value` |
| Write occurrence | Exactly `kind: "p16_write"`, `pc` and `source` |
| `pc` | `0x` followed by exactly eight hexadecimal digits; even, nonwrapping original instruction address |
| `destination`, `source` | Canonical ordinary register name `r0` through `r23`; no aliases |
| `value` | String with `0x` and exactly eight hexadecimal digits, numerically zero or one |

Hexadecimal digits may use either case. No fields are inferred. Explicit
nulls, missing or extra members, wrong types, invalid read values and an
empty plan reject. There is no count, default result or catch-all site.

The list names occurrences, not unique sites. A repeated PC authorizes
another execution only at that precise position in the list. Every
occurrence of that PC must have the same kind and ordinary-register
binding; only successive read values may differ. A further visit after
its last occurrence is exhausted. This permits finite busy-read sequences
without making the loop bounded in firmware or interpreting exhaustion
as success or a vendor return value.

The premise applies throughout the captured interval: no asynchronous
interrupt arrives, no interrupt handler is injected, and no second core
is simulated. Each p16 read is an independently supplied observation.
Neither the previous input nor a previous natural write supplies the next
read. A subsequent SR restore remains a real instruction; the premise does
not assert that such a restore keeps interrupts disabled on hardware.

## Complete preflight

Validate the entire plan before any instruction or callback executes:

1. Match the fixture source digest to the imported program and require the
   pinned language/compiler. Check all types, exact members, limits,
   occurrence bindings and nonwrapping instruction spans.
2. Require initialized, readable, executable original bytes at every site.
   Match the opcode, length, decoded operands, full compiled shape and
   natural fallthrough. No synthetic backing may replace code bytes.
3. Reject overlap with any declared setup or reply memory span. Reject a
   site equal to a function-stub entry or VERSION site. Different bindings
   for the same PC reject even when that PC would not be reached.
4. Reject setup or function-reply register assignments whose storage
   overlaps p16, including aliases. A reply cannot provide an undeclared
   p16 input. Other existing declared register behavior remains unchanged.
5. Reserve an initially unconsumed operation cursor. Any error rejects
   without executing instructions, consuming external replies or writing
   a result artifact. All existing source and memory checks still apply.

At each instruction boundary, compare the configured return stop first.
A stop with remaining operations rejects as unused. A prefix that ends
before an observation must omit that occurrence. Check the instruction
budget before executing a planned operation.

With the plan active, every DI and every compiled access overlapping
p16's four register bytes must match the next occurrence. Reject unknown,
reordered, exhausted, partial, aliased or differently shaped accesses
before stepping. Recheck code-byte equality and the complete binding at
execution, including a declared PC reached through an unexpected instruction.

## Natural execution and ordered events

For DI, preserve the pre-instruction SR for observation. Register a handler
only for the named `irq_disable` operation. The interpreter executes all
four integer operations before that handler. At the actual operation,
validate the pending PC, exact operation shape and resulting SR mask.
The handler records the request and returns to the interpreter. It writes
no register, memory, flags, PC or result varnode. Its acceptance represents
the declared external observation, not physical interrupt-disable effects.

For a p16 read, place only the next supplied word into p16 immediately
before the validated instruction. Execute its COPY normally; do not write
the ordinary destination directly. Check the destination, preserved SR
and other ordinary registers, and natural fallthrough. Record the event
only after the instruction succeeds.

For a p16 write, supply no write result and do not pre-write or normalize
p16. Execute the COPY, check that the actual p16 word equals the original
source register, and record that full 32-bit word. The instruction preserves
SR and other ordinary registers and reaches its natural fallthrough.

Append events to the same ordered array as VERSION, function replies,
MMIO and native-cell observations:

| Event kind | Required fields in addition to `kind` |
|---|---|
| `irq_disable` | `pc`, `operation_index`, `step`, `sr_before`, `sr_after` |
| `p16_read` | `pc`, `operation_index`, `step`, `destination`, `value` |
| `p16_write` | `pc`, `operation_index`, `step`, `source`, `value` |

Address and word fields use the existing eight-digit `0x` string format.
`operation_index` is the zero-based occurrence index. `step` is the number
of successfully executed instructions before this instruction, excluding
function-stub dispatches. DI emits at the actual named operation after
the SR update; p16 events emit after successful COPY with the same
pre-increment step index. Each successful DI or p16 move increments the
instruction count exactly once and produces no function-stub event.

Consume an occurrence only through its actual bound operation. Require
the named DI handler to run exactly once and then reach natural fallthrough.
Any instruction or handler failure aborts without a result artifact.
At a normal stop, every occurrence and every existing reply plan must be
consumed. Preserve failed inputs and the specific diagnostic separately.

Do not skip instructions, advance PC manually, patch language semantics,
replace a function body, or install a default `CALLOTHER` handler. VERSION
keeps its own named callback and independent site cursor. Other
`CALLOTHER` operations, EI, vector instructions and unsupported p16 shapes
remain outside this admission. Other ordinary instructions retain their
existing guards, including the existing RTI policy.

## Recorder integration and compatibility

Both recorders use the same schema, bindings and operation cursor. With
no `irq_p16` member, preserve their previous results and rejection behavior
byte for byte. The existing policy rejects DI; it does not intrinsically
ban every plain p16 COPY when register contents are explicitly supplied.
Do not introduce a new no-plan p16 or RTI restriction.

Scalar retains its existing memory policy. This extension adds no MMIO
read support or native RAM allowance. Clock retains its pinned `start4.elf`
identity, descriptor pointer at 0x0EDDD694, exact 0x0EE056B0 cell/block
checks and all finite read/write guards from
[clock observations](clock-driver.md#replay-and-strict-boundaries).
Those source/block checks still apply when the case supplies no cell.

IRQ/p16 observations cannot authorize a memory access, consume an MMIO
response or create native-cell backing. Keep VERSION, IRQ/p16, each
function's replies and MMIO responses as independent finite input streams.
They share only the actual event ordering. Missing, mismatched, unused
or exhausted responses and undeclared writes remain errors under the
existing contracts. No result artifact is produced for a failed capture.

## Acceptance requirements

- Freeze independent synthetic predictions before examining an
  implementation. Check r0/r23 operands, all low condition-flag patterns,
  both values of SR bit 30, other high SR bits, preserved registers/memory,
  exact natural fallthrough and instruction counts.
- Exercise an immediate zero read and a real loop consuming `1,1,0`.
  Observe natural writes of zero and saved SR words with bit 30 clear
  and set. Check that the next read uses its supplied input, not the write.
- Interleave DI/p16 with VERSION, function replies and Clock MMIO/native-cell
  events. Compare all ordinary registers, guarded memory and complete event
  streams. Generic instruction tests establish the host interface only.
- Reject malformed fields/premises, special registers, wrong source,
  opcode/operand/compiled shape, invalid code backing, overlapping spans,
  stub/VERSION collisions and conflicting repeated-PC bindings.
- Reject p16 setup/reply assignments and unknown, reordered, exhausted,
  unused, partial or aliased accesses. Check stop-before-occurrence,
  instruction-limit boundaries, missing handler consumption and changed
  fallthrough with exact diagnostics and absent artifacts.
- Keep other unsupported-operation, memory, MMIO and native-cell controls
  effective. Reproduce representative no-plan observations and DI rejection
  unchanged. Do not infer new hardware behavior from compatibility tests.
- Before any native continuation, fix its exact storage, external replies,
  CPU word and p16 occurrences, and independently derive complete expected
  state and event order. Distinguish a stop after the p16 loop from a
  complete call. The current seven inspected sites provide no successful
  first-open or IRQ/p16 execution claim.

## Open questions

- BCM2711 p16 arbitration and write semantics. Resolve read side effects,
  all accepted write bits and ownership rules from an applicable primary
  scalar specification or separately approved hardware observations.
- Memory ordering and interrupt behavior. Establish cache/order effects,
  privilege requirements and interrupt-entry timing separately; a
  no-arrival trace cannot settle them.
- Successful first open. The existing [first-open returns](arm-first-open.md)
  use a zero selected callback-table word. Follow the real driver and
  suspend-registration path with verified scalar helpers and explicit
  storage before claiming a successful return. Do not substitute a
  computational callback or guessed memory contents to cross that boundary.
