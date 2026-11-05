# Headless firmware analysis

The [startup memory recorder](startup-zero-observations.md) binds exact
original ELF allocations, detached instruction sites and two synthetic
caller profiles. It records complete memory observations and separate
runtime-data and decoder-transport streams.

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

## Bounded startup inspection

`InspectStartupInitialization.java` exports instruction bytes and compiled
p-code from fixed range sets in `start4.elf`, raspberrypi/firmware
commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`, SHA-256
`38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
The default `initializer` set contains 182 bytes at 0x0EC3D740, file offset
0x3D140, and two bytes at 0x0EC3D7F6, file offset 0x3D1F6. It also inspects
the 36-byte table at 0x0EDD7870, file offset 0x1D7270.

The script verifies the complete original file digest, direct file mapping,
and current-byte equality for each range. Its default `listing` mode
requires existing instructions at every selected code address and stops
if an instruction is missing or crosses a range boundary.

An optional mode argument `pseudo` selects Ghidra's `PseudoDisassembler`.
Each instruction receives only the remaining bytes of its exact range,
with a fresh decoder using the current program context. The output records
the current, default, nondefault and default-disassembly context masks and
values. In the `initializer` set, omitted context keys represent null API
results. A zero context mask marks bits whose values are unknown. No context value is supplied
or changed. Unknown instructions, low-bit code modes, delay slots and
next-instruction dependencies are rejected. Results describe that recorded
decoder context; they do not establish equivalence to an omitted
flow-specific context.

Neither mode performs analysis, emulation or program modification. Selected
current bytes, instruction definitions and context values are checked again
before output. Limits are 92 instructions, 4096 p-code operations and
1048576 output characters.

Use an unused output path outside the tracked tree. The JSON contains
firmware bytes and instruction text and must remain local.

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript InspectStartupInitialization.java \
  38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb \
  /work/analysis/startup-initialization.json
```

Append `pseudo` after the output path to select detached decoding. The
default mode does not fall back to it when an instruction is missing.

An optional fourth argument selects `initializer`, `arrival`, `continuation`
or `soc`; the third argument must then be `listing` or `pseudo`.
The `continuation` and `soc` sets require `pseudo`. Both existing argument forms
and explicit `initializer` retain the same output format. For example,
append `pseudo arrival` after the output path to inspect the arrival set.
Unknown modes and range-set names are rejected.

The `arrival` set binds these 204 code bytes and 48 data bytes in the same
`start4.elf` version and digest:

| Kind | Address | File offset | Bytes |
| --- | --- | --- | ---: |
| Code | 0xCEC00200 | 0x7E0 | 92 |
| Code | 0x0EC2CB90 | 0x2C590 | 54 |
| Code | 0x0EC2FCCC | 0x2F6CC | 2 |
| Code | 0x0EC36AEC | 0x364EC | 30 |
| Code | 0x0EC2FCD0 | 0x2F6D0 | 2 |
| Code | 0x0EC87EE8 | 0x878E8 | 12 |
| Code | 0x0EC87F2E | 0x8792E | 12 |
| Data | 0xCEC00280 | 0x860 | 32 |
| Data | 0x0EE02C64 | 0x202644 | 4 |
| Data | 0x0EDE886C | 0x1E824C | 4 |
| Data | 0x0EE055B0 | 0x204F90 | 4 |
| Data | 0xCEC02000 | 0x231AA0 | 4 |

The data at 0xCEC02000 belongs to file-backed program header 19, whose
file and memory sizes are both 16 bytes. Program headers 17 and 18 share
file offset 0x231AA0 but have zero file size and different virtual addresses.
The exact address and direct file mapping determine the selected source.

Arrival output adds `range_set: "arrival"` and serializes null values
explicitly. Each site also records `instruction_context` from the actual
instruction's base-context register getter, separately from the four
ProgramContext values in `decoder_context`. In pseudo mode this getter
reads the returned detached instruction's input context. Present listing
instructions have the same getter included in the before/after preservation
snapshot. Values retain their observed masks and stored bits; the script
does not supply or normalize them.

The initializer and arrival sets retain the same 92-instruction and output
limits. Static
`CALLOTHER` operations include the installed operation name and varnodes
as output data; the script does not execute them. Static inspection does
not establish a completed startup path or a processor identity.

Append `pseudo continuation` to inspect at most 16 contiguous instructions
from 0x0ED4A08C in the same `start4.elf` version and digest. The source
envelope contains exactly 64 bytes at file offset 0x149A8C, SHA-256
`7e14b716ed728805159a08dde64a420567b4b5d7b15251cee986cb194c872c8b`.
The decoder receives no adjacent bytes and follows no targets. The envelope
does not define a function extent.

The prefix includes a decoded boundary instruction and stops on direct or
indirect control flow, unsupported instructions or p-code, or a missing or
nonsequential fallthrough. External-space p-code branches stop inspection
even when they only skip a predicated instruction to the ordinary next PC.
Constant-space intra-instruction branches alone do not stop it. Unsupported
decode dependencies are recorded without extracting p-code. Unknown
instructions, insufficient source bytes and unknown context produce explicit
decode-stop records; source, mapping, preservation or other invariant
failures produce no output.

Continuation output adds `inspection_kind: "bounded_prefix"`,
`function_complete: false` and a `stop` record with the reason, PC, terminal
site inclusion and consumed instruction/byte counts. The 16-instruction and
64-byte limits are incomplete observation boundaries. Context values and
nulls are explicit as in arrival output. A trailing listing instruction
that crosses the envelope contributes only bounded metadata and context
to preservation checks. The initializer and arrival outputs are unchanged.

Append `pseudo soc` to inspect these fixed ranges in the same `start4.elf`
version and digest:

| Kind | Address | File offset | Bytes |
| --- | --- | --- | ---: |
| Code | 0x0EC6221C | 0x61C1C | 22 |
| Code | 0x0EC6227C | 0x61C7C | 182 |
| Code | 0x0EC62332 | 0x61D32 | 64 |
| Uninterpreted data | 0x0EC62232 | 0x61C32 | 74 |

The decoder visits only the three code ranges, in address order, with no
target following. The 74-byte gap is bound as data and remains undecoded.
Output adds `range_set: "soc"`, `inspection_kind: "fixed_ranges"`,
`function_complete: false` and each range's `kind`. Context values and nulls
are explicit as in arrival output. The 92-instruction, 4096-operation and
output limits remain in force. Calls, VERSION operations and memory accesses
are exported as static p-code; no firmware instructions execute. The selected
ranges do not establish a complete function or control-flow graph.

Append `pseudo post-soc` to inspect the following startup handoff ranges
in the same `start4.elf` version and digest:

| Kind | Address | File offset | Bytes |
| --- | --- | --- | ---: |
| Code | 0x0EC3689E | 0x3629E | 32 |
| Code | 0x0EC3694E | 0x3634E | 2 |
| Code | 0x0EC9BB62 | 0x9B562 | 52 |
| Uninterpreted data | 0x0EE055B8 | 0x204F98 | 4 |

This set uses `range_set: "post-soc"`, explicit context/null values and
the same fixed-range metadata and caps. It rejects `UNIMPLEMENTED`
p-code before writing an output. Decoding ends at 0x0EC368BE,
0x0EC36950 and 0x0EC9BB96; no call or branch target is followed.
The data word remains undecoded. No firmware instruction executes.
These ranges do not establish caller arrival, saved-frame validity,
live pointer preservation or a completed driver return.

`CaptureSocInitialization.java` records the call from 0x0EC6221C to the
terminal return at 0x0EC62370 in the same `start4.elf` version and digest.
It requires the diagnostic byte at GP+0xCCDB8 to be 0..3 and rejects every
external call. The SoC initialization ranges above remain fixed. Six bytes at
0x0EC62372, file offset 0x61D72, serve only as decoder transport; they are
not executable sites or runtime data. For admitted instruction length L,
the decoder may read within [PC,PC+max(8,L+3)). The six-byte instructions
at 0x0EC62334, 0x0EC6234A and 0x0EC62366 instead admit [PC,PC+13), because
their displacement patterns refill eight bytes from PC+5. All spans fit
the same 348-byte source union. The terminal span remains eight bytes.

The request has `schema_version: 1`, `source_sha256`, `tool_sha256`,
`helper_sha256` and `profiles`. The helper is `StartupZeroObservations.java`.
Each profile supplies all 32 scalar registers, a 128-byte stack at SP−64,
seven guarded memory regions, independent ordered `version_inputs` and
conditional `mmio_inputs`. VERSION inputs name 0x0EC6221E/r4 and, when
required, 0x0EC62332/r2. The only MMIO input names the four-byte read at
0x0EC6230E from 0x7E0000B4. Its word is seeded in emulator memory and read
by the original LOAD; no device is accessed. Register words use eight
upper-case hex digits with `0x`; memory bytes use lower-case hex strings.

Profiles use the named regions `flags_a`, `flags_b`, `ready`, `processor`,
`control_mode`, `diagnostic` and `opaque`, with 16, 16, 12, 8, 20, 12 and
12 bytes respectively. Their GP offsets are 0x1560, 0x16E0, 0x3B890,
0x3B8AC, 0x3B920, 0xCCDB4 and 0x3B480. Only the declared fields and
[SP−24,SP) are writable; surrounding bytes are checked as guards.

```sh
GHIDRA_HEADLESS_MAXMEM=2G /opt/ghidra/support/analyzeHeadless \
  /work/analysis/projects firmware_a \
  -process start4.elf -readOnly -noanalysis -max-cpu 1 \
  -scriptPath tools/ghidra \
  -postScript CaptureSocInitialization.java \
  /work/analysis/soc-request.json /work/analysis/soc-observed.json
```

The recorder accepts at most 50 profiles and 128 instructions per profile.
It records complete initial/final registers, memory and stack bytes,
ordered data and VERSION events, separate decoder counters and hashes,
and explicit context masks. Guard violations, unconsumed observations or
unexpected accesses fail without a successful output. The 1048576-character
output contains observations only; compare it separately with expected
results. Keep requests and outputs outside the tracked tree.

An optional `trace-decoder` argument before the request path records the
installed decoder's memory requests for the fixed 81 sites without executing
p-code. It uses the same 348 source bytes and compares each instruction's
bytes, length, p-code and context with the admitted static result. Each site
permits at most 32 reads and 512 bytes. The output lists read addresses,
widths and enclosing spans; it does not establish runtime observations.

## Scalar observations

The [source-backed ELF data contract](elf-data-observations.md) permits
exact scalar reads and writes to declared initialized data regions.
Original file bytes, mappings, permissions and final observations are
checked before execution. Ordered events record actual accesses without
caller overlays or changes to the existing synthetic-memory guards.

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
table-zero returns. The separate [masked first-open composition](bcm2711/arm-first-open-masked.md)
joins real driver registration and the predicate to a complete later rejection.
Successful open and physical effects remain unresolved.

The [mask predicate and word-pair shift](bcm2711/mask-predicate.md) specify
general scalar inputs with 28 complete synthetic calls. The shift separates
the logical 64-bit count interval from its pinned compiled behavior for
all unsigned 32-bit counts. Out-of-range predicate codes read no mask data.

The [driver initialization prefixes](bcm2711/driver-initialization.md)
record actual 96-byte clearing, first lookup preparation and DI with fresh
nested frames. Both stop before SWI; complete initialization and live
startup ordering remain unresolved.

The [service initialization](bcm2711/service-initialization.md) records five
complete standalone paths through the original ELF word update, ordered
MMIO effects and an actual constructed frame consumed by the pinned RTI
semantics. Physical exception behavior, SWI linkage and startup arrival
remain unresolved.

The [service token lookup](bcm2711/service-token-lookup.md) defines exact
32-bit query comparison against the complete original 42-word table. Five
standalone calls compare all ordinary registers and unchanged observation
storage; the connected SWI request and runtime destination store remain open.

The [service word update](bcm2711/service-word-update.md) specifies a complete
standalone scalar body with general 32-bit inputs, ordered VERSION/read/write
observations and nine recorded calls. Full-width shifted values can set bits
beyond the cleared nibble. Physical register meaning and exception entry
remain unresolved.

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
The [masked first-open replay](bcm2711/arm-first-open-masked.md#recorded-complete-call-and-service-boundary)
retains a complete rejection, four further general-domain samples and a
separate clear-mask service prefix.
The [driver-open mask replay](bcm2711/driver-open-masks.md#recorded-calls-and-replay)
executes six complete callbacks with optional mask copying, actual registrar
composition and retained effects on a capacity return.
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
