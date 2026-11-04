# Boot information

The parser and allocation behavior below apply to `start4.elf` from
raspberrypi/firmware commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`,
SHA-256 `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
Parser entry is 0x0EC644E0. The bootloader-state pointer store applies to
`bootmain` from raspberrypi/usbboot commit
`fdb604d018693465c9aa6ec69879df866d2820da`, SHA-256
`4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d`.
Its observed block starts at 0x00086990 and stops before 0x000869A8.

The contract covers parsing supplied records, caching their copies and
preparing a state-pointer field. It does not establish record acquisition,
physical memory placement, complete platform initialization or ARM release.

## State-pointer field

In pinned `start4.elf`, `.text.bootloader_state` occupies 16 bytes at
0x0EE04110, file offset 0x203AF0. Its first two words contain marker
0x41545342 and an initially zero pointer. Entry instruction 0xCEC00202
loads GP from the table word at 0xCEC00290, file offset 0x870, whose value
is 0x0EE04140. The section's pointer word is therefore at GP−0x2C.

| Section offset | Size (bytes) | Meaning |
|---|---:|---|
| 0x00 | 4 | Marker 0x41545342 |
| 0x04 | 4 | Boot-information pointer |
| 0x08 | 8 | Outside this pointer-store contract; preserved |

Pinned `bootmain` looks up the section at 0x0008698C. The block at
0x00086990 leaves a null section pointer alone. For a nonnull section,
it reads the marker; a match writes 0x00040000 to the word at offset
0x04. A different marker leaves the section unchanged. The block neither
reads nor validates the memory addressed by the written pointer.

A host operation needs a writable section buffer with at least 8 accessible
bytes when the section is present. It must reject an insufficient buffer
before an access. Treat an absent section as unchanged. Buffer-length
validation is a host requirement, not a check in this vendor block.
All fields use little-endian representation independently of host alignment.

## Parser state

Pinned `start4.elf` parser 0x0EC644E0 uses the following state:

| Location relative to GP | Size (bytes) | Meaning |
|---|---:|---|
| −0x2C | 4 | Source pointer |
| 0x171C | 4 | Completion word |
| 0x1734–0x176C | 60 | Fifteen cached record pointers |
| 0xFCD8 | 1 | Diagnostic verbosity; recorded cases use zero |

A host parser can represent these fields as a source buffer, a completion
word and a cache indexed by the tags below. The GP offsets describe vendor
state; they are not required host memory addresses. A cached pointer refers
to a copy that includes the record header. Cached copies must outlive their
use and subsequent parser calls.

At 0x0EC644E8–0x0EC6451A, the parser applies these conditions in order:

1. A null source returns without changing completion or the cache.
2. A nonzero completion word returns without reading the source.
3. A first word other than 0x45545342 sets completion to 1 and returns.
4. For matching magic, an unsigned total length above 32768 returns
   without setting completion.
5. Otherwise, the parser computes the end address from source plus total
   length and walks records while the current address is below that end.
   A zero total length produces an empty walk and completion 1.

No function return status is established for this parser. Completion and
cache contents are the observed outputs. A nonzero completion word prevents
later parsing even if the source changes.

## Record layout

The pinned parser at 0x0EC6450A and 0x0EC64862 uses unsigned 32-bit
little-endian fields. The first record is the outer header itself.

| Offset | Size (bytes) | Outer header | Child record |
|---|---:|---|---|
| 0x00 | 4 | Magic 0x45545342 | Tag |
| 0x04 | 4 | Total declared length | Declared copy length, including header |
| 0x08 | 4 | Relative offset to next record | Relative offset to next record |

The next offset is relative to the current record, not the outer header.
Zero terminates the walk. A nonzero value advances the current address;
reaching or passing the outer end also terminates the walk. Both ordinary
termination paths set completion to 1 at 0x0EC6486E. The outer magic itself
causes no allocation or copy.

The dispatch at 0x0EC6453C–0x0EC6485E recognizes these tags:

| Tag | Cached pointer offset from GP | Capacity (bytes) |
|---|---|---:|
| 0x434D4D42 | 0x173C | 16 |
| 0x42535542 | 0x1768 | 80 |
| 0x36565049 | 0x1748 | 48 |
| 0x43455342 | 0x1760 | 76 |
| 0x454D564E | 0x174C | 20 |
| 0x43545242 | 0x1758 | 28 |
| 0x45535047 | 0x1738 | 16 |
| 0x4E545342 | 0x1744 | 200 |
| 0x4D545342 | 0x1740 | 88 |
| 0x4B534452 | 0x1754 | 36 |
| 0x4E4F4342 | 0x1734 | 16 |
| 0x52455642 | 0x176C | 164 |
| 0x52445342 | 0x175C | 24 |
| 0x52575042 | 0x1750 | 152 |
| 0x53545342 | 0x1764 | 24 |

For an uncached recognized record, the pinned parser calls 0x0EC731F6
with arguments 1 and the tag's capacity. It caches the returned pointer
and copies the smaller of the declared length and capacity through
0x0ED1FC8A. The copy starts at the tag word and includes as much of the
header as that length permits. A zero declared length still allocates
and caches storage but copies no bytes.

An already nonzero cache slot prevents another allocation or copy for
that tag. The first encountered record wins; a preexisting cached record
wins over every source record. An unknown tag causes no allocation or
copy. Both cases still read the next-offset field and continue the walk.
The parser neither changes the source nor clears an uncopied destination
tail. Allocation initialization is a separate operation.

## Allocation composition

Pinned `start4.elf` entry 0x0EC731F6 multiplies its count and item-size
arguments and passes the product, literal 32, literal 1 and the incoming
link-register word with bit 31 set to 0x0ED649A8. The tested products do
not overflow; parser calls use count 1 and capacities no greater than
200 bytes. The meanings of the lower allocator's other arguments are
outside this contract.

Wrapper 0x0ED649A8 calls the lower heap allocator at 0x0ED64EBC. A null
result returns null without clearing a destination. A nonnull result
causes exactly the requested number of bytes to be cleared through
0x0ED1FDF0 before the pointer is returned. A supplied nonnull result for
a zero-byte request remains unchanged. This does not establish whether
the actual lower allocator returns a pointer for such a request.

Keep these two operations separate in a host interface:

1. The core parser requests a capacity from an allocation callback,
   caches the successful result and copies the bounded prefix. It
   preserves all other bytes supplied by that callback.
2. The zeroing allocation wrapper requests storage from a lower callback,
   clears the requested span on success and returns the pointer. It
   returns null when the lower callback returns null.

Composing the parser with the zeroing wrapper reproduces normal cleared
storage followed by the record copy. Supplying prefilled storage directly
to the core parser exposes its unchanged-tail behavior. The recorded
core-parser cases use 0xA5-filled storage; the composed cases execute real
zeroing before the copy. Neither behavior should be folded into the other.
The parser's response to allocation failure is not established; successful
storage allocation is a precondition of its supported copy paths.

## Lookup and bounded revision selection

Pinned `start4.elf` lookup 0x0EC642FC calls the parser before selecting a
cached pointer. Recorded calls for tag 0x52455642 return its cache slot
when populated. An unknown tag returns zero; an incomplete parse with a
null source also returns zero.

An internal fallback block at 0x0EC6246E requests that tag and examines
the word at copied-record offset 0x68. The recorded block stops before
0x0EC624C0, with the preceding fallback gates assumed and GP+0x1564
supplied as 1.

| Supplied word at offset 0x68 | Selected local revision value |
|---:|---|
| 0 | 0x00A03110 |
| 2 | 0x00A03114 |
| 4 | 0x00C031C0 |
| 6 | 0x00A03115 |
| Record absent | 0x00A03110 |

These are fallback outputs for synthetic inputs. They do not identify a
physical board or establish the earlier gates, raw information acquisition,
complete board initializer or ARM loader selection. An implementation of
this internal decision remains separate from the generic record parser.

## Bounds and host requirements

Pinned parser 0x0EC644E0 uses the declared total length to stop traversal;
it does not validate every header or copied prefix against that length.
A total length of 8 with 12 actual accessible bytes still reads the next
word at offset 8. A total length of 32768 with a terminating first header
reads only that header. A child length above its capacity needs backing
for the copied prefix, not for the entire declared child length.

A checked host interface must use the actual supplied buffer extent for
memory safety and keep it distinct from the declared total length:

- Read the magic only when 4 source bytes are accessible. For matching
  magic, require 8 accessible bytes before reading the total length.
- Before each traversed record, require its 12-byte header. Before a
  copy, require the smaller of its declared length and capacity.
- Check additions and offsets before use. Require a finite traversal
  with no wrapped addresses or cycles.
- Require each successful allocation to provide at least the requested
  capacity, with storage separate from source bytes and other live copies.
- Define a host failure result for missing backing, arithmetic failure or
  allocation failure. Do not report it as a recovered vendor return code.

The accessible extent need not equal the outer declared length. Apply
bounds to actual reads and writes; the terminating-header cases above
remain valid with their supplied backing. Partial mutation on rejected
inputs is outside the observed finite-input contract and must be defined
by the host API. Portable field access must not rely on host endianness
or pointer alignment.

A header with total length 12 but only 8 accessible bytes reaches the
missing next-word read at 0x0EC64862. A child declaring 164 bytes with only
its 12-byte header backed reaches an unavailable read in memcpy at
0x0ED1FC9E. Strict emulation stops at these accesses. These failures are
not vendor error outputs or evidence of a general malformed-input policy.

## Recorded cases

| Fixture | Cases | Scalar instructions | Boundary |
|---|---:|---:|---|
| [boot-information.json](../../tests/vectors/start4/boot-information.json) | 70 | 6681 | Real parser, lookup and bounded fallback; allocation result supplied |
| [boot-information-allocation.json](../../tests/vectors/start4/boot-information-allocation.json) | 8 | 767 | Real wrappers and zeroing; lower heap result supplied; two composed parser cases |
| [boot-information-pointer.json](../../tests/vectors/bootmain/boot-information-pointer.json) | 3 | 11 | Real bootmain marker check and pointer-word store |

Each fixture includes the source identity, entry/stop addresses, synthetic
registers and memory, intercepted call replies and observed outputs. No
fixture reads physical boot information, executes MMIO, enters the heap
implementation or releases an ARM core. Parser cases exercise all fifteen
capacities at lengths 0, capacity minus 1 and capacity plus 17, along with
empty, unknown, duplicate, cached and lookup cases.

For host tests, reconstruct source bytes at synthetic address 0x24000000
and parser state from the declared GP-relative locations. Map synthetic
allocation pointers to test-owned buffers. Preserve cache identity across
a call; pointer words in expected memory identify which buffer is cached.
Use allocation events to check requested capacity and call count. Compare
the complete observed source, cache and destination bytes, including guards.
Register `r0` is an output only for cases that explicitly observe it;
internal fallback cases observe local `r6`, not a standalone function return.
The fixture's physical register setup is an execution harness, not a host ABI.

## Open questions

- Record production and lifetime. Trace the state constructor and relocation
  path with synthetic data to connect the section pointer to live records.
- Lower heap behavior and parser allocation failure. Test these separately
  with a bounded synthetic heap; the successful-copy contract does not
  supply heap mechanics or a parser failure policy.
- Cache reset and initialization order. Establish when completion and cached
  pointers are initialized or invalidated, and their order relative to SoC
  selection and configuration processing.
- Payload meanings beyond the tested fallback field. Establish each field
  from its producer and consumers before using it for platform decisions.
- Hardware handoff. Establish mapping, cache visibility, reset release and
  ARM entry independently of this parser and metadata-pointer contract.
