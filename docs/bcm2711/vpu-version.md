# Explicit VPU VERSION observations

`VERSION` reads CPU version and core information into a scalar register.
The pinned VideoCoreIV extension represents that result as an unresolved
instruction operation. `CaptureScalarVectors.java` currently rejects it.
The interface below defines an opt-in recorder extension; it does not
supply a BCM2711 hardware value or execute a physical CPU-identification
instruction.

## Source and instruction binding

The first inspected native site belongs to `start4.elf` from firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, size 2303104 bytes,
SHA-256 `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Use Ghidra 12.2, language `vc4:LE:32:default`, compiler specification
`default`, and VideoCoreIV commit
`db09a308c2db6a31ba5e060e6b763713f77e4f7b`, as in
[headless analysis](../analysis.md).

| Property | Required value |
|---|---|
| Instruction address | 0x0EC59EEE |
| File offset | 0x598EE |
| Original bytes, in file order | `E2 00` |
| Length | 2 bytes |
| Destination | `r2` |
| Fallthrough | 0x0EC59EF0 |
| Compiled p-code | Exactly one `CALLOTHER` |
| Operation name and ID | `version`, 0x1 |
| Operation input | One 4-byte constant-space selector with value 0x1; no explicit arguments |
| Operation output | Register-space offset 0x8, size 4 bytes, exactly `r2` |

This native site is an evidence profile, not an address allowlist in the
generic recorder. Other explicit PCs may use the host interface when their
original instructions satisfy the binding below. That does not establish
a verified firmware path at those PCs.

The compiled operation writes directly to `r2`; it has no intermediate
copy or additional memory, flag or control-flow operation. The original
and emulator instruction bytes must match. The generic binding requires
a two-byte opcode `0x00E0 | n` for
destination `rn`, where n is 0 through 23. The decoded register and the
sole compiled operation must agree: named `version`/ID 0x1, one 4-byte
constant selector, no explicit arguments, and a 4-byte output matching
that register. No intermediate copy or additional operation is admitted.
A changed extension or instruction shape requires a separate contract.

These sources establish the instruction/result boundary:

- VideoCoreIV `data/languages/vc4.slaspec:453–455` declares the named
  zero-argument operation and its destination assignment.
- binutils-vc4 `cpu/vc4.cpu:1094–1099`, commit
  `708acc851880dbeda1dd18aca4fd0a95b2573b36`, names the encoding MOVCPUID.
  It supplies encoding information, without execution semantics.
- resim `libresim/src/videocore/VideoCoreIVExecute.hpp:13,178–180`, commit
  `cdc7808ceb7ba4ac00d0d08ca646b58615059150`, assigns its own fixed word
  0x04000104. That simulator constant does not establish a BCM2711 value.
- The author-maintained VideoCore IV programmer manual, wiki commit
  `0cb0ea6271a191e8e1900de7b67928f3070c75fe`, identifies VERSION among scalar
  16-bit instructions. It is independent research, not a Broadcom ISA
  guarantee. The 3D/QPU manual does not specify this scalar instruction.

The exact source paths and pins are in [references](../references.md).

## Input schema

A scalar case may add this member to its existing `execution` object:

```json
"version_input": {
  "word": "0x00000000",
  "sites": [
    { "pc": "0x0EC59EEE", "destination": "r2" }
  ]
}
```

| Member | Requirement |
|---|---|
| `version_input` | Optional object; if present, exactly `word` and `sites` |
| `word` | Required string: `0x` followed by exactly eight hexadecimal digits |
| `sites` | Required nonempty array, in execution order, with unique PCs |
| Site object | Exactly `pc` and `destination` |
| `pc` | `0x` followed by exactly eight hexadecimal digits, naming an even original instruction address |
| `destination` | Canonical ordinary register name `r0` through `r23`; no aliases or special registers |

Hexadecimal digits may use either case. Each declared site executes
exactly once. The initial native example declares one site. Multiple
distinct sites use the same word and must execute in their declared order.
A second visit to a consumed site is exhausted; duplicate site
definitions cannot authorize repetition. There is no count field.

The complete 32-bit word is common and immutable for a case. Do not
mask it, derive it from firmware revision fields, infer it from the host,
or provide a default. Values 0x00000000 and 0x00000040 are the initial
synthetic branch inputs; neither identifies a real CM4. Other words have
no recorded function-continuation claim in this contract.

An absent member preserves the existing recorder behaviour, including
VERSION rejection. An explicit null, incomplete object, extra member,
wrong type, malformed word or empty site list is an error. This schema
adds no default handler for other instruction operations.

## Validation and execution order

Validate the complete plan before executing any instruction or callback:

1. Match the fixture source digest to the imported program, and require the
   pinned language and compiler specification. Validate all field types,
   unique even PCs and ordinary destinations. Require an existing original
   instruction and matching readable, initialized executable bytes at each
   site; no synthetic backing may replace those bytes.
2. Match the original bytes, length, decoded operand and complete compiled
   p-code shape for the declared ordinary destination. Reject every
   special register destination, including
   status, program counter, stack pointer and link register.
3. Reject a site equal to any declared function-stub entry. A function
   callback must not consume or bypass a declared VERSION observation.
4. Reserve the single immutable word and an initially unconsumed site
   cursor. Reject the plan on any validation error, without executing
   instructions, boundary replies or writing a result artifact.

At each instruction boundary, check the configured return stop before
executing an instruction, as in the existing scalar recorder. If execution
stops with any VERSION site unconsumed, reject it. A prefix intentionally
ending before VERSION must omit that site's plan.

When VERSION is reached, require the next unconsumed site to match the
current PC and destination. Recheck instruction bytes and operation shape
against the original program. An unknown, reordered, repeated or exhausted
site fails. A declared site reached through a nonmatching instruction
also fails.

Register a callback only for the named `version` operation. The callback
writes the supplied word to that operation's exact output varnode and
returns control to the interpreter. It must not write another register,
flags, memory, code, descriptors or PC. The interpreter executes the
normal instruction and advances to its natural fallthrough. Do not use a
function stub, address-level skip or default `CALLOTHER` callback.

All other unsupported operations remain rejected, including vector
instructions, interrupts, software interrupts and breakpoints. Preserve
the existing source, memory, code-integrity, stub-consumption and step-limit
guards. This extension introduces no MMIO read support or native RAM
allowance.

## Ordered observation

Append one event to the existing shared event array at the VERSION
boundary, in its actual order relative to other recorded events:

```json
{
  "kind": "version",
  "pc": "0x0EC59EEE",
  "destination": "r2",
  "value": "0x00000000",
  "site_index": 0,
  "step": 15
}
```

`site_index` is the zero-based index in `sites`. `step` is the number of
successfully executed ordinary instructions before this VERSION,
excluding function-stub dispatches. Check the instruction budget first.
The callback records the accepted input, and successful execution then
increments the instruction count once. One VERSION is one instruction;
it produces no function-stub event. The example's index 15 corresponds
to the already observed selected-handle prefix, not a recorded complete
call with this extension.

Consume the site only once. Any instruction or callback failure aborts
without a result artifact. At a normal stop, every declared site must be
consumed and every existing reply/guard check must still pass.

## First conditional control route

In the pinned `start4.elf`, entry 0x0EC59EBE acquires the declared mutex
boundary before checking the handle. A handle unequal to 0x61726D11
reaches the release boundary and returns 0xFFFFFFFF without VERSION.
A VERSION plan on that path would remain unused and must fail.

For a matching handle, the native scalar body stores its configuration
word at GP+0x3B51C before VERSION. At 0x0EC59EE4–0x0EC59EEC, a nonzero
control argument sets configuration bit 6; zero clears it. This
configuration bit is distinct from the returned CPU word.

The immediately following bit test at 0x0EC59EF0 selects the continuation:

| Supplied CPU word | Static continuation |
|---|---|
| 0x00000000 | Load service index from GP+0x3B490; call 0x0ED65284 with that index, the stored configuration and four zero words |
| 0x00000040 | Skip that service call |

Both paths converge at 0x0EC59F08, select raw zero, call the mutex-release
boundary at 0x0EC59F0C and execute the real epilogue at 0x0EC59F12. The
service reply does not determine that raw return in the static sequence.
Mutex and service replies remain explicit external inputs. Their physical
effects are unverified.

These complete continuations are recorder acceptance targets, not
completed differential results. The existing complete invalid-handle
case and the selected-handle prefixes establish the pre-VERSION state;
they do not execute VERSION. The first new captures must enter the real
function with an external return sentinel and execute its actual frames
and unwind, using the supplied word only at the named instruction.

## Acceptance requirements

- Use independent synthetic instruction programs to check ordinary
  destinations `r0` and `r23`, multiple ordered sites sharing one word,
  and invalid or special destinations. These are host-interface checks,
  not additional vendor-path evidence.
- Prove natural execution of the bound compiled operation, the exact
  destination change, preserved other registers/flags/memory, natural
  fallthrough and one-instruction accounting.
- Capture both fixed supplied-word continuations from the real entry,
  with explicit mutex/service replies, full return, ordered events and
  observed state. Keep static predictions separate from recorded results.
- Reject missing or malformed plans, duplicate/unknown/reordered sites,
  wrong destinations, special registers, opcode/length/operation mismatch,
  stub collisions, revisit/exhaustion and unused observations.
- Check a stop before the declared site, the instruction-limit boundary
  and rejection of other unsupported operations. Require the diagnostic
  and absent output artifact for every negative control.
- Reproduce existing captures without `version_input` unchanged.

## Open questions

- Actual BCM2711 word and bit-6 meaning. Establish them from an
  authoritative scalar specification or separately approved hardware
  observation; synthetic branch inputs cannot settle them.
- Physical instruction side effects and privilege behaviour. Compare a
  documented scalar specification or separately approved measurement.
  The present contract covers the pinned interpreter and explicit result.
- Complete first open and higher preparation. The VERSION consumers at
  0x0EC59DE0 and 0x0EC5A6DE have no complete native-path claim here.
  First open still
  reaches MMIO and registration dependencies after VERSION. Resolve their
  remaining state and boundaries before extending
  [ARM object initialization](arm-object.md#first-open-observation-and-runtime-gap).
