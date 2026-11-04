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

## Scalar observations

The [VERSION input contract](bcm2711/vpu-version.md) defines the optional
`execution.version_input` object. It supplies one immutable word and ordered,
unique instruction sites with ordinary destinations `r0` through `r23`.
The recorder validates the complete plan and original instruction bindings
before execution. A named operation callback writes only the exact output
varnode; the interpreter advances normally. Each site produces one ordered
`version` event with its index and the preceding instruction count. Missing,
malformed, mismatched, reordered, repeated or unused observations fail.
Captures without the object retain the existing VERSION rejection and
scalar guards. Supplied words do not identify hardware or establish a
completed native continuation.

`CaptureClockVectors.java` implements the same
[VERSION contract](bcm2711/vpu-version.md#clock-recorder-integration).
Its VERSION cursor remains independent of the existing finite MMIO and
function reply plans. The source identity, descriptor, native-cell and
MMIO guards still apply. VERSION joins the shared event array without
consuming a device reply or authorizing a memory access. The
[first-open routes](bcm2711/arm-first-open.md) include three recorded complete
table-zero returns. Successful open and physical effects remain unresolved.

The [IRQ and p16 contract](bcm2711/vpu-irq.md) specifies a separate
`execution.irq_p16` plan for both recorders. It requires an explicit
no-interrupt-arrival premise and finite ordered instruction occurrences.
It preserves the native SR calculation, supplies each p16 read and records
actual writes. Both recorders use `IrqP16Observations.java` for schema,
instruction binding and ordered consumption. DI rejects without the plan;
other no-plan behavior remains unchanged. The interface supplies no physical
interrupt or mutex behavior.

The schema tests compile against an explicitly selected public Ghidra
installation and require its supported JDK:

```sh
OPEN27XX_GHIDRA_HOME=/opt/ghidra python3 -m unittest \
  tests.test_scalar_version tests.test_clock_version tests.test_irq_p16
```

These tests check JSON types, exact members, complete words, site ordering
and canonical register names. Clock's schema test also checks preservation
of separate MMIO and function plans. They do not run native instructions.
Without `OPEN27XX_GHIDRA_HOME`, the optional API-dependent tests are skipped.
Instruction binding, execution and continuation checks require the headless
recorder.

`CaptureScalarVectors.java` runs the synthetic cases in
`tests/vectors/bootsys/`, `tests/vectors/bootmain/` and
`tests/vectors/start4/` against a matching
imported program. Use the versions above and a read-only project. The
output path must not exist.

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process bootcode4.bin -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript CaptureScalarVectors.java \
  tests/vectors/bootsys/resource-digest.json \
  /work/analysis/resource-digest.json
```

The script checks the imported input SHA-256, then executes scalar
instructions with `EmulatorHelper`. It records the requested registers,
memory bytes, ordered callback and MMIO-write events, and instruction
step counts. Compare the resulting JSON values with the input fixture;
whitespace and object-key order do not affect the comparison. A matching
capture reproduces the declared observations, not every aspect of the
device or boot path.

The schema has these fields:

| Field | Meaning |
|---|---|
| `source` | input filename, repository, version and SHA-256 |
| `cases[].function` | scalar entry, language and optional provisional raw base |
| `setup.register_default` | initial value for every scalar register before overrides |
| `setup.registers` | explicit register overrides |
| `setup.memory` | ordered synthetic memory initialization |
| `execution` | return address, step limit, literal call responses and MMIO responses |
| `expected` | observed registers, memory and ordered events |
| `steps` | executed emulator steps; substituted calls do not count |
| `scope`, `limitations` | behavior exercised and boundaries not executed |

Addresses and register values are hexadecimal strings with `0x`; byte
arrays are hexadecimal strings without a prefix. A memory region uses
`address` and either `hex`, or an integer `size` and one-byte `fill`.
Regions apply in array order, allowing explicit field overlays on a
zero-filled synthetic structure. Synthetic RAM uses
`0x24000000`–`0x24FFFFFF` or `0xE4000000`–`0xE4FFFFFF`; the latter supports
tests of destinations with a high address alias. These are independent
emulator regions, not accesses to hardware.

A substituted call has a unique `entry`, a descriptive `label`, and an
ordered `replies` array of literal register and memory effects. Every
reply must be consumed exactly once in order. Each interception records
`r0` through `r5` and returns to the incoming `lr`. The tested decisions
must remain outside those substitutions.

The recorder rejects uninitialized reads, writes outside declared
synthetic regions, MMIO reads, modified instruction bytes, vector
instructions and unsupported p-code operations. It permits and records
writes to the main-peripheral range. Those events establish write order
and values only; they do not assign device behavior. Fixtures for this
recorder leave `mmio_responses` empty.

### Explicit instruction preparation

`DecodeScalarPaths.java` prepares explicit entry points missed by automatic
analysis. Its arguments are the expected source SHA-256 followed by one or
more 32-bit hexadecimal addresses with a `0x` prefix. It requires
`vc4:LE:32:default`, initialized readable executable memory, and aligned
instruction starts. It rejects defined data and addresses inside an
existing instruction. Existing instruction starts are accepted unchanged.

The helper restricts flow discovery to initialized executable blocks and
disables automatic code analysis. It defines instruction metadata without
clearing existing code/data, changing firmware bytes or exporting
instruction text. Use it only in the read-only invocation immediately
before the scalar recorder; transient definitions are discarded afterward.
The recorder's execution checks remain unchanged. The
[memory-capacity replay](bcm2711/memory-capacity.md#recorded-cases-and-replay)
lists the exact source identity and entry points for that fixture. The
[fixed clock-request replay](bcm2711/clock-request.md#replay) uses the same
unchanged scripts for its original cases and separate four-case
[cold/repeated state profiles](bcm2711/clock-request.md#first-and-repeated-request-states).
The [ARM object replay](bcm2711/arm-object.md#recorded-cases-and-replay)
uses three decoder entries for six complete registration/repeated-open
calls and a separate first-open prefix before `VERSION`.
The [ARM configuration replay](bcm2711/arm-configuration.md#recorded-cases-and-replay)
executes two complete control calls with explicit VERSION instruction results
and literal mutex/service replies.
The [ARM first-open replay](bcm2711/arm-first-open.md#recorded-cases-and-replay)
executes three callback-registration calls and three complete table-zero
first-open returns with actual nested registration and explicit CPU/MMIO inputs.
The [ARM mapping replay](bcm2711/arm-mapping.md#recorded-cases-and-replay)
uses two decoder entries and the same recorder for twelve complete
software-table calls, including the actual fresh-to-repeat state relation.

### Fixed clock recorder

`CaptureClockVectors.java` replays the [fixed clock programming fixtures](bcm2711/clock-driver.md)
and the [first clock composition](bcm2711/clock-composition.md#exact-fixture-and-replay).
The latter contains two complete calls and two intermediate source-return
prefixes; its unchanged decoder prepares the 31 listed entry points.
The [resource composition](bcm2711/resource-composition.md#complete-call-fixture-and-replay)
uses the same recorder for two complete requests with shared state across
both clock calls, control phases and the final resource/manager return.
The [higher start composition](bcm2711/arm-start-composition.md#exact-fixture-and-replay)
adds the actual outer caller and uses 54 decoder entries. Its fixture
contains two complete calls and two lower-return prefixes.
It uses the same two-path invocation shape as `CaptureScalarVectors.java`,
with separate restrictions for this pinned source and exact native cell.
Each `mmio_responses` record supplies `pc`, `address` and four little-endian
bytes in `hex`. Reads must consume those records exactly in order;
unknown, mismatched and unused replies fail. `mmio_write_addresses` lists
permitted four-byte write addresses for each case. Actual write values
come from execution, not expected-output injection.

The sole additional setup/observation region is four bytes at 0x0EE056B0.
Before execution, the recorder verifies source SHA-256, literal descriptor
pointer, exact block bounds, uninitialized read/write/non-executable status
and absence of instruction bytes. It records every executed cell read/write
as `elf_ram_read` or `elf_ram_write`, separately from `supplied_mmio_read`
and `mmio_write`. Partial cell accesses and other native writes fail.
All instruction-byte, unsupported-operation, declared-memory, finite-call
reply and step-limit checks remain active. These are offline observations;
no input is obtained from a physical device.

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
