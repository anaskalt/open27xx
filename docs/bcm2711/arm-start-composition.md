<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Fixed ARM start-request composition

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Every firmware address below is a VPU virtual address in that file.
The entry is `0x0EC5A81E(0x61726D11)`.

Two complete calls join the [higher start-request gate](arm-control.md#start-request-software-state)
to the actual [fixed resource composition](resource-composition.md).
They differ only in the first source-lock observations: one matching
word, or exactly 2000 zero words. Both lower resource calls return zero;
both higher calls set their active word to 1 and return zero after their
own mutex release. These are conditional software results, not evidence
of an ARM entry address, physical clock/reset completion or ARM execution.

## Entry state and object binding

The identified `start4.elf` higher call uses four distinct 32-bit words:

| GP-relative location | Exact supplied value | Meaning on this route |
|---|---|---|
| 0x3B474 | 1 | Open-count gate |
| 0x3B518 | 1 | Mapping-state gate |
| 0x3B494 | 0 | Inactive state |
| 0x3B478 | Existing resource record 0 identity | Object passed to the lower request |

The fixture uses GP 0xE4000000 and resource-object word 0xE40DA4C4.
That word equals record 0's self identity at GP+0xDA4C4. This is an
explicit supplied binding. It does not identify the object's runtime
producer or prove registration, ownership, open state or actual mapping.
Represent the same relationship with an opaque nonzero token shared by
the higher object field, lower request identity and record 0's self word.
The token is not a dereferenceable host pointer. No other record binding
or object relationship is included.

All [fixed resource entry premises](resource-composition.md#fixed-state-and-boundaries)
apply unchanged: fresh record 0, no other requests, held mask zero,
dependency selection zero, resource selection one, prehook zero,
configuration A/B/C/D equal to 0/1/0/0, initialized reference-zero clock
manager, planner 1200, exact driver sentinels and native cell zero.
The two source plans, both control phases and final poll replies are
exactly those in the resource composition. No new MMIO read profile,
native-cell state or driver argument is added.

The four higher words occupy separate four-byte regions disjoint from
every lower region. In particular, configuration service index GP+0x3B490
and higher active word GP+0x3B494 are adjacent distinct fields. The higher
mutex at GP+0x3B470 is distinct from the resource-manager, resource-outer,
resource and clock mutexes at GP+0xDA4C0, GP+0xFD4, GP+0xD33EC and
GP+0x3E810. The higher/ARM handle 0x61726D11, resource handle zero,
clock handle 0xC10C1234 and object identity remain separate values.

Every external acquire, release, diagnostic and configuration-service
boundary has a literal raw-zero reply and preserves memory and other
registers. These bodies do not execute. Mutex boundaries have one defined
argument, their opaque identity; trailing recorded registers are incidental.
The lower diagnostic/service arguments retain their
[existing definitions](resource-composition.md#fixed-state-and-boundaries).
The actual resource entry and selected bodies are never supplied replies.

## Owned sequence and result order

Use a separate composed operation that owns higher state and the nested
resource work. The existing higher resource callback is a scalar reply
boundary; its standalone observations do not authorize arbitrary nested
effects or represent a stopped resource outcome. Dispatch the real fixed
lower operation explicitly and retain its actual result.

For the identified `start4.elf`, the sequence is:

1. Form the higher 16-byte saved frame at 0x0EC5A81E and call acquire
   0x0ED64D02 at 0x0EC5A82C with identity GP+0x3B470. All higher and
   lower state retains its entry values during this observation.
2. At 0x0EC5A830–0x0EC5A850, check handle 0x61726D11, open count,
   mapping marker and active state. The exact supplied 1/1/0 values
   select the accepted successful route. Load the bound object word
   at 0x0EC5A854.
3. At 0x0EC5A85C call actual 0x0ED7C9B0 with `(object,23,1,1)`.
   Execute the complete resource sequence: diagnostic and manager
   acquisition, masks 0x80 then 0x100, configuration, two clocks in
   persistent state, both control phases, final clears/polls, all
   resource releases and the lower manager release and return.
4. At the return position 0x0EC5A860, the actual lower raw word is zero
   and higher active remains zero. Preserve that raw word separately.
   The comparison at 0x0EC5A862 reaches the active store of 1 at
   0x0EC5A868.
5. Call release 0x0ED64D3A at 0x0EC5A86C with the higher mutex identity.
   Its observer sees active 1 and completed lower state. Restore the
   retained result at 0x0EC5A870 and unwind at 0x0EC5A872. The higher
   returned word is zero; its release reply does not replace it.

The two clocks retain their shared state and scratch relationship. The
enclosing wrapper clears the same scratch to zero before each clock
request; both requests produce 600000000. The second clock skips
source/divider work and uses the first clock's actual native-cell result.
No state is reset between these calls.
The complete resource's final record bit 23, aggregate/prehook 0x180,
held zero and final clock/driver/native state all persist after the higher
return.

The source-lock exhaustion route still performs the later word, divider,
control and release work. Source raw 4 is established by the earlier
[source-return evidence](clock-composition.md#exact-fixture-and-replay).
These higher fixtures directly record lower resource raw zero and higher
raw zero; they do not add another inner source-register snapshot.

## Visibility, storage and preflight

Higher active remains zero throughout all lower observations, including
the lower manager release. The direct return checkpoint still sees zero;
only the subsequent higher store changes it to 1 before the higher release.
Open count, mapping marker and resource-object word remain unchanged.
General state stores are not individual recorded events. The checkpoints
and cited store/call positions establish this order; full memory is not
sampled at every callback. Observers must preserve every higher and lower
API object and may update only separate bookkeeping storage.

The caller supplies distinct higher state, lower record/aggregate/held/
prehook state, configuration, clock-manager and driver state, native cell,
shared rate scratch, immutable inputs/read plans, observers and result
storage. Preserve the lower operation's ownership and disjointness rules.
The native scratch is an internal stack object; a portable scratch view
does not turn its synthetic address into a host parameter or ABI rule.

Validate the entire higher and lower operation before the first higher
acquisition or any effect. Preflight covers required pointers, complete
declared extents, address wrap, pairwise overlap, the exact gate and
object-binding profile, every reachable observer, all nested read plans,
both control phases and final polls. It must also
cover the predictable repeated-clock state. A lower validation error
must not first be discovered after emitting the higher acquisition.
Missing fields must not become inferred zeros or enlarged backing regions.

The caller establishes actual backing, typed alignment, lifetime and
writability. Preflight cannot prove backing or lifetime. Host validation
errors preserve all higher/lower state, scratch and result bytes and emit
no observations. Observers return normally, preserve API objects, avoid
reentry and concurrent mutation, and perform no hardware access.
Undeclared replies and mid-operation
provider failures have no recovery or rollback policy in this contract.

Keep host status, actual lower raw result, actual higher raw result,
active state and the clock-rate scratch separate. The lower result is
available only after its complete return. Store final composed result
storage only after the higher release. A forecast literal zero or a host
status cannot substitute for the actual nested result. Active 1 and raw
zero do not report a physical completion status.

## Returned-only domain

This composition accepts exactly the successful handle/open/mapping/active
profile above and the two complete lower read plans. Standalone higher
gate rejections, other nonzero gate values, nonzero mutex replies,
resource reply 7, shared/held/duplicate resource requests, notifications
and arbitrary callback effects are not additional combinations here.

The [resource context contract](resource-request.md#false-condition-context)
distinguishes `RETURNED(raw)` from `STOPPED(stop_flag=1)` before 0x0ED7C75A.
The latter has no vendor return word. A direct context callback's returned
7 is separate from a stopped manager/check prefix whose register contains
7. Converting a stopped outcome or its host status to scalar zero or 7
would invent a resource return, an active-state decision and a normal
higher release.

The fixed fresh lower route has no false check: its request bit is clear
and both actual selected bodies return zero. No context descriptor,
GP+0xE50/+0xE54 state or context reply is supplied or consumed. A portable
adapter must establish this returned-only domain in preflight; it cannot
accept a general tagged resource outcome and discard its tag. No normal
unwind or higher release after a stopped outcome is defined here.

## Exact fixture and replay

The [arm-start-composition.json](../../tests/vectors/start4/arm-start-composition.json)
fixture has SHA-256
`07f454c21c78b6302929e1aa5d086dc123cf3bbbd5920eacfc4dd47dc8820c98`.
Its four executions of the identified `start4.elf` are:

| Case | Stop | Instructions | Raw at stop / active | MMIO reads/writes | Native reads/writes |
|---|---|---:|---|---|---|
| higher-start-immediate | Complete return | 4603 | 0 / 1 | 65 / 58 | 6 / 2 |
| higher-start-first-source-lock-exhausted | Complete return | 14598 | 0 / 1 | 2064 / 58 | 6 / 2 |
| higher-resource-return-immediate | Before 0x0EC5A860 | 4595 | 0 / 0 | 65 / 58 | 6 / 2 |
| higher-resource-return-first-source-lock-exhausted | Before 0x0EC5A860 | 14590 | 0 / 0 | 2064 / 58 | 6 / 2 |

Only the first two rows are whole-call implementation comparisons. Each
has eight acquisitions, eight releases, three diagnostics and six service
boundaries. Complete calls total 19201 instructions. The prefixes omit
the final higher release and total 19185 instructions. Their event
streams exactly equal the corresponding full-call prefixes. They verify
the lower returned word and intermediate active state, not a portable
partial-execution operation.

Each input has 37 disjoint regions containing 6615 bytes: the 6599-byte
resource setup plus four higher words. The existing 4160-byte stack starts
entirely as 0xA5; no saved frames or result bytes are inserted. The higher
prologue adds 16 bytes before the lower frames, moving the shared clock
scratch from initial SP minus 120 to initial SP minus 136, at 0x2400FF78
for supplied initial SP 0x24010000.

Each execution compares 2591 specified bytes: 2455 non-stack state/output
bytes, eight scratch bytes and two 64-byte stack-edge guards. Other
initialized interior-stack bytes are not observed. Complete calls restore
SP 0x24010000 and observed saved registers. Prefixes retain SP 0x2400FFF0,
r6/r7 equal to the higher mutex identity and r8 equal to 0xFFFFFFFF.
The prefix harness seeds incoming LR with internal stop 0x0EC5A860;
those active frames cannot replace the complete caller frame. Complete
calls use external return sentinel 0x24040000. These locations and
incidental register values are evidence, not host calling conventions.

Use the imported program and versions in [headless analysis](../analysis.md).
From the repository root, with an unused output path:

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
  0x0EC58CEE 0x0ED56136 0x0ED64C08 0x0EC5A81E \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/arm-start-composition.json \
  /work/analysis/arm-start-composition.json
cmp tests/vectors/start4/arm-start-composition.json \
  /work/analysis/arm-start-composition.json
```

Compare the entire JSON, including both prefixes. The unchanged public
recorder retains source/instruction identity, unsupported-operation
rejection, exact finite MMIO replies, write allowlists, unused-reply
rejection, declared-memory bounds and its sole guarded four-byte native
cell. The 54-entry decoder changes transient instruction metadata only;
the project is read-only and firmware bytes remain unchanged.

Omitting the higher object word must fail at 0x0EC5A854; omitting open
count must fail at 0x0EC5A83E; removing the final higher release reply
must fail at 0x0ED64D3A. Each requires its own diagnostic and absent
result file. A zero process exit alone is insufficient. These strict
harness rejections do not establish portable preflight atomicity or
firmware error returns.

## Open questions

- Runtime preparation. Establish the writers of the higher gate/object
  words and the object's registration, ownership and mapping before
  treating the supplied binding as a live initialization path.
- Broader outcomes. Record other higher gate/reply combinations and
  stopped lower routes separately before defining another composition
  domain, stop-capable outer interface or recovery behavior.
- Physical completion. Verify real mutex/service effects, register
  readback/timing, memory/cache visibility and ARM entry/reset prerequisites
  before treating the software active flag or raw zero as a hardware result.
