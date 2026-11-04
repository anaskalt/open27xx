<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Fixed clock programming callbacks

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`,
2303104 bytes. Addresses are VPU virtual addresses in that file. The
[request manager](clock-request.md) selects these three complete calls:

| Entry | Defined arguments |
|---|---|
| 0x0EC7D978 | `(handle,2,1200000000,0)` |
| 0x0EC7C7D0 | `(handle,0x30,7,5,0x3F800000,0)` |
| 0x0EC7D5EA | `(handle,5,2)` |

The source and divider calls issue MMIO reads and writes under finite
supplied read plans. The selected-clock call instead accesses a single
word in mapped, uninitialized ELF RAM. These address spaces stay distinct.
The 22 cases use the original reference-address descriptors and explicit
cached state. They establish software effects and raw results, not live
initialization, physical lock, elapsed time or an achieved clock rate.

The [first clock composition](clock-composition.md) joins these bodies to
the initialized manager and adds one exact divider read pair, beginning
with 5 and ending with 0x00345678. Its separate contract owns nested state
and cell effects. The 22 standalone fixture profiles below stay unchanged.

## Common premises

In the identified `start4.elf`, all three entries compare the incoming
handle with GP+0x3E494 before their programming effects. The source tests
at 0x0EC7D978–0x0EC7D98E, the selected-clock body at
0x0EC7C7D4–0x0EC7C7DE, and the divider at 0x0EC7D5EE–0x0EC7D5F4.
A mismatch returns raw 0xFFFFFFFF without MMIO/native-cell accesses or
observed cache changes. Equality alone does not prove handle acquisition.
The source and divider fixtures use matching 0xC10C1234, or mismatching
0xC10C1235. The selected-clock fixtures also cover equality of two zero
words; that body has no separate nonzero-handle requirement on this path.

Source and divider fixtures supply GP+0x1564=1, selecting the numerical
reference 54000000 where consumed. Source and selected-clock fixtures
supply diagnostic byte GP+0xCCE48=0, preventing their diagnostic branches.
All three sets have no external function-call replies. Real resolvers,
scalar arithmetic and the directly required wait/setup helpers execute.
No interrupt, vector instruction or hardware access occurs outside the
explicit simulated memory operations.

Previous cache/request words, helper selectors and read plans are supplied
inputs. They are not inferred from ELF zero fill, pointer equality or a
live board. A missing input is an error in the host harness, not zero.
Reference-layout pointers do not establish post-relocation live aliases.

## Descriptor fields

The identified `start4.elf` source resolver 0x0ECC47B6 selects descriptor
0x0EDE229C for index 2 at call 0x0EC7D9B6:

| Field address | File offset | Value |
|---|---|---|
| 0x0EDE22A0 | 0x1E1C80 | 0x7E101170 |
| 0x0EDE22A4 | 0x1E1C84 | 0x7E1021E0 |
| 0x0EDE22A8 | 0x1E1C88 | 0x7E1022E0 |
| 0x0EDE22AC | 0x1E1C8C | 0x7E1020FC |
| 0x0EDE22B0 | 0x1E1C90 | 0x7E1020F8 |
| 0x0EDE22B4 | 0x1E1C94 | 0x7E1020F4 |
| 0x0EDE22B8 | 0x1E1C98 | 0x7E1020F0 |
| 0x0EDE22E8 | 0x1E1CC8 | 5000 |
| 0x0EDE22EC | 0x1E1CCC | 600 |
| 0x0EDE22F8 | 0x1E1CD8 | 0x200 |
| 0x0EDE2300 | 0x1E1CE0 | 0x2 |

Resolver 0x0EC7AC52 selects divider descriptor 0x0EDE2204 for index 5.
The source-7 selected-clock path calls it at 0x0EC7C80C; the divider calls
it at 0x0EC7D5FA:

| Field address | File offset | Value |
|---|---|---|
| 0x0EDE2210 | 0x1E1BF0 | 0x7E1023E0 |
| 0x0EDE2214 | 0x1E1BF4 | 0x7E101170 |
| 0x0EDE221C | 0x1E1BFC | 0x2 |
| 0x0EDE2220 | 0x1E1C00 | 1 |
| 0x0EDE222C | 0x1E1C0C | 0xFFFFFFFF, consumed by selected-clock body only |

Clock 0x30 selects descriptor 0x0EDDD690 at 0x0EC7C8B8:

| Field address | File offset | Value |
|---|---|---|
| 0x0EDDD694 | 0x1DD074 | 0x0EE056B0, first word pointer |
| 0x0EDDD698 | 0x1DD078 | 0x0EE056B4, second pointer, not accessed |
| 0x0EDDD6A4 | 0x1DD084 | Zero quantization mask |
| 0x0EDDD6A8 | 0x1DD088 | Zero width byte |

The descriptor fields are in read-only load segment
0x0EDD78C0–0x0EE02B77. The two word pointers address the non-executable
read/write segment 0x0EE056A0–0x0EE05FCF, whose file-backed size is zero.
They do not identify peripheral registers. The supplied first word is not
proof of its runtime initializer or purpose; the second word stays absent.

The [BCM2711 register reference](clocks.md) independently names
0x7E101170 as CM_PLLB, 0x7E1021E0 as A2W_PLLB_CTRL, 0x7E1022E0 as
A2W_PLLB_FRAC, 0x7E1023E0 as A2W_PLLB_ARM, 0x7E1020F0/F4/F8/FC as
PLLB ANA0/1/2/3, 0x7E101100 as CM_OSCCOUNT and 0x7E101114 as CM_LOCK.
Those definitions supply no read values. The BCM2711 role of
0x7E102070–0x7E10207C remains unresolved; older-chip names do not settle it.

## Source request and cache effects

For the identified `start4.elf` source call, stores at 0x0EC7D9A8,
0x0EC7D9AC and 0x0EC7D9B4 set request marker GP+0x3E6AC to 1 and the
64-bit requested word at GP+0x3E6B0 to 1200000000. These precede descriptor
lookup and comparisons. The fixed request passes the two bound comparisons
using descriptor words 5000 and 600 multiplied by 1000000. Other requested
values and boundary inclusivity are outside this contract.

At 0x0EC7DA5E/0x0EC7DA60 the body stores 1200000000 into the 64-bit rate
cache at GP+0x3E4A8, before MMIO accesses. The fixture's prior rate is
1000000000; its initial marker/rate words are 0x55667788, 0x11223344 and
0x99AABBCC. Both request and rate caches retain their changed values on
the observed raw-return-4 path. Their store positions are static sequence
facts; the fixture records MMIO events and final guarded cache bytes,
not individual cache-store events.

Scalar arithmetic computes the truncated integer quotient
`(1200000000 * 2^20 + 27000000) / 54000000`. Its integer part is 22 and
its low 20 bits are 0x38E39. The fraction request is therefore 0x5A038E39.
This arithmetic defines a programming word, not measured frequency.

### Source access order

The source body first reads ANA2 at 0x0EC7DAE0 and CTRL at 0x0EC7DB06.
Its initial CM_PLLB read at 0x0EC7DB22 supplies 0x00345678, saved for the
final mask operation. The following branches refer to supplied bits;
fixture names `enabled` and `disabled` describe only CTRL bit 17.

If initial CTRL bit 17 is clear, helper 0x0EC7B9E0 runs before that initial
CM_PLLB read. It consumes GP+0x1568=0, GP+0xCC93C=0 and GP+0xCC940=1200.
These inputs choose selector 1. It reads these four words in ascending
address order, then writes them in the reverse address order shown:

| Address | Read PC / supplied word | Write PC / written word |
|---|---|---|
| 0x7E102070 | 0x0EC7BA18 / 0x00123456 | 0x0EC7BA46 / 0x5A123456 |
| 0x7E102074 | 0x0EC7BA1E / 0x00234567 | 0x0EC7BA42 / 0x5A002C00 |
| 0x7E102078 | 0x0EC7BA26 / 0x00345678 | 0x0EC7BA3A / 0x5A00002C |
| 0x7E10207C | 0x0EC7BA2E / 0x00456789 | 0x0EC7BA36 / 0x5A000000 |

Full reconfiguration occurs when initial CTRL bit 17 is clear or initial
ANA2 bit 14 is set. The latter case omits the helper above. After the
initial CM_PLLB read, full reconfiguration proceeds in this order:

| PC | Access | Supplied read or actual write |
|---|---|---|
| 0x0EC7DB3A | Read ANA3 | 0x00111111 |
| 0x0EC7DB3C | Read ANA2 | Same supplied initial ANA2 |
| 0x0EC7DB42 | Read ANA1 | 0x00222222 |
| 0x0EC7DB46 | Read ANA0 | 0x00333333 |
| 0x0EC7DB48 | Read CM_PLLB | 0x00345678 |
| 0x0EC7DB56 | Write CM_PLLB | Read word OR 0x5A000002 = 0x5A34567A |
| 0x0EC7DB7E | Write CM_OSCCOUNT | 0x5A000036 |
| 0x0EC7DB80 | Read CM_OSCCOUNT until zero | Zero, or 0x1234 then zero |
| 0x0EC7DB86 | Read CM_PLLB | 0x0034567A |
| 0x0EC7DB94 | Write CM_PLLB | Read word OR 0x5A000100 = 0x5A34577A |
| 0x0EC7DB98 | Write ANA3 | 0x5A000000 |
| 0x0EC7DBBE | Write ANA2 | 0x5A000000 |
| 0x0EC7DBC4 | Write ANA1 | 0x5A128000 |
| 0x0EC7DBC8 | Write ANA0 | Supplied ANA0 OR 0x5A000000 = 0x5A333333 |

For initial CTRL bit 17 set, both paths next read CTRL at 0x0EC7DBD8 and
write fraction 0x5A038E39 at 0x0EC7DBDA. If its low ten-bit integer differs
from 22, each step reads CTRL at 0x0EC7DBEA and writes at 0x0EC7DBFC.
The request is `(supplied_word & 0xFFFF8C00) | 0x5A001000 | next_integer`.
Initial integers 20, 22 and 24 produce 21→22, no integer writes and 23→22,
respectively. Each iteration uses its explicit read reply; the harness does
not invent a readback from its previous write.

For initial bit 17 clear, the body instead writes the fraction at
0x0EC7DC0C, reads CTRL zero at 0x0EC7DC12 and writes 0x5A001016 at
0x0EC7DC22. Both branches then:

1. Read CM_PLLB at 0x0EC7DC24. Supply 0x0034577A for reconfiguration,
   otherwise 0x00345678. Write `(read_word & 0xFFFFFEFF) | 0x5A000000`
   at 0x0EC7DC2E.
2. Read CM_LOCK at 0x0EC7DC34 until mask 0x200 is nonzero, or until
   2000 nonmatching replies exhaust the counter at 0x0EC7DC40.
3. Read CM_PLLB again at 0x0EC7DC44, supplying 0x0034567A after
   reconfiguration or 0x00345678 otherwise. Write
   `(initial_CM_word & current_read_word) | 0x5A000000` at 0x0EC7DC4E.
   This write occurs on both the matched and exhausted lock paths.
4. On the recorded matching-lock path with original CTRL bit 17 clear,
   read CTRL 0x00001016 at 0x0EC7DC7C and write 0x5A021016 at 0x0EC7DC84.

Matching lock replies produce raw zero. The recorded 2000-zero exhaustion
case returns raw 4 after its cache updates and final CM write. That case
has initial CTRL bit 17 set, integer 22 and ANA2 zero. The delayed full
reconfiguration case supplies two zero lock replies followed by 0x200.
No arbitrary delay length, exhausted full-reconfiguration combination or
other requested rate is included.

The CM_OSCCOUNT loop has no firmware iteration limit on this path.
Finite supplied replies make the positive tests complete. A missing zero
fails the strict harness; it is not a vendor timeout. The CM_LOCK loop has
the separate actual 2000-read bound described above.

## Selected native word

The identified `start4.elf` selected-clock call reads 0x0EE056B0 at
0x0EC7C918. The original zero mask and factor bits 0x3F800000 produce
internal divider word zero through 0x0EC7C924–0x0EC7CAF2. The source-code
field remains 0xFFFFFFFF. The fixed path reads the same cell again at
0x0EC7CB0A and writes `(word & 0xFFFFFFEF) | 0x5A000000` at 0x0EC7CB16.

Helper 0x0EC7E664, called at 0x0EC7CB1A, reads that cell at 0x0EC7E66A
and tests bit 7. A clear bit ends the loop immediately. While it remains
set, a counter starting at 2000 decrements. Exhaustion causes another
read at 0x0EC7E67C and a write ORing 0x5A000020 at 0x0EC7E684.
No external mutation or supplied read response changes this native word.
Both immediate and exhausted cases return raw zero through the early
return at 0x0EC7CB1E–0x0EC7CB22 and 0x0EC7C8C0.

| Initial cell / handle relation | Final cell | Raw result | Reads / writes | Instructions |
|---|---|---|---|---:|
| 0 / matching 0xC10C1234 | 0x5A000000 | 0 | 3 / 1 | 87 |
| 0x10 / matching 0xC10C1234 | 0x5A000000 | 0 | 3 / 1 | 87 |
| 0x12345678 / matching 0xC10C1234 | 0x5A345668 | 0 | 3 / 1 | 87 |
| 0x80 / matching 0xC10C1234 | 0x5A0000A0 | 0 | 2003 / 2 | 10085 |
| 0 / matching zero words | 0x5A000000 | 0 | 3 / 1 | 87 |
| 0x12345678 / mismatching handle | Unchanged | 0xFFFFFFFF | 0 / 0 | 10 |

The second pointer 0x0EE056B4, later helper 0x0EC7E6B2 and later enable
byte GP+0x3E518 are not consumed. The fixture supplies that enable byte
zero and verifies it remains unchanged; it does not prove a dependency on
it. No MMIO or callback event occurs in any of these six cases.

## Divider request

In the identified `start4.elf`, the matching-handle divider call writes
marker 1 at GP+0x3E72C and count 2 at GP+0x3E730, at 0x0EC7D616 and
0x0EC7D620. These stores precede arithmetic and MMIO. The initial words
are 0x12345678 and 0x87654321. The fixed count divided by descriptor scalar
1 yields target 2 with zero remainder. Other count/scalar combinations
are outside this contract.

At 0x0EC7D656 the body reads A2W_PLLB_ARM and masks it to eight bits.
Raw bytes 0, 1 and 2 skip decrementing. A larger byte decreases by one
per stage until 2. Each stage writes `0x5A000000 | next_byte` at
0x0EC7D67C, then command 0x5A00021C to CM_OSCCOUNT at 0x0EC7D69C.
That command uses `(54000000 / 1000000) * 10`; no duration is assigned
to the resulting 540. Reads at 0x0EC7D69E continue until a supplied zero
before another decrement. There is no firmware poll-count bound.

The body always writes 0x5A000002 to A2W_PLLB_ARM at 0x0EC7D6B0 after
the loop or its bypass. This repeats the last target write when stepping
already reached 2. It then reads CM_PLLB at 0x0EC7D6B6 and writes
`(read_word & 0xFFFFFFFD) | 0x5A000000` at 0x0EC7D6C0, returning raw zero.
No CM_LOCK read or completion callback occurs.

The raw zero byte follows the software bypass just described. It is not
converted to the hardware divider interpretation of 256 from the separate
register reference. Higher supplied bits also do not affect the byte
comparison; the tested 0x12340102 takes the equal-byte path.

## Recorded profiles

Each row below is a paired profile, not an independently combinable set of
input dimensions. All return stops are external sentinel 0x24030000;
all 22 cases are complete calls with restored SP. No native caller ABI,
stack address or incidental preserved-register value defines a host API.

| Source case | Initial CTRL / ANA2 | Lock replies | Raw result | Reads / writes | Instructions |
|---|---|---|---|---|---:|
| enabled-equal | 0x00020016 / 0 | 0x200 | 0 | 7 / 3 | 701 |
| enabled-increase | 0x00020014 / 0 | 0x200 | 0 | 9 / 5 | 718 |
| enabled-decrease | 0x00020018 / 0 | 0x200 | 0 | 9 / 5 | 718 |
| disabled-immediate | 0 / 0 | 0x200 | 0 | 19 / 16 | 776 |
| disabled-delayed | 0 / 0 | 0, 0, 0x200 | 0 | 22 / 16 | 788 |
| enabled-reconfigure | 0x00020016 / 0x4000 | 0x200 | 0 | 14 / 10 | 737 |
| lock-count-exhausted | 0x00020016 / 0 | 2000 zeros | 4 | 2006 / 3 | 10696 |
| invalid-handle | No reads | None | 0xFFFFFFFF | 0 / 0 | 12 |

Only `disabled-delayed` supplies CM_OSCCOUNT replies 0x1234 then zero;
other reconfiguration cases supply an immediate zero. Every remaining
source read word is defined in the sequence above and in its exact fixture.

| Divider case | Initial ARM word / CM_PLLB | Command replies per decrement | Raw result | Reads / writes | Instructions |
|---|---|---|---|---|---:|
| initial-zero | 0 / 0x0034567A | None | 0 | 2 / 2 | 42 |
| initial-one | 1 / 0x0034567A | None | 0 | 2 / 2 | 42 |
| initial-equal | 2 / 0x0034567A | None | 0 | 2 / 2 | 42 |
| initial-higher | 5 / 0x0034567A | Zero | 0 | 5 / 8 | 87 |
| initial-maximum | 255 / 0x0034567A | Zero | 0 | 255 / 508 | 3587 |
| higher-delayed | 5 / 0x0034567A | 0x321, then zero | 0 | 8 / 8 | 93 |
| masked-equal | 0x12340102 / 0x00345678 | None | 0 | 2 / 2 | 42 |
| unequal-handle | No reads | None | 0xFFFFFFFF | 0 / 0 | 7 |

The maximum-byte case performs 253 decrement stages, with 253 divider
writes, 253 command writes, the repeated final divider write and final
CM write. All source/divider reads are explicit little-endian words;
subsequent readback is never inferred from the write history.

| Exact fixture | Cases / instructions | SHA-256 |
|---|---|---|
| [clock-source.json](../../tests/vectors/start4/clock-source.json) | 8 / 15146 | `dfb8bd8ebe810bb90855dc9a0d701108a88c6215306b9827201bceb6663fac78` |
| [clock-word.json](../../tests/vectors/start4/clock-word.json) | 6 / 10443 | `d9fb830adc8c889696959227d29eba473013b67acfeafc20cdeef413d4c4c2ae` |
| [clock-divider.json](../../tests/vectors/start4/clock-divider.json) | 8 / 3942 | `d67ac8367485ab008e8880617b9a89ac330ec7be0703207ee6e9a30401eb892f` |

Together they execute 29531 scalar instructions, record 2362 supplied MMIO
reads and 590 MMIO writes, plus 2015 native-cell reads and six writes.
They compare all declared non-stack state and its surrounding guards,
the full ordered event streams and the observed registers, including
restored SP. Native-cell events include every
executed read/write with its PC; setup and final observation are not events.

## Portable state and host preconditions

Expose three separate fixed operations with the argument tuples above.
Represent the handle/comparison pair as opaque 32-bit words, marker/count
fields as 32-bit words, and requested/cached rates as unsigned 64-bit words.
The selected-clock operation owns one explicit 32-bit cell for the duration
of the call, with no external mutation. It must not turn that cell into an
MMIO provider or infer an alias with synthetic GP+0x1570.

For source/divider operations, supply an immutable finite read plan before
execution. Each record identifies the logical MMIO word and its literal
32-bit reply; the fixture additionally identifies the exact read PC. Emit
each read and write in the documented order. Derive actual writes through
the described arithmetic, masks and loops. A previously issued write is
not itself a read reply. Preserve repeated final writes and distinguish
reads from requests even when their numerical words match.

Use only the exact paired profiles above, including their initial cache
sentinels, helper selectors, diagnostics state and reply sequences. A
mismatched-handle profile needs no programming providers. The zero/zero
handle profile is supported only for the selected-word case. Other handles,
rate/count arguments, descriptor layouts, read values, combinations and
repeated-state compositions require separate evidence. Do not expose a
general PLL, frequency-selection or arbitrary-register API from these cases.

The caller establishes actual backing, alignment, writability and lifetime
of state/cell/output storage. Executable preflight checks required pointers,
lengths, address-wrap bounds, overlap, supported profile and all reachable
read/write providers before effects. State, native cell, reply-plan storage
and result storage must not overlap. Validate plan shape and sufficiency
before emitting events or changing state. A host validation error preserves
state and emits no calls; report it separately from raw zero, 4 or
0xFFFFFFFF. These host preconditions do not validate live firmware pointers
or acquisition of a hardware resource.

A provider may return only its declared reply and may not mutate other
state, inject extra replies or add asynchronous native-cell changes.
Undeclared responses, provider failures and concurrent access are outside
this contract; no invented rollback or vendor timeout is assigned to them.
The finite lock counter is actual software behavior. Exhausting a host
read plan for the unbounded command loop is a host failure, not raw 4.

Keep raw results separate from the resulting cache and event state.
The source's raw 4 leaves changed caches and issued requests intact. The
selected-word finite-counter branch returns zero even after its fallback
write. The [manager contract](clock-request.md) separately specifies that
its tested programming boundary replies are not propagated. These leaf
fixtures do not define a new combined manager API or prove live startup.

## Replay and strict boundaries

Use the imported program and versions in [headless analysis](../analysis.md).
The separate `CaptureClockVectors.java` retains finite exact MMIO read
matching, per-case word-write allowlists, strict declared memory, instruction
byte equality, unsupported-operation rejection and exclusive result creation.
It checks the pinned file identity, literal first-cell pointer, exact block
bounds, uninitialized read/write/non-executable status and absence of
instruction bytes at the four-byte cell. Only 0x0EE056B0 with size 4 can
be supplied outside the ordinary synthetic RAM ranges. The existing
`CaptureScalarVectors.java` has a separate memory policy. The implemented
[Clock VERSION extension](vpu-version.md#clock-recorder-integration)
adds only an explicit instruction-result boundary and preserves every
guard described here. The clock fixtures below contain no VERSION plan
and retain their expected observations unchanged. The
[native first-open routes](arm-first-open.md) record three complete
table-zero returns; successful open and physical effects remain unresolved.

The implemented [IRQ and p16 observation contract](vpu-irq.md) retains these
source, descriptor, MMIO and native-cell guards. Its separate finite cursor
records instruction observations under a no-interrupt-arrival premise.
The recorder rejects DI when the plan is absent.

Run from the repository root with three unused output paths:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EC7D978 0x0ECC47B6 0x0EC7B9E0 0x0EC2FBDA 0x0EC2F9B8 \
  0x0EC7C7D0 0x0EC7AC52 0x0EC7E664 0x0EC7E6B2 0x0EC7B978 \
  0x0EC7A2A4 0x0EC7E008 0x0EC7D5EA \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/clock-source.json /work/analysis/clock-source.json \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/clock-word.json /work/analysis/clock-word.json \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/clock-divider.json /work/analysis/clock-divider.json
cmp tests/vectors/start4/clock-source.json /work/analysis/clock-source.json
cmp tests/vectors/start4/clock-word.json /work/analysis/clock-word.json
cmp tests/vectors/start4/clock-divider.json /work/analysis/clock-divider.json
```

Compare the complete JSON. Decoding changes transient metadata only.
Missing or mismatched MMIO replies, unused replies and undeclared writes
must fail without a result file. Supplying the second cell, a partial cell
or an out-of-cell write must also fail. Removing the first cell produces
an uninitialized read at 0x0EC7C918, rather than a guessed value. These are
harness guards, not firmware return values or measurements of hardware.

The [fixed resource composition](resource-composition.md#two-clock-calls-in-persistent-state)
adds the exact matching-handle native-word profile with initial cell
0x5A000000 for its second request. It preserves updated source/divider
state without calling those operations again; it does not extend their
initial-state domains.

## Open questions

- Runtime state. Establish descriptor relocation, live aliases, acquisition,
  initialization and ownership before binding these reference-layout
  inputs to a physical device. In particular, determine the initializer
  and purpose of the first selected native word.
- Physical readback. Validate actual register acknowledgments, timing and
  achieved rates before treating any request or raw return as completion.
- Broader domains. Obtain differential evidence for other source/count/rate
  arguments, descriptor fields, helper selectors and combinations before
  extending these paired profiles.
- Unresolved register bank. Establish BCM2711 meanings for
  0x7E102070–0x7E10207C before assigning hardware names or analog effects.
- Unbounded polls and providers. Verify actual command failure behavior and
  provider/concurrency semantics before defining cancellation or recovery.
