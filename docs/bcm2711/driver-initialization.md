<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Driver initialization before the first SWI

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

The driver table word at 0x0EDFA4DC selects initialization entry 0x0ED005BC.
Two recorded prefixes enter that real body, clear its 96-byte control
span with the actual scalar fill, prepare the first lookup request and
execute DI. Both stop before SWI0 at 0x0ED6528E with nested frames still
live. These observations do not define a portable initialization API or
establish a completed initializer, runtime startup order or service result.

| Entry | File offset | Bytes | Role |
|---|---|---:|---|
| 0x0ED005BC | 0xFFFBC | 92 | Complete initialization body |
| 0x0ED1FDF0 | 0x11F7F0 | 4 | Branch to the actual scalar fill |
| 0x0ED1FE14 | 0x11F814 | 56 | Scalar fill body |
| 0x0ED6529A | 0x164C9A | 36 | Service-token lookup wrapper |
| 0x0ED65284 | 0x164C84 | 22 | Service wrapper containing the SWI boundary |

Body SHA-256 values, in table order, are
`d0e5dc1f987faf09d912a43d47215437165c8e395b7888705ab4fdd3695d5147`,
`cb445a2435e6986911d09398f3a4fd8d6e601d9b166331993f8038cdd5eafa6e`,
`53b507ec19bbc050f208616bbbd6e7673141b97a6b94a93e005c99d00d0c6cec`,
`6b50ce245ee9396c9bcbdb08cd0000fdb038c3f6f3d2e5c4c9dbff22b45cbff9`
and `d886096e0e9c13d778c15f3b223fe12c2f5d13c7b837f007ae666464081d92fa`.
The full source bodies include suffixes not executed by these prefixes.

## Clearing and first lookup preparation

At 0x0ED005CA the initializer calls 0x0ED1FDF0 with destination
GP+0xCB480, fill byte zero and count 96. The branch reaches the
[identified scalar fill](abi.md#library-entry-points) at 0x0ED1FE14.
For the supplied aligned destination, it performs 24 word stores and
returns naturally to 0x0ED005CE. No fill result or memory effect is
substituted by a reply.

All bytes from GP+0xCB480 through GP+0xCB4DF become zero. The cleared span
includes these fields, whose relationships follow the named source sites:

| Offset from GP+0xCB480 | Size | Relationship |
|---|---:|---|
| 0 | 4 | Later initializer store at 0x0ED00610 sets this word to one |
| 4 | 4 | Later request path stores saved status at 0x0ED0072C |
| 8 | 4 | Destination supplied to the first service-token lookup |
| 0x0C, 0x10, 0x14 | 4 each | Destinations supplied by the later three lookup calls |
| 0x18 | 4 | Low mask consumed by the [mask predicate](mask-predicate.md) |
| 0x1C | 4 | High mask consumed by the mask predicate |
| 0x20 through 0x5F | 64 | Remaining bytes in the cleared span |

For original GP 0x0EE04140, the span starts at 0x0EECF5C0 in a segment
with no file-backed bytes. That mapping does not supply its initial
contents. The recorded prefixes start with explicit nonzero synthetic
state and demonstrate the clearing effect if this initializer is entered.
They do not establish when the real startup sequence enters it.

The initializer next forms token 0xCEC006D0 and destination GP+0xCB488,
then calls lookup wrapper 0x0ED6529A at 0x0ED005DA. That wrapper prepares
service index zero, the token and four zero words, then calls service
wrapper 0x0ED65284 at 0x0ED652AE. The service wrapper saves incoming r6,
copies the actual current SR to r6 at 0x0ED65288 and executes DI at
0x0ED6528C under the [IRQ observation contract](vpu-irq.md).

No earlier executed instruction in these prefixes writes SR. The fill's
fused comparisons and loop branches leave it unchanged. DI clears bit 30
and preserves the remaining bits, with explicit no interrupt arrivals.
There is no p16 observation or physical synchronization claim.

## Stop boundary and live frames

The first unexecuted instruction is SWI0 at 0x0ED6528E. The prefixes do
not execute an exception operation, select a trap vector, construct a
trap frame, invoke a service or return through RTI. The existing scalar
unsupported-operation guard remains active at this boundary.

The recorded prefix convention sets both initial outer LR and stop PC
to 0x0ED6528E. The initializer saves that LR in its fresh outer frame.
Its genuine fill call installs return 0x0ED005CE; the frameless fill
consumes that return normally. The initializer's lookup call installs
0x0ED005DE, which the lookup wrapper saves. The wrapper's service call
installs 0x0ED652B2. No initializer or lookup epilogue executes before the
stop, so the initial outer LR is not consumed as a return.

With initial SP 0x24010000, both prefixes stop with SP 0x2400FFEC and
LR 0x0ED652B2. The five changed stack words are:

| Address | Word | Origin |
|---|---|---|
| 0x2400FFFC | 0x0ED6528E | Saved initial outer LR |
| 0x2400FFF8 | 0x0ED005DE | Saved real lookup caller return |
| 0x2400FFF4 | 0xA0000006 | Saved incoming r6 |
| 0x2400FFF0 | 0xA0000007 | Saved incoming r7 |
| 0x2400FFEC | 0xFFFFFFFF | Service wrapper's saved lookup r6 |

Every other declared stack byte remains unchanged. These are frames from
fresh entry execution, not a reconstructed completed-call frame.
A complete initializer would need an ordinary external return address
and a separately established exception transition.

At the boundary, r0 is service index zero, r1 is token 0xCEC006D0,
r2 through r5 are zero, r6 holds pre-DI SR and r7 is destination
0xE40CB488. These are prepared arguments and saved state, not service
results or a raw initializer return.

The lookup-result store at 0x0ED652B6 remains unexecuted. The initializer's
later lookup calls at 0x0ED005EA, 0x0ED005FA and 0x0ED0060A, final store
of one at 0x0ED00610 and epilogue at 0x0ED00616 also remain unexecuted.
The first lookup destination contains zero because fill cleared it;
zero does not demonstrate a resolved service index. The guarded word at
GP+0x3B484 is neither read nor written by these prefixes and remains an
explicit opaque input.

## Recorded prefixes and replay

[driver-initialization.json](../../tests/vectors/start4/driver-initialization.json)
contains the two exact synthetic prefixes, SHA-256
`c6cc285e00a579d19cfdf5694c8981ca5ce17cfd53d4be2d2ad2b5c59bb21b5a`.
Both use GP 0xE4000000, a fresh 128-byte 0xA5 stack view, 16-byte guards
around the 96-byte control span and a disjoint guarded opaque-word span.
Their starting registers and byte patterns are synthetic software inputs.

| Case | Initial control bytes | Incoming SR and saved r6 | Final SR | Instructions |
|---|---|---|---|---:|
| status-bit-clear | 96 copies of 0xC7 | 0x000000A5 | 0x000000A5 | 79 |
| status-bit-set | Byte i is (37i+11) modulo 256, i from 0 through 95 | 0x400000A5 | 0x000000A5 | 79 |

Each contains one ordered DI event at preceding-step count 78. The two
prefixes total 158 instructions, 64 compared register words, 552 observed
bytes and two events. Every ordinary register, stack byte, control byte
and guard byte is compared. Both control spans are zero at the boundary;
all guards and the independent opaque span retain their original bytes.

Independent source-derived paths visit 33 PCs covering 108 bytes, with
29 writes totaling 116 bytes per prefix and no data reads. The recorder
compares final state, event order and instruction totals; it does not
export a PC or memory-access trace. The source-derived write sequence is
distinct from the directly compared final bytes.

Use the imported program and versions in [headless analysis](../analysis.md),
with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0ED005BC 0x0ED1FDF0 0x0ED1FE14 0x0ED6529A 0x0ED65284 \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/driver-initialization.json /work/analysis/driver-initialization.json
cmp tests/vectors/start4/driver-initialization.json /work/analysis/driver-initialization.json
```

The fixture supplies only one DI observation per prefix. It contains no
p16, VERSION, MMIO or computational replies. Four controls reject missing
clear-word backing at 0x0ED1FE36, missing lookup-frame backing at
0x0ED6529A, absent DI observation at 0x0ED6528C and unsupported SWI at
0x0ED6528E. The SWI control starts with ordinary external LR/stop
0x24040000 and fails before executing the instruction. Each control
produces no result artifact. Earlier fill or frame stores can precede
rejection; absent output does not imply rollback.

## Open questions

- Startup ordering and lifetime. Establish the actual invocation order
  and subsequent writes before treating these zeroed masks or control
  fields as live state at first open. The initializer table selection and
  successful prefixes alone do not prove startup ordering.
- Lookup completion and final state. Establish the real SWI/vector/trap
  frame/RTI transition and all four lookup outcomes before accepting the
  output index words, final store of one or complete initializer return.
  The [standalone token lookup](service-token-lookup.md) establishes
  the scalar table result, including index 10 for token 0xCEC006D0. It
  does not prove SWI delivery or the wrapper's destination write.
  The standalone [service word body](service-word-update.md) and
  [service initialization](service-initialization.md) remain separate
  evidence. The latter constructs its own frame and completes through
  pinned RTI semantics; it does not prove SWI trap-frame production or
  this driver initializer's lookup result.
- Opaque first-open word. Identify its actual producer and lifetime;
  the observed clearing span excludes GP+0x3B484. Neither initialization
  prefix nor [driver-open callback](driver-open-masks.md) produces it.
  Separate [original-table startup calls](startup-initialization.md#relation-to-first-open-state)
  clear this word with GP 0x0EE04140. Establish startup ordering,
  intervening writes and address mapping before using that zero at first open.
- Physical interrupt behavior. Resolve the [IRQ questions](vpu-irq.md#open-questions)
  separately. A supplied no-arrival condition and observed SR change do
  not establish real interrupt delivery, exclusion or hardware state.
