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
