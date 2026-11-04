<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Fixed resource request composition

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Every firmware address below is a VPU virtual address in that file.
The entry is `0x0ED7C9B0(object,23,1,1)` with a fresh matching object.

Two complete calls execute dependency calculation, selected resource
bodies for masks 0x80 and 0x100, configuration requests, two clock requests
in shared state, control-register requests and the full outer return.
They cover immediate first-source lock observation and finite lock-count
exhaustion. Both return raw zero. This is a conditional software resource
request, not the higher ARM-start wrapper or a hardware launch result.
The separate [higher start composition](arm-start-composition.md) connects
this route to 0x0EC5A81E under exact successful gate and object-binding
premises, with direct lower-return checkpoints.

## Fixed state and boundaries

The [resource-request contract](resource-request.md) defines the manager
record layout and dependency calculation. This composition admits only
its fresh slot-0 path:

| Input in the identified `start4.elf` | Required state |
|---|---|
| Object / record 0 | Present; matching nonzero self identity; logical request word zero |
| Array at GP+0xDA4C4 | 32 records, stride 28 bytes; all bytes other than record 0's self word zero |
| Table / handle / held mask at GP+0xDA984/+0x04/+0x08 | 0x0EDFD200 / 0 / 0 |
| Aggregate pointer at GP+0x14B0 | Separate writable four-byte output |
| Dependency selection GP+0xCD4 | Zero |
| Resource selection GP+0x1564 | 1 |
| Skip / prehook words GP+0xD33F8/+0x04 | 0 / 0 |
| ARM configuration table / handle / service index | 0x0EDE54D4 / 0x61726D11 / 1 |
| Configuration A / B / C / D | 0 / 1 / 0 / 0 |

The configuration locations and field meanings are the opaque inputs in
[ARM control](arm-control.md#configuration-inputs). Dependency selection
zero and resource selection one are different inputs. Resource handle
zero, ARM handle 0x61726D11 and clock handle 0xC10C1234 are distinct words.

The first clock uses every fixed manager, driver, planner, miss/override
and native-cell premise in the
[first clock composition](clock-composition.md#fixed-entry-state):
already initialized manager, reference zero, old clock cache 500000000,
zero manager source/divider rates and count, exact driver sentinels,
planner 1200 and native cell zero. No open or cold initializer executes.
The neighboring native cell and synthetic GP+0x1570/+0x04 remain absent.
The native word is not an MMIO reply or an alias of a manager field.

All remaining external bodies return literal zero without changing memory
or other registers. No caller can supply a different reply in this domain.
The portable argument definitions are:

| Boundary | Defined portable arguments |
|---|---|
| Resource diagnostic, 0x0ED17442 | `(0x4000,0x0ED7CAB0,object_identity,23,1,1)` |
| Each clock diagnostic, 0x0ED17442 | `(0x4000,0x0EC7EF38,0x30,600000000,0,0,0)` |
| Acquire/release, 0x0ED64D02 / 0x0ED64D3A | One opaque mutex identity |
| Configuration service, 0x0ED65284 | `(1,value,offset,0,0,0)` |

The clock diagnostic's seventh word follows the
[static callsite contract](clock-request.md#diagnostic-boundary); each
fixture event records only six physical registers. Registers after a
mutex's first argument are incidental and are not extra portable inputs.
Callback, format, address and mutex identities are opaque tokens, not
callable host pointers. Four separate mutex identities represent manager
GP+0xDA4C0, outer GP+0xFD4, resource GP+0xD33EC and clock GP+0x3E810.

## Resource routing and owned effects

A separate composed operation owns the record/aggregate/prehook changes,
selected bodies, configuration routing, nested clocks, native cell,
control observations and final return. Existing resource and manager
providers preserve their inputs and observe predeclared replies.
Installing a state-changing nested body as one of those providers exceeds
their interface; dispatch the composed work explicitly.

For the identified `start4.elf`, the order is:

1. Observe the resource diagnostic at 0x0ED7C9DE, then acquire the manager
   mutex at 0x0ED7C9E6. Record/request/prehook state retains its input
   values during these calls. Compute old aggregate zero, set record 0's
   bit 23 at 0x0ED7CA0C and recompute aggregate 0x180. Held mask stays zero.
2. Dispatch table slot 0x14 to 0x0ED550B2 with `(0,0x80)` at
   0x0ED7CA94. The body acquires outer then resource mutexes through
   0x0EC58CEE/0x0ED5511C. Prehook 0x0ED56136 ORs mask 0x80 into its
   word at 0x0ED56148. Selection one at 0x0ED55610 goes directly to
   common raw-zero completion. Release resource then outer and return
   to 0x0ED7CA96. This body performs no clock or control-MMIO operation.
3. Dispatch the actual next added bit with `(0,0x100)`. Acquire outer
   then resource again; prehook changes 0x80 to 0x180. Selection one at
   0x0ED55648 selects the following work.
4. Execute configuration 0x0EC5EE2A at 0x0ED55652. Its six service
   `(value,offset)` pairs are `(0xA,0x41C)`, `(0x3030,8)`, `(0x1000,0)`,
   `(0x30,0x4F5200)`, `(0xF,0x4F5204)` and `(0x210,0x4F5220)`.
   These are requested values. Supplied service return words are zero;
   privileged-service effects remain unverified.
5. Wrapper 0x0EC80D02 with argument 1 calls 0x0EC80D20. Clear the shared
   eight-byte rate scratch to zero at 0x0EC80D28/+0x06, then run the
   first real clock request at 0x0EC80D40. Execute one control phase
   below after that request returns.
6. Wrapper 0x0EC80CA4 with argument 1 calls 0x0EC80D20 again. Clear the
   same scratch to zero again, retain all manager/driver/native state,
   run the repeated clock request and execute the second control phase.
7. Execute the final clear/poll operations below. Common completion sets
   the selected result to zero at 0x0ED554AC, releases resource at
   0x0ED554B0 and outer through actual wrapper 0x0EC590BC. Restore the
   resource frame at 0x0ED554DE/+0x02 and return to 0x0ED7CA96.
8. The manager checks that actual zero result, completes its remaining
   bit scan, releases the manager mutex at 0x0ED7CAA8 and returns raw
   zero after its saved-frame restoration at 0x0ED7CAAE.

The aggregate is written as zero before the request-word store and as
0x180 afterward. At the resource acquisitions, request bit 23 and aggregate
0x180 are already set. Each prehook store follows its acquisitions and
precedes its releases or body work. General RAM stores are not individual
fixture events; these ordering statements use the identified store/call
positions together with the complete traces and final state.

## Two clock calls in persistent state

The first request follows the [first composition](clock-composition.md),
including its exact five-read divider pair and actual source raw result
zero or 4. It continues through native-word and divider operations in both
cases. The manager returns zero and writes unsigned 64-bit 600000000 to
the shared scratch before its clock release.

The second request starts from the first request's actual mutations:

| State | Value retained into the second request |
|---|---|
| Manager source / divider-rate caches | 1200000000 / 600000000 |
| Manager divider count / clock cache | 2 / 600000000 |
| Descriptor-miss byte 0x30 / divider miss / source miss | 1 / 0x20 / 0x80 |
| Driver source marker / requested / cached | 1 / 1200000000 / 1200000000 |
| Driver divider marker / count | 1 / 2 |
| Native word | 0x5A000000 |

The first control phase does not mutate these software fields. At
0x0EC7EC70–0x0EC7ECA0, the second request finds the selected source already
equal. At 0x0EC7ED98–0x0EC7EDAC it finds
`600000000 × 2 = 1200000000` and clears its pending divider request.
It performs acquisition, diagnostic, selected native-word operation and
release, with no source or divider call. Planner inputs remain required.
The manager caches and miss state remain unchanged; the scratch is written
as 600000000 after its explicit second zeroing.

This adds only the matching-handle selected-word profile with initial
native cell 0x5A000000 and fixed arguments
`(0xC10C1234,0x30,7,5,0x3F800000,0)`. The actual cell is read at
0x0EC7C918 and 0x0EC7CB0A, has bit 4 cleared and is ORed with
0x5A000000 for the store at 0x0EC7CB16, then is read at 0x0EC7E66A.
All three read values and the written value are 0x5A000000; raw return is
zero. No external mutation or scripted native-cell read exists.

Updated source/divider state is carried unchanged. It is not a new
supported initial profile for another source or divider operation, since
neither executes again here. The repeated word profile does not admit
arbitrary native cells or another bit-7 exhaustion combination. The
unreached enable-byte input described in the first composition remains
unreached on this second word path.

## Ordered control phase

Each 0x0EC80D20 call in the identified `start4.elf` performs the same
algorithm after its clock request. All arithmetic below uses unsigned
32-bit words. Let `P = 0x5A000000`, `A = 0x7E1023E0`,
`B = 0x7E100110`, `C = 0x7E101170` and `Q = 0x7E101100`.
These abbreviations label numeric addresses without assigning device roles.

1. Read A at 0x0EC80D50 and retain this word as `saved`. Read 0x7E1021E0
   at 0x0EC80D52. At 0x0EC80D66 write
   `(saved & 0xFFFFFF00) | (reply & 0x3FF) | P` to A. The ten-bit mask
   is deliberate; it is not truncated to the eight cleared bits.
2. Read 0x7E1000FC at 0x0EC80D68 even though its value is not used in
   the later write arithmetic. Read B at 0x0EC80D74 and write
   `(reply & 0xFFFFF000) | P` at 0x0EC80D84.
3. Write `P | 0x10` to Q at 0x0EC80D8A, then poll Q at 0x0EC80D90
   until its supplied word is zero.
4. Perform the following nine rows in order. Each row reads its target,
   computes and writes the stated word, writes `P | 8` to Q, then polls
   Q at the listed PC until zero. Every target read is a fresh supplied
   observation, independent of prior writes.

| Row | Target / read PC | Written expression | Write PC | Q write / poll PC |
|---:|---|---|---|---|
| 1 | C / 0x0EC80D9C | `reply | P | 2` | 0x0EC80DA6 | 0x0EC80DAE / 0x0EC80DB2 |
| 2 | B / 0x0EC80DBE | `reply | P | 0x400` | 0x0EC80DC6 | 0x0EC80DC8 / 0x0EC80DCE |
| 3 | C / 0x0EC80DD4 | `(reply & 0xFFFFFFFD) | P` | 0x0EC80DE0 | 0x0EC80DE2 / 0x0EC80DE6 |
| 4 | C / 0x0EC80DEC | `reply | P | 2` | 0x0EC80DF6 | 0x0EC80DF8 / 0x0EC80DFC |
| 5 | B / 0x0EC80E02 | `reply | P | 0x800` | 0x0EC80E0A | 0x0EC80E0C / 0x0EC80E12 |
| 6 | C / 0x0EC80E18 | `(reply & 0xFFFFFFFD) | P` | 0x0EC80E24 | 0x0EC80E26 / 0x0EC80E2A |
| 7 | C / 0x0EC80E30 | `reply | P | 2` | 0x0EC80E3A | 0x0EC80E3C / 0x0EC80E40 |
| 8 | B / 0x0EC80E46 | `reply | P | 0x3FF` | 0x0EC80E4E | 0x0EC80E50 / 0x0EC80E56 |
| 9 | C / 0x0EC80E5C | `(reply & 0xFFFFFFFD) | P` | 0x0EC80E68 | 0x0EC80E6A / 0x0EC80E6E |

5. Write `saved | P` to A at 0x0EC80E7A. Read 0x7E1000FC once more at
   0x0EC80E7C before returning. Preserve this read in the observations.

Each phase therefore has 22 writes, ten command polls and 24 reads in the
recorded domain. Its complete literal read plan is fixed as follows;
the same plan is supplied separately for both phases:

| Read location or ordered group | Literal replies |
|---|---|
| A at 0x0EC80D50 | 0x12345678 |
| 0x7E1021E0 at 0x0EC80D52 | 0xABCDE155 |
| 0x7E1000FC at 0x0EC80D68 / 0x0EC80E7C | 0x13579BDF / 0x2468ACE0 |
| B at 0x0EC80D74 / 0x0EC80DBE / 0x0EC80E02 / 0x0EC80E46 | 0x00123ABC / 0x00123000 / 0x00123400 / 0x00123C00 |
| C at 0x0EC80D9C / 0x0EC80DD4 / 0x0EC80DEC / 0x0EC80E18 / 0x0EC80E30 / 0x0EC80E5C | 0x12345670 / 0x12345672 / 0x12345670 / 0x12345672 / 0x12345670 / 0x12345672 |
| Each of the ten Q polls, in algorithm order | One zero word each |

The two phases compute their writes from these reads and saved words;
they do not play back an expected write array. The exact finite plan is
the supported input domain. Additional delay words, changed data words
or different pairings require separate evidence. The vendor command loops
have no software count limit here; rejecting a missing terminating reply
is a host validation result, not a fabricated firmware timeout.

## Final clears and polls

After the second phase, 0x0EC80CE0 reads 0x7E00B440 at 0x0EC80CE6,
clears bit 9 and writes at 0x0EC80CEA. The reply is 0xFFFFFFFF and the
written word is 0xFFFFFDFF.

At 0x0ED55668, read 0x7EC11018 as 0x12345679; clear bit 0 and write
0x12345678 at 0x0ED5566E. Next read 0x7EC1101C as 0xABCDEF91 at
0x0ED55670; clear bit 0 and write 0xABCDEF90 at 0x0ED55676.
Poll 0x7EC11018 at 0x0ED55678 until bit 1 is clear, then poll
0x7EC1101C at 0x0ED5567E for the same condition. The exact supplied
poll replies are one 0x12345678 and one 0xABCDEF90. The loops have no
firmware count limit on this path. No BCM2711 device role is assigned
to these two addresses by this contract.

## Results, visibility and portable preflight

The full operation has three diagnostics, seven acquisitions, seven
releases and six service calls. Its observable order is:
resource diagnostic, manager acquire; mask-0x80 outer/resource acquires
and resource/outer releases; mask-0x100 outer/resource acquires; six
services; first clock including its own acquire/diagnostic/release;
first phase; second clock including its own acquire/diagnostic/release;
second phase; final clears/polls; resource/outer releases; manager release.
Enable bodies and clocks are actual nested work, not extra intercepted
enable events.

The output record has bit 23 set, aggregate is 0x180, held mask is zero
and prehook is 0x180. Clock/driver/native state has the values in the
persistent-state table. The shared rate scratch ends as unsigned 64-bit
600000000. The full returned word is zero in both source-lock profiles.
Inner source raw 4 is established by the first composition's source-return
prefix; these complete resource calls observe its continuation and final
zero rather than adding a new inner-return snapshot.

Before each nested clock acquisition, the same logical scratch has been
cleared to zero. Its first result is not left visible as the second clock's
incoming output. Other state is not reset. Service observers precede the
first scratch clear; the first phase observes completed first-clock state;
the second phase and final releases observe the retained state and second
completed output. Store-order checks follow the cited instructions;
the fixture does not contain every RAM byte at every external call.

The portable composed interface owns distinct record/aggregate/held/
prehook state, configuration, clock-manager state and miss fields, source
and divider state, one native word, one shared eight-byte scratch, immutable
read plans, observers and final raw-result storage. A portable scratch view
represents an internal native stack object, not a recovered native function
parameter. Initial scratch/aggregate contents are preserved until their
specified writes; the fixture supplies 0xA5 bytes. Its opaque object
identity is nonzero and equals record 0's self identity. All other record
words are zero. Do not expose native table addresses as dereferenceable
pointers or conflate the separate mutex/handle identities.

Preflight validates every required pointer, declared extent, address wrap,
pairwise overlap, fixed input/state profile, every reachable observer and
all complete nested read plans before the initial resource diagnostic or
any state write. This includes both control phases and final polls.
The second source/divider calls are unreachable and have no reply plan.
The second native word derives from the first operation's actual store;
it is not another caller-supplied state snapshot. Predictable internal
continuation must not encounter an unvalidated helper domain and silently
translate a host error into raw zero.

Host errors preserve all state, scratch and results and emit no events.
Caller-owned objects remain backed, aligned where typed, writable where
required and alive through the call. Preflight cannot prove actual backing
or lifetime. Keep provider bookkeeping and indirectly referenced storage
separate from all API objects. Observers may inspect state and update only
their separate bookkeeping; they return normally, preserve API objects,
avoid reentry/concurrent mutation and perform no hardware access.
Native-write observations follow the actual store. Raw composition-result
storage is written only after the final manager release. Keep host status,
actual nested raw results, logical rate output and hardware outcome distinct.

This domain has no context failure or stopped outcome. The separate
[tagged context contract](resource-request.md#false-condition-context)
remains unchanged. A duplicate request, held/shared suppression, nonzero
enable reply, disable, arbitrary request or higher ARM-start wrapper is
outside this composition. No normal unwind after an unsupported stop is
implied.

## Complete-call fixture and replay

The [resource-composition.json](../../tests/vectors/start4/resource-composition.json)
fixture has SHA-256
`1f6df457d17a969dcbd429b08dc1a7cc78ee72a49adc8c1ba3dcae7d5a310c2d`.

| Case | Instructions | MMIO reads/writes | Native reads/writes | External calls | Returned word |
|---|---:|---|---|---:|---|
| start-immediate | 4575 | 65 / 58 | 6 / 2 | 23 | 0 |
| start-first-source-lock-exhausted | 14570 | 2064 / 58 | 6 / 2 | 23 | 0 |

Both calls start at the actual manager entry and use external return
sentinel 0x24040000. Actual prologues form the 32-byte manager frame and
the 36-byte saved plus 20-byte local resource frame. The shared clock
output is initial SP minus 120. The real resource and manager epilogues
restore initial SP and all observed saved registers. These complete
frames are not copied from the earlier resource-prefix fixture, whose
outer LR was seeded with an internal stop address.

Each case compares 2575 specified memory bytes, including every declared
non-stack region, the eight-byte scratch and two 64-byte stack-edge guards.
Other saved-stack bytes are not observed. The complete ordered events and
specified registers are compared. Native GP/SP, incidental registers,
instruction counts and PCs describe the reference execution, not a host
calling convention. The two complete calls total 19145 instructions,
2129 MMIO reads, 116 MMIO writes, 12 native reads, four native writes and
46 external boundaries.

Use the imported program and versions in [headless analysis](../analysis.md).
From the repository root, with a fresh output path:

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
  0x0EC7D5EA 0x0EC5EE2A 0x0EC534A2 0x0ED6D2DA 0x0EC80D02 \
  0x0EC80CA4 0x0EC80D20 0x0EC80CE0 0x0ED550B2 0x0EC590BC \
  0x0ED7C9B0 0x0ED7C744 0x0ED7C768 0x0ED7C786 0x0ED7C832 \
  0x0ED56032 0x0ED7C840 0x0ED55CD4 0x0ED00582 0x0EC52ED2 \
  0x0EC58CEE 0x0ED56136 0x0ED64C08 \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/resource-composition.json \
  /work/analysis/resource-composition.json
cmp tests/vectors/start4/resource-composition.json \
  /work/analysis/resource-composition.json
```

The unchanged public recorder rejects altered instructions, unsupported
operations, undeclared memory/writes, mismatched or missing MMIO replies
and unused replies. Only its existing guarded four-byte native-cell
exception is allowed. Decoding changes transient metadata only; project
and firmware bytes remain unchanged.

Negative controls remove the native cell, planner input, aggregate pointer,
final read, command replies or seventh manager release; alter the first
read PC; add an unused reply or spurious second source/divider read; or
remove a fraction-write permission. Each must report its strict diagnostic
and produce no result file. A zero headless-process status alone is not
evidence of successful execution. These failures are recorder controls,
not firmware error codes.

## Open questions

- Runtime preparation. Establish registration, real table relocation,
  state acquisition, native-cell initialization, aliases and ownership
  before binding these supplied inputs to a live startup.
- Privileged and concurrent effects. Verify real open/mutex/context/service
  bodies, exception handling and callback mutation before extending the
  literal-zero unchanged-state boundary contract.
- Other software paths. Record disable, duplicate/shared requests,
  context-stop routing, higher ARM callers, other masks and additional
  clock domains separately. Do not combine standalone profiles freely.
- Physical completion. Establish register meanings, readback/timing,
  memory/cache visibility and reset/entry prerequisites before treating
  request order, raw zero or a numerical rate as physical completion.
