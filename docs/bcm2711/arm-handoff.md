# ARM stub metadata

The metadata behavior below applies to `start4.elf` from
raspberrypi/firmware commit `ab5c7f86283ceb58b7adb269cae1d16092a31bf6`,
SHA-256 `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb`.
The observed block starts at VPU address 0x0ED14B8A inside loader
0x0ED14134 and stops before 0x0ED14BB6.

This contract prepares data in an ARM stub buffer. It does not establish
where the buffer maps in ARM memory, how caches become coherent, how
reset is released, or whether the ARM executes the stub.

## Buffer layout

Offsets are relative to the beginning of the stub. Metadata words are
unsigned 32-bit little-endian values. The buffer must contain at least
256 bytes; the metadata occupies its 16 bytes at offsets 0xF0–0xFF.
Bytes before 0xF0 and after 0xFF remain unchanged by this operation.

| Offset | Size (bytes) | Before preparation | After a matching header |
|---|---:|---|---|
| 0x00 | 240 | Opaque stub contents | Unchanged |
| 0xF0 | 4 | Magic 0x5AFE570B | Zero |
| 0xF4 | 4 | Stub version | Zero |
| 0xF8 | 4 | Initial DTB field | Supplied DTB value when present, otherwise zero |
| 0xFC | 4 | Initial kernel field | Supplied kernel value when loading succeeds, otherwise zero |
| 0x100 | Remaining buffer length minus 256 | Opaque remaining contents | Unchanged |

The pinned block at 0x0ED14B8A checks only the magic at 0xF0. A different
magic leaves the buffer unchanged. A matching magic clears both the magic
and version words, including a nonzero initial version. It does not
validate the initial version or the supplied DTB/kernel values.

The pinned BSD-3-Clause source
[raspberrypi/tools `armstubs/armstub8.S`](https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/armstub8.S)
defines the same fields. Its primary-core path reads the DTB and kernel
words at 0xF8 and 0xFC. The 8 bytes at 0xF0 also serve as the core 3
spin slot after firmware clears them. Its
[`armstubs/Makefile`](https://github.com/raspberrypi/tools/blob/439b6198a9b340de5998dd14a26a0d9d38a6bcac/armstubs/Makefile)
builds the BCM2711/GIC variant with `BCM2711=1` and `GIC=1`.
These source definitions do not prove a VPU-to-ARM handoff.

## Preparation inputs

A caller supplies a writable stub buffer and its byte length, a 32-bit
DTB value, a DTB-presence flag, a 32-bit kernel value and a kernel-load
result. These address values are already selected by the caller; this
operation neither translates nor dereferences them.

For the pinned block at 0x0ED14B8A:

1. If the magic differs from 0x5AFE570B, preserve every buffer byte.
2. Otherwise, clear the words at 0xF0 and 0xF4.
3. Write the DTB value at 0xF8 when the presence flag is nonzero; write
   zero when the flag is zero.
4. Write the kernel value at 0xFC when the load result is zero; write
   zero for a nonzero result.

A host helper must reject a null buffer or a length below 256 bytes before
reading or writing any byte, and leave rejected buffers unchanged. These
are host-side validity requirements; the vendor block has no buffer-length
argument or bounds check. Use the stated little-endian representation
independently of host endianness or pointer alignment. Input values must
fit in 32 bits; wider addresses require a separate format contract.
A missing magic is an unchanged-buffer result, not a successful preparation.
No filename, board RAM size, boot medium or kernel-version constant is
required by this operation.

## Recorded cases

[armstub-metadata.json](../../tests/vectors/start4/armstub-metadata.json)
contains five synthetic executions of the pinned block, independently
reproduced with 55 scalar instructions total. They execute no file loader,
ARM instructions, MMIO, reset or cache operation.

| Case | DTB present | Kernel result | Output DTB | Output kernel |
|---|---:|---|---|---|
| Matching magic | 1 | 0 | 0x00123400 | 0x00200000 |
| No DTB | 0 | 0 | 0 | 0x00200000 |
| Kernel error | 1 | 0xFFFFFFFF | 0x00123400 | 0 |
| Neither input available | 0 | 0xFFFFFFFF | 0 | 0 |
| Different magic | 1 | 0 | Initial field unchanged | Initial field unchanged |

The fixture represents only the metadata span at synthetic address
0x240000F0. For a host test, place that span at offset 0xF0 in a buffer
of at least 256 bytes and compare the expected span at the same offset.
Fill the other bytes with guards and require them to remain unchanged.
The presence flag is the little-endian word at offset 0x2C of the fixture's
stack region at 0x24010000; the kernel result is its word at 0x28.
The supplied DTB and kernel values are `r6` and `r7`. The execution setup
uses `r15=0` and `r17=buffer+0xC0`; these are block-entry conditions,
not an application calling convention. Host tests need only these
synthetic inputs and expected bytes, not a vendor file or emulator.

## Open questions

- ARM placement and visibility. Trace the loader's buffer-address
  translation, mapping service and cache operations before treating the
  supplied values as verified ARM physical addresses.
- Reset and entry. Resolve the BCM2711 reset/clock acknowledgments and
  initial core state, then verify an approved hardware boot before
  defining a complete ARM launch sequence.
- Other stub formats. Check another format's source and vendor consumer
  before extending the 32-bit fields or applying this contract to it.
