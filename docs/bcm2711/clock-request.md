<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Fixed clock request

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file; file offsets start at zero.
The request is `0x0ED55EFA(0x30,600000000,0,0,0,output)`, with an eight-byte
output buffer. The clock identifier, numerical planning and callback order
are separate from physical clock settings or completion.

The contract executes software dispatch, descriptor selection, arithmetic,
cache changes and notification routing. Driver programming, open, mutex,
diagnostic and notification callbacks have explicit supplied replies.
No MMIO or exception instruction executes. The
[register reference](clocks.md) describes a separate source boundary;
these request observations do not establish register programming.

## Entry and initialization boundaries

In the identified `start4.elf`, wrapper 0x0ED55EFA reads GP+0xD33F8.
For supplied values 1 and 0xFFFFFFFF, it skips the request and preserves
incoming `r0=0x30`, the output and the observed cache. That raw word is
not a success or failure code produced by a driver.

With skip word zero, wrapper 0x0EC7EA02 calls initializer 0x0EC7E764,
requests acquisition of mutex GP+0x3E810 at 0x0EC7EA1C, executes request
body 0x0EC7EA3C, releases the same mutex at 0x0EC7EA34 and restores the
body's raw result to `r0` at 0x0EC7EA38. The request fixtures supply
initialized flag GP+0x184C equal to 1, so initialization returns without
changing the supplied state. Mutex and diagnostic replies are zero and
have no memory effects; their actual implementations are not executed.

Two separate cases call the initializer itself with flag zero. At
0x0EC7E776 it writes flag 1 before clearing the 1156-byte state block
beginning at GP+0x3E810. It obtains a driver table, stores it at state+0x04,
then calls the table's open slot at 0x0EC7E794 with `(0,state+0x08)`.
The supplied open reply writes a handle into that four-byte output and
returns a raw word. With selection GP+0x1564 equal to 1, the initializer
then stores little-endian 54000000 at state+0x24, regardless of that reply.

| Supplied open result / handle write | Initializer's final result and state |
|---|---|
| 0 / 0xC10C1234 | Raw zero; flag 1, selected table, supplied handle and reference 54000000 persist |
| 7 / 0 | Raw 7; flag 1, selected table, zero handle and reference 54000000 still persist |

Both are complete initializer calls with restored SP. They do not continue
into a clock request, acquire a real driver handle or establish that the
initialized flag implies a usable handle. The value 7 is not assigned an
open-error enum. The real open body remains an explicit callback boundary.

## Diagnostic boundary

In the identified `start4.elf`, call 0x0EC7EAC2 targets diagnostic entry
0x0ED17442. Its defined input is seven 32-bit words in this order:

| Position | Fixed request value | Meaning at the callsite |
|---:|---|---|
| 0 | 0x4000 | Opaque diagnostic control word |
| 1 | 0x0EC7EF38 | Opaque format identity |
| 2 | 0x30 | Clock identifier |
| 3 | 600000000 | Requested value, low word |
| 4 | 0 | Requested value, high word |
| 5 | 0 | Original request word in incoming `r3` |
| 6 | 0 | Original request word in incoming `r4` |

The first six words occupy `r0` through `r5` at the boundary. Store
0x0EC7EAA8 places the seventh at the outgoing stack pointer before the
register setup at 0x0EC7EAAA–0x0EC7EABE. The caller's output pointer is not
a diagnostic argument. Preserve all seven logical words in a portable
callback; represent entry and format identities as opaque tokens, without
dereferencing the firmware format address or exposing a native stack.
No logging severity, rendered text or diagnostic implementation is defined.

The fixture records only the six register words in its boundary event.
The seventh word's placement follows the static callsite stores; it is not
an extra field captured in that event. The supplied diagnostic reply is
raw zero with no memory effects, as in the recorded request profiles.

## Selected table and state

For supplied selection GP+0x1564=1, the identified `start4.elf` resolver
0x0EC79C42 loads the table pointer from 0x0EE02C54, file offset 0x202634.
Its reference value is 0x0EDE7F04:

| Table slot | Word address | File offset | Target |
|---|---|---|---|
| Open +0x0C | 0x0EDE7F10 | 0x1E78F0 | 0x0EC7B978 |
| Source request +0x18 | 0x0EDE7F1C | 0x1E78FC | 0x0EC7D978 |
| Divider request +0x20 | 0x0EDE7F24 | 0x1E7904 | 0x0EC7D5EA |
| Clock request +0x24 | 0x0EDE7F28 | 0x1E7908 | 0x0EC7C7D0 |
| Descriptor +0x38 | 0x0EDE7F3C | 0x1E791C | 0x0EC7AE8A |

The descriptor body executes. The other four table bodies are supplied
boundaries in these fixtures. Raw pointer words and an initialized flag
do not establish their live relocated addresses, acquisition or lifetime.

The state base below is GP+0x3E810. Rate fields are unsigned 64-bit
little-endian numerical words; the count field is 32 bits.

| State offset | Size (bytes) | Fixed-path field |
|---|---:|---|
| 0x04 | 4 | Driver table pointer |
| 0x08 | 4 | Driver handle |
| 0x24 | 8 | Reference word written by cold initialization |
| 0x44 | 8 | Source cache slot 7 |
| 0x11C | 8 | Divider-rate cache slot 5 |
| 0x188 | 4 | Divider-count cache slot 5 |
| 0x334 | 8 | Requested-clock cache slot 0x30 |
| 0x464 | 32 | Four notification records, stride 8 bytes |

A notification record has a clock byte at offset zero and callback pointer
at offset four. Recorded request cases have either four empty records or
one clock-0x30 callback in the first record with the remaining three empty.
Registration and multiple-callback rollback are not part of these cases.

Normal request cases supply handle 0xC10C1234 both at state+0x08 and
GP+0x3E494. Descriptor callback 0x0EC7AE8A checks this equality. It is a
matching-handle premise, not proof of acquisition or validity. The remaining
declared inputs are:

| GP-relative field | Supplied state |
|---|---|
| 0x1564 | Selection word 1 |
| 0xD1B80, 0xD1B7C, 0xD1B78 | Empty descriptor/rate override heads, zero |
| 0xD1B88 | 86 descriptor-miss bytes, initially zero |
| 0xD1BE4, 0xD1BE0 | Override-miss bitmaps, initially zero |
| 0x3B938 | Cached planner input 1200, or 1500 in one case |

Accessor 0x0EC635DA(4) reads the last field at 0x0EC635E0. Its values are
synthetic cached inputs, not measured board limits or hardware frequencies.
Source selection, old caches and callback availability are declared inputs;
no missing field is inferred from zero-filled firmware memory.

## Descriptor and fixed numerical plan

In the identified `start4.elf`, descriptor callback 0x0EC7AE8A calls
0x0ED479FE. Empty override lookup through 0x0ED4714E marks descriptor-miss
byte 0x30 at GP+0xD1B88. The default branch at 0x0ED47C56 selects clock
byte 0x30, source index 7 and divider index 5, with the remaining descriptor
fields zero. Descriptor metadata at 0x0EDDD690 supplies its count constraints.
These descriptor and planner operations execute; their results are not
callback replies.

Actual planner 0x0ED47D14, override helpers and scalar arithmetic select
the following two fixed plans for the requested value 600000000:

| Cached input GP+0x3B938 | Planned source word | Divider count | Clock callback ratio bits |
|---:|---:|---:|---|
| 1200 | 1200000000 | 2 | 0x3F800000, scalar float 1.0 |
| 1500 | 1800000000 | 3 | 0x3F800000, scalar float 1.0 |

This table defines the two recorded observations, not an interpolation
formula or a general frequency policy. The driver boundary arguments are:

| Boundary | Defined input portion |
|---|---|
| Source at 0x0EC7D978 | `(handle,2,planned_source_low,0)` |
| Clock at 0x0EC7C7D0 | `(handle,0x30,7,5,0x3F800000,0)` |
| Divider at 0x0EC7D5EA | `(handle,5,planned_count)` |

The source-cache index 7 and source driver's argument 2 are distinct
values on this fixed route. All six register words are recorded at each
boundary; unused trailing registers are not extra portable API arguments.
The numerical settings are requested values, not observed hardware rates.

## Lookup-miss ordering

For the fixed initialized request in the identified `start4.elf`, diagnostic
call 0x0EC7EAC2 occurs before descriptor call 0x0EC7EAE8. The descriptor
lookup stores 1 into miss byte GP+0xD1B88+0x30 at 0x0ED4719C. The body
then calls the pre-change notifier at 0x0EC7EB1A; the first matching callback
runs at 0x0EC7E920. These boundaries see the following miss state when the
supplied callbacks preserve memory:

| Boundary | Descriptor-miss byte 0x30 | GP+0xD1BE4 | GP+0xD1BE0 |
|---|---:|---|---|
| Diagnostic call | 0 | 0 | 0 |
| Pre-change notification | 1 | 0 | 0 |
| First programming call | 1 | 0x20 | 0x80 |

Only after the pre-change notifier returns zero does the body call planner
0x0ED47D14 at 0x0EC7EC58. Its divider-override lookup sets GP+0xD1BE4 to 0x20 at
0x0ED47036, followed by the source-override lookup setting GP+0xD1BE0 to
0x80 at 0x0ED47446. Both stores precede the first programming call for
all listed profiles. A rejected pre-change request reaches neither store.
The numerical caches and caller output still have their supplied values
at the diagnostic and pre-change boundaries.

These intermediate positions follow the static control flow and store
addresses. The recorded cases capture boundary arguments/order and final
memory; they do not sample memory inside diagnostic or notification
callbacks. The table does not extend the contract to callback mutation,
concurrent readers or hardware visibility.

## Cache changes and programming order

The identified `start4.elf` body 0x0EC7EA3C compares the planned source to
its old source cache at 0x0EC7EC70–0x0EC7ECA0. With planner input 1200,
the supplied old source values produce these orders:

| Old source cache | Old divider-rate cache | Programming boundary order |
|---:|---:|---|
| 0 | 0 | Source, clock, divider |
| 1000000000 | 250000000 | Divider, clock, source, divider |
| 2000000000 | 500000000 | Source, clock, divider |
| 1200000000 | 300000000 | Clock, divider |

Every case starts with divider count zero and requested-clock cache
500000000. These combinations are explicitly supplied state, not asserted
to be normal live cache contents. The 1500 case starts with zero source
and divider-rate caches and uses source, clock, divider order with count 3.

The lower-source case calls the divider with count 2 at 0x0EC7ECC2 before
storing that count into its cache at 0x0EC7ECD2. The other cases also store
their planned count at 0x0EC7ECD2. Where a source change occurs, its cache
is written at 0x0EC7ED6E/+0x02. For zero or higher old source, the source
callback has already run at 0x0EC7ED44. For a lower old source, the cache
write precedes the delayed source call at 0x0EC7EEBC.

The divider-rate cache is updated at 0x0EC7EDC2/+0x04 before the clock
callback at 0x0EC7EE4A. The fixed cases retain a pending final divider
request, called at 0x0EC7EECE. Thus the lower-source case makes two divider
calls, both with count 2. Equal source skips the source callback but still
updates the divider rate and calls the divider under its supplied old state.

After programming, the requested-clock cache becomes 600000000 through
0x0EC7EF00/+0x04. The body then sends the post-change notification at
0x0EC7EF14 and copies the cache into the caller's eight-byte output at
0x0EC7EF2A/0x0EC7EF2C. That output copy follows the notification return.
Final normal state has source 1200000000 or 1800000000, divider rate
600000000, count 2 or 3, and requested-clock/output value 600000000.

Descriptor-miss byte 0x30 becomes 1. Override-miss bitmap GP+0xD1BE4 becomes
0x20 and GP+0xD1BE0 becomes 0x80 after the full plan. The fixture compares
all 1156 state bytes, the miss state and the entire 48-byte output/guard
span. The output's 16-byte prefix and 24-byte suffix remain unchanged.

All three supplied programming return words can be changed from zero to
0xFFFFFFFF without changing the observed event sequence, final state/output,
raw result zero or instruction count in the zero-cache case. This software
path does not propagate those literal replies. It does not establish that
0xFFFFFFFF is a real error enum, that a hardware operation completed, or
that the actual driver body returns on a failure.

## Notification results

In the identified `start4.elf`, notifier 0x0EC7E8E6 scans the four records.
The recorded nonempty case uses only the first record with synthetic
callback destination 0x24030000. The destination is not an identified
vendor callback. The actual observed calls are:

| Phase | Defined argument portion |
|---|---|
| Before change | `(0x30,0,600000000,0)` |
| After change | `(0x30,2,600000000,0)` |

The literal replies change only `r0` and have no memory effects. A first
pre-change reply 7 prevents programming. Descriptor lookup has already
marked its miss byte, but rate-miss bits, the manager cache and caller
output remain unchanged. At 0x0EC7EB24 the body reads the prior clock cache
and returns its low word, 500000000, instead of forwarding reply 7.

With pre-change reply zero and post-change reply 7, all programming and
cache updates occur. The notifier selects raw 0xFFFFFFFF, and the request
still copies updated cache 600000000 into the output, then returns raw
0xFFFFFFFF.
The software updates are not rolled back on this path. Multiple registered
callbacks, callback memory effects and any rollback-notification sequence
are outside the recorded cases.

## Recorded cases

[clock-request.json](../../tests/vectors/start4/clock-request.json) contains
12 cases and 6916 scalar instructions, SHA-256
`664df1604587c7f2cd7c2576ef16afb44a0020c93effd9bffcc4ca39b7d72902`.
Ten cases enter request wrapper 0x0ED55EFA. Two enter initializer
0x0EC7E764 directly. All are complete calls with restored SP and external
return sentinel 0x24040000; there are no internal-stop prefixes. Completing
the initializer is separate from completing a cold clock request.

| Case | Instructions | Raw `r0` / final observation |
|---|---:|---|
| Zero prior source | 772 | Zero; output/cache 600000000 |
| Skip word 1 | 4 | 0x30; no calls or observed state changes |
| Skip word 0xFFFFFFFF | 4 | 0x30; no calls or observed state changes |
| Programming replies all 0xFFFFFFFF | 772 | Same observations as zero replies |
| Lower old source | 792 | Zero; two divider calls |
| Higher old source | 782 | Zero; source before clock |
| Equal old source | 750 | Zero; no source callback |
| Pre-change reply 7 | 241 | 500000000; output untouched |
| Pre-change 0, post-change 7 | 787 | 0xFFFFFFFF; updated output/cache persist |
| Cached planner input 1500 | 772 | Zero; planned source 1800000000/count 3 |
| Initializer, open reply 0 / supplied handle | 620 | Zero; initialized fields persist |
| Initializer, open reply 7 / supplied zero handle | 620 | 7; initialized fields still persist |

GP 0xE4000000, SP 0x24010000 and output 0x24020010 are synthetic test
locations. The initializer fixtures start with 1156 state bytes set to
0xA5; real clearing and pointer/reference stores execute around the literal
open reply. Its handle write is the only supplied callback memory effect.
Other callbacks preserve memory. The observed source/code bytes and scalar
instruction semantics remain unchanged.

## Portable state and host preconditions

Represent rates as unsigned 64-bit words, count and skip/initialized fields
as 32-bit words, and handle/table/callback identities as opaque tokens.
Keep the descriptor-miss byte, two override-miss bitmaps and notification
selection separate from the numerical caches. The host operation is either
the fixed request or a direct cold initializer; do not implicitly compose
a nonzero-open-reply/zero-handle initializer with a subsequent request.

The caller establishes actual backing, writability, required alignment and
lifetime for all supplied objects. Executable preflight checks required
pointers, lengths, address-wrap bounds, overlap, supported profiles and
reachable providers; it cannot prove the caller's backing or lifetime.
The request's external output buffer, manager state and immutable reply-plan
storage must not overlap. The initializer's declared handle write is an
explicit write to state+0x08. Preflight errors emit no calls and preserve
state/output. Report them through a host status separate from vendor raw
zero, 0x30, 7, 0xFFFFFFFF or a cached-rate result. A nonzero handle token
must match its supplied comparison token; this relation does not establish
driver acquisition or ownership. Missing inputs must not become silent zeros.

The supported inputs are the fixed profiles above: identifier 0x30,
requested 600000000 with high word and remaining request words zero;
selection 1; no overrides; initial miss state zero; initialized flag 1 for
request cases; the four listed source/divider-rate pairs with count zero
and old requested-clock cache 500000000. Planner input 1500 is covered only
with zero source/divider caches. Skip values are 0, 1 and 0xFFFFFFFF.
Notification records are empty or the single first-slot clock-0x30 record
with the documented reply sequence on the zero-source, planner-1200 profile.
Nonzero programming replies are covered only by the zero-cache profile
without notifications. The cold initializer profiles use flag
zero and the two exact open-result/handle-write pairs. Other combinations
or repeated-state requests require additional evidence. The listed dimensions
are not a tested Cartesian product and do not define a general clock API
or arbitrary-state parity.

Supply the literal reply plan before execution. Preflight only providers
reachable under the selected profile before changing state or emitting
calls. Skipped requests need no programming providers. Open replies declare
both the raw word and the permitted four-byte handle write. The other
providers return the documented literal words and preserve state. Dynamic
providers that return undeclared words or introduce other memory effects
remain outside this contract; no error or rollback policy for them is defined.
Incidental registers and native stack addresses do not define a host ABI.

Preserve the raw result separately from output/cache state. Skip returns
the input identifier; a pre-notification rejection returns the old rate's
low word; a post-notification nonzero reply returns 0xFFFFFFFF after updates;
the initializer returns its supplied open word. None is a physical-completion
status. Compare callback identity, defined arguments, order, state changes
and output preservation independently.

## Replay

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
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/clock-request.json /work/analysis/clock-request.json
cmp tests/vectors/start4/clock-request.json /work/analysis/clock-request.json
```

Compare the complete JSON, including state/output bytes, all six boundary
register arguments, reply indexes and instruction counts. Decoding changes
transient metadata only. The unchanged recorder rejects unknown reads,
undeclared writes, modified instruction bytes and unsupported operations.
Omitting only GP+0x3B938 from the baseline causes an uninitialized four-byte
read at 0xE403B938 by 0x0EC635E0 and produces no result artifact. This is a
recorder boundary, not a vendor error return.

## Open questions

- Driver completion. Specify the selected programming and open bodies,
  initialized state and physical readbacks before interpreting a requested
  setting or raw return as an achieved rate.
- Runtime state. Trace acquisition, initialization, relocation, ownership
  and visibility of tables, handles and caches before using these supplied
  reference-layout fields in a live clock path.
- Broader planning. Verify other identifiers, values, overrides and old
  cache combinations before extending the two fixed numerical plans.
- Notifications and synchronization. Verify registration, multiple callbacks,
  mutation and real mutex behavior before defining concurrent operation,
  rollback or dynamic-provider recovery.
