# VideoCore scalar calling convention

The observations below apply to these pinned files. Addresses are VPU
addresses, not file offsets. The raw-file addresses use the provisional
`0x80000000` analysis base described in [analysis.md](../analysis.md).

| File | Source version | SHA-256 |
|---|---|---|
| `bootmain` | usbboot `fdb604d018693465c9aa6ec69879df866d2820da` | `4deaac8f1e266a626bb422fd7d17bb69c98cb39be2e7db5e566cae68a8e17e4d` |
| `bootcode4.bin` | usbboot `fdb604d018693465c9aa6ec69879df866d2820da` | `9e1b0b7df904a7fdc22e263d530c6e4c48921229631dd7ea2325271843996f6c` |
| `recovery.bin` | rpi-eeprom `236b4406753e604fde3315cb521a2f843c9f8f85` | `d2496ef5dd106f250197f1cdf9fc2eecda90acdc0fc420a63b20940c06130ce1` |
| `start4.elf` | firmware `ab5c7f86283ceb58b7adb269cae1d16092a31bf6` | `38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb` |

The pinned `bootmain` at file offset `0x040D22` and `start4.elf` at file
offset `0x231B98` contain `MetaWare Linker v5.6.19`. This identifies the
linker. The observations below establish selected scalar call behavior;
they do not specify every MetaWare ABI rule.

## Arguments and results

The following examples refer to the pinned `bootmain` above.

| Property | Observation | Example addresses |
|---|---|---|
| Scalar register arguments | The first six 32-bit argument words use `r0` through `r5`, in order | Six-argument wrapper `0x000AB04C`; variadic wrappers `0x000A8544` and `0x000A8AF0` |
| Scalar stack arguments | The seventh and eighth words occupy entry `sp` and entry `sp + 4` | Caller stores at `0x000AB08C` and `0x000AB092`; callee loads at `0x0009C100` and `0x0009C110` after a 28-byte save area |
| Scalar result | `r0` carries a pointer or 32-bit status | Copy `0x0009F42C`, fill `0x0009F5C0`, hash start `0x0009C312` |
| Stack direction | Register saves and local storage reduce `sp`; return restores the entry value | Copy `0x0009F42C`–`0x0009F478`; compression `0x00098590`–`0x00098E76` |
| Saved working registers | The compression routine saves and restores `r6` through `r20`; the formatter saves and restores `r6` through `r19` | Compression `0x00098590`; formatter `0x000A9558` |
| Link register | A nested call can replace `lr`; return can restore `pc` directly from the saved return address | Hash finish `0x0009C1C8` returns at `0x0009C2F2` |

In the pinned `bootmain`, emulated calls to `0x0009F42C` and `0x0009F5C0`
return the destination in `r0` and restore `sp`. The tests cover lengths
0, 1, 2, 3, 4, 7, 8, 9, 15, 16, 31 and 64 with destination alignments 0
through 3; copy also covers every source alignment. Registers `r6` through
`r23` and `gp` retain their entry values in these tests.

For the pinned `bootmain`, hash start `0x0009C312`, update `0x0009C3DA` and
finish `0x0009C1C8` produce the same SHA-256 digests as an independent host
implementation for 12 message lengths from 0 through 1024 bytes. The
finish call restores `sp`, `r6` through `r23`, and `gp`. It returns to the
supplied address with `lr = 0x0009BEFE`, the return address of a nested
call. Physical `lr` preservation is therefore not a caller guarantee.

## Variadic arguments

For the pinned `bootmain`, let `S` be `sp` on entry. The wrappers below
store remaining register arguments immediately before the stack arguments.
Each slot is 4 bytes. A pointer to the first slot forms the argument list.

| Wrapper | Fixed arguments | Register save locations | Argument-list consumer |
|---|---|---|---|
| Printf-like `0x000A8544` | `r0`: format | `r1` at `S - 20`, then `r2` through `r5` at successive words through `S - 4` | `0x000A9522`, list in `r1` |
| Bounded formatting `0x000A8AF0` | `r0`: destination; `r1`: capacity; `r2`: format | `r3` at `S - 12`, `r4` at `S - 8`, `r5` at `S - 4` | `0x000A953C`, list in `r3` |

The first argument beyond `r5` remains at `S` in both pinned `bootmain`
wrappers. An emulated call to `0x000A8AF0` with a 128-byte destination,
three variadic register words and two stack words formats unsigned
integers, hexadecimal, a string and a signed integer correctly. This
checks argument order across the register/stack boundary. It does not
establish complete C-library formatting semantics.

## Library entry points

Names below describe identified behavior, not recovered symbol names.
Each row refers to the pinned file in the identity table.

| File | Copy | Fill | Evidence |
|---|---|---|---|
| `bootmain` | `0x0009F42C` | `0x0009F5C0` | 240 scalar emulation cases |
| `bootcode4.bin` | `0x80004DD2` | `0x80004E20` | 240 scalar emulation cases |
| `recovery.bin` | `0x80009324` | `0x800093B2` | 240 scalar emulation cases |
| `start4.elf` | `0x0ED1FC8A` | `0x0ED1FE14` | 240 scalar emulation cases |

For these pinned files and addresses, copy takes destination, source and
length in `r0`, `r1` and `r2`. Fill takes destination, byte value and length
in those registers. Both return the destination. The tested nonoverlapping
copy and fill behavior matches `memcpy` and `memset`.

The pinned `bootmain` has these cryptographic entry points:

| Address | Identified role | Evidence |
|---|---|---|
| `0x0009C312` | SHA-256/SHA-224 state initialization | Eight initial state words; variant in `r1`; context variant field at offset `0x68` |
| `0x00098590` | SHA-256 compression | 64-round computation; round table at `0x000BD954`; used by update and finish |
| `0x0009C3DA` | SHA-256 update | Context, input pointer and length in `r0`–`r2`; host digest comparison |
| `0x0009C1C8` | SHA-256 finish | Padding and big-endian digest output; host digest comparison |
| `0x0009C0B2` | RSA PKCS#1 v1.5 verification | Eight-argument API, encoded-message construction, public operation and comparison |
| `0x0009C040` | RSA public operation | Integer import, comparison with the modulus, modular exponentiation and integer export |
| `0x000AB0A8` | PKCS#1 v1.5 SHA-256 encoding | `0x00 0x01` prefix, `0xFF` padding, separator, 19-byte DigestInfo prefix and 32-byte digest |

The pinned `bootmain` verifier at `0x0009C0B2` matches the structure of
Mbed TLS `mbedtls_rsa_rsassa_pkcs1_v15_verify` in
[Mbed-TLS/mbedtls `library/rsa.c`](https://github.com/Mbed-TLS/mbedtls/blob/2fc8413bfcb51354c8e679141b17b3f1a5942561/library/rsa.c).
It requests two temporary buffers of the modulus length, constructs the
expected encoding, applies the public operation, compares the buffers,
and clears and releases them. Its bad-input and verification-failure
results are `-0x4080` and `-0x4380`, matching the Mbed TLS definitions in
[`include/mbedtls/rsa.h`](https://github.com/Mbed-TLS/mbedtls/blob/2fc8413bfcb51354c8e679141b17b3f1a5942561/include/mbedtls/rsa.h).
The firmware specializes this path to digest identifier 6 and digest
length 32. These API, control-flow and error-value matches identify the
Mbed TLS family; the reference release does not identify the firmware's
library version.

In the pinned `bootmain`, formatter wrappers `0x000A8544`, `0x000A9522`,
`0x000A8AF0` and `0x000A953C` converge on `0x000A9558`, which interprets
format conversions and calls an output callback. Their identified roles
are printf-like, vprintf-like, bounded variadic formatting and bounded
argument-list formatting, respectively.

## Ghidra specification

The installed VideoCoreIV specification derives from
[aleph-void/ghidra-videocore4 `data/languages/vc4.cspec`](https://github.com/aleph-void/ghidra-videocore4/blob/db09a308c2db6a31ba5e060e6b763713f77e4f7b/data/languages/vc4.cspec).
Its default prototype provides six scalar argument registers, stack
arguments from offset 0, a downward-growing stack and a result in `r0`.
These settings agree with the pinned `bootmain` examples above. The
specification remains unchanged. Its declaration of `lr` as unaffected
must not be interpreted as physical preservation by vendor callees.

## Open questions

- Complete preserved-register set. The pinned `bootmain` routines at
  `0x00098590` and `0x000A9558` establish their own saves, not every
  function's contract. Check functions that modify the higher scalar
  registers, special registers and `gp` before defining a complete ABI.
- Wide and aggregate values. Check paired-register arguments and results,
  structure returns, floating-point values and mixed-width variadic calls
  in the pinned files. The scalar-word examples do not establish their
  alignment or placement rules.
- Link-register modeling. Compare decompiler data flow around the pinned
  `bootmain` call and return sequence at `0x0009C1C8` with the observed
  `lr` clobber. Add a separate compiler prototype if the existing
  unaffected declaration propagates an incorrect value across a call.
- Mbed TLS version and stage coverage. Compare additional functions with
  pinned upstream releases before assigning a version. Establish RSA and
  Mbed TLS identities independently in `bootcode4.bin`, `recovery.bin`
  and `start4.elf`; identification in `bootmain` does not prove that every
  other stage includes the same library or configuration.
