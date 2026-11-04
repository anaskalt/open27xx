# BCM2711 VPU build

The `open27xx-start4` profile builds an unsigned ELF32 VPU image from
librerpi/lk-overlay's `rpi4-start4` project. It includes the upstream UART,
VPU clock, interrupt and scheduler initialization. It does not start the
Cortex-A72, load Linux files or serve mailbox properties. Hardware behavior
is unverified.

## Build

Requirements: Linux, Python 3.9 or later, Git, GNU Make and a vc4-toolchain
installation with the C and C++ frontends and `libgcc`. The toolchain must
provide `vc4-elf-gcc`, `vc4-elf-ld`, `vc4-elf-size`, `vc4-elf-nm` and
`vc4-elf-objcopy`.
The freestanding build does not use a target C++ standard library.
The compiler patch uses the C `limits.h` header, removes an unused
namespace directive and supplies C++14 assertion messages. It leaves
the upstream fixed-point arithmetic unchanged.

The VPU compiler build uses these revisions:

| Repository | Commit |
|---|---|
| itszor/vc4-toolchain | `2f57f093ef6bc77470152f00e98f38843e8fbbc3` |
| puppeh/binutils-vc4 | `708acc851880dbeda1dd18aca4fd0a95b2573b36` |
| puppeh/gcc-vc4 | `0fe4b83897341742f9df65797474cb0feab4b377` |
| puppeh/newlib-vc4 | `89abe4a5263d216e923fbbc80495743ff269a510` |
| puppeh/resim | `cdc7808ceb7ba4ac00d0d08ca646b58615059150` |

The compiler identifies itself as GCC 6.2.1, dated 20161217; the linker
identifies itself as GNU binutils 2.23.51. Enable the C++ frontend when
building GCC; a C-only installation cannot compile the clock helpers.

```sh
make -C src/start4 fetch
make -C src/start4 JOBS=2
make -C src/start4 check
```

Set `TOOLCHAIN_PREFIX=/path/to/bin/vc4-elf-` when the tools are outside
`PATH`. `JOBS` accepts 1 or 2. `fetch` downloads only pinned public source;
it does not fetch vendor firmware. Subsequent builds use the cached
commits and recreate the source and object directory.

On macOS, package an already-built Linux x86-64 compiler prefix with the
provided Containerfile. The build context must contain only the compiler
installation, with `bin/`, `lib/` and its other installed directories:

```sh
docker build --platform linux/amd64 -f src/start4/Containerfile \
  -t open27xx-vpu-sdk /path/to/vc4-prefix
docker run --rm --platform linux/amd64 --cpus=2 --memory=3g \
  -v "$PWD:/work" -w /work open27xx-vpu-sdk make -C src/start4
```

The Containerfile packages the external compiler; it does not build it.
The Ubuntu base image is pinned by digest. Distribution package updates
can change the ARM compiler version, which the armstub manifest records.

| Output | Contents |
|---|---|
| `build/start4/start4.elf` | unsigned VPU image with debug information removed |
| `build/start4/manifest.json` | artifact SHA-256, compiler/linker versions, source pins and local input hashes |
| `build/start4/build.log` | compiler and linker output |
| `build/start4/work/` | complete external sources, retained notices, local changes and build objects |

The check validates ELF class, byte order, machine 137, program-header
bounds, the entry point, the 33554432-byte VPU region at 0xC4000000 and the
two named loader metadata sections. The allocator ends at 0xC5FF0000;
the upper 65536 bytes remain reserved for the boot stack. The linker and
ELF check reject an image that extends into this reserve. The build also
checks the linked `_end` and `_fstack` symbols against those bounds. This
region is the open target's memory policy; its validity on hardware remains
unverified. The check requires only `PT_LOAD` nonzero program headers
because the documented bootmain helper copies every
nonzero type. These structural checks do not establish hardware bootability.

## ARM mapping-table preparation

[`arm_mapping.h`](arm_mapping.h) exposes `arm_mapping_prepare` from
[`arm_mapping.c`](arm_mapping.c). The
[mapping-table contract](../../docs/bcm2711/arm-mapping.md) defines twelve
paired profiles. The operation accepts a four-word argument object,
caller-owned state, a table byte view and its complete declared length,
an observer plan and a separate raw-result word. The numeric base, offset,
handle and table identity never become host pointers.

The state groups active, capacity, marker, selection and service-index
words. Invalid handle zero requires only arguments and raw-result storage.
Active rejection requires only active state and acquire/release observers.
The six range/zero/alignment profiles also require capacity. The four table
profiles require marker, selection and at least 128 table bytes; only
selection zero requires the service index and service observer. Unused
state members are neither read nor validated and remain unchanged.

Preflight checks the exact paired profile and every reachable observer
before any effect. All supplied objects and full declared table extents
participate in address-wrap and overlap checks, including optional objects
whose contents the selected path ignores. Null table requires zero length.
All distinct objects are disjoint, including arguments, state, plan and
result. Table bytes may be unaligned; typed objects require their type's
alignment. The caller supplies actual backing, writable state and outputs,
and lifetime. Bytes beyond the 128-byte table remain unchanged.

The operation owns the arithmetic and table updates. It computes bound
and step from capacity, uses 32-bit wrapped sums and checks unsigned
remainders before modifying the table. Fresh state receives 64 little-endian
halfwords and marker 1. A repeat can consume the actual fresh output and
replace entry 63 while preserving the other entries. Wrapped-index failure
retains the preceding table fill and marker store.

| Host status | Effect |
|---|---|
| `ARM_MAPPING_OK` | Complete operation; raw result stored after release or directly for invalid handle |
| `ARM_MAPPING_INVALID` | Required pointer or reachable observer missing; no effects |
| `ARM_MAPPING_UNSUPPORTED` | Input outside the twelve paired profiles; no effects |
| `ARM_MAPPING_BOUNDS` | Short used table or wrapped host span; no effects |
| `ARM_MAPPING_OVERLAP` | Distinct declared objects overlap; no effects |

The separate raw result preserves the returned word, including
0xFFFFFFFC for the admitted wrapped-index path. That path succeeds as a
host operation and keeps its state writes. Its numeric offset wrap is
distinct from host-address span overflow. Raw-result input is unconstrained.

Acquire observes the incoming state. Release follows any table/marker
updates, including the retained failure writes. Selection-zero service
also sees those completed stores and precedes release. Observers receive
only semantic arguments and fixed replies: zero for mutex calls and 7 for
service. Service reply 7 does not change final raw zero. Observers return
normally, preserve arguments and all API objects, keep mutable bookkeeping
and indirect storage separate, and avoid reentry, concurrent mutation and
hardware access. They do not supply arithmetic or table results.

```sh
python3 -m unittest tests.test_arm_mapping
make -C src/start4 check-arm-mapping
```

Tests compare all twelve complete fixtures, ordered observations, full
table bytes, state and raw results. They carry actual fresh output into
the repeat and check unused state fields, exact profiles, complete declared
spans, missing observers and unaligned table buffers. The VPU target writes
`build/start4/arm-mapping.o` without linking it into the runtime. Software
table preparation does not establish physical mapping, cache visibility,
completed open or ARM execution.

## ARM entry stub

The separate ARM build needs `aarch64-linux-gnu-gcc`,
`aarch64-linux-gnu-ld` and `aarch64-linux-gnu-objcopy`:

```sh
make -C src/start4 armstub
```

Set `ARM64_TOOLCHAIN_PREFIX` for another compatible prefix. This builds
the pinned upstream `armstub8-gic.bin` target with `BCM2711=1` and `GIC=1`.
The source initializes the ARM execution state, generic timer and GIC;
the primary core branches to the supplied kernel entry with the supplied
device-tree pointer, while secondary cores wait on release slots.

`build/start4/armstub8-gic.bin` and `armstub-manifest.json` are separate
artifacts. The VPU image does not embed, patch, load or execute this stub.
The build checks its 256-byte padding and the four-word header at 0xF0.

## ARM stub metadata preparation

[`armstub.h`](armstub.h) exposes the freestanding `armstub_prepare` helper
from [`armstub.c`](armstub.c). The caller supplies a writable buffer and
its byte length, followed by the DTB value, DTB-presence flag, kernel value
and kernel-load result. Both values are 32-bit fields; the helper neither
translates nor dereferences them.

| Result | Buffer effect |
|---|---|
| `ARMSTUB_INVALID` | Null buffer or length below 256 bytes; no access |
| `ARMSTUB_UNCHANGED` | Magic does not match; no writes |
| `ARMSTUB_PREPARED` | Metadata at 0xF0–0xFF is prepared; every other byte is unchanged |

The helper uses byte accesses so the buffer does not require pointer
alignment. The [metadata contract](../../docs/bcm2711/arm-handoff.md)
defines the little-endian fields and the presence/result rules.

```sh
python3 -m unittest tests.test_armstub
make -C src/start4 check-armstub-metadata
```

The host test compiles the firmware C helper with `CC` (default `cc`),
then compares it with all five recorded metadata cases. It also checks
guard bytes, short and null buffers, unaligned buffers and field limits.
The Make target compiles the same helper with the VPU compiler and writes
`build/start4/armstub-metadata.o`. It does not link it into `start4.elf`.
Connecting this helper to a loader still requires contracts for buffer
placement, cache visibility and ARM release.

## Boot-information helpers

[`boot_info.h`](boot_info.h) exposes the freestanding parser, lookup,
zeroing allocator, bounded revision fallback and metadata-pointer preparation in
[`boot_info.c`](boot_info.c). The [format contract](../../docs/bcm2711/boot-information.md)
defines the fifteen tags, capacities, traversal and allocation behavior.
These helpers operate on caller-supplied buffers. They do not acquire boot
information, initialize a board or start an ARM core.

Initialize `struct boot_info_state` to zero. `boot_info_parse` receives that
state, a source pointer and accessible byte length, an allocation callback
and its context. The source length is independent of the declared traversal
length: only the bytes actually read must be backed. Field accesses use
bytes and accept unaligned source and destination buffers.

The callback receives count 1 and the record capacity. It returns a host
status and fills `struct boot_info_buffer` with a writable pointer and its
accessible length. A null pointer reports allocation failure to the parser.
A successful allocation must provide the requested capacity. The parser
checks its extent and rejects overlap with source bytes, state or a live
cached span before copying. Callbacks must not modify the source, state or
existing cached storage, and must not reenter the same parser state.

Each cache slot retains the allocation's pointer and the tag's capacity.
The first record for a tag wins. An existing pointer is not dereferenced
merely to skip a duplicate or return a lookup result. Storage remains owned
by the callback's caller and must outlive the state and every returned
view. The helper does not free storage. A callback retains responsibility
for any allocation rejected by host checks.

`boot_info_lookup` first runs the parser, then returns the cached buffer
for its tag, or a null buffer for an incomplete parse, unknown tag or
missing record. A nonzero completion word preserves its exact value and
prevents further source access, even when the source changes. A null source
also preserves state. Create a separate zero-initialized state for another independent record
set; automatic cache invalidation is outside the contract.

| Host result | Meaning |
|---|---|
| `BOOT_INFO_OK` | The documented operation returned; inspect completion or the output buffer for its effect |
| `BOOT_INFO_INVALID` | A required state, output or wrapper-context argument is absent |
| `BOOT_INFO_BOUNDS` | An accessed header, copied prefix or allocated span lacks backing |
| `BOOT_INFO_OVERFLOW` | A supplied span or size calculation wraps the host address/size range |
| `BOOT_INFO_ALLOCATION` | A needed parser callback or its returned pointer is absent |
| `BOOT_INFO_OVERLAP` | Writable storage overlaps source, state or a cached span, or a lookup output overlaps state |

These statuses are host safety results, not recovered firmware return
codes. A parse failure leaves completion unset and retains any records
cached before the failure. It does not cache the failing record. Retrying
uses the retained records. Callback effects are not rolled back, including
zeroing performed before parser overlap checks. A callback status other
than `BOOT_INFO_OK` is returned unchanged. Callers must supply valid state,
result and context objects with correct extents. These objects must not
overlap each other, source bytes or any live cached or allocated storage.
The parser detects source/state overlap and checks each allocation against
the source, state and cached spans. Lookup detects output/state overlap
before modifying either object. Callers must enforce all other separation
requirements. The helpers cannot establish the lifetime of a supplied
pointer or detect a falsely reported allocation extent.

`boot_info_allocate_zeroed` is a separate allocation callback. Its context
is `struct boot_info_zero_allocator`, containing the lower callback, lower
context and an opaque 32-bit caller word. The wrapper checks count times
item size, passes the product, literals 32 and 1, and the caller word with
bit 31 set to the lower callback. It clears exactly the requested number
of bytes on success, preserving any remaining accessible tail. A null
lower result returns a null output with `BOOT_INFO_OK`; the parser treats
that null output as its own allocation failure. A nonnull zero-size result
is returned without writes. The extra lower arguments have no assigned
platform meaning in this API.

Using this wrapper with the parser gives zeroed record tails. Supplying a
prefilled allocator directly preserves those tails. The two operations
remain separately testable. The lower callback must also satisfy the
storage-separation requirements before the wrapper clears its result.

`boot_info_prepare_pointer` accepts an absent section unchanged. A present
section requires at least 8 bytes; a matching marker writes 0x00040000 to
its second little-endian word. Other bytes remain unchanged. The helper
does not access the memory addressed by that field.

`boot_info_fallback_revision` receives a presence flag and the decoded
32-bit word at record offset 0x68. Only word bits 1 and 2 affect its result;
an absent record selects 0x00A03110. The caller selects this bounded fallback
path and obtains the word from an accessible record. The helper does not
infer board identity or implement the preceding selection gates.

```sh
python3 -m unittest tests.test_boot_info
make -C src/start4 check-boot-info
OPEN27XX_SANITIZERS=1 python3 -m unittest tests.test_boot_info
```

The host test compiles the C helper with `CC` and replays synthetic records,
cache identity, allocation calls, zeroing and pointer-store cases. It
checks every observed memory span, including guards, and the documented
lookup, allocation and bounded revision outputs. All 126 recorded cases
are covered. Native registers and stack locations are outside this
portable API. Composed allocation cases supply the recorded
opaque caller word at the lower-call boundary; they test its forwarding,
not native call-site identity. Separate wrapper cases derive that word
from the supplied return-address input. A native harness runs 16384
deterministic inputs with exact allocation sizes; the optional sanitizer
mode compiles that harness with AddressSanitizer and UndefinedBehaviorSanitizer.

The Make target compiles `build/start4/boot-info.o` with the pinned VPU
compiler and `-Os -ffixed-lr`. This target verification configuration reserves
LR from register allocation. Preserve `-ffixed-lr` when integrating the
helper with the pinned VPU toolchain. Native host builds do not use this
option. The target does not link the helper into `start4.elf`; acquisition
and runtime integration require further contracts.

## Memory-capacity helper

[`memory_capacity.h`](memory_capacity.h) exposes the freestanding
`memory_capacity_measure` helper from [`memory_capacity.c`](memory_capacity.c).
It implements the complete two-pass calculation in the
[capacity contract](../../docs/bcm2711/memory-capacity.md). The caller selects
the supported nonzero path with diagnostics disabled and supplies the byte
service. The helper does not acquire hardware data, initialize board state,
assign memory ownership or construct a usable memory map.

The arguments are a byte-service callback, its context, a writable
`uint32_t` size output in MiB and a separate writable `uint32_t` class output.
The callback receives its context and three unsigned words: selector,
first index and second index. Its `uint8_t` return value is a byte reply;
there is no callback failure code. Each pass requests selectors 5 then 8
at `(0,0)`, `(1,0)`, `(0,1)` and `(1,1)`, in that order. Both passes execute
all eight requests, including the replies unused by the calculation.

The helper writes 256 to the size output before the first callback and
preserves that value throughout all sixteen callbacks. The class output
keeps its incoming value during the callbacks. On completion, the first
pass supplies the size in MiB and the second pass supplies the raw class.
Class 7 is a successful numeric result and can accompany different sizes.
The samples can differ; the helper does not reuse first-pass replies in
the second pass. The maximum arithmetic result is 16384 MiB; converting
MiB to bytes requires arithmetic wider than 32 bits.

| Host result | Meaning |
|---|---|
| `MEMORY_CAPACITY_OK` | Both passes completed; both output words are written |
| `MEMORY_CAPACITY_INVALID` | A callback or output pointer is null |
| `MEMORY_CAPACITY_OVERLAP` | The two output words overlap |

Host validation happens before any write or callback. A validation error
preserves both outputs. These statuses are separate from the raw class.
Both output objects must be aligned, writable and valid throughout the
call. They must not overlap each other or any storage the callback mutates,
including storage reached indirectly through its context. The caller owns
all objects and enforces lifetime, alignment and context separation; the
helper checks null arguments and output/output overlap only.

The context may be null if the callback accepts it. Otherwise it and its
referenced objects remain valid throughout both passes. The callback may
update its own bookkeeping, such as a reply cursor, and observe the output
words. It must preserve the outputs and fixed configuration, return
normally and not reenter the operation. Concurrent output or configuration
mutation, callback failure and hardware access are outside this API.

```sh
python3 -m unittest tests.test_memory_capacity
make -C src/start4 check-memory-capacity
```

The host test compiles with `CC` and compares all 24 complete helper cases
with the recorded MiB output, raw class, output guards and first three
callback arguments. Incidental register words, native stack state and the
four internal initializer slices are outside this helper comparison.
Separate tests cover mutable callback bookkeeping, output visibility,
distinct observations, unused replies, null arguments and overlapping or
adjacent outputs.

The Make target writes `build/start4/memory-capacity.o` with the pinned VPU
compiler using `-Os -ffixed-lr`. Preserve `-ffixed-lr` when integrating with
that toolchain; native host builds omit it. The target does not link the
helper into `start4.elf`. Runtime integration needs acquisition, path
selection and memory-ownership contracts.

## Memory-bank serializer

[`memory_layout.h`](memory_layout.h) exposes `memory_layout_serialize` in
[`memory_layout.c`](memory_layout.c). The
[serialization contract](../../docs/bcm2711/memory-layout.md) defines the
ordered numeric tuples and big-endian cell encoding. These bytes do not
establish physical banks, usable ownership, reserved ranges or payload
placement. The helper performs no device-tree insertion or hardware access.

The input structure contains address and size cell counts, a lower-span
byte count, total MiB, a control word and an optional decoded record. A null
record means absent. A present `memory_layout_record` supplies the flags
and selector words from offsets 0x80 and 0x88. The helper does not acquire,
copy or parse a raw record. A caller decoding those offsets must independently
establish at least 140 readable bytes; the record's own length is insufficient.

The helper accepts total values from 0 through `MEMORY_LAYOUT_MAX_TOTAL_MIB`
(16384 MiB), every unsigned 32-bit lower-span, control and record word, and
cell counts of 1 or 2. The total bound is a comparison limit. Lower-span
fractional MiB are discarded; zero still emits the first tuple. No minimum
total or cached-capacity limit is applied. With one address cell, every
selected base must be below 4096 MiB, including any base advanced by size
splitting. This condition depends on the selected branch, so a clipped
selector-24 case can accept a total above 4096 MiB.

`output` is a caller-owned byte buffer with the supplied `capacity`.
`written` points to a `size_t` output. Success writes the complete payload,
stores its length in bytes and preserves all bytes after that extent. The
helper checks the complete encoded extent and every emitted base before
writing. It does not produce partial output.

| Host status | Meaning |
|---|---|
| `MEMORY_LAYOUT_OK` | The complete payload and its byte count are written |
| `MEMORY_LAYOUT_INVALID` | A required pointer is null or an extent cannot be represented |
| `MEMORY_LAYOUT_UNSUPPORTED` | A cell count, total or emitted one-cell base is outside the supported domain |
| `MEMORY_LAYOUT_CAPACITY` | The supplied output capacity is smaller than the encoded extent |
| `MEMORY_LAYOUT_OVERLAP` | Mutable output storage overlaps another argument |

These statuses are host API rules, separate from the returned byte count.
Every error preserves the output buffer and `written`. All pointers except
the optional record are required, including when capacity is zero. Input,
record and length objects must have the declared type, alignment and extent.
The byte buffer requires no additional alignment. Objects remain valid for
the entire synchronous call; none is retained, allocated or freed.

The entire declared output capacity and the `written` object must not
overlap each other, the input structure or a present record. The helper
checks these overlaps and rejects address-range wrap before access. The
caller enforces actual backing, alignment, lifetime and immutability of the
inputs. Concurrent mutation of any argument is unsupported.

```sh
python3 -m unittest tests.test_memory_layout
make -C src/start4 check-memory-layout
```

Host tests compare all 44 complete serializer fixtures: every output byte,
returned length, unchanged inputs, output tail and guards. The four internal
cached-capacity caller slices remain outside this API. Separate tests cover
exact and short capacities, null and overlapping arguments, wrapping extents,
numeric limits, full-width record/control words and repeated size splitting.

The Make target writes `build/start4/memory-layout.o` with the pinned VPU
compiler using `-Os -ffixed-lr`. Preserve that LR reservation when integrating
with this toolchain; native host builds omit it. The helper remains unlinked
from `start4.elf`. Runtime use requires separate acquisition, ownership,
placement and complete tree-mutation contracts.

## ARM control request helpers

[`arm_control.h`](arm_control.h) exposes the freestanding configuration and
start-request helpers in [`arm_control.c`](arm_control.c). The
[request contract](../../docs/bcm2711/arm-control.md) defines the bounded
software operations. These helpers issue callbacks over caller-owned state.
They do not access MMIO, acquire source buffers, implement a resource
transition or provide clock, reset, memory-visibility or ARM-entry guarantees.

`arm_control_configure` receives `struct arm_control_configuration`, an
incoming 32-bit result, a service callback, callback context and output
pointer. The configuration contains opaque driver, selection, handle,
service-index and A/B/C/D words. The helper never dereferences the driver
word. A zero driver emits no callback and copies the incoming result to
the output; this preserved value is not a success status. With a nonzero
driver, only selection 1 and `ARM_CONTROL_HANDLE` (0x61726D11) are supported.
Other routing values return `ARM_CONTROL_UNSUPPORTED` before any callback.
The zero-selection internal boundary has no portable function counterpart.

The service callback receives context followed by service index, selected
value, relative offset and three zeros, in that order. The helper forwards
the service index unchanged. A/B/C/D retain their opaque meanings; each is
tested only for zero or nonzero. Six requests always occur in order, including
requests whose value is zero. Nonzero D appends the seventh request. The
configuration remains unchanged. Service return words are ignored, including
nonzero words. All requests complete and the output is 0.

`arm_control_start` receives `struct arm_control_start_state`, a handle,
a native mutex-object pointer, `struct arm_control_start_callbacks` and an
output pointer. The callback table contains acquire, release and resource
request functions with one shared context. Acquire and release receive
context followed by the identical mutex pointer. The helper does not
dereference that pointer. The resource callback receives context, the
unchanged 32-bit `resource_object`, resource 23 and literals 1 and 1. The
resource-object word is not converted to a native pointer or entry address.

After acquire, the helper requires the handle to equal `ARM_CONTROL_HANDLE`,
nonzero `open_count`, nonzero `mapping_marker` and zero `active`. A rejected
gate selects result 0xFFFFFFFF without calling the resource callback. An
accepted request preserves the resource reply as the selected result and
sets `active` to exactly 1 only for reply 0. Release observes that state
update and runs after both gate rejection and an accepted resource request.
Mutex return words are ignored. The helper writes the selected result after
release.
All other state remains unchanged. An active word of 1 is software state;
it does not establish ARM execution. The recorded resource replies are 0
and 7; additional host boundary tests check full-width result preservation.

| Host status | Meaning |
|---|---|
| `ARM_CONTROL_OK` | The supported operation completes and writes the function result |
| `ARM_CONTROL_INVALID` | A required pointer or callback is null; no callback or write occurs |
| `ARM_CONTROL_UNSUPPORTED` | Nonzero driver with unsupported selection or handle; no callback or write occurs |
| `ARM_CONTROL_OVERLAP` | Result/state, result/callback-table or state/callback-table overlap; no callback or write occurs |

These statuses are host API rules, separate from the function result.
A gate rejection or nonzero resource reply returns `ARM_CONTROL_OK` with
the selected 32-bit result. Ignored configuration-service and mutex words
are raw boundary returns, with no assigned failure or lock-ownership meaning.
They do not stop requests, skip gates or change the selected result. The
callbacks must return normally; the API provides no transport-error channel,
rollback, retry or recovery from callback exceptions or nonlocal exits. Real
synchronization and callback side effects require a separate contract. A
host validation error leaves the output and state untouched and emits no
callback. The output is valid only with `ARM_CONTROL_OK`.

State, configuration, output and callback-table pointers must refer to
properly aligned objects of the declared type and extent. Objects and
callback functions remain valid for the whole synchronous call; the helper
retains none of them and allocates or frees no storage. Configuration and
output are always required. The service callback is required only for a
nonzero driver with supported routing. Start requires state, output, a
nonnull mutex pointer, a callback table and all three callbacks, even when
a software gate will reject the request. Context may be null if callbacks
accept it.

Output, input/state, callback-table, context storage and mutex storage must
not overlap. The helper checks output/input and output/state overlap, and
start also checks output/table and state/table overlap. The caller enforces
the remaining separation, lifetime and extent requirements. Callbacks must
not modify configuration, state, output or callback-table objects, reenter
the same state or perform hardware operations. Independent calls must not
concurrently access the same state. A mutex callback boundary alone provides
no synchronization guarantee.

```sh
python3 -m unittest tests.test_arm_control
make -C src/start4 check-arm-control
```

The host tests compare all 40 complete function fixtures: 24 configuration
cases and 16 start-request cases. They compare callback order and arguments,
object identity, returned values and every represented state field. The
internal zero-selection boundary remains outside helper functionality.
Incidental registers and native stack locations are not portable outputs.
Additional tests cover nonbinary field values, repeated calls, null and
overlapping arguments and ignored boundary return words.

The Make target compiles `build/start4/arm-control.o` with the pinned VPU
compiler, `-Os` and `-ffixed-lr`. Preserve the LR reservation for this
toolchain when integrating the helper. The target does not link it into
`start4.elf`; the image's advertised features remain unchanged.

## Host staging

```sh
make -C src/start4 stage
```

This creates `build/start4/stage/` with the checked image named
`open27xx.elf`, an identity manifest and `config.txt.fragment`. It does
not access a boot partition. The candidate fragment selects
`start_file=open27xx.elf` and `fixup_file=open27xx-none.dat`; the latter
file must remain absent. An empty `fixup_file` value retains the default
vendor fixup selection.

The [loader contract](../../docs/bcm2711/start4.md#replacement-file-selection)
establishes these filename choices and the zero-length fixup continuation.
It does not establish complete ELF acceptance or entry execution.
Complete the offline backup and review the original `config.txt` for
conflicting selections before an approved hardware test. The fragment is
not a complete replacement for that configuration file.

## Sources and licenses

[`sources.json`](sources.json) pins every external source used by these
targets. The armstub files also have SHA-256 checks. The LK pin must match
the overlay's recorded submodule commit.

| Source | License and retained notices |
|---|---|
| librerpi/lk-overlay `50c95c1c6e34e8717415f4f1fafbfd8b060f6e8c` | GPL-2.0-or-later, except per-file notices; `README.md`, `COPYING` and source headers |
| librerpi/lk `2770b28104c15e52555a45143836c9c82945d740` | MIT core, with per-file exceptions; `LICENSE` and source headers |
| raspberrypi/tools `439b6198a9b340de5998dd14a26a0d9d38a6bcac`, `armstubs/armstub8.S` | BSD-3-Clause notice in the source header |

External sources remain outside the tracked tree. Their notices remain in
the exported source directories. Distribution of a built image must retain
the applicable notices and provide its complete corresponding source,
including the pinned dependencies and local build profile.

The profile removes the upstream interactive shell, diagnostic tests,
signing dump, OTP module, graphics demos and GENET diagnostic interrupts.
The platform patch excludes the older-board GPIO selection that depends on
the OTP module. Loader metadata is kept in separate named sections before
the linker's `.text.*` wildcard. The UART status line reports completion
of VPU initialization without printing bootloader state.

The build overrides `MEMBASE` and `MEMSIZE` so that LK's page allocator
uses the linker region and excludes the stack reserve. The upstream
defaults describe a region below the linked image; using them here would
make the allocator's unsigned available-size calculation wrap.

## Open questions

- BCM2711 ARM release. The pinned overlay's ARM selection accepts processor
  identifiers 0–2 and does not implement the BCM2711 handoff. Establish
  the required clock, reset, memory and cache sequence before connecting
  the separate armstub.
- Boot files. The pinned Linux loader runs on ARM and selects files for
  earlier boards. Specify a BCM2711 path for kernel, device-tree and
  initramfs loading, with bounded placement and a defined boot partition.
- Mailbox properties. The upstream server implements a small subset and
  reports a fixed 67108864-byte ARM memory region. Define the Linux tag
  set and board-specific values, then compare them on hardware before
  enabling a server.
- Complete loader acceptance. The filename and zero-length fixup contract
  is documented, but earlier compatibility and signature checks, and
  entry execution remain unproved for this unsigned image. Verify those
  paths before treating the staged files as a bootable replacement.

Pinned upstream paths and ARM boot references are listed in
[`docs/references.md`](../../docs/references.md). The restoration procedure
is in [`docs/bcm2711/start4.md`](../../docs/bcm2711/start4.md#restoring-the-boot-partition).

## Fixed resource requests

[`resource_request.h`](resource_request.h) exposes the separate freestanding
helpers in [`resource_request.c`](resource_request.c), following the
[fixed request contract](../../docs/bcm2711/resource-request.md).
`resource_request_execute` handles the supplied logical request `(23,1,1)`.
`resource_request_dependency` returns 0x180 for index 23 and selection 0 or 1.
`resource_request_context_call` and `resource_request_check` expose the direct
context and conditional-check operations. These helpers remain unlinked from
`start4.elf` and do not select a runtime provider or access hardware.

The manager receives explicit inputs, a record buffer and record count,
mutable held/aggregate state, a literal reply plan and an outcome object.
All five pointers are required. The buffer must contain at least 32 typed
records; only the first 32 are scanned or modified. Each record contains
an opaque self token and a logical request word. The selected record index
must be below 32. The input `object_present` is exactly 0 or 1 and distinguishes
an absent represented object from a null host pointer. A present identity
must be nonzero. An absent object or unequal selected self token returns
raw 0xFFFFFFFF without a boundary call or state change. That path does not
inspect dependency selection, state words, other records or reply fields.

For a matching object, selection is 0 or 1, each scanned logical request
word is zero or 0x00800000, and held state is zero or 0x180. The scan uses
only nonzero self tokens; an inactive record's supported request word is
ignored. Tokens do not establish registration, ownership or physical
addresses. The supplied handle and mutex identity are opaque unsigned
32-bit words. The aggregate output may contain any incoming word.

The reply plan declares the two enable words in mask order 0x80 then
0x100. The first may be 0 or 7; a reachable second reply must be 0. A
reachable false condition requires `check_context`, with explicit nonzero
descriptor/callback identity tokens, an opaque word, literal reply 0 or 7,
a provider and its bookkeeping context. Zero identity tokens are outside
this host representation; the helper does not infer initialization from
them. Only reachable reply fields and context objects are inspected.

Providers return `void` and receive the declared reply as an argument.
They observe the boundary; they do not compute another reply. The plan has
separate diagnostic, acquire, release and enable providers sharing one
bookkeeping context. Check context has its own provider and bookkeeping
context. All providers needed by the declared execution path are validated
before the first call or state write. A first enable reply of 7 therefore
requires context in advance. An already-held request needs no enable
provider, and a planned stop needs no release provider. True conditions
need no context pointer, fields or provider.

| Boundary | Argument words | Declared reply |
|---|---|---|
| Diagnostic | 0x4000, opaque diagnostic label 0x0ED7CAB0, object identity, 23, 1, 1 | 0 |
| Acquire/release | Supplied mutex identity | 0 |
| Enable | Supplied handle, single-bit mask | Selected enable reply |
| Context | Opaque word, callback identity, descriptor identity | Context reply |

Argument arrays are temporary and valid only during the synchronous provider
call. The diagnostic label is an observation token, not a host string pointer.
Native addresses, incidental argument registers and stack frames are outside
this API. Providers may record events and update cursors in separate caller-owned
bookkeeping storage. They must preserve inputs, records, state, plan, context
descriptors, outcome and the supplied argument array; return normally; and
avoid reentry, concurrent mutation and hardware access. A bookkeeping context
may be null if its provider accepts it. Provider failure, mutation and replies
chosen during execution have no defined recovery or rollback policy.

The manager writes the old aggregate after acquire. It then checks for a
duplicate request, sets the selected request bit, recomputes the aggregate
and clears the held dependencies. Both aggregate calculations precede that
clear. Added dependencies emit enables in increasing mask order. Context
reply zero lets a failed condition continue; reply 7 produces a stopped
outcome with state and calls retained through that check. A duplicate stop
precedes the request store and held-mask clear. An enable-result stop follows
those writes. There is no automatic release or rollback at either stop.

| Host status | Meaning |
|---|---|
| `RESOURCE_REQUEST_OK` | Inspect the tagged outcome or direct dependency result |
| `RESOURCE_REQUEST_INVALID` | A required pointer/provider is missing or an extent wraps |
| `RESOURCE_REQUEST_UNSUPPORTED` | An accessed input or reply is outside the fixed domain |
| `RESOURCE_REQUEST_BOUNDS` | Fewer than 32 records or a selected index outside the first 32 |
| `RESOURCE_REQUEST_OVERLAP` | Accessed API storage overlaps |

Host errors preserve every caller-owned state/output byte and emit no
boundary call. Host statuses are separate from the tagged outcome.
`RESOURCE_REQUEST_RETURNED` selects `value.raw_return`.
`RESOURCE_REQUEST_STOPPED` selects `value.stop_flag`, which is 1, and has
no vendor return word. Direct context reply 7 is a returned raw 7. A false
check with reply 7 is stopped. A true check returns its nonzero condition
unchanged. The helper executes no `BKPT` and defines no continuation from a
stopped outcome. It cannot be routed directly into `arm_control_start`'s
raw-word callback without a separately defined policy for stopped outcomes.

All accessed typed objects require correct alignment, actual backing,
writability where modified, and validity throughout the call. The caller
establishes these properties. The helper checks nulls, address-range wrap,
record count/index and pairwise overlap of inputs, the entire declared record
buffer, state, plan and outcome before accessing fields. It also checks a
reachable context descriptor against those objects. Direct context/check
operations check their accessed context and outcome extents and overlap.
A true check ignores context entirely. The caller keeps all provider
bookkeeping and indirectly referenced storage separate from the API objects.
No object or pointer is retained, allocated or freed.

```sh
python3 -m unittest tests.test_resource_request
make -C src/start4 check-resource-request
```

Host tests compare all 16 portable fixtures: two dependencies, two direct
contexts, three checks and nine manager returns/stops. Comparisons cover
defined boundary arguments and replies, records, held/aggregate words,
outcome tags and guards. Separate tests cover preflight, callback-visible
state, slot 31, inactive records, bounds, wrap, overlap and adjacent storage.
The real resource-selection prefix remains excluded. Disable behavior,
other logical requests, context initialization, registration, concurrency,
resource selection and live clock/release effects require separate contracts.

The Make target writes `build/start4/resource-request.o` using the pinned
VPU compiler with `-Os -ffixed-lr`. Preserve that LR reservation for this
toolchain; native host builds omit it. The isolated target does not link
or modify the firmware runtime.

## Fixed clock requests

[`clock_request.h`](clock_request.h) exposes three freestanding helpers in
[`clock_request.c`](clock_request.c), following the
[fixed clock-request contract](../../docs/bcm2711/clock-request.md).
`clock_request_execute` handles only the documented clock 0x30 request for
600000000. `clock_request_initialize` performs the separate cold initializer.
`clock_request_execute_cold` composes the documented zero-open-result
initializer with the first request. All remain unlinked from `start4.elf`.
They do not acquire a real driver, program registers or establish an
achieved clock rate.

The manager buffer uses the contract's 1156-byte little-endian layout.
Cache fields contain unsigned 64-bit numerical words; handle, table and
notification callback fields contain opaque 32-bit identity tokens.
`struct clock_request_state` holds the separate initialized flag, 86
descriptor-miss bytes and two override-miss bitmaps. The request receives
explicit input fields, an eight-byte output buffer, a literal reply plan
and a separate raw-result word. Every pointer is required. Buffers may be
larger than the required size; the helpers preserve their remaining bytes.
Byte buffers accept unaligned addresses. Typed objects require alignment.

The original request profiles accept selection 1,
initialized flag 1, no overrides, zero initial miss state, divider count
zero and requested-clock cache 500000000. Source and divider-rate caches
must be one of `(0,0)`, `(1000000000,250000000)`,
`(2000000000,500000000)` or `(1200000000,300000000)` with planner input 1200.
Planner input 1500 accepts only `(0,0)`. The request's high word and two
remaining argument words are zero. A table token must be nonzero, and the
nonzero handle token must equal the comparison token. Tokens establish
neither pointer validity nor ownership.

Three further initialized profiles accept planner input 1200, zero skip
and option words, no overrides and empty notification records:

| Profile | Reference | Source / divider-rate / count / requested-clock cache | Miss state |
|---|---:|---|---|
| First request after initialization | 54000000 | 0 / 0 / 0 / 0 | All zero |
| Repeat with reference zero | 0 | 1200000000 / 600000000 / 2 / 600000000 | Descriptor byte 0x30 = 1, divider/source bitmaps 0x20/0x80 |
| Repeat after cold initialization | 54000000 | 1200000000 / 600000000 / 2 / 600000000 | Descriptor byte 0x30 = 1, divider/source bitmaps 0x20/0x80 |

All other descriptor-miss bytes remain zero. These profiles require zero
reachable programming replies. They cannot combine with notifications,
skip paths, planner input 1500 or different cache pairs. The original
profiles retain their own reply and notification rules below.

Skip words 1 and 0xFFFFFFFF accept the zero-cache, planner-1200 profile
with empty notification records. They return raw 0x30 without callbacks
or state/output changes. Active requests accept empty notification records
or one first-slot clock-0x30 record on the same zero-cache profile. The
notification replies are pre-change 7, or pre-change 0 followed by
post-change 7. Other records are empty. Registration and additional
notification combinations are outside the helper's domain.

The reply plan declares each reachable programming and notification
reply before execution. Programming replies are zero, except that the
zero-cache, planner-1200 profile with empty notification records also
accepts all three programming replies equal to 0xFFFFFFFF. The lower-source
profile declares both divider replies as zero. Unreachable reply fields
and providers are ignored. A pre-change reply of 7 therefore needs no
programming providers. An equal source needs no source provider. A skipped
request needs no providers. All reachable providers are checked before
any callback or state/output store. Completed-cache repeats require the
selected-clock, diagnostic, acquire and release providers. They require
neither a source nor a divider provider and ignore those unreachable replies.

Providers return `void` and receive a boundary enum, an opaque callback
identity, a temporary array of defined argument words and the declared
reply. The array is valid only during the synchronous call. Callback
identity labels name the documented boundary; they are never called as
addresses. Notification identity comes from the first record. The mutex
argument comes from the explicit `mutex_identity` token. Diagnostic,
acquire and release replies are fixed zero. The diagnostic array contains
seven words: `(0x4000,0x0EC7EF38,0x30,600000000,0,0,0)`. Its final word
is defined by the public callsite contract; the fixture event records only
the first six register words.

Providers may observe state and update bookkeeping in separate storage.
They must preserve inputs, manager/state, output, raw-result word, plan
and argument arrays; return normally; and avoid reentry, concurrent mutation
and hardware access. Context may be null if the provider accepts it.
Dynamic replies, provider memory effects and recovery from nonlocal exits
have no defined policy. Observer callbacks alone provide no synchronization.

The request preserves the documented cache-store and callback order,
including both divider calls for a lower old source. A pre-change rejection
leaves caches and output unchanged, retains the descriptor miss and returns
the prior clock cache's low word. A post-change reply of 7 retains all
updates, copies the new rate into the output after notification returns
and returns raw 0xFFFFFFFF. Programming reply words do not alter this
bounded software path. The raw result is written after mutex release.
The two supported repeated profiles preserve all completed caches and miss
state, call the selected-clock provider, and copy 600000000 into a fresh
output buffer. The reference word remains unchanged. Other repeated states
are unsupported.

The initializer accepts selection 1, a nonzero table token, initialized
flag zero and either open reply 0 with handle write 0xC10C1234 or open reply
7 with handle write zero. It sets the flag, clears exactly 1156 manager
bytes, stores the table token and invokes its open observer with the table,
argument zero, actual `manager + 8` output pointer, declared reply and
handle write. The observer preserves that output. After it returns, the
helper applies the declared four-byte handle write, stores reference
54000000 and returns the declared raw reply. The separate miss state and
any manager tail are preserved. The initializer never continues into a
clock request, including after open reply 7.

The cold request takes the request inputs, a nonzero table token, manager
and state, output buffer, open plan, request plan and raw-result word:

```c
clock_request_execute_cold(inputs, table, manager, manager_length, state,
                          output, output_length, open_plan, plan, raw_return);
```

It accepts flag zero, 1156 manager bytes each equal to 0xA5, zero miss state,
planner input 1200 and zero skip/options/override heads. The open reply is
zero with handle write 0xC10C1234, matching the input comparison token.
Preflight covers both plans and every reachable provider before any store
or callback. After clearing the manager and installing the table token,
the open observer sees zero handle, reference and numerical caches. The
helper then writes the supplied handle and reference 54000000 before mutex
acquisition. Source, selected-clock and divider calls follow. No intermediate
raw result is stored: all observers see the incoming raw-result word until
release returns. This entry does not compose nonzero open replies or other
callbacks with a request.

| Host status | Meaning |
|---|---|
| `CLOCK_REQUEST_OK` | The bounded operation returned; inspect raw result and state/output separately |
| `CLOCK_REQUEST_INVALID` | A required pointer/provider is absent or an address extent wraps |
| `CLOCK_REQUEST_UNSUPPORTED` | An input, cache combination or reachable reply is outside the fixed profiles |
| `CLOCK_REQUEST_BOUNDS` | The manager or output buffer is shorter than required |
| `CLOCK_REQUEST_OVERLAP` | Supplied API storage overlaps |

Host errors preserve every state/output byte and emit no callback. The
helper checks all typed object extents and the entire declared buffer
lengths for address wrap and pairwise overlap before reading fields.
This includes immutable plans, inputs and the raw-result word. The open
handle write is the sole declared internal output within the manager.
Callers establish actual backing, writability, alignment and lifetime,
and keep provider bookkeeping and indirectly referenced storage separate
from every API object. No object is retained, allocated or freed.

```sh
python3 -m unittest tests.test_clock_request
make -C src/start4 check-clock-request
```

The host tests compare all sixteen complete request/initializer fixtures,
including defined callback arguments, identities, replies, raw results,
all 1156 manager bytes, miss state and output guards. Additional tests
cover callback-visible state, reachability, unsupported combinations,
nulls, short buffers, address wrap and overlap. Sequential tests carry
initializer and request output state directly into subsequent requests
with fresh output/raw storage. Unsupported repeated states are rejected.
Incidental register words and native stack addresses are excluded from
the portable comparison.

The Make target writes `build/start4/clock-request.o` with the pinned VPU
compiler using `-Os -ffixed-lr`. Preserve that LR reservation when using
this toolchain; native host builds omit it. Runtime acquisition,
relocation, ownership, concurrency and physical clock completion require
separate contracts before integration.

## Fixed clock programming helpers

[`clock_driver.h`](clock_driver.h) exposes three freestanding operations
from [`clock_driver.c`](clock_driver.c), bounded by the
[programming contract](../../docs/bcm2711/clock-driver.md):

| Operation | Fixed arguments | Writable state |
|---|---|---|
| `clock_source_program` | Source 2, requested 1200000000 | Request marker, requested and cached 64-bit rates |
| `clock_word_program` | Clock 0x30, source 7, divider 5, factor bits 0x3F800000, final argument 0 | One native 32-bit cell |
| `clock_divider_program` | Divider 5, count 2 | Request marker and count |

These are separate leaf operations. They remain unlinked from `start4.elf`
and from `clock_request_execute`; their state cannot be substituted for
the manager's state. They emit observations and update caller-owned storage.
They do not acquire a driver, dereference peripheral addresses or establish
a physical rate, lock, timing interval or completion state.

Each input structure contains the incoming and comparison handle words.
The supported matching value is 0xC10C1234; the mismatched profile uses
incoming 0xC10C1235. The native-word operation also accepts both handles
zero with initial cell zero. Other handles are unsupported. Source and
divider selection is 1. The source's helper selection and gate are zero,
helper input is 1200, and diagnostics are disabled. The native-word inputs
also retain the fixture's zero diagnostic and enable bytes. The enable
byte remains an immutable supplied value, without an assigned control role.

Initial source state is marker 0x55667788, requested
0x99AABBCC11223344 and cached 1000000000. Initial divider state is marker
0x12345678 and count 0x87654321. The native cell accepts zero, 0x10,
0x12345678 or 0x80 with the matching nonzero handle. Its mismatched profile
requires 0x12345678. The resource composition adds exactly initial cell
0x5A000000 with matching handle 0xC10C1234. Other updated source, divider
or native-cell states do not become supported initial profiles.

Source and divider receive a `clock_driver_plan`: an immutable array of
`clock_driver_read` records, a record count and an observer. Each record
contains a logical address and its literal reply word. Preflight accepts
only the exact paired source or divider profiles in the contract, including
their complete reply order. The dimensions cannot be combined independently.
Missing, extra, reordered or changed records fail before execution. Writes
never supply later reads. The three selector-1 setup words at
0x7E102074–0x7E10207C are fixed profile constants; the helper does not infer
a wider register-field rule from them.

The source updates both request fields and the rate cache before its first
MMIO observation. It computes the rounded fixed-point quotient from the
requested rate and reference 54000000, then applies the documented integer
steps, masks and ordered writes. The actual 2000-read lock counter returns
raw 4 on its accepted exhaustion profile, retaining the updated caches and
final CM write. Matching lock returns raw zero. The divider updates its
marker/count before its first observation, masks the initial word to eight
bits and steps down to 2 when required. It preserves the repeated final
target write. Raw byte zero takes the documented bypass; it is not treated
as a divisor of 256.

Command polling has no firmware count limit. The accepted plans include
their terminating zero replies, validated in advance. Missing termination
is a host validation error, never a raw lock-counter result. The finite
native-cell loop is separate: it reads only the supplied cell, clears bit
4, and tests bit 7 up to 2000 times. Exhaustion adds bit 5 and still returns
raw zero. There is no native-cell reply plan or asynchronous mutation.

The synchronous `void` observer receives its context, event kind, address
identity and word. `CLOCK_DRIVER_MMIO_READ` and `CLOCK_DRIVER_MMIO_WRITE`
describe supplied reads and issued requests. `CLOCK_DRIVER_NATIVE_READ`
and `CLOCK_DRIVER_NATIVE_WRITE` describe access to the actual cell, labeled
0x0EE056B0. A native write is observed after the store. The address tokens
are never converted to host pointers. Every event precedes the raw-output
store, so observers see the incoming raw-output word throughout a call.
The fixtures' instruction PCs and incidental registers do not define this
portable API.

Every top-level pointer is required, including the plan or observer object.
Matching profiles require a nonnull observer function. Mismatched profiles
return raw 0xFFFFFFFF with no events or state changes and need no observer
function; their MMIO plan count must be zero and its read pointer may be
null. Context may be null when the observer accepts it. The observer must
return normally and preserve every API object. Its bookkeeping storage and
indirectly referenced objects must remain separate. Reentry, concurrent
mutation, dynamic replies, hardware access and recovery from observer
failure have no defined policy.

| Host status | Meaning |
|---|---|
| `CLOCK_DRIVER_OK` | The fixed operation returned; inspect raw output and state separately |
| `CLOCK_DRIVER_INVALID` | A required object, read pointer or reachable observer is absent |
| `CLOCK_DRIVER_UNSUPPORTED` | Inputs, state or the complete read sequence are outside the accepted profiles |
| `CLOCK_DRIVER_BOUNDS` | A span or record-size calculation wraps, or required read records are missing |
| `CLOCK_DRIVER_OVERLAP` | Declared API storage overlaps |

Host errors preserve all state and output bytes and emit no events. Checks
cover typed-object extents, read-array size multiplication, address wrap
and pairwise overlap before effects. Truncated or altered profiles can
report either bounds or unsupported according to the first failing check.
Callers establish actual backing, alignment, writability and lifetime.
The helpers retain no pointers and allocate no storage.

```sh
python3 -m unittest tests.test_clock_driver
make -C src/start4 check-clock-driver
```

The host tests compare all 22 complete cases, including 2362 MMIO reads,
590 MMIO writes, 2015 native reads and six native writes. They check cache
visibility at every event, raw-output timing, repeated final writes,
guarded state, every literal reply/address, unsupported combinations,
missing termination, nulls, overlap, address wrap and repeated-state
rejection. The Make target compiles `build/start4/clock-driver.o` with
`-Os -ffixed-lr`; preserve the LR reservation for the pinned VPU compiler.
Runtime initialization, descriptor relocation, ownership, concurrency
and physical readback require further contracts before integration.

## First owned clock composition

[`clock_composition.h`](clock_composition.h) exposes
`clock_composition_execute` from [`clock_composition.c`](clock_composition.c).
It implements the two complete calls in the
[first clock composition contract](../../docs/bcm2711/clock-composition.md).
The operation owns manager transitions and dispatches the source,
native-word and divider helpers directly. It stays unlinked from the
runtime image. The existing manager providers retain their observation-only
contract; installing a state-mutating leaf call as a provider is unsupported.

The inputs contain the existing request fields and explicit source helper
selection, gate, input and diagnostic fields. The manager uses exactly the
1156-byte entry profile in the contract: table 0x0EDE7F04, handle
0xC10C1234, clock cache 500000000 and all remaining bytes zero. The separate
miss state has initialized flag 1 and zero misses. Source and divider
state retain the leaf contract's initial sentinels; the native cell is zero.
The manager reference remains zero and is distinct from the leaf arithmetic
reference 54000000. Mutex identity is an opaque observation token supplied
through the request inputs.

The composed plan contains the immutable source/divider read arrays,
their observers, a native-cell observer, and acquire/diagnostic/release
observers. These last three use the existing request-provider signature
with literal zero replies. There are no programming reply fields. Source
accepts only enabled-equal immediate lock or exactly 2000 zero lock replies.
Divider accepts exactly five reads: initial 5, three zero command replies,
and final 0x00345678. The standalone divider also accepts this additional
exact pair while retaining all eight prior divider profiles. Its other
final 0x0034567A replies cannot be substituted independently.

The native cell remains actual caller-owned storage. Composition has no
enable-byte input or lookup. Its adapter supplies zero to the word helper's
required, unreachable enable field as an internal compatibility constant.
This value does not represent a firmware observation.

Whole-path preflight validates every required object, observer, exact
entry value and complete read plan before acquisition or any state change.
It checks full declared manager/output extents, all typed objects and both
read arrays for wrap and pairwise overlap. Invalid later divider data cannot
leave an earlier source or cell update. Host status uses `clock_driver_status`:
null required objects or observers return `CLOCK_DRIVER_INVALID`; short or
wrapping spans and overflowing array sizes return `CLOCK_DRIVER_BOUNDS`;
unsupported entry values or read plans return `CLOCK_DRIVER_UNSUPPORTED`;
overlap returns `CLOCK_DRIVER_OVERLAP`. No host error emits an observation
or changes any API storage. Truncated plans can report bounds or unsupported
according to the first failing check.

Acquisition and diagnostic observe entry state. Source observations see
changed miss fields and manager count 2, with the old manager rate caches
and output. Native-word and divider observations see manager source
1200000000 and divider-rate 600000000, with clock cache 500000000 and
unchanged output. Release sees completed state and output 600000000.
The result structure receives actual `source_raw`, `word_raw`, `divider_raw`
and `manager_raw` words only after release. The tuples are `(0,0,0,0)` and
`(4,0,0,0)`. Source raw 4 does not skip either subsequent operation.

Observers preserve every API object and use separate bookkeeping storage.
They return normally and cannot reenter, access hardware, change plans or
mutate the native cell asynchronously. The helper allocates no storage and
retains no pointers. Caller backing, typed alignment, writability and
lifetime remain preconditions. The two recorded source-return prefixes
check intermediate state and event ordering; they do not define partial
execution operations. Other first states, repeated requests, notifications,
cold initialization and arbitrary callbacks require separate contracts.

```sh
python3 -m unittest tests.test_clock_composition tests.test_clock_driver
make -C src/start4 check-clock-composition
```

The tests compare both complete event streams and final state, and compare
the corresponding source-return prefixes as intermediate observations.
They check every manager byte, miss field and read-plan word, observer-time
state/result visibility, later-plan rejection, full-span overlap, address
wrap, guards and repeated-state rejection. The target compiles composition
and driver objects with `-Os -ffixed-lr`; preserve the LR reservation for
the pinned VPU compiler. The shared internal leaf preflight functions are
read-only implementation plumbing, not additional firmware operations.

## Owned fixed resource composition

[`resource_composition.h`](resource_composition.h) exposes
`resource_composition_execute` from [`resource_composition.c`](resource_composition.c).
The [complete resource contract](../../docs/bcm2711/resource-composition.md)
defines its two fixed resource-23 profiles. The helper owns record,
aggregate and prehook stores, both selected resource bodies, configuration
routing, two actual clock operations and the ordered control requests.
It remains unlinked from the runtime image. Existing resource and clock
request providers retain their observation-only interfaces.

```c
resource_composition_execute(inputs, records, records_length, resource,
                             manager, manager_length, clock_state,
                             source, divider, cell, scratch, scratch_length,
                             plan, result);
```

The record buffer contains 32 little-endian records with a 28-byte stride.
Its first 896 bytes must contain only record 0's nonzero self identity;
that identity equals the request's opaque identity. The request selects
record 0, logical index 23, arguments 1/1, dependency selection zero and
resource handle zero. Resource table is 0x0EDFD200, resource selection is
one, and skip, held and prehook words are zero. Configuration has table
0x0EDE54D4, handle 0x61726D11, service index one and A/B/C/D equal to
0/1/0/0. The four mutex tokens are distinct. Tokens describe observations
and are never dereferenced or called.

Clock inputs, manager bytes, miss state, source/divider sentinels and native
cell must match the first-clock contract. The plan embeds its source and
divider reads, word observer and mutex/diagnostic observers. It also holds
two separate 24-read control plans and one five-read final plan. Each must
match the complete literal read sequence in the resource contract. Source
lock is immediate or exhausts its actual 2000-read counter. No caller
supplies a source, divider, native-word or resource reply in place of the
owned operation. Resource diagnostic, mutex and service observers receive
the documented identity, defined argument words and literal zero reply.
Clock diagnostics preserve all seven logical words.

The operation calculates the old aggregate, sets record 0's bit 23 and
calculates aggregate 0x180. It processes added masks 0x80 then 0x100,
acquiring outer then resource and releasing resource then outer for each.
Prehook stores follow the acquisitions. The first body makes no clock or
control request. The second dispatches six configuration services, then
the two clocks and their control phases. Control writes use the actual
supplied words, masks and saved first word; expected write arrays are not
inputs. The ten command polls per phase and two final bit polls retain
their supplied observations. Missing termination fails preflight and
does not become a firmware timeout.

The first eight scratch bytes are cleared immediately before each clock
acquisition. The first clock runs source, selected word and divider. Its
source raw 4 retains its mutations and continues through both later
operations. The second clock uses the completed manager/source/divider
state and actual native cell; it performs only the selected-word operation.
Its native reads and write all contain 0x5A000000. Scratch is written as
unsigned 64-bit 600000000 before each clock release. The intermediate
control phase preserves these software fields. The final result contains
the first clock's four actual raw words, repeated word and manager raw
words, and resource raw zero. It is stored only after the manager release.
There is no tagged stop or higher ARM-start operation in this interface.

Whole-path preflight covers all fixed input/state fields, required
observers, complete read plans and the predicted repeated-word domain
before the first resource diagnostic. Checks include size multiplication,
address wrap and pairwise overlap for every API object, all five read
arrays, and the complete declared records, manager and scratch spans.
Only the first 896, 1156 and eight bytes of those buffers can change;
tails remain untouched. Initial aggregate and scratch contents remain
visible until their specified stores.

Host status uses `clock_driver_status` with the same invalid, unsupported,
bounds and overlap meanings as the first composition. Host errors emit no
events and preserve every state, scratch and result byte. Callers supply
backing, lifetime, writable storage and typed alignment. Observers preserve
all API objects, return normally, use separate bookkeeping and avoid
reentry, concurrent mutation and hardware access. No pointer is retained
and no storage is allocated. Request order, numerical rates and raw zero
do not establish physical completion.

```sh
python3 -m unittest tests.test_resource_composition
make -C src/start4 check-resource-composition
```

Tests compare both complete fixture event streams and final memory, plus
callback-visible resource/prehook ordering, nested clock cache timing,
scratch clearing and native-store visibility. They exercise altered later
reads, missing polls/observers, unsupported state, all pairwise API/array
overlaps, full-span tails and address/size overflow. The target compiles
standalone resource, clock and configuration objects with `-Os -ffixed-lr`.
Runtime acquisition, initialization and physical behavior require separate
contracts before integration.

## Owned fixed ARM start composition

[`arm_start_composition.h`](arm_start_composition.h) exposes
`arm_start_composition_execute` from
[`arm_start_composition.c`](arm_start_composition.c). The
[higher composition contract](../../docs/bcm2711/arm-start-composition.md)
defines two complete calls through the real fixed resource operation.
The helper owns higher gates and active state, dispatches the resource
composition directly and remains unlinked from the runtime image.

```c
arm_start_composition_execute(inputs, start, records, records_length,
                              resource, manager, manager_length, clock_state,
                              source, divider, cell, scratch, scratch_length,
                              plan, result);
```

Inputs contain handle 0x61726D11, an opaque higher mutex token and the
existing fixed resource inputs. The separate `arm_control_start_state`
requires open count 1, mapping marker 1, active 0 and a nonzero object
token equal to both the lower request identity and record 0's self word.
The higher mutex token differs from all four lower mutex tokens. Tokens
are never converted to host pointers. Configuration service index and
higher active remain separate fields.

The plan embeds the resource plan and adds higher acquire/release
observers with one defined argument, the mutex token, and literal zero
replies. It has no resource-result provider. The lower operation retains
both clock requests, shared manager/driver/native state, scratch clears,
control phases and final polls. Only immediate first-source lock or
exactly 2000 zero lock replies are accepted. Source raw 4 retains its
updates and continues through all remaining operations.

Higher acquisition sees entry state. Higher active stays zero throughout
every lower observation, including the lower manager release. After the
actual lower return, its raw word is retained separately and zero sets
active to 1. Higher release sees active 1 and completed lower state. Only
after that release does the final result receive the actual nested result
structure and a separate `higher_raw` word. Host status, raw words, active
state and the unsigned 64-bit rate scratch have distinct meanings.
Open count, mapping marker and object token remain unchanged.

Whole-path preflight checks both higher gates and the complete lower
operation before higher acquisition or any store. It includes every
required observer, both control plans, final polls, predictable repeated
clock state, all typed object extents, read-array size multiplication and
full declared records/manager/scratch lengths. Every region is checked
for address wrap and pairwise overlap, including immutable inputs and
the full final result. Shared read-only resource preflight is internal
implementation plumbing. Existing standalone interfaces and supported
profiles remain unchanged.

Host status uses `clock_driver_status`: absent objects or observers return
`CLOCK_DRIVER_INVALID`; short or wrapping spans and overflowing read
counts return `CLOCK_DRIVER_BOUNDS`; unsupported gates, states or complete
plans return `CLOCK_DRIVER_UNSUPPORTED`; overlap returns
`CLOCK_DRIVER_OVERLAP`. Host errors preserve every API byte and emit no
observation. Callers establish actual backing, typed alignment, lifetime
and writability. Observers return normally, preserve every API object,
use separate bookkeeping and avoid reentry, concurrent mutation and
hardware access. No storage is allocated and no pointer is retained.

This returned-only operation accepts no general tagged resource outcome,
context descriptor or stopped path. A stopped prefix has no scalar return
word and supplies no higher active-state decision or release behavior.
Other higher gates, lower outcomes and provider effects need separate
contracts. Raw zero and active 1 do not establish physical completion.

```sh
python3 -m unittest tests.test_arm_start_composition
make -C src/start4 check-arm-start-composition
```

Tests compare both complete event streams and all specified final memory,
plus both evidence-only lower-return prefixes. Observers check unchanged
active state throughout lower work and deferred final-result storage.
Rejection tests cover later read errors, missing observers, every pair of
API objects/read arrays, full buffer tails, address/count overflow, exact
gate and object binding, full-width 32-bit tokens and repeated-state
rejection. The target builds standalone higher, resource, clock and
configuration objects with `-Os -ffixed-lr`. Runtime object preparation,
ownership, synchronization and physical behavior require further contracts.
