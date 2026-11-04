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
