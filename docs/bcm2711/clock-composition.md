<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# First fixed clock composition

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Every firmware address below is a VPU virtual address in that file.
The request is `0x0ED55EFA(0x30,600000000,0,0,0,output)`.

This contract joins the [fixed manager request](clock-request.md) to the
actual [source, native-word and divider bodies](clock-driver.md) for one
first request. Two complete calls execute the manager, planner and all
three bodies. Two additional executions stop immediately after source
return to record intermediate state. Those prefixes are evidence for
ordering, not complete requests or additional host operations.

## Fixed entry state

In the identified `start4.elf`, wrapper 0x0ED55EFA takes the normal path
with GP+0xD33F8 zero. The manager at GP+0x3E810 is already initialized;
initializer 0x0EC7E764 performs no clearing, open call or handle write.
The reference table and descriptor addresses remain unchanged. These are
supplied software premises, not results of live initialization.

| Input | Exact value |
|---|---|
| Request identifier / requested word | 0x30 / unsigned 64-bit 600000000 |
| Request argument3 / argument4 | 0 / 0 |
| Initialized flag GP+0x184C / selection GP+0x1564 | 1 / 1 |
| Manager table, state+0x04 | 0x0EDE7F04 |
| Manager handle, state+0x08 / comparison GP+0x3E494 | 0xC10C1234 / 0xC10C1234 |
| Manager reference, state+0x24 | Unsigned 64-bit zero |
| Manager source / divider-rate / count, state+0x44/+0x11C/+0x188 | 0 / 0 / 0 |
| Manager clock cache, state+0x334 | Unsigned 64-bit 500000000 |
| Other bytes in the 1156-byte manager, including notification records | Zero |
| Descriptor-miss bytes, GP+0xD1B88, 86 bytes | Zero |
| Divider/source miss words, GP+0xD1BE4/+0xD1BE0 | Zero |
| Override heads, GP+0xD1B80/+0xD1B7C/+0xD1B78 | Zero |
| Planner input GP+0x3B938 | 1200 |
| Source helper selection/gate/input, GP+0x1568/+0xCC93C/+0xCC940 | 0 / 0 / 1200 |
| Diagnostic byte GP+0xCCE48 | Zero |
| Driver source marker, GP+0x3E6AC | 0x55667788 |
| Driver requested source, GP+0x3E6B0 | Unsigned 64-bit 0x99AABBCC11223344 |
| Driver source cache, GP+0x3E4A8 | Unsigned 64-bit 1000000000 |
| Driver divider marker/count, GP+0x3E72C/+0x3E730 | 0x12345678 / 0x87654321 |
| Native cell, 0x0EE056B0 | Explicit 32-bit zero |

The manager's reference zero is distinct from the source arithmetic's
54000000 divisor and the divider command's 54000000 input described in
the leaf contract. Driver request/cache fields are separate from manager
caches. Preserve their exact initial sentinels; manager initialization
does not supply them. The native cell is separate caller-owned storage,
not an MMIO reply, a manager field or an alias of GP+0x1570.

At 0x0ED64D02, 0x0ED17442 and 0x0ED64D3A, acquisition, diagnostic and
release each receive one literal raw-zero reply with no memory effects.
The mutex identity is GP+0x3E810. The diagnostic's seven defined words
are `(0x4000,0x0EC7EF38,0x30,600000000,0,0,0)` as specified in the
[diagnostic boundary](clock-request.md#diagnostic-boundary). These three
external bodies do not execute. No notification callback is registered.

## Owned dispatch and order

Expose a separate fixed composed operation. It owns manager transitions,
the three nested driver operations, their state/cell effects and the
final output. It accepts immutable source/divider read plans and observers;
it does not accept source/clock/divider literal return words in place of
executing the corresponding operations.

The existing manager providers observe predeclared replies and preserve
all API objects. Installing a state-mutating driver call as one of those
providers exceeds that interface. The separate composed operation must
dispatch the stateful work explicitly. The same restriction applies to
resource-request providers: this contract supplies no resource body.

For the identified `start4.elf`, the owned sequence is:

1. Observe acquisition at 0x0EC7EA1C and diagnostic at 0x0EC7EAC2.
   Numerical caches, output and miss state still have their entry values.
2. Descriptor lookup stores descriptor-miss byte 0x30 equal to 1 at
   0x0ED4719C. The empty pre-change notification pass calls no provider.
3. Planner 0x0ED47D14 consumes 1200, selects source 1200000000 and count 2,
   and sets divider/source miss words to 0x20/0x80 at
   0x0ED47036/0x0ED47446. Store manager count 2 at 0x0EC7ECD2.
4. At 0x0EC7ED44 execute source body 0x0EC7D978 with
   `(0xC10C1234,2,1200000000,0)`. Its source index 2 differs from
   manager source-cache slot 7. Its request/cache stores precede its MMIO.
   Retain its actual raw result, zero or 4, without treating 4 as a host
   error or skipping subsequent work.
5. After source return 0x0EC7ED46, write manager source cache 1200000000
   at 0x0EC7ED6E/+0x02, then divider-rate cache 600000000 at
   0x0EC7EDC2/+0x04.
6. At 0x0EC7EE4A execute selected-word body 0x0EC7C7D0 with
   `(0xC10C1234,0x30,7,5,0x3F800000,0)`. It reads the actual native cell
   twice as zero, writes 0x5A000000, and reads that stored value once.
   Its raw return is zero.
7. At 0x0EC7EECE execute divider body 0x0EC7D5EA with
   `(0xC10C1234,5,2)`. It stores driver marker/count 1/2 before its MMIO
   and returns raw zero after the complete read/write sequence below.
8. Store manager clock cache 600000000 at 0x0EC7EF00/+0x04. The empty
   post-change notification pass calls no provider. Copy the unsigned
   64-bit value 600000000 to output at 0x0EC7EF2A/+0x02.
9. Observe release at 0x0EC7EA34. Restore the manager's raw-zero result
   at 0x0EC7EA38 and complete the wrapper return.

Raw source/clock/divider tuples are exactly `(0,0,0)` and `(4,0,0)`.
Both yield manager raw zero and the same final state/output. No general
nonzero-return policy follows. The actual source return 4 is recorded at
the intermediate stop; the complete exhaustion call records continuation
through both later operations and final raw zero.

## Exact read plans

For source body 0x0EC7D978 in the identified `start4.elf`, the complete
ordered read plan is:

| Read PC | Address | Literal reply |
|---|---|---|
| 0x0EC7DAE0 | 0x7E1020F8 | 0 |
| 0x0EC7DB06 | 0x7E1021E0 | 0x00020016 |
| 0x0EC7DB22 | 0x7E101170 | 0x00345678 |
| 0x0EC7DBD8 | 0x7E1021E0 | 0x00020016 |
| 0x0EC7DC24 | 0x7E101170 | 0x00345678 |
| 0x0EC7DC34 | 0x7E101114 | One 0x200, or exactly 2000 zero words |
| 0x0EC7DC44 | 0x7E101170 | 0x00345678 |

These are the existing enabled-equal and lock-count-exhausted source
profiles. The source writes fraction 0x5A038E39 to 0x7E1022E0 at
0x0EC7DBDA, then 0x5A345678 to 0x7E101170 at 0x0EC7DC2E and again at
0x0EC7DC4E. The lock reads occur between the latter two writes. The
2000-zero profile exhausts the actual finite counter and returns raw 4.

The joined divider body 0x0EC7D5EA uses this additional exact paired
leaf profile:

| Read PC | Address | Literal reply |
|---|---|---|
| 0x0EC7D656 | 0x7E1023E0 | 5 |
| 0x0EC7D69E | 0x7E101100 | 0 |
| 0x0EC7D69E | 0x7E101100 | 0 |
| 0x0EC7D69E | 0x7E101100 | 0 |
| 0x0EC7D6B6 | 0x7E101170 | 0x00345678 |

For each next divider byte 4, 3 and 2, write `0x5A000000 | next_byte`
to 0x7E1023E0 at 0x0EC7D67C, write command 0x5A00021C to 0x7E101100 at
0x0EC7D69C, then consume its zero reply. Write 0x5A000002 again at
0x0EC7D6B0. Consume the final 0x00345678 and write 0x5A345678 to
0x7E101170 at 0x0EC7D6C0.

This five-read pair extends the divider leaf domain by exactly one pair.
It does not make final 0x00345678 interchangeable with 0x0034567A in
other profiles. Equal final write values do not make distinct read plans
equivalent. Command polls have no software timeout here; their supplied
zeros bound these observations. Neither missing replies nor command-plan
exhaustion is the source's raw-4 result. No read value is inferred from a
preceding write.

The native cell has no scripted read plan. Its reads/writes at
0x0EC7C918, 0x0EC7CB0A, 0x0EC7CB16 and 0x0EC7E66A access actual storage.
The second native cell 0x0EE056B4, later enable-byte lookup and
GP+0x1570/+0x04 are not reached or supplied by the joined fixture.
The composed interface requires no firmware enable-byte input or lookup.
An adapter using the existing word helper supplies zero in its required
but unreachable enable field as an internal compatibility constant; that
constant is not an observation of firmware or hardware state.

## State visibility and host validation

For the identified `start4.elf`, the intermediate source-return stop at
0x0EC7ED46 and the complete return establish:

| Field | At source return | At complete return |
|---|---|---|
| Manager source cache | 0 | 1200000000 |
| Manager divider-rate / count | 0 / 2 | 600000000 / 2 |
| Manager clock cache | 500000000 | 600000000 |
| Descriptor miss / divider miss / source miss | 1 / 0x20 / 0x80 | Same |
| Driver source marker / requested / cached | 1 / 1200000000 / 1200000000 | Same |
| Driver divider marker / count | 0x12345678 / 0x87654321 | 1 / 2 |
| Native cell | 0 | 0x5A000000 |
| Caller output | Unchanged | Unsigned 64-bit 600000000 |

Do not precompute these final mutations before dispatch. During source
observations the manager source/divider-rate/clock caches retain their old
values; its count and miss fields have already changed. During native-word
and divider observations, manager source/divider-rate caches have changed,
while manager clock cache and output retain their old values. Release
observes completed state/output. Driver observers preserve manager objects
as well as their own inputs, plans, state, cell and results. Native-write
observation follows its store; all leaf observations precede the leaf's
raw-result store.

General cache stores are not individual fixture events. The two source
snapshots and the store addresses above establish their order. Tests of
other callback-visible fields are explicit checks of this order, not a
claim that every callback captured a full state buffer. Compare the
recorded event kind/address/word order and final state directly. Event PCs,
synthetic GP/SP values and incidental register words are evidence
locations, not a portable caller ABI or executable host pointers.

Caller-owned storage includes the manager byte span, manager miss state,
source state, divider state, native cell, output, immutable inputs/plans,
observers and result words. Preserve these as distinct objects. The caller
establishes actual backing, lifetime, writability and typed alignment.
Executable preflight checks required pointers, declared lengths,
address-wrap bounds, pairwise overlap, exact entry profile, both complete
read plans and every reachable observer before acquisition or any effect.
Use the complete declared extents for overlap checks, not only bytes later
written. Buffer guards and tails remain unchanged.

Preflight covers the entire path, including the final divider plan. A bad
divider plan must not leave an earlier source update, cell store or
acquisition observation. Missing, extra, mismatched or unsupported plan
records fail before execution. A host validation error preserves every
state, cell, output and result byte and emits no observation. Keep host
status separate from each actual driver raw word, manager raw result and
the eight-byte requested-rate output. Store the composed result only after
release; the observer cannot replace an actual leaf result with a forecast
literal or a host error code.

Observers return normally and use separate bookkeeping storage. They may
not mutate API objects, reenter the operation, perform hardware access or
change the native cell asynchronously. Dynamic callbacks, undeclared
replies and mid-operation provider failures have no defined recovery or
rollback behavior in this contract.

## Exact fixture and replay

The [clock-composition.json](../../tests/vectors/start4/clock-composition.json)
fixture has SHA-256
`392fb2777fd26be429765748d346558cff34e83542ca8c50997fa04d79b00ad4`.
Its four executions of the identified `start4.elf` are:

| Case | Stop / raw word | Instructions | MMIO reads/writes | Cell reads/writes |
|---|---|---:|---|---|
| composed-immediate | Complete return / 0 | 1647 | 12 / 11 | 3 / 1 |
| composed-lock-exhausted | Complete return / 0 | 11642 | 2011 / 11 | 3 / 1 |
| source-return-immediate | Before 0x0EC7ED46 / 0 | 1185 | 7 / 3 | 0 / 0 |
| source-return-lock-exhausted | Before 0x0EC7ED46 / 4 | 11180 | 2006 / 3 | 0 / 0 |

Only the first two rows are whole-call implementation comparisons. They
restore SP and observe all declared state/output guards. The last two rows
retain active frames and untouched output; their event streams equal the
corresponding complete-call prefixes. They check the intermediate source
return and must not require a portable partial-execution API. Across all
four executions there are 25654 instructions, 4036 MMIO reads, 28 MMIO
writes, six native reads, two native writes and ten literal external calls.

Use the imported program and versions in [headless analysis](../analysis.md).
Run from the repository root with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0ED55EFA 0x0EC7EA02 0x0EC7E764 0x0EC7EA3C 0x0EC7AE8A \
  0x0ED479FE 0x0ED4714E 0x0EC7E8E6 0x0ED47D14 0x0ED4700A \
  0x0ED47414 0x0EC2F8AE 0x0EC2F8DA 0x0EC2F7D2 0x0EC2F9B8 \
  0x0EC2FBDA 0x0EC635DA 0x0ED204F6 0x0EC7A7E4 0x0EC79C42 \
  0x0EC7D978 0x0ECC47B6 0x0EC7B9E0 0x0EC7C7D0 0x0EC7AC52 \
  0x0EC7E664 0x0EC7E6B2 0x0EC7B978 0x0EC7A2A4 0x0EC7E008 \
  0x0EC7D5EA \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/clock-composition.json \
  /work/analysis/clock-composition.json
cmp tests/vectors/start4/clock-composition.json \
  /work/analysis/clock-composition.json
```

Compare the entire JSON, including the prefixes. The unchanged public
recorder retains instruction-byte equality, unsupported-operation
rejection, exact finite PC/address/word read matching, write allowlists,
unused-reply rejection, declared-memory bounds and step limits. Its only
native-cell exception is the guarded four-byte 0x0EE056B0 region.
Decoding changes transient instruction metadata only; the project is
read-only and firmware bytes remain unchanged.

Wrong first-read PC, a missing final read, an unused extra read, an absent
fraction-write permission, an omitted native cell, an omitted planner
input and replies ending before the first divider command read must each
fail with a diagnostic and no result file. Process exit zero alone does
not establish replay success. These guards do not define vendor errors.

## Open questions

- Initialization and runtime mapping. Establish actual driver acquisition,
  reference relocation, native-cell initialization, ownership and aliases
  before connecting this supplied state to live startup. Cold manager
  requests with actual driver bodies require separate evidence.
- Broader composition. Specify separately repeated requests, a native
  cell initially 0x5A000000, notifications, overrides, planner input 1500,
  lower-source ordering and arbitrary callbacks before accepting them.
  The manager-only cold/repeated profiles do not enlarge this first-call
  domain. A complete resource body and its surrounding MMIO remain
  separate work.
- Physical completion. Establish actual synchronization, register replies,
  timing, achieved rates and ARM-release prerequisites before assigning
  hardware meaning to the requested values or raw return words.
