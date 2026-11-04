# Headless firmware analysis

`tools/ghidra/analyze.py` imports four inputs into a fresh Ghidra project,
runs automatic analysis and exports JSON inventories. It requires Python
3.9 or later, Ghidra 12.2 and the VideoCoreIV extension release
`ghidra-rare-v1.0.0` from aleph-void/ghidra-videocore4, commit
`db09a308c2db6a31ba5e060e6b763713f77e4f7b`. The extension's
[`README.md`](https://github.com/aleph-void/ghidra-videocore4/blob/db09a308c2db6a31ba5e060e6b763713f77e4f7b/README.md)
describes installation and the `vc4:LE:32:default` language. The tested
Java version is OpenJDK 25.0.5.0.2; set `JAVA_HOME` to select the intended
installation when several versions are installed.

Fetch the pinned inputs with `scripts/fetch-blobs.sh --all`. Their
versions and SHA-256 digests are in
[bcm2711/vendor-files.md](bcm2711/vendor-files.md).

```sh
python3 tools/ghidra/analyze.py \
  --ghidra-home /opt/ghidra \
  --project-dir /work/analysis/projects \
  --project-name firmware_a \
  --output-dir /work/analysis/run_a \
  --bootsys blobs/bcm2711/bootfiles/2711/bootcode4.bin \
  --bootmain blobs/bcm2711/bootfiles/2711/bootmain \
  --recovery blobs/bcm2711/recovery.bin \
  --start4 blobs/bcm2711/start4.elf
```

The project name and output directory must be unused. Ghidra rejects
some project paths containing hidden directory names; use a path without
dot-prefixed components, or a symlink to the intended project directory.
The runner preserves symlinks in the project path. Keep projects, logs
and exports outside the tracked tree. They contain firmware-derived data.

Imports run sequentially with one analysis worker and a 2 GiB Java heap
limit. The ELF loader selects the language for `bootmain` and `start4.elf`;
their entry points and memory sections come from the ELF headers.
`PrepareFirmware.java` resets analysis options to the installed defaults
before automatic analysis.

The raw input path requires 512 initial zero bytes and a 284-byte footer
whose first little-endian word equals the preceding body length. It marks
the prefix and footer as byte arrays in non-executable blocks. The
intervening body is executable. The raw address choice remains provisional
as described below.

The preparation script adds one uninitialized, readable, writable,
volatile, non-executable block at `0x7C000000`–`0x7FFFFFFF` (67108864 bytes).
This is the main-peripheral range in *BCM2711 ARM Peripherals*, revision 4,
section 1.2.4, page 6, in [references.md](references.md). The block records
the legacy master view; it does not emulate devices or assign register
reset values. ARM-only local-peripheral ranges are not part of that view.

## Repeatability

Run the same command with a second fresh project name and output
directory. Compare `bootsys.json`, `bootmain.json`, `recovery.json`,
`start4.json` and `manifest.json` byte for byte. Keep the inputs, scripts,
Ghidra version, extension files and Java version fixed for the comparison.

Each report records the input digest, loader format, language, compiler
specification, analysis options, entry points, memory blocks, function
names and body ranges, and bookmarks. Reports omit project paths,
timestamps and database identifiers. The manifest records input sizes,
input hashes, script hashes and report hashes. Logs retain diagnostic
messages and timing; they are not deterministic comparison artifacts.
For raw imports, Ghidra's `image_base` metadata remains `0x00000000`;
the memory-block addresses record the selected mapping at `0x80000000`.

Successful analysis means that the configured analyzers finish. It does
not establish the accuracy of every instruction, function boundary or
calling convention. Review Bad Instruction bookmarks and the calling
convention before emulating a function. Vector instructions have
processor-specific p-code operations without execution semantics in this
extension; do not emulate vector code.

## Open questions

- Raw load address and entry point. The pipeline uses base `0x80000000`
  and entry `0x80000200` for both raw inputs. Confirm the mapping through
  absolute references and scalar emulation before using it as a runtime
  contract. The pinned `bootcode4.bin` offsets and digest are in
  [bcm2711/bootsys.md](bcm2711/bootsys.md); the pinned `recovery.bin` layout
  is in [bcm2711/usbboot.md](bcm2711/usbboot.md).
- Analysis coverage. Default analyzers can miss code reached through
  computed branches or mistaken data boundaries. Resolve each relevant
  entry and call path before using an exported function as a test oracle.
