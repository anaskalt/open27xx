<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Resource request control

The behavior below belongs to `start4.elf` from raspberrypi/firmware commit
`ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Addresses are VPU virtual addresses in that file; file offsets start at zero.
The contract covers the fixed call `0x0ED7C9B0(object,23,1,1)`, its logical
dependency calculation and conditional check behavior.

The [ARM control caller](arm-control.md#start-request-software-state) issues
this call at 0x0EC5A85C. Logical index 23 sets request bit 0x00800000. The
dependency callback produces mask 0x180, whose added bits select callbacks
for 0x80 and then 0x100. These are software values and callback arguments.
They do not establish register effects, clock completion or ARM execution.

## Records and selected table

The identified `start4.elf` request function 0x0ED7C9B0 reads these fields:

| Location | Size (bytes) | Observed use |
|---|---:|---|
| Object +0x00 | 4 | Must equal the supplied object address |
| Object +0x08 | 4 | Logical request bits |
| GP+0xDA4C0 | Opaque | Manager mutex object passed by address |
| GP+0xDA4C4 | 896 | Array of 32 records, each 28 bytes |
| GP+0xDA984 | 4 | Selected callback table pointer |
| GP+0xDA988 | 4 | Opaque handle passed to enable/disable callbacks |
| GP+0xDA98C | 4 | Separately held dependency mask |
| GP+0x14B0 | 4 | Pointer to the four-byte aggregate output |
| GP+0xCD4 | 4 | Dependency selection word |

The fixtures place the requested object in array slot 0. A null object or
one whose first word differs from its address returns raw 0xFFFFFFFF at
0x0ED7CAAC, without a diagnostic, mutex call or state change. The matching
self-pointer check does not establish registration, ownership or membership
in the scanned array. No membership test occurs in this entry check.

The reference table is 0x0EDFD200. Its literal pointer occurs at
0x0EE02CBC, file offset 0x20269C. The relevant raw table words are:

| Table offset | Word address | File offset | Target |
|---|---|---|---|
| 0x14 | 0x0EDFD214 | 0x1FCBF4 | 0x0ED550B2, enable callback |
| 0x18 | 0x0EDFD218 | 0x1FCBF8 | 0x0ED54AE0, disable callback |
| 0x1C | 0x0EDFD21C | 0x1FCBFC | 0x0ED56032, dependency callback |

The table address and handle word zero are supplied state. These file
words do not establish the live table after relocation or initialization.
The request fixtures execute the real dependency callback. Complete
manager cases intercept the enable body and supply literal return words.
No disable body executes in the recorded cases.

## Aggregate dependency calculation

In the identified `start4.elf`, helper 0x0ED7C768 scans all 32 records at
GP+0xDA4C4 with a 28-byte stride. It ignores a record whose first word is
zero. For every other record it ORs the word at offset 0x08 into a logical
request word. This scan tests only whether the first word is nonzero; it
does not repeat the caller's self-pointer comparison.

Helper 0x0ED7C786 begins its dependency result with the held mask at
GP+0xDA98C. It scans the logical request bits in increasing index order.
For every set bit it calls the selected table's slot 0x1C with `(0,index)`
and ORs the returned mask. At 0x0ED7C7B6 it writes the result through the
pointer at GP+0x14B0. Wrapper 0x0ED7C832 returns that stored word.

The complete dependency cases call 0x0ED56032 with `(0,23)`. With supplied
GP+0xCD4 equal to either 0 or 1, the result is 0x180. The paths take six
and five scalar instructions respectively. Other logical indexes and
selection values are outside the recorded dependency contract.

## Fixed request sequence

For the matching object and arguments `(object,23,1,1)`, the identified
`start4.elf` function 0x0ED7C9B0 performs this sequence:

1. Call diagnostic boundary 0x0ED17442 at 0x0ED7C9DE with arguments
   `(0x4000,0x0ED7CAB0,object,23,1,1)`, then mutex-acquire boundary
   0x0ED64D02 at 0x0ED7C9E6 with object GP+0xDA4C0.
2. Compute the old aggregate through 0x0ED7C832.
3. Test whether object request bit 23 is clear. Pass that condition to
   check helper 0x0ED7C744 at 0x0ED7CA04. Its false-condition behavior is
   specified below; it is not an automatic error return.
4. After the check returns, set bit 23 in the object's request word at
   0x0ED7CA0C and compute the new aggregate through 0x0ED7C832.
5. If the held mask is nonzero, call dependency slot 0x1C with `(0,23)`
   at 0x0ED7CA3A, then clear its returned bits from the held mask at
   0x0ED7CA40. The old and new aggregate values used for dispatch were
   computed before this clear.
6. If the old and new aggregates differ, process removed bits from 31
   down to 0 through table slot 0x18, then added bits from 0 up to 31
   through slot 0x14. Each call receives the supplied handle and a
   single-bit mask. The enable call site is 0x0ED7CA94.
7. After each potential callback position, compare its selected raw word
   to zero and pass the Boolean result to 0x0ED7C744. A position that
   needs no callback uses zero for this comparison.
8. Call mutex-release boundary 0x0ED64D3A at 0x0ED7CAA8, restore the saved
   frame, and return raw zero at 0x0ED7CAAC–0x0ED7CAAE.

Steps after a check execute only if that check returns. The descending
removed-bit loop is a static control-flow observation; the fixed enabling
cases have no removed dependencies and do not test disable behavior.

With a fresh slot-0 request, no other requests and held mask zero, old
aggregate zero becomes 0x180. The observed enable order is `(0,0x80)` then
`(0,0x100)`. Both supplied return words are zero in the normal manager case.

If a second nonzero record already contains bit 23, both aggregates are
0x180. Slot 0 still receives its request bit, but no enable call occurs.
With held mask initially 0x180 and no prior request bits, both aggregates
are also 0x180; the held mask then clears to zero and no enable call occurs.
In both cases the aggregate output remains 0x180.

The observed diagnostic and mutex replies are literal zero, preserve
other registers and change no memory. These calls establish software
ordering under those replies. They do not establish lock ownership,
registration or synchronization. Callback mutation and concurrent state
changes are outside the contract.

## False-condition context

In the identified `start4.elf`, check helper 0x0ED7C744 saves LR and
allocates a four-byte local. A nonzero argument returns directly. A zero
argument calls 0x0ED64C08 at 0x0ED7C74C. That dispatcher reads:

| Location | Observed operation |
|---|---|
| GP+0xE50 | Read a descriptor pointer into `r2` |
| GP+0xE54 | Read an opaque word into `r0` |
| Descriptor +0x18 | Read callback pointer into `r1` |

At 0x0ED64C12 it tail-branches to that callback. The observed arguments
are `(opaque,callback,descriptor,r3,r4,r5)`, preserving the last three
incoming words. No null check occurs in this dispatcher. Direct cases
with supplied callback return 0 or 7 return that exact raw word.

The check helper branches on the context reply at 0x0ED7C750. Reply zero
allows local cleanup and return. Reply 7 writes a local word of 1 at
0x0ED7C756 and reaches the stop before the `BKPT` instruction at
0x0ED7C75A. No behavior after that instruction is defined by the fixtures.

The original GP literal is 0x0EE04140. Its two fields above are raw zero
words at addresses 0x0EE04F90 and 0x0EE04F94, file offsets 0x204970 and
0x204974. Those file values do not establish live initialization. The
fixtures instead supply descriptor 0x24060010, opaque word 0xC0DEC0DE and
callback destination 0x24070000. The destination is an explicitly
intercepted synthetic boundary, not an identified vendor callback.
Replies change only `r0` and have no memory effects.

The complete manager failure-condition cases distinguish the two replies:

| Trigger | Supplied context reply | Observed behavior |
|---|---|---|
| First enable callback returns 7 | 0 | Continue to enable mask 0x100, then release manager and return zero |
| First enable callback returns 7 | 7 | Stop before `BKPT` after the first enable; no second enable or manager release before the stop |
| Object already contains bit 23 | 0 | Continue, retain the bit, recompute the same aggregate, make no enable calls, release manager and return zero |
| Object already contains bit 23 | 7 | Stop before `BKPT` before the request-word store; no enable or release call before the stop |

In both first-enable cases, the request bit and aggregate 0x180 are
already stored before the check. They are not rolled back before the
observed return or stop. In the duplicate cases, the initial request bit
is already set and the first aggregate has been written before the check.
The value 7 is a literal raw word, not a known error enum. These observations
do not establish the real callback's identity, computation or assertion
policy.

## Real resource-selection prefix

One dispatch fixture starts at the actual 0x0ED7C9B0 entry, executes the
complete resource-0x80 callback and the resource-0x100 prologue/selection,
then stops before 0x0ED55648 in the identified `start4.elf`. It supplies
GP+0xCD4=0, GP+0x1564=1 and GP+0xD33F8=0. The prehook at 0x0ED56136 ORs
each mask into GP+0xD33FC, changing its supplied zero to 0x80 and then 0x180.

The real getter calls return table pointers 0x0EDFA4DC and 0x0EDE54A8.
Each resource invocation executes wrapper 0x0EC58CEE and the resource
acquisition call. Resource 0x80 takes the selection-word branch to the
common return, executes wrapper 0x0EC590BC and restores its saved frame.
Only the actual mutex functions are intercepted. Resource 0x100 then
reaches the stop with these observed values:

| Field | Value |
|---|---|
| `r0` | 0x180 |
| `r6`, `r8` | GP+0xD33EC |
| `r7` | 0x100 |
| `r9` | 0x0EDE54A8 |
| `r11` | 0x0EDFA4DC |
| `r12` | 0xFFFFFFFF |
| SP | Initial SP minus 88 bytes |

The real prologues save 32 manager bytes and 36 resource bytes, then
allocate 20 resource-local bytes. The nested resource return address is
0x0ED7CA96. The recorder seeds incoming LR from its stop address, so the
manager frame contains synthetic outer LR 0x0ED55648. These actual saved
frames are not a natural caller frame ready for a full unwind. The prefix
does not execute the selected clock/release body or return from the request.

The three context prefixes likewise seed incoming LR with stop 0x0ED7C75A.
They stop with SP below its input by eight bytes for a direct check or
40 bytes for a manager check. The latter helper return word is 0x0ED7CAA2
for the enable-result check, or 0x0ED7CA08 for the duplicate-request check.
Each local flag is 1. These are instruction-boundary observations, not
returned failure statuses.

## Portable representation and host preconditions

The fixed software operation can be represented without native VPU
pointers or stack layout. The following representation names observable
state; it does not define a hardware interface:

| Portable input or state | Required meaning |
|---|---|
| Explicit object-present flag | Distinguish the vendor-null case from a host API pointer error |
| Object identity and stored self identity | Unsigned 32-bit tokens compared for equality |
| Requested record selection | For a present matching object, select its request word in the supplied 32-record array; fixtures use slot 0 |
| 32 records | Each holds a 32-bit presence/self word and 32-bit logical request word; scanning uses only nonzero presence |
| Held dependency mask | Mutable 32-bit word corresponding to GP+0xDA98C |
| Aggregate output | Mutable 32-bit word written by each aggregate calculation |
| Dependency operation | Fixed index 23 returns 0x180 for the documented selection inputs |
| Enable boundary | Opaque handle, single-bit mask and an explicit raw reply |
| Check-context boundary | Explicit callback/descriptor identities, opaque word and literal reply; no inferred initialization |
| Diagnostic and mutex boundaries | Ordered observable calls, with the documented unchanged-state replies |

Use a tagged outcome for a returned raw word versus a stop before `BKPT`.
The stopped outcome preserves the state already changed and the call
prefix already emitted. It has no vendor return word. A direct context
reply 7 is a returned word; a manager/check prefix with `r0=7` at the stop
is not a returned result. Incidental registers and native stack addresses
remain emulator observations rather than portable API parameters.

Host validation must establish buffer lengths, writable state/output and
an in-range record selection before accessing caller-owned memory. Reject
unsupported input shapes before emitting calls or changing state. The
supported input restrictions are:

| Input | Supported domain |
|---|---|
| Logical index and two request arguments | 23, 1 and 1 |
| Dependency selection GP+0xCD4 | 0 or 1; complete manager fixtures use 0 and direct dependency fixtures cover both |
| Every logical request word | Zero or 0x00800000; no other bits |
| Held dependency mask | Zero or 0x180 |
| Present requested identity | Nonzero token identifying the selected record |
| Matching requested record | Its stored self token equals the requested identity |
| Other record presence/self words | Zero for inactive records; active fixture records contain their own identity token |

Represent an absent requested object and a mismatched stored self token
explicitly. They are vendor input cases that return raw 0xFFFFFFFF, not
host pointer errors. A represented mismatch must retain that vendor result;
it must not be silently converted into host validation failure. An absent
host API pointer must not silently select the vendor-null case. Identity
tokens express the observed comparison without asserting ownership.

The portable input supplies the literal reply words before execution, as
the fixtures do. Preflight the providers reachable under that declared
reply plan before emitting calls or changing state. A fresh request whose
first enable reply is 7 therefore requires the context provider in advance;
a true condition needs no context fields or provider. Providers that may
return an undeclared word or mutate state are outside this contract. No
error or rollback policy for such providers is defined here.

An unavailable context on a reachable false-condition path must not become
an implicit zero reply. Host validation errors remain distinct from vendor
raw words and the pre-`BKPT` outcome. Callback identity tokens label the
selected boundary; incidental argument-register contents and native callback
addresses do not prescribe a host calling convention.

The fixtures cover fresh, shared, held and duplicate states, unchanged-state
diagnostic/mutex replies zero, enable replies zero or first reply 7, and
context replies zero or 7. These are the fixed observed reply sets, not
general callback failure semantics. They do not establish arbitrary
logical-index mappings, arbitrary record identity relationships, disable
parity, callback memory effects or missing-context recovery. Keep a real
callback/initialization provider outside this portable contract until its
behavior is specified and verified.

## Recorded cases and replay

The two fixture sets contain only synthetic state, literal replies and
observations. They retain separate complete-call and prefix scopes:

| Fixture | Cases | Instructions | Complete calls / prefixes | SHA-256 |
|---|---:|---:|---|---|
| [resource-request.json](../../tests/vectors/start4/resource-request.json) | 8 | 4093 | 7 / 1 | `5b0906663e4f25159c7cdbfad9a91b3adb5694f076f51d9886f00d4c7d1ff925` |
| [resource-context.json](../../tests/vectors/start4/resource-context.json) | 9 | 3679 | 6 / 3 | `c457573e8441a92df1608838d9d5248304477c542765086fd239fe2912e8158d` |

The first set records both dependency selections, null/mismatched objects,
fresh/shared/held requests and the actual-entry resource prefix. The second
records two direct context returns, true/false checks, and complete or
stopped manager paths for enable reply 7 and duplicate requests. All
callback arguments, declared state, guards, observed registers and counts
are compared. No MMIO or exception instruction executes.

Use the imported program and versions in [headless analysis](../analysis.md).
Run from the repository root with unused output paths. The preparation
script defines transient instruction metadata without changing source
bytes or instruction semantics. This command replays both sets:

```sh
for fixture in resource-request resource-context; do
  GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
    /work/analysis/projects firmware_a \
    -process start4.elf -readOnly -noanalysis -max-cpu 1 \
    -scriptPath tools/ghidra \
    -postScript DecodeScalarPaths.java \
    38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
    0x0ED7C9B0 0x0ED7C744 0x0ED7C768 0x0ED7C786 0x0ED7C832 \
    0x0ED56032 0x0ED550B2 0x0ED00582 0x0EC52ED2 0x0EC58CEE \
    0x0ED56136 0x0EC590BC 0x0ED64C08 \
    -postScript CaptureScalarVectors.java \
    "tests/vectors/start4/$fixture.json" \
    "/work/analysis/$fixture.json"
  cmp "tests/vectors/start4/$fixture.json" \
    "/work/analysis/$fixture.json"
done
```

Compare the complete JSON, including reply indexes and every specified
memory byte. The unchanged recorder rejects missing state, exhausted or
unused replies, writes outside declared memory, modified instruction bytes
and unsupported operations. Omitting GP+0xE50 fails at 0x0ED64C08; omitting
GP+0xE54 fails at 0x0ED64C0C; omitting the callback slot fails at 0x0ED64C10.
Removing the pre-`BKPT` stop causes rejection at 0x0ED7C75A before execution.
These are recorder failures, not vendor return values.

## Open questions

- Context initialization and callback. Trace the writers of GP+0xE50/+0xE54
  and the selected descriptor before assigning a runtime target, context
  meaning or assertion policy. Raw zero file words do not settle this.
- Registration and other requests. Establish object acquisition, record
  lifetime, additional logical dependency mappings and disable behavior
  before extending the fixed request domain or defining ownership rules.
- Live resource effects. Verify the selected resource body, its clock and
  service dependencies, initialized state and physical readbacks before
  interpreting callback order or a raw-zero return as ARM release.
- Synchronization and callback mutation. Execute the real boundaries and
  study their state effects before extending the unchanged-state callback
  premise or defining concurrent operation.
