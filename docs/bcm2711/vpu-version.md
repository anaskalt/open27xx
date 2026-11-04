# Explicit VPU VERSION observations

`VERSION` reads CPU version and core information into a scalar register.
The pinned VideoCoreIV extension represents that result as an unresolved
instruction operation. `CaptureScalarVectors.java` and
`CaptureClockVectors.java` accept an explicit result through the opt-in
interface below; an absent plan still rejects VERSION. Clock retains its
existing finite MMIO and native-cell guards. The supplied result does not
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

A scalar case may add this member to its existing `execution` object.
The Clock recorder extension uses exactly the same object:

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

Apart from explicitly bound VERSION, mnemonics beginning with `v` and
all other `CALLOTHER` operations remain rejected. Other instructions keep
the existing scalar guards; this extension adds no RTI restriction or
physical interrupt semantics. Preserve the existing source, memory,
code-integrity, stub-consumption and step-limit guards. Scalar gains no
MMIO read support or native RAM allowance. Clock retains only its existing
MMIO and native-cell facilities, as specified below.

The separate [IRQ and p16 specification](vpu-irq.md) describes a pending
opt-in interface for the same recorders. It keeps an independent occurrence
cursor and preserves this VERSION contract. That interface is not yet
implemented and does not change the current DI rejection.

## Clock recorder integration

Apply the complete VERSION schema, preflight, operation binding, natural
step and ordered-consumption rules above to `CaptureClockVectors.java`.
Do not add another input format or broaden either recorder's memory policy.
An absent `version_input` must preserve Clock's existing results and
VERSION rejection byte for byte.

Clock still requires the pinned `start4.elf` identity, the original
descriptor pointer at 0x0EDDD694 and its existing mapped-block checks for
0x0EE056B0. Those checks apply even when the case does not supply that
cell. VERSION neither supplies the cell nor changes its initial or final
value. The allowed four-byte cell, exact block bounds, uninitialized
read/write/non-executable permissions and instruction-byte exclusion
remain as described in the [clock observation contract](clock-driver.md#replay-and-strict-boundaries).

Preserve the independent, finite MMIO read plan and per-case word-write
allowlist. A supplied read must still match its declared PC, address,
size and bytes. Unknown, mismatched or unused reads and undeclared writes
fail without a result artifact. VERSION must not consume a read reply,
authorize a write or create a physical MMIO observation.

VERSION, function replies, MMIO reads/writes and declared native-cell
accesses use the existing shared event array in actual execution order.
The VERSION site cursor and `site_index` are independent of MMIO
`reply_index` and each function's reply cursor. VERSION retains its
pre-instruction `step` value and counts as one instruction. Existing
event shapes, instruction counting and no-plan results remain unchanged.
At the return stop, all VERSION sites, MMIO responses and function replies
must be consumed under their respective existing rules.

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
to the selected-handle control path documented in
[ARM configuration control](arm-configuration.md).

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

The two complete matching-handle/control-1 continuations are recorded in
the [finite ARM configuration profiles](arm-configuration.md). They do not
extend the native input domain to every control argument or handle.
The earlier invalid-handle call and selected-handle prefixes remain
separate observations; the prefixes do not execute VERSION.

## First-open acceptance target

The Clock recorder covers three first-open returns in the same pinned `start4.elf`:
entry 0x0EC59D24, VERSION at 0x0EC59DE0, file offset 0x597E0, original
bytes `E4 00`, destination `r4`. The supplied word is bound by the same
original-instruction and compiled-operation checks; its bit-6 test has
no assigned hardware meaning.

The recorded first-open continuations select these paired routes:

| Supplied CPU word | Secondary word at GP+0xCC934 | Service 0x0ED65284 |
|---|---|---|
| 0x00000000 | Not consumed | Use service index at GP+0x3B490 and the current configuration word at GP+0x3B51C |
| 0x00000040 | 0 | Skip the service |
| 0x00000040 | 1 | Use that service index and value 0x200 |

When called, the service receives four further zero words. Its reply is
an explicit external input. Each route then reads 32 bits at 0x7E00B44C
from instruction 0x0EC59E12. Use one explicit synthetic MMIO response,
with no claim that its value is a real device observation. The VERSION
event precedes this read; the conditional service event lies between them.

The following call at 0x0EC59E22 targets the real scalar helper
0x0ED651FC with code 0x5E, callback token 0x0EC5716E and an old-callback
output at GP+0x3B488. That helper clears the output, loads the selected
table word at GP+0xE3D4 and returns raw 0xFFFFFFFF for a zero table word.
It overwrites incoming r3 with the code before using it; the preceding
MMIO read is not a fourth defined helper argument. Execute the helper
normally, with explicit table and output backing. Do not substitute a
return-only callback for its computation.

The [complete first-open profiles](arm-first-open.md) use a zero selected
table word and the three paired CPU/secondary-word routes above. They
enter the actual function with fresh storage and an external return
sentinel, execute both registration helpers, and retain the actual
object/configuration/frame effects. All three return raw 0xFFFFFFFF
without the higher release. Count, object, capacity and configuration
writes remain; the handle output is unchanged. Full results and finite
portable storage rules are in that separate contract.

These returned paths do not establish physical mapping or successful
first open. Their frames are separate from the existing
[first-open prefix](arm-object.md#first-open-observation-and-runtime-gap)
that ends before VERSION.

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
- For Clock, repeat VERSION instruction/result and malformed-plan checks
  without bypassing its existing source, descriptor or memory checks.
  Check ordered interleaving with finite MMIO responses and function
  replies, as well as the independent exhaustion and unused-plan errors.
- Keep Clock's missing/mismatched/unused read, undeclared-write and
  native-cell controls effective. Reproduce the existing clock fixtures
  without a VERSION plan unchanged and compare the three complete
  first-open observations against their exact finite fixtures. Fix any
  additional path's inputs and full-state predictions before capture.

## Open questions

- Actual BCM2711 word and bit-6 meaning. Establish them from an
  authoritative scalar specification or separately approved hardware
  observation; synthetic branch inputs cannot settle them.
- Physical instruction side effects and privilege behaviour. Compare a
  documented scalar specification or separately approved measurement.
  The present contract covers the pinned interpreter and explicit result.
- Successful first open and higher preparation. The three table-zero
  paths through 0x0EC59DE0 complete with raw 0xFFFFFFFF. Follow the later
  getter/driver callbacks after successful registration and resolve
  their state and external boundaries before claiming successful open.
  The consumer at 0x0EC5A6DE still has no complete native-path claim here.
  Preserve these limits when extending
  [ARM object initialization](arm-object.md#first-open-observation-and-runtime-gap).
