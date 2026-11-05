# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Freestanding service-token lookup with complete scalar state, full-width
  queries, fixed numeric tokens and complete input/output storage preflight.
- Read-only startup inspection with exact source ranges, original-file
  mapping checks and explicit listing or detached p-code decoding.
- Service-token lookup contract with the complete 42-word numeric table,
  general scalar inputs and five complete original-table captures.
- Freestanding scalar service initialization with complete input preflight,
  final register/frame state and ordered numeric VERSION, table and MMIO events.
- Service initialization contract with an original ELF word update, ordered
  VERSION/MMIO observations and five complete constructed-frame RTI captures.
- Source-backed ELF data observations with original-file digest checks,
  exact scalar access plans, complete final observations and host API tests.
- Freestanding masked first open with shared prefix and helper computations,
  complete storage preflight, ordered observations and retained rejection effects.
- Masked first-open composition contract with actual shared registration,
  derived status, ordered retained effects, bounded general inputs and
  five complete synthetic rejections with a separate service prefix.

- Driver initialization prefixes with actual 96-byte clearing, first lookup
  preparation and DI observations before the unresolved SWI boundary.
- Freestanding general mask predicate and scalar word-pair shift, with
  shared computation, complete storage preflight and full-width counts.
- General mask-predicate and scalar word-pair shift contracts, with bounded
  host storage, explicit extended-count semantics and 28 complete captures.
- Freestanding driver-open mask copy and fixed suspend registration with
  shared whole-call preflight, retained capacity effects and outer raw zero.
- Driver-open mask contract with actual suspend registration, whole-call
  preflight and six complete synthetic callback captures.
- Freestanding general service word updates with complete storage preflight,
  explicit VERSION/read/write observations and full-width value arithmetic.
- General service-word-update contract with full-width values, explicit
  VERSION/MMIO observations and nine complete synthetic calls.
- Freestanding bounded suspend registration with scalar helper composition,
  complete preflight, retained object tails and ordered DI/p16 observations.
- Bounded suspend-registration contract with actual helper composition,
  preserved record tails and 16 complete synthetic IRQ/p16 calls.
- Opt-in IRQ and p16 observations in both scalar recorders, with complete
  instruction binding, finite occurrences, natural SR/COPY execution and schema tests.
- Freestanding suspend tuple lookup, bounded string length and bounded copy,
  with shared length computation and complete storage preflight.
- Conditional IRQ and p16 observation contract for both scalar recorders,
  with explicit inputs, natural instruction steps and unchanged memory guards.
- Suspend lookup, string-length and bounded-copy contracts with general
  bounded inputs and 20 complete scalar fixture comparisons.
- Freestanding selected callback registration and complete table-zero first
  opens with actual object registration, whole-call preflight and ordered observations.
- Callback-registration and complete first-open return contracts with six
  finite profiles, retained state and explicit CPU/MMIO inputs.
- Opt-in VERSION observations in the finite Clock recorder with independent
  site consumption, preserved MMIO/native-cell guards and schema tests.
- Explicit VERSION input contract for finite Clock observations, with
  preserved memory guards and conditional first-open acceptance targets.
- Freestanding ARM configuration control with explicit CPU and reply inputs,
  complete preflight and two ordered fixture comparisons.
- Complete ARM configuration-control contract with two explicit CPU inputs,
  ordered service observations and finite portable profiles.
- Opt-in scalar VERSION observations with strict input and instruction
  binding, a named operation callback, ordered events and schema tests.
- Explicit CPU VERSION input contract for scalar observations, with strict
  plan validation and conditional control-route acceptance.
- Freestanding ARM mapping-table preparation with exact profile validation,
  retained failure writes and twelve complete fixture comparisons.
- ARM mapping-table contract with twelve complete synthetic calls,
  actual repeated state and retained writes on a wrapped-index failure.
- Freestanding ARM object registration and repeated-open helpers with exact
  profile validation, ordered observations and six complete fixture comparisons.
- ARM object registration and repeated-open contracts with six complete
  synthetic calls, one first-open prefix and explicit retained-record fields.
- Owned fixed ARM start composition with whole-path validation, retained
  nested results, ordered active-state storage and complete fixture comparisons.
- Fixed ARM start composition with explicit resource-object binding,
  two complete synthetic calls and two lower-return checkpoints.
- Owned fixed resource composition with shared clock state, algorithmic
  control requests, whole-path preflight and complete fixture comparisons.
- Fixed resource composition with two state-sharing clock requests,
  ordered control-register operations and two complete synthetic calls.
- Owned first clock composition with complete nested programming, whole-path
  preflight, two complete fixture comparisons and source-return order checks.
- Cold clock-request composition and completed-cache repeated requests with
  full provider preflight and four additional synthetic fixture comparisons.
- First fixed clock-composition contract with two complete synthetic calls,
  two source-return prefixes and explicit nested state ownership.
- Freestanding fixed source, native-word and divider clock helpers with
  complete read-plan preflight and 22 synthetic fixture comparisons.
- Fixed clock-request state contracts and four synthetic cases for cold
  initialization, the first request and completed-cache repeated requests.
- Freestanding fixed clock-request and cold-initializer helpers with declared
  replies, bounded profiles and 12 complete synthetic fixture comparisons.
- Fixed source, selected-word and divider clock contracts with 22 synthetic
  cases and a strict public recorder for finite MMIO replies and one RAM cell.
- Fixed clock-request contract and 12 synthetic cases for planning,
  cache order, notification replies and separate lazy initialization, with
  lookup-miss ordering at diagnostic and notification boundaries and
  explicit diagnostic argument words.
- Freestanding fixed resource-request helper with literal boundary replies,
  tagged return/stop outcomes and 16 synthetic fixture comparisons.
- Fixed resource-request contract and 17 synthetic cases for dependency
  order, shared-state suppression and conditional check-context behavior.
- Standard-pair lower-span arithmetic and 27 synthetic cases for explicit
  byte-argument transfers into the memory-bank serializer.
- Freestanding memory-bank serializer with bounded output, explicit host
  validation and 44 complete synthetic fixture comparisons.
- Memory-bank serialization contract and 48 synthetic cases for ordered
  big-endian cells, numeric range selection and bounded caller stores.
- Freestanding memory-capacity helper with ordered byte callbacks, separate
  MiB/class outputs and 24 complete synthetic fixture comparisons.
- Memory-capacity calculation contract and 28 synthetic cases, with separate
  MiB/class observations and explicit instruction preparation for replay.
- BCM2711 PLLB register addresses and fields from pinned public sources,
  with explicit applicability and clock-state limits.
- Freestanding ARM configuration-request and software start-request helpers,
  with 40 synthetic fixture comparisons and separate host validation results.
- ARM service and mutex return-word checks, with 17 synthetic vectors
  for ignored replies and preserved resource results.
- ARM configuration-request routing and software start-request gates,
  with 24 synthetic vectors and explicit service boundaries.
- Ordinary ELF feature-word requirements, 35 synthetic compatibility
  vectors and conditional observations for the open VPU image.
- Freestanding boot-information parser, cache lookup, zeroing allocator,
  bounded revision fallback and metadata-pointer preparation, with 126
  synthetic fixture comparisons and host bounds checks.
- Boot-information record layouts, copy bounds, allocation zeroing and
  state-pointer execution vectors.
- Pinned VPU bring-up build with ELF bounds checks and a separate BCM2711
  ARM entry stub build; ARM handoff and Linux loading remain unimplemented.
- Freestanding ARM stub metadata preparation with five synthetic fixture
  comparisons and host buffer bounds checks.
- Repeatable headless Ghidra imports and metadata exports for four BCM2711 firmware stages.
- Scalar calling-convention observations and library entry points for the pinned firmware.
- Boot-flow documentation and synthetic execution vectors for resource loading,
  digest checks, SDRAM selection, configuration, boot modes and firmware loading.
- Scalar fixture capture with explicit memory and device-call boundaries.
- Filename override and zero-length fixup checks for replacement firmware loading.
- ARM stub metadata format and five scalar execution vectors for buffer preparation.

### Changed

- Reserve LR in the isolated boot-information VPU compilation target.

### Fixed

- Reject misaligned typed storage before callback registration or first-open
  field access and effects, including supplied unused words and plan arrays.
- Run macOS CI on Intel runners to avoid ARM64 allocation failures.
- Initialize clock and resource composition validation buffers so optimized
  GCC builds pass with uninitialized-value warnings treated as errors.

## [0.1.1] - 2026-11-04

### Fixed

- Use LZSS history snapshots for references and reject unwritten history.
- Limit LZSS encoder matches to bytes initialized before each reference.

## [0.1.0] - 2026-11-04

### Added

- `tools/eeprom.py`: list, extract, verify and rebuild BCM2711 SPI EEPROM images.
- Lossless EEPROM image serialization and LZSS/LZ4 section encoders, with
  regression tests across the pinned image catalog.
- Scripts to fetch and verify the pinned vendor firmware.
- Documentation of the BCM2711 boot chain and EEPROM image format.
- Continuous integration: license compliance, lint and tests.

### Changed

- Tie BCM2711 firmware observations to pinned files, hashes and offsets; separate unverified behavior from format evidence.
- Reject existing output files and unsafe or duplicate extraction filenames.
