<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Driver-open mask registration

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, 2303104 bytes, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file. File offsets start at zero.

The callback at 0x0ED0067E optionally copies two mask words, calls the
actual [suspend registrar](suspend-registrar.md), then returns raw zero.
Its 46-byte body starts at file offset 0x10007E and has SHA-256
`7c529b05c672835f09c2afbe4f8c03ecbb7ac4fe06433cb05fe6b190faccffbd`.
The general behavior follows its complete control flow and the bounded
registrar contract. Six native calls check selected paths; they do not
restrict the accepted inputs to six profiles.

## Optional mask copy

Incoming r0 is either zero or a pointer to two little-endian words. For
zero, the branch at 0x0ED00680 skips all source reads and mask stores.
For a nonzero pointer, the callback performs these accesses in order:

| Order | Instruction address | Access |
|---:|---|---|
| 1 | 0x0ED00684 | Read source+4 as the high word |
| 2 | 0x0ED00686 | Read source+0 as the low word |
| 3 | 0x0ED00688 | Write low word to GP+0xCB498 |
| 4 | 0x0ED0068E | Write high word to GP+0xCB49C |

Both source words are loaded before either destination store. Their values
are arbitrary unsigned 32-bit words; no bit mask or normalization applies.
The copy precedes every registrar path, including its capacity return.
There is no restoration of previous masks when the registrar is full.

The portable destination byte view begins at original GP+0xCB498: low word
at offset zero, high word at offset four. It is required and contains from
8 through 0xFFFFFFFF bytes. Only the first eight bytes can change. All
remaining destination bytes retain their incoming values, including when
the source is present. An absent source preserves the complete destination.

The optional source is a separate immutable byte view. A null descriptor,
or a descriptor with null bytes and zero extent, means no copy. A nonnull
byte pointer means a present source and requires 8 through 0xFFFFFFFF
bytes. A null byte pointer with nonzero extent is invalid. Only the first
eight source bytes are read; its full declared extent participates in
storage checks. Source and destination are disjoint and need no alignment.
Use byte-wise little-endian access without assuming aligned host words.

Requiring a destination view on the no-copy path is a portable storage
rule. The native null-source path does not access the mask destination.
The finite native cases use aligned words; unaligned byte views are a
portable storage requirement, not an additional native observation.

## Fixed registration and result

The callback forms the following registrar arguments at 0x0ED00694 through
0x0ED006A2, then calls 0x0EDA7260 at 0x0ED006A4:

| Registrar argument | Value or source |
|---|---|
| First key | 1 |
| Callback token | 0x0ED004C6 |
| Cookie | 0 |
| Name bytes | GP+0x9FE0 |
| Incoming status S | The callback's incoming SR word |

The tuple is fixed by this body. It is not a caller-selected tuple or a
literal fixture choice. Token 0x0ED004C6 is a comparison and stored-record
identity; this operation never invokes it or converts it to a host function
pointer. It is nonzero, so the registrar's absent-zero-callback route is
unreachable here. Incoming native r1 is overwritten before registration;
it does not supply an output address consumed by this callback.

The portable operation supplies a bounded name view for the original
GP-relative name source. Any byte string permitted by the registrar's
termination rules is accepted; `driver.c` is only a synthetic test input.
No literal vendor name or basename is embedded in the operation. The view
does not establish a runtime alias or name-initialization sequence.

Use the actual existing registrar computation with this fixed tuple.
Its state, lookup, basename selection, scalar length/copy composition,
logging condition and ordered IRQ/p16 observations remain unchanged.
No supplied computational result or return-only callback replaces it.

At 0x0ED006A8 the outer callback discards the completed registrar result
and selects raw zero. The real outer epilogue is at 0x0ED006AA.

| Initial registrar state | Registrar raw result | Outer raw result | Retained effects |
|---|---|---|---|
| Count at least 40 | 0xFFFFFFFF | 0 | Optional masks and saved S |
| Count below 40, fixed tuple present | 0 | 0 | Optional masks and saved S |
| Count below 40, fixed tuple absent | 0 | 0 | Optional masks, saved S and actual insertion |

The outer zero does not mean that insertion occurred. A capacity return
retains the mask copy and saved status but leaves records, count and flag
unchanged. A match preserves those same fields. Insertion stores the fixed
tuple and basename, increments count and clears the insertion flag.

## General registrar domain and observations

The portable operation receives incoming S, the mask views, registrar
object view, optional name view, conditional logging byte, finite p16 plan,
all three registrar observers and a separate required outer raw-result.
It constructs the fixed tuple internally. S and both initial/source mask
words accept arbitrary unsigned 32-bit values.

The complete [bounded registrar domain](suspend-registrar.md#state-and-input-domain)
applies, with the fixed tuple above:

- The object contains 2936 through 0xFFFFFFFF bytes. Its signed count is
  from zero through 0x7FFFFFFF. Other record fields and padding are arbitrary.
- Count at least 40 performs no record lookup or name/logging content
  access. It needs no enlarged backing and permits absent name and logging.
- For count below 40, logging is required and lies from zero through three.
  The first exact matching tuple wins. All nonmatching records are valid
  arbitrary data, including records with zero callback tokens.
- Only an absent tuple with count below 40 requires a name. Its extent
  is from 1 through 0x7FFFFFFF bytes with a NUL inside. Bytes before the
  first NUL are arbitrary. Basename selection and 21-byte truncation use
  the real shared helpers; no fixed name length is assumed.
- Capacity and match routes do not read name contents or test termination.
  Unused supplied name/logging contents are not numerically or semantically
  validated, but every supplied object and full span still passes storage
  checks. Unused name may be absent or a valid unused view.
- The finite read plan contains zero or more ones followed by exactly one
  zero, with nonzero word count q and `4*q <= 0xFFFFFFFF`. It supplies no
  default read. The explicit no-interrupt-arrival premise still applies.

All observations are the registrar's actual semantic DI/read/write events.
Mask stores are ordinary software-state writes and add no observer event.

| Observation boundary | Mask destination | Registrar object | Outer raw-result |
|---|---|---|---|
| DI and each p16 read | Copy already complete, or original masks for absent source | Original object | Incoming value |
| Final p16 write | Same retained masks | Saved S and all path-specific writes complete | Incoming value |
| Completed outer call | Same retained masks | Completed registrar state | Zero |

DI reports S before and S with bit 30 cleared after. Every read reports its
supplied word. The final p16 write reports full S, and native SR restores
to S. These observations do not establish physical IRQ synchronization.
Publish the outer raw result only after the final observer returns normally
and registration completes. Keep the registrar's raw result in separate
internal storage; it must never be published through the outer destination.

## Whole-call preflight and composition

Complete a read-only preflight of the entire operation before either mask
store, DI, any observer, any object write or outer result publication.
This includes all required pointers, alignment, full spans, overflow and
overlap checks, source-presence rules, count, logging, complete p16 plan,
observer availability and conditional name termination. Determine fixed-tuple
lookup and the reachable name requirements without effects.

Factor or expose reusable read-only validation from `suspend_register` so
both the standalone registrar and this composition use the same domain
checks. Use that validation before copying masks, then execute the existing
registrar computation with the fixed tuple and a private raw-result word.
A shared validated execution path is permitted if both operations use it.
Do not duplicate lookup/basename logic in a second implementation, invoke
the registrar speculatively, or rely on its later validation after masks
have already changed. Merely restoring masks on error is insufficient:
host-invalid calls must produce no intermediate write or event.

Every caller-supplied descriptor, scalar-input object, read plan, observer
configuration, result object and full byte span is pairwise disjoint.
This includes source and destination, name, registrar object, logging,
unused views and all declared tails. Check pointer-plus-size arithmetic
and read-plan multiplication before forming offsets or reading contents.
Zero-length views have no byte span. Null optional descriptors represent
only their documented absence; nonnull descriptors themselves require valid
storage even when their bytes are unused.

Typed objects and read-plan words require natural alignment; byte storage
does not. All byte extents are at most 0xFFFFFFFF. Internal registrar record
and basename subviews belong to the one object/name view and are not new
caller-supplied aliases. Private tuple and result objects do not relax any
overlap check involving caller-owned inputs or the outer result.

The caller provides actual readable/writable backing and lifetime, with
no concurrent mutation. Span arithmetic cannot prove allocation validity.
Observers return normally, preserve inputs and API objects, avoid reentry
and perform no hardware access. Read-only context references may inspect
masks, object and the old outer result. Mutable observer bookkeeping and
all indirectly writable storage remain disjoint from supplied API storage.
Those indirect-storage and observer-behavior conditions are caller premises;
preflight cannot inspect arbitrary references held by an observer.

Because validated masks are disjoint from registrar inputs, their copy
cannot invalidate an accepted registration premise. With immutable input
state and conforming observers, later validation cannot introduce a new
host failure after the first mask store. No pointer is retained, allocated
or freed. Original GP, source addresses and callback identities do not
become host addresses.

Host invalidity leaves masks, source, object, name, all API storage and the
outer raw-result unchanged, and emits no observations. Use the registrar's
host status categories for invalid arguments, bounds and overlapping spans.
Host errors are separate from the completed outer raw-zero result and from
the discarded registrar raw 0xFFFFFFFF. Native recorder rejection can occur
after actual effects and does not define portable rollback.

## Recorded calls and replay

[driver-open-masks.json](../../tests/vectors/start4/driver-open-masks.json)
contains the six complete calls, SHA-256
`39f2b2f6f46096c5a783fd451e8d687371b4c91696ea0ad246013854c79b647c`.
All object, mask, optional source, name and stack inputs are synthetic.
Null cases retain 0x89ABCDEF/0xFEDCBA98; copy cases write source pair
0x01234567/0x76543210. The full source and all guard bytes remain unchanged.

| Case | Count | Incoming S | p16 reads | Instructions |
|---|---:|---|---|---:|
| null-capacity | 40 | 0x00000006 | 0 | 30 |
| null-existing | 1 | 0x00000006 | 0 | 55 |
| null-insertion | 0 | 0x00000006 | 0 | 312 |
| copy-capacity | 40 | 0x40000006 | 0 | 34 |
| copy-existing | 1 | 0x40000006 | 0 | 59 |
| copy-insertion | 0 | 0x40000006 | 1, 1, 0 | 320 |

The calls total 810 instructions, 198 compared scalar register words,
18994 observed bytes and 20 ordered events. All enter the actual callback
with a fresh four-byte outer frame; the registrar and scalar helpers add
their genuine frames. Every call executes the natural outer epilogue and
restores SP. Full stack residue and every declared byte are compared.

The independent source-derived paths visit 133 PCs covering 390 bytes
across the callback and its dependencies. The runtime recorder compares
final state, event order and step totals; it does not export a PC trace.
These six calls do not exhaust mask words, counts, records, names, S or
finite busy streams supported by the source-derived bounded domain.

Use the imported program and versions in [headless analysis](../analysis.md),
with an unused output path:

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript DecodeScalarPaths.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  0x0ED0067E 0x0EDA7260 0x0EDA6DA6 0x0ED7B898 0x0EDA6698 0x0ED1FC44 \
  -postScript CaptureScalarVectors.java \
  tests/vectors/start4/driver-open-masks.json /work/analysis/driver-open-masks.json
cmp tests/vectors/start4/driver-open-masks.json /work/analysis/driver-open-masks.json
```

The existing [IRQ/p16 interface](vpu-irq.md) and scalar guards remain active.
The fixture contains no MMIO, VERSION, SWI, RTI or computational stubs.
Four controls reject missing high-source backing at 0x0ED00684, missing
low-source backing at 0x0ED00686, missing high-destination backing at
0x0ED0068E and a short budget before 0x0ED006AA. Each produces no result
artifact. The latter two can follow earlier writes; missing capture output
does not imply rollback.

## Open questions

- Runtime mask, object and name producers. Establish executed initialization
  and lifetime before treating explicit inputs as live startup state.
  Known optional-copy and initialization relationships do not prove it.
- Higher caller and opaque output. The first-open call at 0x0EC59E56 supplies
  a null source. Nonnull standalone cases do not establish a higher runtime
  path. This callback does not write GP+0x3B484 or produce its opaque word;
  identify its actual producer before claiming a successful first open.
- Physical synchronization and later services. Resolve the registrar's
  [IRQ questions](vpu-irq.md#open-questions) and later SWI/RTI boundaries
  separately. No fixed callback token is invoked here.
- Broader storage. Establish overlapping-source/destination or registrar
  aliases, wrapping addresses and negative-count behavior before extending
  the present disjoint, nonwrapping domain.
