<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Bounded suspend registration

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

The registrar at 0x0EDA7260 performs a capacity check, tuple lookup and
conditional insertion into supplied software state. Its 232-byte body
starts at file offset 0x1A6C60 and has SHA-256
`46b093030883a8b54a8d3b39b69ad96b5de380712c04448cbb0fc72b76897296`.
It uses the real [scalar helpers](suspend-helpers.md) and the conditional
[IRQ and p16 observations](vpu-irq.md). The domain below follows the full
control flow and arithmetic bounds. Finite native calls check selected
inputs; they do not enumerate the accepted values.

The operation assumes no asynchronous interrupt arrives and accepts an
explicit finite p16 read sequence. These premises describe a complete
software call. They do not establish physical lock acquisition, runtime
object initialization or a successful [first open](arm-first-open.md).
All tuple words are opaque identities. No callback token is invoked.

The [driver-open callback](driver-open-masks.md) composes this registrar
with an optional two-word mask copy and an outer raw-zero return. Its
whole-call preflight precedes all mask and object writes.

## State and input domain

The native entry receives a first key, callback token, cookie and name
pointer in r0 through r3. It retains the incoming SR word before DI at
0x0EDA7270. GP+0x14E4 supplies the object pointer at 0x0EDA727E.
The portable operation receives the tuple words, incoming SR word S,
object byte view, optional name byte view, conditional logging byte,
finite p16 read plan, event observer and a separate raw-result destination.

The original object and the portable object view share offset zero:

| Field | Object offset | Size in bytes | Access |
|---|---|---:|---|
| Saved SR | 0x00 | 4 | Written on every accepted call |
| Record i first key | 0x1C+36i | 1 | Read during lookup; low byte written on insertion |
| Record i callback token | 0x20+36i | 4 | Read during lookup; written on insertion |
| Record i cookie | 0x24+36i | 4 | Read during lookup; written on insertion |
| Record i basename | 0x28+36i | 22 | Written only on insertion |
| Signed count | 0xB5C | 4 | Read on every call; incremented on insertion |
| Insertion flag | 0xB74 | 4 | Cleared only on insertion |

All word fields are little-endian. The object view contains at least
2936 bytes, through offset 0xB77, and at most 0xFFFFFFFF bytes. Its full
declared extent participates in validation. Each record is 36 bytes;
the record byte view used by lookup begins at object+0x1C. Bytes between
fields, unused records, the gap before count and any declared tail have
no prescribed value and remain unchanged unless a listed store reaches
them. No object clearing occurs.

The initial signed count n is from zero through 0x7FFFFFFF. Counts at
least 40 take the capacity return without accessing records, the name,
the insertion flag or the logging byte. They need no additional record
backing. Negative counts are outside this portable domain: the source
capacity test admits them, and an absent nonzero callback can then use
a negative insertion index. They must not be reinterpreted as empty state.

All three tuple arguments and S are arbitrary unsigned 32-bit words.
Record keys, callback tokens, cookies, padding and unused name bytes are
arbitrary. A zero callback token remains a valid lookup key. The first
key compares as a full word against a zero-extended record byte. A value
such as 0x101 cannot match byte 1; insertion still stores only its low byte.

For n below 40, supply a logging byte from zero through three. The load
at 0x0EDA7318 and comparison at 0x0EDA731E then bypass diagnostic output.
The value is a conditional input, not an inferred initialized global.
For n at least 40, an optional supplied logging value remains unused
and is not numerically validated.

Only an absent tuple with nonzero callback needs name contents. For that
path, the source extent is from 1 through 0x7FFFFFFF bytes and contains
a NUL. Let L be the index of its first NUL; L is from zero through
0x7FFFFFFE. Bytes before it are arbitrary, including 0x80 through 0xFF.
The name is immutable and disjoint from the object. No name contents are
read or termination-checked on capacity, match or absent-zero-callback
returns. An unused name may be a null view with zero extent. Every
supplied view still satisfies the storage rules below.

## Ordered registration behavior

The registrar follows this sequence under the stated domain:

1. Preserve S, execute DI at 0x0EDA7270 and consume p16 reads at
   0x0EDA7272 until the first zero. The object remains unchanged during
   these observations.
2. Write S to object+0 at 0x0EDA7280. Load n at 0x0EDA7282 and perform
   the signed comparison with 40 at 0x0EDA7288.
3. For n at least 40, write S to p16 at 0x0EDA728C, restore SR at
   0x0EDA7292 and return raw 0xFFFFFFFF. All other object bytes remain
   unchanged.
4. For n below 40, run tuple lookup at 0x0EDA72A0 using the three full
   argument words. The helper scans indices zero through n-1 and returns
   the first exact match, as specified in [tuple lookup](suspend-helpers.md#tuple-lookup).
5. A match selects raw zero and leaves every record, count and insertion
   flag unchanged. If no tuple matches and the callback is zero, select
   raw one at 0x0EDA7344 and preserve those same fields. The zero-callback
   test at 0x0EDA72AA follows lookup; a matching zero callback returns zero.
6. For an absent tuple with nonzero callback, compute the basename and
   copy it into record n. Store the first key's low byte at 0x0EDA72F6,
   callback at 0x0EDA72FA and cookie at 0x0EDA72FE. Increment count at
   0x0EDA7308, clear object+0xB74 at 0x0EDA730C and select raw zero.
7. All three n-below-40 paths read saved S from object+0 at 0x0EDA730E,
   write the complete word to p16 at 0x0EDA7310, restore SR at
   0x0EDA7314 and consume the below-four logging byte. Return naturally
   through 0x0EDA7342.

The capacity decision precedes lookup. A full object therefore returns
0xFFFFFFFF even if its records already contain the tuple or its callback
argument is zero. Count 39 permits insertion into record 39 and becomes
40. A subsequent call with that state takes the capacity return.

| Initial state and arguments | Raw return | Writes beyond saved SR |
|---|---|---|
| n at least 40 | 0xFFFFFFFF | None |
| n below 40, matching tuple | 0 | None |
| n below 40, no match, callback zero | 1 | None |
| n below 40, no match, callback nonzero | 0 | Basename, tuple, count n+1 and zero insertion flag |

## Basename and helper composition

The insertion path calls the real length helper at 0x0EDA72B6. Starting
at the last byte before the first NUL, the reverse scan at 0x0EDA72D4
through 0x0EDA72E0 finds the last slash byte 0x2F or backslash byte 0x5C.
The basename starts immediately after that separator. If neither occurs,
it starts at the source's first byte. Empty input and a trailing separator
produce an empty basename. There is no encoding conversion, separator
normalization or special handling of dot components.

At 0x0EDA72F2 the real bounded-copy helper receives the basename, capacity
22 and offset zero. For basename length B it writes `min(B,21)` bytes
and one NUL. It preserves the rest of the 22-byte field and both remaining
bytes in the 36-byte record. All other padding remains unchanged. The
copy helper computes the full basename length through its real nested
length/search calls even when the destination truncates the name. Its
returned length is discarded by the registrar.

The portable computation reuses the existing
[tuple lookup, length and bounded copy](suspend-helpers.md) over bounded
subviews. No supplied result or computational callback replaces lookup,
basename selection, length or copying. The name must terminate within its
complete declared view even when only 21 bytes fit.

## IRQ and p16 observations

The read plan consists of zero or more words equal to one followed by
exactly one zero. It is nonempty and has a finite declared length. Reject
any other value, a missing terminal zero or entries after the first zero.
For q supplied 32-bit read words, require `4*q <= 0xFFFFFFFF` and backing
for that complete span. Compute the product without overflow.
Every read is an independent supplied observation. No prior p16 state or
natural write supplies another read.

Emit one ordered DI observation, every planned read and one write:

| Observation | Value and visible object state |
|---|---|
| DI at 0x0EDA7270 | SR before is S; SR after is S with bit 30 cleared; object unchanged |
| Each p16 read at 0x0EDA7272 | Next declared zero/one word; object unchanged |
| p16 write at 0x0EDA728C or 0x0EDA7310 | Full S, including bit 30; saved SR and all path-specific object writes complete |

The actual following SR restore retains all 32 bits of S. Final native
SR and p16 both equal S. Do not normalize the p16 write to zero or to its
low bit. DI's mask and the later saved-word write/restoration are separate
operations; the no-arrival premise still applies after restoration.
No extra acquire, release, diagnostic or callback event is synthesized.

The native recorder's instruction PCs, operation indices and step indices
are defined by [IRQ observations](vpu-irq.md#natural-execution-and-ordered-events).
The portable observer reports the semantic DI/read/write order and words.
It does not need a VPU register file, instruction counter or physical
mutex. Incidental flags between DI and restoration are not host inputs.
Observers see the incoming raw-result destination throughout; the final
raw result is published only after all observations and writes complete.

## Storage and complete preflight

Perform one complete read-only preflight before DI, observer calls, object
writes or result publication. Validate required arguments, the count
domain, all full extents, overflow, alignment, disjoint storage, the
entire p16 plan and observer availability. Determine the tuple outcome
without effects so that reachable name termination and logging premises
are validated before the first observation. Reuse read-only intermediate
results if desired; this does not change source order or visible state.

Object and name byte views need no alignment. Typed parameters, view
descriptors, event configuration, read-plan words and the raw-result
object require natural alignment. All byte extents are at most
0xFFFFFFFF. Check pointer-plus-extent overflow before pointer arithmetic
or content access. Check read-plan element multiplication before forming
its byte span. The original mapping also requires nonwrapping 32-bit
addresses for its object, records, name and caller stack.

Every supplied API object and full declared span is disjoint from every
other supplied object/span, including immutable inputs, unused views,
the read plan, observer configuration and output. Internal record and
basename subviews belong to the one object view; they are not separately
supplied overlapping arguments. Declared tails participate in overlap
and wrap checks even when their contents are unused. A null optional
view requires zero extent. Zero-length views have no byte span.

The caller supplies actual backing, required readability/writability and
lifetime; arithmetic checks cannot prove that arbitrary pointers name
live allocations. No pointer is retained, allocated or freed. The object,
name and input plan do not change concurrently. Observers return normally,
preserve API objects and arguments, avoid reentry and perform no hardware
access. Read-only context references may inspect object state and result;
mutable observer bookkeeping and indirectly writable storage remain
disjoint from all API objects. These observer behavior and indirect-storage
conditions are caller premises. Preflight checks declared spans; it cannot
discover arbitrary storage reached by an observer or prove its side effects.

On host invalidity, emit no observations and leave every API object and
the raw-result destination unchanged. The host status is separate from
native raw zero, one and 0xFFFFFFFF. All three raw values are completed
executions with the specified saved-SR write and ordered observations;
none requests rollback. A native recorder failure can occur after actual
emulated effects and does not define portable unchanged-state rejection.

## General bounds from control flow

The signed comparison at 0x0EDA7288 partitions the accepted count domain
into 0 through 39 and 40 through 0x7FFFFFFF. The upper partition has no
record or name path. In the lower partition, lookup visits at most 39
records and insertion uses index at most 39. Its product `36*n` is at
most 1404 and the last possible name terminator is at object+0x5B9.
All record accesses fit below the count and flag in the fixed object.
The count increment is at most 40 and cannot overflow a signed word.

Length's bound gives `L+1 <= 0x7FFFFFFF`, so its nested byte search reaches
the NUL before its count-exhausted branch. The reverse scan starts at
L-1, visits at most L bytes and stops at a separator or index -1. No byte
is read at index -1. The native address arithmetic at 0x0EDA72C0 or
0x0EDA72E4 may form a temporary source-minus-one value before adding one
at 0x0EDA72EC. A portable implementation must use bounded integer indices
and avoid forming a host pointer before the source object. The selected
basename is a suffix through the same first NUL and satisfies the scalar
length/copy bounds.

Each read of one repeats only the loop at 0x0EDA7272/0x0EDA7276. The
terminal zero is the sole exit condition; finite plan exhaustion is not
a firmware result. After that exit, the capacity path or bounded scalar
paths reach the common natural return under the logging premise. These
arguments establish the bounded domain independently of the finite
native matrix. They do not prove termination for an unending busy stream.

## Recorded cases and replay

[suspend-registrar.json](../../tests/vectors/start4/suspend-registrar.json)
contains 16 complete calls with synthetic object, name, stack and input
state. Its SHA-256 is
`ad308116d008f0f3ae5a526c9d1292813cd61a159b636114993d08aad063f8dc`.
The fixture contains no function stubs, computational replies, MMIO or
VERSION observations. IRQ/p16 inputs use the existing explicit interface.

| Case | Checked behavior | Instructions |
|---|---|---:|
| capacity-40-busy-status | Count 40, SR bit 30 set, p16 reads 1,1,0 | 25 |
| capacity-41 | Count 41 with fixed object backing | 21 |
| capacity-signed-maximum | Count 0x7FFFFFFF with fixed object backing | 21 |
| absent-zero-callback | Raw one without name storage | 41 |
| matching-zero-callback | Match before the zero-callback test | 46 |
| insert-final-slot | Count 39 becomes 40; p16 reads 1,0 | 443 |
| match-final-existing-record | Last match after all three mismatch gates | 348 |
| wide-key-byte-truncation | Key 0x101 misses byte 1, then stores byte 1 | 213 |
| empty-name-with-tail | Empty name; bytes after NUL preserved | 110 |
| plain-high-byte-name | Name bytes 0x80/0xFF; bytes after NUL preserved | 159 |
| slash-name | Basename after slash | 301 |
| backslash-name | Basename after backslash | 300 |
| trailing-slash-name | Empty basename after slash | 157 |
| trailing-backslash-name | Empty basename after backslash | 156 |
| basename-21 | All 21 data bytes fit | 615 |
| basename-22-truncation | 21 data bytes copied; full length remains 22 | 633 |

The calls total 3589 instructions, 528 observed register words,
49876 observed memory bytes and 51 ordered events. Every case compares
all declared bytes, including its full 2936-byte object, name tails,
128-byte stack, pointer/logging storage and external guards. Capacity
cases omit name and logging storage; match and absent-zero-callback
cases omit name storage. These omissions check actual conditional reads.

All calls start at 0x0EDA7260 with fresh frames and return naturally
through 0x0EDA7342 to an external sentinel. The registrar saves a 36-byte
frame. Actual helper calls add their own frames; the deepest stack use
is 52 bytes. SP and r6 through r13 restore. Complete stack residues and
incidental registers are native observations, not host API parameters
or a required host calling convention.

The independently derived source paths visit 123 instruction addresses
covering 352 bytes across the registrar and its four scalar dependencies.
The ten unvisited instructions belong to the excluded diagnostic path
at 0x0EDA7322 through 0x0EDA733C and the byte-search exhausted-count
return at 0x0ED1FC5A. The runtime recorder compares complete final state,
events and instruction counts; it does not export an executed-PC trace.
The matrix samples boundaries and branches. It does not exhaust all
counts, tuple words, strings, SR words or finite busy streams admitted
by the separate control-flow argument above.

Use the imported program and versions in [headless analysis](../analysis.md),
with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0EDA7260 0x0EDA6DA6 0x0ED7B898 0x0EDA6698 0x0ED1FC44 \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/suspend-registrar.json /work/analysis/suspend-registrar.json
cmp tests/vectors/start4/suspend-registrar.json /work/analysis/suspend-registrar.json
```

Four additional requests check strict capture boundaries:

| Missing premise | Rejection site |
|---|---|
| NUL within a two-byte name view | Search read at 0x0ED1FC52 |
| First basename byte in record 39 | Copy write at 0x0EDA66AC |
| Zero occurrence after two busy reads | Third p16 read at 0x0EDA7272 |
| Declared capacity-path p16 write | Write at 0x0EDA728C |

Each request produces the expected diagnostic and no result artifact.
These are recorder errors after some native instructions have executed,
not firmware raw returns or portable preflight results. In particular,
missing capture output does not imply rollback of earlier emulated writes.

## Open questions

- Runtime producers. Establish the initialization and lifetime of the
  object, count, records and logging byte before using this operation in
  live startup. The pointer load at 0x0EDA727E establishes consumption,
  not initialized state.
- Physical synchronization. Resolve BCM2711 p16 arbitration, write
  semantics and memory ordering separately, as listed in
  [IRQ open questions](vpu-irq.md#open-questions).
- Diagnostics. Inspect and capture the path from 0x0EDA7322 through
  diagnostic call 0x0EDA733C before admitting logging bytes at least four.
- Broader storage domains. Establish negative-count, overlapping-view
  and wrapping-address behavior before extending these bounds.
- Higher composition. Follow the real caller and its remaining work
  before treating this standalone return as a successful first open,
  acquired runtime handle or complete hardware initialization.
