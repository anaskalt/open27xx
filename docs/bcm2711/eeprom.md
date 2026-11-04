# SPI EEPROM image

`pieeprom-2026-10-30.bin` from raspberrypi/rpi-eeprom commit
`236b4406753e604fde3315cb521a2f843c9f8f85` is 524288 bytes, SHA-256
`6abfaea480f93da47a790f89751ed45d3af6e88ee8fb337d4eb62ad125ca3e8a`.
Offsets below refer to this file unless another sample is named.
`tools/eeprom.py` lists, extracts, verifies and rebuilds the image.

## Sections

Each section starts with an 8-byte header. The fields at `0x000000` are
magic `0x55AAF00F` and payload length 50930.

| Offset in section | Size (bytes) | Field |
|---|---|---|
| 0x00 | 4 | magic, big-endian |
| 0x04 | 4 | payload length, big-endian |
| 0x08 | length | payload |

The next section starts at the following 8-byte boundary. In this image,
alignment gaps and padding-section payloads contain `0xFF`. The end marker
at `0x06D768` and all remaining bytes through `0x07FFFF` are `0xFF`.

raspberrypi/rpi-eeprom `rpi-eeprom-config` at the pinned commit accepts
`0xFFFFFFFF` or `0x00000000` as an end marker. Its `BootloaderImage.parse`
uses `magic & 0xFFFFF00F == 0x55AAF00F` to recognize section headers.
Bits 4 through 11 identify the type.

| Magic | Type | Payload |
|---|---|---|
| 0x55AAF00F | bootcode | bootsys; see [bootsys.md](bootsys.md) |
| 0x55AAF11F | file | 12-byte name, 4 zero bytes, contents |
| 0x55AAF22F | plain | 16-byte name, contents |
| 0x55AAF33F | LZSS | 16-byte name, compressed contents, 32-byte SHA-256 of decompressed contents |
| 0x55AAF44F | LZ4 | 16-byte name, LZ4 frame, 32-byte SHA-256 of decompressed contents |
| 0x55AAFEEF | padding | `0xFF` bytes |

Names in the listed samples are ASCII and zero-padded. The pinned
`rpi-eeprom-config` rewrites type `0x11` file slots and reserves the final
4096 bytes when allocating replacement data. These are host-tool rules;
they do not establish device-side parsing behavior.

The older formats have these concrete examples:

| File | SHA-256 | Section offset | Contents |
|---|---|---|---|
| `pieeprom-2019-07-15.bin` | `21bacc1bbbeba42f6aab58656dc61dd402265d8a3e33d35aa8cd5d281d2a4c49` | 0x00AE68 | plain `memsys00.bin` |
| `pieeprom-2020-03-04.bin` | `f5058a8f6ff23fc87138c5e0a4ad9caf223438470bf48ee56beedaee44b9ce51` | 0x020000 | LZSS `memsys00.bin` |

Both files are in the pinned rpi-eeprom `firmware-2711/` tree.

## Compression

The LZSS rules below refer to `2711/bootcode4.bin` from raspberrypi/usbboot
commit `fdb604d018693465c9aa6ec69879df866d2820da`, SHA-256
`9e1b0b7df904a7fdc22e263d530c6e4c48921229631dd7ea2325271843996f6c`.
The scalar decoder starts at file offset `0x0F7E`, address `0x80000F7E`
under the provisional `0x80000000` mapping.

1. A flag byte describes up to eight items, least significant bit first.
2. A clear bit denotes one literal output byte.
3. A set bit denotes two bytes: distance minus one, then length minus one.
   Both distance and length range from 1 to 256.
4. The history contains 256 bytes. Its write position starts at zero and
   advances modulo 256 for every output byte.
5. Before emitting a reference, copy all its source bytes from the
   current history into a temporary buffer. For write position `p`,
   distance `d` and length `n`, source byte `i` comes from
   `(p - d + i) & 0xFF`, for `0 <= i < n`. This copy wraps at the end of
   the history and completes before any history update for that item.
6. Emit the temporary bytes in order, writing each to the history at the
   current write position. A literal updates the history in the same way.
7. Complete streams terminate at input exhaustion. An incomplete
   reference is an error; the cases below do not specify every possible
   trailing flag or truncated-item combination.

A reference therefore reads a snapshot of the ring. For example, after
literal bytes `0x00` through `0xFF`, a distance-1, length-8 reference emits
`FF 00 01 02 03 04 05 06`. The first emitted `0xFF` does not replace the
source bytes of the same reference.

The decoder at `0x80000F7E` does not initialize the supplied history. Its
SPI caller at file offset `0x9A70` passes two 256-byte stack areas for
history and temporary storage without clearing the history in that
routine. This does not establish the stack contents on entry. Output
that reads unwritten history depends on those prior contents.

A portable stream references only initialized history: every source slot
of a reference must have been written by earlier output before that
reference begins, including slots reached by wrapping. Testing only
`distance <= output length` is insufficient. After 256 output bytes,
all slots are initialized; before then, validity must cover the complete
source range. A decoder without an explicit initial-history input rejects
references to unwritten slots instead of assigning them zero values.

[lzss.json](../../tests/vectors/lzss.json) contains 26 synthetic cases
recorded from the decoder with an actual vendor output callback at
`0x8000A56C`. Each case includes the encoded bytes, supplied initial
history byte, observed decoded bytes and whether all references use
initialized history. The zero-filled and `0x5A`-filled probes distinguish
caller-dependent output from portable streams. The cases cover overlap,
ring wrap and a 256-byte reference. Their supplied history is a test
condition, not a boot-path guarantee.

The 120-image pinned catalog contains 1079 LZSS occurrences of `bootmain`,
`mcb.bin`, `memsys*.bin`, `logo.bin` and `font.bin`, with 94 distinct
encoded streams. None references unwritten history or uses a length
greater than its distance. Snapshot decoding reproduces every stored
SHA-256, including the `memsys00.bin` resource at `0x020000` in the
2020-03-04 sample above. Catalog digest checks alone cannot distinguish
the snapshot rule from a decoder that feeds newly emitted bytes back
into the same reference.

Type `0x44` sections in the 2026-10-30 image decode as LZ4 frames. For
example, the frame at `0x00C930` yields `bootmain`, whose digest is listed
in [vendor-files.md](vendor-files.md).

The host LZSS encoder chooses the longest snapshot match of 3 to 256
bytes within the 256-byte window. It considers only references whose
complete source range is initialized by prior output. Equal-length
matches select the smallest distance. Shorter matches become literals.
A match may have a length greater than its distance when the existing
ring snapshot contains the required bytes. It must not rely on bytes
that the same reference will emit. This produces deterministic output;
it does not reproduce the original compressed bytes. The host LZ4 encoder uses 65536-byte linked blocks,
compression level 9 and a stored content size, without frame or block
checksums. Both encoders append the SHA-256 of the decoded contents to
the section payload.

## Section map

Offsets identify section headers. Length includes the name and, for
compressed sections, the digest. Sizes are in bytes. Padding sections are
omitted; controller payloads are outside the CM4 scope and are not decoded.

| Offset | Type | Name | Length | Decoded size |
|---|---|---|---|---|
| 0x000000 | bootcode | `bootsys` | 50930 | 50930 |
| 0x00C918 | LZ4 | `bootmain` | 211955 | 267042 |
| 0x040518 | LZ4 | `memsys00.bin` | 12706 | 20492 |
| 0x0436C8 | LZ4 | `memsys01.bin` | 11237 | 20492 |
| 0x0462B8 | LZ4 | `memsys02.bin` | 10368 | 20492 |
| 0x048B40 | LZ4 | `memsys03.bin` | 9963 | 20492 |
| 0x04B238 | LZ4 | `memsys04.bin` | 11885 | 20492 |
| 0x04E0B0 | LZ4 | `memsys05.bin` | 11829 | 20492 |
| 0x050EF0 | LZ4 | `memsys06.bin` | 11026 | 20492 |
| 0x053A10 | LZ4 | `memsys07.bin` | 12103 | 20492 |
| 0x056960 | LZ4 | `memsys08.bin` | 10488 | 20492 |
| 0x059260 | LZ4 | `mcb.bin` | 1340 | 12384 |
| 0x0597A8 | LZSS | `vl805hub.bin` | 7028 | — |
| 0x05B328 | LZSS | `vl805mcu.bin` | 60451 | — |
| 0x069F58 | LZ4 | `logo.bin` | 2256 | 12844 |
| 0x06A830 | LZ4 | `font.bin` | 7422 | 27404 |
| 0x06C538 | file | `versioninfo` | 70 | 54 |
| 0x06C588 | file | `updatetime` | 24 | 8 |
| 0x06C600 | file | `pubkey.bin` | 528 | 512 |
| 0x06C900 | file | `cacert.der` | 2064 | 2048 |
| 0x06D200 | file | `bootconf.sig` | 1040 | 1024 |
| 0x06D700 | file | `bootconf.txt` | 95 | 79 |

## File contents

The offsets in this table identify the contents after the section header
and the 16-byte name area.

| Offset | File | Observation |
|---|---|---|
| 0x06C550 | `versioninfo` | 54 bytes, including a final zero byte; build date `2026/10/30 23:20:35`, identifier `13c4219f` |
| 0x06C5A0 | `updatetime` | little-endian words `0x00000000`, `0xFFFFFFFF` |
| 0x06C618 | `pubkey.bin` | 512 zero bytes |
| 0x06C918 | `cacert.der` | 2048 zero bytes |
| 0x06D218 | `bootconf.sig` | 1024 zero bytes |
| 0x06D718 | `bootconf.txt` | 79 bytes of configuration text |

The configuration at `0x06D718` contains `[all]` followed by `BOOT_UART=0`,
`WAKE_ON_GPIO=1`, `POWER_OFF_ON_HALT=0` and `NET_INSTALL_AT_POWER_ON=1`, each
on a separate line with a final newline. Their presence does not establish
how the bootloader interprets them.

## Host update timestamp

At the pinned rpi-eeprom commit, `rpi-eeprom-config`
`BootloaderImage.set_timestamp` writes a complemented 32-bit timestamp
followed by the timestamp, both little-endian. It first searches for
`updatetime` within the first 65536 bytes. If none exists there, it writes
the words into the last 8 bytes of the image.

For `pieeprom-2026-10-30.bin`, the section at `0x06C588` lies outside that
search range. The host method therefore selects `0x07FFF8` and `0x07FFFC`.

## Host tool

```sh
python3 tools/eeprom.py list image.bin
python3 tools/eeprom.py verify image.bin
python3 tools/eeprom.py extract image.bin contents
python3 tools/eeprom.py rebuild image.bin copy.bin
python3 tools/eeprom.py rebuild image.bin rebuilt.bin --recompress original
```

`rebuild` without `--recompress` preserves every byte: section headers,
names, payloads, alignment gaps, padding sections and the entire trailer.
It does not require the LZ4 package. `--recompress original` re-encodes each
compressed CM4 resource with its existing codec. `--recompress lzss` and
`--recompress lz4` select one codec for those resources. Sections whose
names start with `vl805` remain unchanged. Plain and file sections also
remain unchanged. Recompression checks each selected resource's original
digest before encoding, then stores a digest of the same decoded bytes.

Recompression uses this host allocation policy:

1. Preserve section order and padding sections. Align changed sections
   with `0xFF` bytes.
2. Keep the original image size. A shorter section chain adds `0xFF`
   bytes before the original trailer.
3. A longer chain consumes only the initial `0xFF` run of the trailer,
   leaving at least 8 `0xFF` bytes before any non-`0xFF` contents.
4. Preserve the final 4096 bytes and all non-`0xFF` trailer contents at
   their original offsets. Reject an image that cannot fit.

These are host-tool rules. Recompression does not establish device support
for a different codec or layout. Verification checks the bootsys footer
length and compressed-section SHA-256 values; it does not validate
signatures or establish that an image boots.

Output files must not exist. Extraction rejects duplicate filenames and
names containing path separators, and checks all destination names before
writing any files. Rebuilding the input file in place is rejected, including
through a hard link or symbolic link. Format and capacity errors are
reported before a rebuilt output is created.

The Python API exposes the same format operations:

```python
from tools.eeprom import Image, LZSS, Section

image = Image.parse(raw_image)
assert image.serialize() == raw_image
packed = Section.from_data(LZSS, b"example contents", name="example.bin")
assert packed.data() == b"example contents"
rebuilt = image.recompress("original").serialize()
```

`Section.with_data(data, kind=None)` encodes decoded contents using the
existing type unless another type is supplied. It preserves the raw name
area when the source and destination use the same name layout. Conversion
between the 12-byte file name layout and the 16-byte layout validates and
re-encodes the name. Section codecs accept arbitrary byte contents.
`Image.recompress()` returns a new image or raises `FormatError` if a
digest, codec choice or capacity check fails.

## Open questions

- Timestamp selection on the device. Trace the references to `updatetime`
  and the end-of-image timestamp, then compare their precedence in
  emulation with distinct timestamp values.
- Decoder edge cases. Extend the synthetic cases for truncated items and
  trailing flag bits before specifying all malformed-input behavior.
  The decoder's initial history depends on caller memory; trace earlier
  stack use before assigning an initial fill to a particular boot path.
- Signature and key slots. Determine the firmware's accepted lengths and
  parsing rules for the slots at `0x06C600` and `0x06D200` using synthetic
  input in emulation; the zero-filled published slots cannot establish
  those rules.
