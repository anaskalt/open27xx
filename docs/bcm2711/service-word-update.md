<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Service word update

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

Entry 0xCEC006D0 selects a word and bit position from a code and an explicit
VERSION observation, then updates that word. Its shared scalar tail starts
at 0xCEC006A6. Together they occupy 56 bytes at file offset 0xC86, with
SHA-256 `6cd1d831bbdeabc3b4279e46b3658898cff0800ca20ffb06d4be33ddf9dc4704`.
The complete control flow defines the general arithmetic below. Nine
standalone calls check selected inputs; they are not an input whitelist.

The operation has no software object, allocation, callback dispatch or
ordinary RAM update. It consumes one VERSION observation and one supplied
32-bit peripheral read, then records one write. The word's physical role,
actual hardware effects and exception entry remain unresolved.

## Inputs and word selection

The native entry receives an opaque word, code Q and value X in r0 through
r2. The opaque word is an arbitrary unsigned 32-bit value and is ignored.
VERSION at 0xCEC006D4 supplies word V;
the load at 0xCEC006BC supplies old word W. Q, X, V and W are arbitrary
unsigned 32-bit values within this computational contract.

| Quantity | Definition | Range |
|---|---|---|
| Bank b | Bits 19 through 16 of V | 0 through 15 |
| Word index j | Bits 5 through 3 of Q | 0 through 7 |
| Shift s | Four times bits 2 through 0 of Q | 0, 4, 8, 12, 16, 20, 24, 28 |
| Address A | 0x7E002010 + 0x800b + 4j | 0x7E002010 through 0x7E00982C |
| Field mask M | 0xF shifted left by s | Four selected bits |
| Shifted value T | X shifted left by s, reduced modulo 2^32 | Unsigned 32-bit word |
| Stored word N | W with bits in M cleared, then bitwise OR with T | Unsigned 32-bit word |

The value X is not masked to four bits before shifting. For example,
X=0x10 with s=0 and W=0 stores 0x10, outside the cleared low nibble.
With s=28, the same X shifts entirely beyond bit 31 and contributes zero.
Bits outside M remain from W unless a surviving bit of T sets them.

Bits above Q's low six and bits outside V's 19:16 field do not affect the
address or shift. Address A is four-byte aligned and cannot wrap: the
largest bank contribution is 0x7800 and the largest word contribution is
0x1C. All shifts are below 32. Use unsigned 32-bit arithmetic for mask,
complement, shift and OR; truncation of T is intentional. No data-dependent
branch, loop or subordinate function call changes this computation.

The store at 0xCEC006CA uses the same address A as the load. The function
selects raw zero at 0xCEC006CC and returns naturally at 0xCEC006CE. It does
not report the old word, stored word or write success through that return.
Only ordinary scalar registers r0 through r5 are written; the body does not
touch the stack, LR or SR. Incidental register values are observations, not required
portable API outputs.

## Portable observation contract

The portable operation receives a required request object containing the
opaque word, Q and X, a required immutable observation plan, a required
observer configuration and a separate required 32-bit raw-result object.
The plan contains V, exactly one read address and old word W, and exactly
one permitted write address. Both declared addresses must equal A. No
default VERSION, old word, read address or write permission is supplied.

These explicit observations describe the environment of the scalar call.
They do not identify a physical processor, authorize live MMIO or prove
that every selected bank exists. The implementation never converts A or
the opaque word into a callable or dereferenceable host pointer. It neither
reads hardware nor writes the selected address directly.

After complete preflight, emit exactly these semantic events in order:

| Order | Event | Values |
|---:|---|---|
| 1 | VERSION observation | Full V |
| 2 | Supplied word read | Address A and full W |
| 3 | Word write | Address A and full N |

Use the immutable plan's words for the computation. The observer reports
the events; it does not provide a replacement result or modify the plan.
There are no retries, additional reads or synthetic acquire/release events.
Observers see the incoming raw-result value throughout all three events.
Publish raw zero only after the write event returns normally.

Native event PCs, site index, read index, VERSION destination and preceding
instruction count are recorder metadata. The portable observer reports the
semantic order, words and addresses above without emulating a register file.
The native VERSION event follows two completed instructions and has
`step: 2`; its site index and the read's independent reply index are zero.

## Storage and complete preflight

Validate the whole operation before the first observer call or result
write. Require all API objects and a nonnull observer function. Validate
the complete observation plan, including exact read and write addresses,
before accepting either observation. Arbitrary Q, X, V and W remain valid
when those addresses match the derived A. Do not compare inputs with the
nine recorded profiles or restrict values to a low nibble.

Typed request, plan, observer configuration and raw-result objects require
natural alignment. Their complete host spans must not wrap or overlap one
another, including immutable objects. Check pointer-plus-size arithmetic
before dereferencing fields. Object sizes are fixed; there is no variable
array, byte-view tail or pointer derived from a firmware address.

The caller supplies actual backing, readability, result writability and
lifetime. Integer span checks cannot prove that an arbitrary pointer names
a live allocation. No pointer is retained, allocated or freed. Request,
plan and configuration do not change concurrently or during observations.

An observer context is an opaque host reference and may be null if the
observer accepts it. The operation does not dereference that reference.
Observers return normally, preserve all API objects, avoid reentry and
perform no hardware access. Read-only context references may inspect the
inputs and old result. Mutable observer bookkeeping and all indirectly
writable storage remain disjoint from the API objects. These lifetime,
indirect-storage and observer-behavior requirements are caller premises;
preflight cannot discover arbitrary storage reached by an observer or
prove its side effects. No mutable input provider is invoked after preflight.

Host invalidity emits no events and leaves all API objects and the result
unchanged. Host status is distinct from the native raw-zero return. Once
the three events begin, the immutable valid input plan has no remaining
validation failure. A native recorder rejection can occur after emulated
effects; it does not define portable rollback or unchanged-state failure.

## Caller and exception boundary

The table at 0xCEC01B60 contains 42 service tokens. Entry 10 at 0xCEC01B88
is 0xCEC006D0. The initialization body at 0x0ED005BC passes that token to
lookup wrapper 0x0ED6529A and supplies GP+0xCB488 as its destination.
This static relationship does not establish completed initialization.

The service dispatcher at 0xCEC00DA0 shifts incoming service arguments
r1 through r5 into handler arguments r0 through r4 before its indirect
call at 0xCEC00DBC. For the recorded first-open inputs, the caller at
0x0ED00738 targets wrapper 0x0ED65284 with code 0x5E and value 1.
With explicitly supplied service index 10 and
opaque word 0xD3D3D3D3, the selected body therefore receives opaque
0xD3D3D3D3, code 0x5E and value 1. The index and opaque word are supplied
caller state, not demonstrated initialization or a produced handle.
The first three standalone cases retain those argument words with three
different synthetic read observations.

The service wrapper at 0x0ED65284 reaches SWI0 at 0x0ED6528E. The dispatcher
eventually reaches RTI at 0xCEC00DCA. Neither wrapper, exception entry,
dispatcher execution nor RTI is part of these standalone calls. No supplied
exception frame or service-return stub joins them. Successful standalone
completion does not establish successful [first open](arm-first-open.md).

## Recorded cases and replay

[service-word-update.json](../../tests/vectors/start4/service-word-update.json)
contains the nine complete calls. Its SHA-256 is
`416aeae16ca949d804a282a4d38c6797fb9fc27c41bbba4b2d5f5dfa3812ee7d`.
All storage and external observations are synthetic. Each call enters at
0xCEC006D0 with fresh stack backing, executes the complete body and returns
to an external caller sentinel. There are no computational function stubs.

| Case | Address | Shift | Stored word |
|---|---|---:|---|
| first-open-zero-word | 0x7E00201C | 24 | 0x01000000 |
| first-open-ones-word | 0x7E00201C | 24 | 0xF1FFFFFF |
| first-open-pattern-word | 0x7E00201C | 24 | 0xA1A5A5A5 |
| first-open-clear-field | 0x7E00201C | 24 | 0x10345678 |
| low-field-unmasked-value | 0x7E002810 | 0 | 0x00000010 |
| highest-bank-overflowed-value | 0x7E00982C | 28 | 0x0FFFFFFF |
| last-field-in-word | 0x7E002010 | 28 | 0xF1234567 |
| next-word-full-value | 0x7E003014 | 0 | 0xFFDDFF11 |
| masked-code-version-alias | 0x7E003014 | 0 | 0xFFDDFF11 |

Each call executes 23 instructions and records three events. Totals are
207 instructions, 288 compared scalar register words, 1152 unchanged
stack bytes and 27 events. The independently derived paths cover the
body's 23 PCs and 56 bytes. The recorder measures final state, event order
and instruction counts; it does not export an executed-PC trace. These
finite inputs do not exhaust the general scalar domain.

Use the imported program and versions in [headless analysis](../analysis.md),
with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0xCEC006D0 \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/service-word-update.json /work/analysis/service-word-update.json
cmp tests/vectors/start4/service-word-update.json /work/analysis/service-word-update.json
```

The unchanged [VERSION interface](vpu-version.md#clock-recorder-integration)
binds the exact scalar instruction and observation. Clock's existing
source, descriptor, memory, MMIO-read and write-permission guards remain
active. No IRQ/p16 plan is required by this body.

Four controls reject a missing VERSION plan at 0xCEC006D4, an unscripted
read at 0xCEC006BC, an undeclared write at 0xCEC006CA and a one-instruction
short budget before the natural return at 0xCEC006CE. Each produces no
completed result artifact. The missing-VERSION diagnostic literally says
`vector instruction` because the legacy guard rejects mnemonics beginning
with `v`; the rejected opcode is scalar VERSION. The budget control can
already have recorded the write, so absent output does not imply rollback.

## Open questions

- Physical register role and bank existence. Bind the computed addresses
  to an authoritative register definition or separately approved hardware
  observation before assigning interrupt, routing or other device meaning.
- Actual VERSION and old-word observations. Establish them for the target
  hardware; supplied scalar values do not identify a real processor state.
- Runtime index and opaque word producers. Establish executed initialization
  and caller state before claiming a complete first-open service call.
  The [initialization prefix](driver-initialization.md) clears the first
  lookup destination and prepares its request, but stops before SWI and
  the result store. The cleared word is not a demonstrated lookup result.
- Exception composition. The separate [service initializer](service-initialization.md)
  updates the original table word and completes through its own constructed
  frame at RTI 0xCEC00D80. Establish SWI trap-frame production, vector
  selection, tag interpretation, privilege and the dispatcher's distinct
  return at 0xCEC00DCA before joining the wrapper, dispatcher and selected
  body. Preserve the independent standalone evidence.
