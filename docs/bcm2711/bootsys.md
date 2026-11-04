# bootsys

bootsys is the first EEPROM stage in raspberrypi/usbboot
`docs/secure-boot-chain-of-trust-2711.pdf`, page 1, at commit
`fdb604d018693465c9aa6ec69879df866d2820da`. The diagram describes the
secure-boot chain; it does not establish the behavior of every boot mode.

All binary offsets below refer to `2711/bootcode4.bin` from that commit's
`firmware/bootfiles.bin`: 50930 bytes, SHA-256
`9e1b0b7df904a7fdc22e263d530c6e4c48921229631dd7ea2325271843996f6c`.
These bytes equal the first section payload at EEPROM offset `0x000008` in
`pieeprom-2026-10-30.bin`, identified in [vendor-files.md](vendor-files.md).
Code addresses below use the provisional `0x80000000` analysis mapping;
subtract that base to obtain file offsets. Behavior and vectors refer to
this pinned `bootcode4.bin` unless another file is named.

## Layout

| Offset | Size (bytes) | Contents |
|---|---|---|
| 0x0000 | 512 | zero bytes |
| 0x0200 | 50134 | body, including the digests below |
| 0xC5D6 | 284 | footer |

## Resource digests

Each location contains the 32-byte SHA-256 of the named decompressed section
of `pieeprom-2026-10-30.bin`. The digest also equals the final 32 bytes of
that compressed section. Section locations are in [eeprom.md](eeprom.md).

| Offset in bootsys | Resource |
|---|---|
| 0xB8C0 | `logo.bin` |
| 0xB8E0 | `font.bin` |
| 0xB900 | `mcb.bin` |
| 0xB920 | `memsys00.bin` |
| 0xB940 | `memsys01.bin` |
| 0xB960 | `memsys02.bin` |
| 0xB980 | `memsys03.bin` |
| 0xB9A0 | `memsys04.bin` |
| 0xB9C0 | `memsys05.bin` |
| 0xB9E0 | `memsys06.bin` |
| 0xBA00 | `memsys07.bin` |
| 0xBA20 | `memsys08.bin` |
| 0xBBA8 | `bootmain` |

The SDRAM dispatcher at `0x80006FE8` passes the MCB digest at `0x8000B900`
and the successive memsys digests at `0x8000B920`–`0x8000BA20` to the
resource wrapper at `0x80007384`. The bootmain path at `0x8000972C` passes
`0x8000BBA8` to that wrapper.

## Resource lookup

The wrapper at `0x80007384` takes a name, an optional digest-output pointer,
an optional expected-digest pointer, a buffer-pointer list and a transfer
flag in `r0` through `r4`. A zero-terminated list identifies destination
buffers. Each buffer descriptor has this layout, established by
`0x800014C4`, `0x80001466` and the payload loader at `0x80009FE4`:

| Descriptor offset | Size (bytes) | Field |
|---|---|---|
| 0x00 | 4 | marker `0x42554646` |
| 0x04 | 4 | data address |
| 0x08 | 4 | used length |
| 0x0C | 4 | capacity |
| 0x10 | 4 | additional state, initialized to zero |

For a backend selector other than 7 at `gp + 0x33C`, the wrapper calls
`0x80009CA0` to locate an EEPROM section and `0x80009FE4` to load it.
Lookup takes a name in `r0` and a 32-byte result area in `r1`. It returns
0 for a match, `0xFFFFFFFE` for a null or empty argument, and
`0xFFFFFFFF` for the tested missing-name, invalid-header and read-error
cases. The section-header format is in [eeprom.md](eeprom.md).

At `0x80009CA0`, lookup starts at EEPROM offset zero and reads 24 bytes per
candidate. It requires `magic & 0xFFFFF00F == 0x55AAF00F` and a payload
length with its top byte clear. It compares a terminated copy of at most
15 name bytes and advances to the next 8-byte section boundary when a
candidate does not match. The recognized named types populate these
result fields:

| Result offset | Size (bytes) | Field |
|---|---|---|
| 0x00 | 4 | section magic, little-endian |
| 0x04 | 4 | section payload length, little-endian |
| 0x08 | 16 | terminated resource name |
| 0x18 | 4 | reported transfer length |
| 0x1C | 4 | EEPROM contents address, section offset plus 24 |

| Magic | Reported transfer length |
|---|---|
| 0x55AAF11F | payload length minus 16 |
| 0x55AAF22F | payload length minus 36 |
| 0x55AAF33F | payload length minus 48 |
| 0x55AAF44F | payload length minus 48 |

The thirteen cases in
[resource-lookup.json](../../tests/vectors/bootsys/resource-lookup.json)
execute this parser with synthetic SPI header responses. They cover each
named type, skipping a nonmatching or unknown type, malformed headers,
missing names and missing arguments. SPI setup, reads and cleanup are
explicit substituted call boundaries.

## Transfer and digest checks

The payload loader at `0x80009FE4` receives the lookup result, destination
list, contents-relative offset, transfer length, digest-output pointer,
expected-digest pointer and transfer flag. The seventh argument is on the
stack. It sums the unused destination capacities before calling the
transfer routine at `0x8000A0F4`.

| Section magic | Transfer mode passed to 0x8000A0F4 |
|---|---|
| 0x55AAF33F | 1, LZSS |
| 0x55AAF44F | 2, LZ4 |
| other | 0, direct transfer |

After a successful transfer, `0x80009FE4` requests SHA-256 when either
digest pointer is nonzero. The helper at `0x8000658A` hashes each buffer's
used bytes in list order. It writes the watchdog value `0x5A0FFFFF` to
`0x7E100024` while processing data. A supplied expected digest takes
precedence over the compressed resource's stored digest. Without a
supplied expectation, the LZSS and LZ4 paths read 32 digest bytes after
the requested encoded contents. A direct transfer with only a
digest-output pointer computes and returns the digest without comparing
it.

| Result from 0x80009FE4 | Observed condition |
|---|---|
| 0 | successful tested transfer and any requested comparison |
| 1 | total unused capacity is less than the requested transfer length |
| 3 | substituted transfer returns 3; the status passes through |
| 4 | computed and expected digests differ |

On a digest mismatch, `0x80009FE4` clears every destination buffer's used
bytes and retains the used-length fields. The digest-output area still
contains the computed digest. The wrapper at `0x80007384` converts a
nonzero payload-loader result to `0xFFFFFFFF`.

[resource-digest.json](../../tests/vectors/bootsys/resource-digest.json)
records eleven cases with one or two destination buffers, supplied and
stored digests, capacity rejection, transfer failure and mismatch
clearing. The transfer boundary supplies synthetic bytes; SHA-256,
comparison, clearing and status handling execute in the vendor code.
[sha256.json](../../tests/vectors/bootsys/sha256.json) exercises the
one-shot scalar hash at `0x80004AD6` for eight input lengths spanning the
padding and block boundaries. The digests agree with a separate host
SHA-256 calculation.

For selector 7 at `gp + 0x33C`, `0x80007384` uses the cached backend handle
at `gp + 0x104`. It obtains a size through `0x8000AB9E` and reads through
`0x8000ABF8`. It rejects a nonpositive size, insufficient capacity and a
negative read result. After reading, it computes the digest and performs
the requested comparison. This wrapper returns `0xFFFFFFFF` on a digest
mismatch and leaves the received bytes in place. These decisions are
captured in
[alternate-resource.json](../../tests/vectors/bootsys/alternate-resource.json)
with literal backend responses; the backend transport is not emulated.

## Scalar decompression

The SPI transfer path at `0x80009A70` selects the LZSS entry at
`0x80000F7E` or the LZ4 entry at `0x8000109C`. Their input and output are
callbacks. [decompression.json](../../tests/vectors/bootsys/decompression.json)
executes thirteen synthetic literal, reference and error cases through these
decoders. The output callback at `0x8000A56C` writes into the destination
descriptors and advances their used lengths.

The LZSS cases include a complete 256-byte literal history, references
that wrap around that history, and different supplied initial fills.
References read the ring before updating it for that item. With a full
literal history `0x00` through `0xFF`, distance 1 and length 8 produce
`FF 00 01 02 03 04 05 06` for either initial fill. The format and portable
encoder contract are in [eeprom.md](eeprom.md).

The cases at `0x8000109C` cover an uncompressed LZ4 block, a compressed
literal block and invalid magic. They do not establish all LZ4 options,
back-reference boundaries or malformed-stream behavior. The failure
callback is substituted in error cases, so its device-level effect is
outside the observed result.

## Footer

The field boundaries follow librerpi/rpi-tools `signing-tool/docs.txt` at
commit `a700385d9b1c2f93d755d4455792ce7b08f90ede`. The first two fields are
checked directly in `bootcode4.bin`; the cryptographic interpretation is
from that source.

| Offset in bootsys | Size (bytes) | Field |
|---|---|---|
| 0xC5D6 | 4 | body length, little-endian: 50646 |
| 0xC5DA | 4 | key index, little-endian: 1 |
| 0xC5DE | 256 | RSA signature field |
| 0xC6DE | 20 | legacy checksum field |

The body length equals the file size minus 284. The matching footer
boundaries in `recovery.bin` are listed in [usbboot.md](usbboot.md).

## Documented role

The pinned usbboot chain-of-trust diagram assigns these operations to
bootsys: checking the customer public-key digest, verifying the EEPROM
configuration, and loading bootmain and resources while checking embedded
hashes. The resource operations above have scalar execution evidence.
That evidence does not establish signature policy or ROM footer
acceptance.

## Open questions

- Load address and entry point. The 512 zero bytes at `0x0000` do not
  establish either. Resolve the absolute references in the body starting
  at `0x0200`, then validate a candidate memory map in emulation.
- Footer checks with secure boot disabled. Obtain a vendor specification
  for the relevant ROM revision. The secure-boot diagram alone does not
  determine which footer fields the ROM checks in that mode.
- Plain-section trailer. The lookup at `0x80009CA0` subtracts 36 bytes
  from a `0x55AAF22F` payload. Trace consumption of the additional
  20 bytes in a historical plain resource before assigning their role.
- Full transport and decoder behavior. Reproduce SPI/device timing and
  the selector-7 backend independently. Extend scalar decoder vectors
  across all supported options and window boundaries before treating
  these observations as a complete malformed-input specification.
- LZSS caller prehistory. Neither `0x80000F7E` nor its SPI caller at
  `0x80009A70` clears the supplied history. Trace earlier stack use before
  assigning initial bytes to a particular boot path. The vectors declare
  their initial bytes explicitly.
- Signature policy. Trace configuration and resource-signature callers
  separately; successful digest checks do not establish when a signature
  is required.
