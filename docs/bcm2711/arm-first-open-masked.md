<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# ARM first-open mask rejection

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

First-open entry 0x0EC59D24 can complete with raw one after real object,
callback and suspend registration, followed by a nonzero mask predicate.
It releases the higher mutex boundary and preserves the caller's handle
output. This is a completed rejection with retained effects. It does not
establish successful first open, live initialization or an acquired handle.

| Body | File offset | Bytes | SHA-256 |
|---|---|---:|---|
| First open, 0x0EC59D24 | 0x59724 | 358 | `2496ff8e231f807a6ece6091765af98dd2f7182106ea1c22339c00e8684bf6cd` |
| Driver getter, 0x0ED00582 | 0xFFF82 | 8 | `aebc6f7e04502d030b65290a641d766eddd7934547f9e67b53f4f031f0c25ece` |
| Second driver callback, 0x0ED00700 | 0x100100 | 72 | `d9ffe74fbb26aa541f89df1fd795d4d16a739256157e333d2d1a411c235558a5` |

The getter reads the immutable word at 0x0EE02C10, file offset 0x2025F0,
and returns table identity 0x0EDFA4DC. Table slots 0x0C and 0x14 select
0x0ED0067E and 0x0ED00700. Their pointer words are at file offsets 0x1F9EC8
and 0x1F9ED0. This fixed table identity is not a host address or a provider
result. The first slot is the actual [driver-open callback](driver-open-masks.md).
The second calls the actual [mask predicate](mask-predicate.md) at 0x0ED0070A.

## Parameters and inherited helper domains

Provide one complete `arm_first_open_masked` operation. Preserve the
existing `arm_first_open_execute` signature and its separate
[table-zero return domain](arm-first-open.md). This operation composes
the actual shared prefix and helpers; it does not continue after a call
to that already-completed table-zero operation. No separate second-slot
wrapper or portable partial-first-open operation is required.

The first-open comparisons at 0x0EC59D2E–0x0EC59D58 select:

| Parameter word P | Selector K |
|---|---:|
| 0x80 | 0 |
| 0x100 | 1 |
| 0x200 | 2 |
| 0x400 | 3 |

The parameter byte B is zero, one or two. The unsigned bound at 0x0EC59D5E
and three-byte switch table at 0x0EC59D68 select 0, 0x800 or 0xC00,
respectively. All twelve P/B combinations belong to this bounded domain.
No parameter truncation admits values outside these sets.

Initial open count is zero. The resource-object output initially contains
0xA5A5A5A5. The 896-byte record prefix uses one of the three successful
existing [object-registration profiles](arm-object.md#record-storage-and-fixed-profiles):
first free record zero, first free record one, or free record zero with
retained request fields. Metadata remains `(0x0EC59E8C,0x158)` and the
logical record-token base remains 0xE40DA4C4. Every declared tail byte is
preserved. Full arrays, absent object output and arbitrary occupied records
are outside this composition's inherited object domain.

Selected callback state uses either successful existing
[registration profile](arm-first-open.md#selected-callback-registration-profiles):
initial token 0x0EC3EA48 or 0x11223344, with old-callback output initially
0xA5A5A5A5. The actual first-open caller supplies code 0x5E and replacement
0x0EC5716E. It does not invoke either token. Both paths replace the selected
word; the old output becomes zero for the default token or 0x11223344 for
the prior-token profile. Other tokens and null callback output remain
outside these inherited helper profiles.

These explicit helper restrictions do not restrict masks, registrar
contents or names to the literal captured values. Extend the underlying
shared helper contracts before accepting other record or callback domains.

## General scalar and registrar inputs

Configuration source X, incoming entry SR, supplied MMIO read word,
opaque first-open word and incoming handle-output word are arbitrary
unsigned 32-bit values. Initial capacity, configuration, driver-table word
and four later driver-state words are also arbitrary unsigned 32-bit values;
the actual path overwrites them before using their new values.

The explicit VERSION word V is any unsigned 32-bit value with bit 6 set.
The supplied secondary word at original GP+0xCC934 is zero. This exact
condition follows 0x0EC59DE2–0x0EC59DEC to 0x0EC59E08 without executing
the earlier service call at 0x0EC59E04. No service reply, service observer
or service index is required. CPU identity and the physical meaning of bit 6
remain unspecified. VERSION is a supplied instruction observation.

The first callback receives a null mask source at 0x0EC59E54/0x0EC59E56.
Use the real `driver_open_register` computation with absent source. The
required mask destination contains 8 through 0xFFFFFFFF bytes, with low
word at offset zero and high word at offset four. Every mask byte and tail
remains unchanged. Both words are arbitrary, subject to low bit 30 being
set: actual `mask_predicate(0x5E)` must compute one. Do not replace that
computation with a supplied rejection value or a fixed fixture comparison.

The actual suspend tuple is `(1,0x0ED004C6,0)`. The full bounded
[registrar domain](suspend-registrar.md#state-and-input-domain) applies:

- Its object view contains 2936 through 0xFFFFFFFF bytes. The signed count
  is from zero through 0x7FFFFFFF. Records and padding are arbitrary.
- Count at least 40 takes the capacity path without reading record, name
  or logging contents. It needs no larger object backing.
- Count below 40 requires a logging byte below four and computes the first
  matching tuple with the existing scalar lookup.
- A matching tuple consumes no name bytes. An absent tuple inserts the
  fixed nonzero callback and requires the existing bounded NUL-terminated
  name domain, basename selection and 21-byte truncation rules.
- The read plan is zero or more one words followed by one zero, with
  nonzero count q and `4 × q <= 0xFFFFFFFF`. No interrupt arrival is supplied.

Any permitted synthetic name is accepted. The operation does not embed a
vendor basename or infer its producer. Unused name/logging contents are not
semantically validated. Every supplied object and full byte span still
participates in storage checks, including unused views and tails.

### Derived registrar status

The nested driver status is derived from the real preceding scalar flow.
It is not an independently supplied registrar SR. Let I be entry SR and
`U = I & 0xFFFFFFF0`:

| Selected callback profile | Last flag-setting comparison | Nested status S |
|---|---|---|
| Default token | 0x0ED6520C compares code 0x5E with 0x80 | `U | 6` |
| Prior token | 0x0ED65246 compares replacement 0x0EC5716E with zero | `U` |

These comparisons replace the low four compiled status bits and preserve
the upper 28. The intervening fused branches, moves, stores and declared
mutex/diagnostic replies preserve status. Pass this computed S to the real
driver-open operation. DI reports S and S with bit 30 cleared. Its actual
path-specific final p16 write reports full S, then status restores to S.
The later predicate comparisons leave final native SR equal to U.
This is pinned scalar behavior, not evidence of physical interrupt state.

## Actual sequence and retained state

For this domain, the identified first-open body performs these operations:

1. Observe higher acquire at 0x0EC59D88, then store open count one at
   0x0EC59D92. Execute the actual resource-object registrar at 0x0EC59DA6.
   It clears the object output, selects the first free record in the
   supported profile, writes identity/index/metadata and observes its
   diagnostic and manager release. Retained request fields remain intact.
2. Store capacity P at 0x0EC59DBE. At 0x0EC59DDE store
   `((X & 0xFFFF0FFF) & 0xFFF0001C) | K | 0xF000 | T`, where T is the
   byte-selected value 0, 0x800 or 0xC00. Observe VERSION and take the
   bit-6-set/secondary-zero branch.
3. Read the supplied 32-bit word from 0x7E00B44C at 0x0EC59E12.
   Execute actual callback registration at 0x0EC59E22. Its code register
   replaces the incidental MMIO word; the read value does not choose
   the callback or change the later rejection.
4. Write word eight to 0x7E00B9BC at 0x0EC59E34. Store the four words
   below in the listed order, then write word one to the same MMIO
   address at 0x0EC59E44.
5. Execute the actual getter and store table identity 0x0EDFA4DC at
   GP+0x3B480 through 0x0EC59E4A. Invoke actual slot 0x0C with null source.
   It completes real suspend registration and returns zero even if that
   registrar returned 0xFFFFFFFF for capacity.
6. Load the explicitly supplied opaque word from GP+0x3B484 at
   0x0EC59E62. Invoke slot 0x14 with that word, code 0x5E and value one.
   The real predicate calls the shared word-pair shift and reads both masks.
   Its nonzero result follows 0x0ED00710/0x0ED00714 to the actual epilogue
   at 0x0ED00746, returning one without the second-slot DI or service.
7. Observe higher release at 0x0EC59E6E. The nonzero branch at
   0x0EC59E72 reaches 0x0EC59E86 and the actual outer epilogue 0x0EC59E88.
   Return raw one without writing the handle output at 0x0EC59E80.

| Store order | First-open instruction | Original state address | Word |
|---:|---|---|---:|
| 1 | 0x0EC59E38 | GP+0x3B520 | 1 |
| 2 | 0x0EC59E3C | GP+0x3B528 | 1 |
| 3 | 0x0EC59E40 | GP+0x3B524 | 0 |
| 4 | 0x0EC59E42 | GP+0x3B52C | 0 |

These are software words with no assigned physical register meaning.
All effects remain after raw one. In particular, open count, object and
record registration, capacity/configuration, callback replacement, table
identity, four software words and the registrar's saved S remain. Insertion
also retains its tuple/name/count/flag changes. Capacity and match preserve
their specified records, count and flag. No rollback or successful handle
acquisition follows from completion.

## Portable composition and observations

Represent the existing first-open parameter/state and record storage,
entry SR, VERSION/secondary words, opaque input and handle output, mutable
driver-table/four-word state, masks, registrar object/name/logging, literal
reply/read plans, registrar p16 plan, observers and separate outer raw result.
Native identities remain unsigned tokens; none becomes a host pointer.

Use the actual `arm_object_register`, `arm_callback_register`,
`driver_open_register` and `mask_predicate` computations. The driver uses
its actual shared registrar and scalar helpers. Keep all nested raw results
in private storage. Getter identity is the source-bound constant above;
there is no configurable getter or scalar-return provider.

Factor the common first-open scalar prefix and its read-only preflight so
this operation and the existing table-zero operation share the same code.
Their accepted input domains remain explicit and distinct. Do not duplicate
the prefix or call the old operation speculatively and continue after its
return. Use a shared validated execution path where necessary; private
nested inputs/results do not relax checks on caller-owned storage.

External function observations retain fixed zero replies with no memory
or SR changes. The logical reply plan has exactly five zeros in this order:
higher acquire, manager acquire, registrar diagnostic, manager release,
higher release. Their semantic arguments remain the mutex identities and
actual selected-record diagnostic tuple in [object registration](arm-object.md).
VERSION and the one MMIO read are explicit inputs, separate from these replies.
The read plan contains exactly one entry: PC 0x0EC59E12, address 0x7E00B44C,
size four and an arbitrary supplied word. One write observer receives both
actual MMIO write events, reporting PC, address, size four and word 8/1.
Writes have no supplied completion value or dynamic response.
The registrar reports its actual DI, each supplied p16 read and final write.
No observer chooses a dynamic result or performs a computational callee.

| Observation | Visible state |
|---|---|
| Higher acquire | All incoming state, count zero |
| Manager acquire | Count one, cleared object output, original records; capacity/configuration still incoming |
| Diagnostic and manager release | Selected record and object updated; capacity/configuration still incoming |
| VERSION and MMIO read | Capacity P and computed configuration; original callback and old-callback output |
| First MMIO write, word 8 | Callback replacement and old-callback output complete; four driver words and table still incoming |
| Second MMIO write, word 1 | Four driver words complete; table still incoming |
| Registrar DI and p16 reads | Table identity stored; masks unchanged; registrar object still incoming |
| Registrar final p16 write | Registrar's saved S and all path-specific writes complete |
| Higher release | All retained state complete, predicate has computed rejection |

Every observer sees the incoming outer raw-result word and unchanged handle
output. Publish outer raw one only after the higher-release observer returns
normally. Native physical register tuples and stack residue are fixture
observations, not additional host arguments or a portable calling convention.
The observer table follows source store/call ordering; native fixtures do
not snapshot memory at every observation.

## Whole-call storage preflight

Complete a read-only preflight before higher acquire, any count/object store,
MMIO observation or nested operation. Validate all required storage, typed
alignment, full extents, products/address wrap, pairwise overlap, supported
parameter/object/callback domains, initial count, VERSION/secondary condition,
all five replies, one exact-address read, the observer for both writes, derived S,
complete registrar read plan, conditional logging/name requirements and
computed nonzero mask predicate. No late nested validation may discover a
host error after prefix effects.

Reuse read-only validation of the real object and callback operations and
the existing shared driver/registrar preflight. Evaluate the mask computation
without effects during preflight, then perform the actual predicate again
at its sequence position. Inputs remain immutable under the caller premises;
no earlier effect writes masks, name, logging or the read plan. Registrar
execution uses the same validated state and its private result.

The object records contain at least 896 bytes; masks at least eight; the
registrar object at least 2936. Each complete byte extent is at most
0xFFFFFFFF. Conditional name bounds remain those of the registrar. All tail
bytes are preserved. Byte storage may be unaligned; typed inputs, descriptors,
state, plans, observers, word arrays and results require natural alignment.
Null byte pointers require zero extent and are permitted only for a view
whose absence is documented. Required views cannot be absent.

Every supplied API object and full declared span is pairwise disjoint,
including immutable inputs, raw result, handle output, masks, records,
registrar object, name, logging, reply/read arrays, unused views and tails.
Internal views of one owned mask/object/name span are not additional
caller-supplied aliases. Check all descriptor storage before reading fields
and all spans before following offsets. Arithmetic checks do not prove actual
backing, readability, writability or lifetime; callers provide those.

Host-invalid calls preserve every object and emit no observations. Use the
existing first-open host status categories with these isolated cases:

| Host category | Condition |
|---|---|
| Invalid | Missing required storage/observer, typed misalignment, invalid null view, logging at least four when consumed, or an invalid p16 word/sequence |
| Bounds | Short or excessive byte extent, short reply/read plan, invalid p16-plan extent/product, address wrap, negative registrar count, or a required name without a bounded NUL |
| Overlap | Any intersecting caller-supplied objects or full spans |
| Unsupported | Other outer parameters, object/callback profiles, nonzero open count, VERSION/secondary condition, clear-mask result, nonzero function reply, mismatched MMIO read PC/address/size, or extra reply/read-plan entry |

An empty p16 plan is a bounds failure under the registrar contract. Preserve
that contract's distinctions for nested validation; a negative registrar count
must not become unsupported, and malformed p16 values must not become bounds
failures. When several independent premises fail, any applicable documented
category may be returned; a single violated premise has its listed category.
Host error status is separate from the completed firmware raw one.

A clear mask is unsupported before any effect, because its actual continuation
requires the unresolved service. It is not converted into a fabricated return
or a portable partial execution. Other VERSION/secondary routes, nonzero open
counts, unsupported object/callback profiles and service replies remain outside
this operation. Existing standalone operations keep their own domains.

Observers return normally, preserve inputs/API storage, avoid reentry,
concurrent mutation and hardware access, and keep mutable bookkeeping and
indirectly writable references separate from supplied storage. Read-only
context references may inspect state/results. Indirect references and observer
behavior are caller premises, not properties preflight can prove. No pointer
is retained, allocated or freed.

## Recorded complete call and service boundary

[arm-first-open-post-registrar.json](../../tests/vectors/start4/arm-first-open-post-registrar.json)
retains the exact two-case fixture, SHA-256
`9ac0b3e66c591013cc5b51c54968238cb2759d2292f3aead90c6d3c622a06e7c`.
The complete masked case takes 422 instructions and 12 events. It supplies
P/B 0x400/2, slot zero, default callback, entry SR zero, VERSION 0x40,
secondary zero, configuration source 0x12345678, MMIO word 0x11223344,
low mask 0x40000000/high mask zero, empty registrar and synthetic `irq.c`.
Nested S is six. It returns raw one to the external sentinel with SP restored.
The opaque word remains 0xD3D3D3D3; the handle output remains 0xA5A5A5A5.

The second case supplies clear masks and stops after 429 instructions and
13 events, before executing service entry 0x0ED65284. The actual call at
0x0ED00738 reaches this boundary with 52 bytes of live outer/slot frames.
It has executed the second-slot DI/read and saved status, but has not
returned from the slot or first open. Its initial outer LR equals the stop
by recorder convention; that saved word is not consumed before this call.
This prefix is not an accepted input to the portable masked operation.

Both cases start fresh at the actual first-open entry. Together they compare
66 scalar register words, 10358 bytes and 25 events. Their source-derived
paths visit 310 PCs covering 916 bytes. The recorder compares complete final state,
event order and step totals; it does not export a runtime PC trace. The
single completed profile does not exhaust the source-derived bounded domain.

Five controls reject missing low-mask, opaque-word and service-index reads,
a missing second DI occurrence and a budget before the actual service call.
Each rejection has no result artifact. Earlier effects can have occurred;
recorder rejection does not imply rollback or portable host-error semantics.

### Additional complete calls

[arm-first-open-masked.json](../../tests/vectors/start4/arm-first-open-masked.json)
contains four further complete synthetic calls, SHA-256
`9723fc811759aa8f791406529f51295ea99ec81ed5b3aeba1dbc07e2b55aab5f`.
They exercise the other parameter/switch/record/callback combinations and
conditional registrar paths without repeating either earlier call.

| Case | P/B | Object profile | Callback profile | Registrar path | Steps | Events |
|---|---|---|---|---|---:|---:|
| small-slot1-capacity | 0x80/0 | First free record 1 | Default | Capacity 40 | 216 | 12 |
| medium-stale-match | 0x100/1 | Retained fields | Prior | Matching tuple | 240 | 14 |
| large-slot0-insert39 | 0x200/2 | First free record 0 | Default | Insert at count 39, long basename | 1341 | 12 |
| maximum-stale-empty-insert | 0x400/0 | Retained fields | Prior | Insert at count 0, empty name | 307 | 13 |

| Case | Incoming SR | Derived S | p16 reads | Final SR |
|---|---|---|---|---|
| small-slot1-capacity | 0x400000A5 | 0x400000A6 | 0 | 0x400000A0 |
| medium-stale-match | 0xC00000F9 | 0xC00000F0 | 1, 1, 0 | 0xC00000F0 |
| large-slot0-insert39 | 0xA500003F | 0xA5000036 | 0 | 0xA5000030 |
| maximum-stale-empty-insert | 0x01234567 | 0x01234560 | 1, 0 | 0x01234560 |

Capacity has no name or logging backing; match has no name backing. The
actual calls complete without accessing those absent inputs. Insertions use
synthetic names and the real length, basename and bounded-copy helpers.
Configuration, VERSION/MMIO, mask, opaque, handle and overwritten-state
words also vary. All four return raw one through genuine epilogues, restore
SP and preserve their complete supplied mask views and caller handle words.

The four calls compare 132 register words, 20716 bytes, 51 events and 2104
instructions. The source-derived paths visit 329 PCs covering 976 bytes.
All saved-stack residue and declared guards participate in the comparison.
These samples cover each named branch or profile; they do not exhaust the
Cartesian parameter domain, SR/mask words, records, names or read streams.
The generality of that bounded domain follows the cited control flow and
shared helper contracts, separately from these finite native observations.

Four further controls reject a missing second resource-record self word at
0x0ED7C952, a missing insertion-name NUL at 0x0ED1FC52, an undeclared
capacity-specific p16 write at 0x0EDA728C and an exhausted third busy read
at 0x0EDA7272. Each has the exact request-local diagnostic and no output.
Their predicted instruction positions come from source-derived paths, not
exported runtime counters for failed calls. Earlier memory writes can remain.

### Replay

Use the imported program and versions in [headless analysis](../analysis.md),
with two unused output paths:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EC59D24 0x0ED7C928 0x0ED651FC 0x0ED00582 0x0ED0067E \
  0x0EDA7260 0x0EDA6DA6 0x0ED7B898 0x0EDA6698 0x0ED1FC44 \
  0x0ED00640 0x0ED00700 0x0EC2FCAA \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/arm-first-open-post-registrar.json /work/analysis/arm-first-open-post-registrar.json \
  -postScript CaptureClockVectors.java \
  tests/vectors/start4/arm-first-open-masked.json /work/analysis/arm-first-open-masked.json
cmp tests/vectors/start4/arm-first-open-post-registrar.json /work/analysis/arm-first-open-post-registrar.json
cmp tests/vectors/start4/arm-first-open-masked.json /work/analysis/arm-first-open-masked.json
```

The unchanged Clock recorder retains its VERSION, memory, source/native-cell,
MMIO and [IRQ/p16](vpu-irq.md) guards. The getter's immutable ELF literal is
read from the pinned source; no computational reply supplies its result.
No SWI/RTI execution or service completion is included in either fixture.

## Open questions

- Successful first open. The clear-mask continuation calls 0x0ED65284.
  The separate [service word update](service-word-update.md) verifies its
  selected standalone scalar body, not SWI entry, trap-frame production,
  dispatcher return or RTI. Establish that transition before composing it.
- Runtime state producers. The [initialization prefix](driver-initialization.md)
  clears the driver-control span, but stops before its first lookup SWI.
  Establish startup order and completed index lookup, callback/record state,
  registrar-object/name lifetime and the opaque GP+0x3B484 producer.
- Wider object and callback domains. Extend the shared helper contracts
  with source-backed bounded inputs and differential evidence before
  removing their inherited profile restrictions here.
- Physical observations. Establish IRQ/p16, VERSION and MMIO meanings and
  observable device behavior independently. Explicit values and retained
  software effects do not establish synchronization or a hardware boot.
