<!-- SPDX-FileCopyrightText: 2026 The open27xx Authors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# BCM2711 clock registers

CPRMAN has legacy-bus base address 0x7E101000 and a register span of
8192 bytes in Linux v6.12. The BCM2711 device tree selects
`brcm,bcm2711-cprman`. The clock driver registers PLLB and its ARM channel
for both BCM2835 and BCM2711 through `SOC_ALL`.
See [the base declaration][base], [the BCM2711 compatible][compatible]
and [the PLLB descriptors][pllb] with [their SoC mask][soc-mask].

Addresses below use the legacy master view defined in *BCM2711 ARM
Peripherals*, release 4, section 1.2.4, page 6. The tables follow the
driver's BCM2711 register selection. A complete BCM2711 startup sequence
and initial clock state remain open questions.

## Register map

Offsets are relative to 0x7E101000. Names and offsets come from
Linux `drivers/clk/bcm/clk-bcm2835.c`,
[lines 147–220][registers] and [lines 248–287][channels].
Its [debug register labels][analog-labels] identify the four analog words
at consecutive 4-byte offsets from `A2W_PLLB_ANA0`.

| Offset | Legacy-bus address | Register |
|---|---|---|
| 0x100 | 0x7E101100 | `CM_OSCCOUNT` |
| 0x114 | 0x7E101114 | `CM_LOCK` |
| 0x170 | 0x7E101170 | `CM_PLLB` |
| 0x10F0 | 0x7E1020F0 | `A2W_PLLB_ANA0` |
| 0x10F4 | 0x7E1020F4 | PLLB ANA1 |
| 0x10F8 | 0x7E1020F8 | PLLB ANA2 |
| 0x10FC | 0x7E1020FC | PLLB ANA3 |
| 0x11E0 | 0x7E1021E0 | `A2W_PLLB_CTRL` |
| 0x12E0 | 0x7E1022E0 | `A2W_PLLB_FRAC` |
| 0x13E0 | 0x7E1023E0 | `A2W_PLLB_ARM` |

`A2W_PLLB_FRAC` controls the PLL fractional value. `A2W_PLLB_ARM` controls
the ARM output divider. Their offsets differ by 0x100.

## Fields

The [control definitions][registers] and [channel definitions][channels]
provide these masks. Unlisted bits have no assigned meaning here.

| Register | Bits | Field |
|---|---|---|
| `CM_PLLB` | 0 | `LOADARM` |
| `CM_PLLB` | 1 | `HOLDARM` |
| `CM_PLLB` | 8 | Shared `CM_PLL_ANARST` analog-reset mask |
| `CM_LOCK` | 9 | `FLOCKB`, the PLLB lock mask |
| `A2W_PLLB_CTRL` | 9:0 | `NDIV` |
| `A2W_PLLB_CTRL` | 14:12 | `PDIV` |
| `A2W_PLLB_CTRL` | 16 | `PWRDN` |
| `A2W_PLLB_CTRL` | 17 | `PRST_DISABLE` |
| `A2W_PLLB_FRAC` | 19:0 | Fractional value |
| `A2W_PLLB_ARM` | 7:0 | ARM channel divider |
| `A2W_PLLB_ARM` | 8 | Channel disable |

The ARM channel divider encodes 1 through 255 directly and 256 as zero.
The driver sets the divider and pulses `LOADARM`. It sets `HOLDARM` when
disabling the channel and clears it when enabling the channel. These are
the operations in [lines 802–875][divider-ops]. The PLLB descriptor
selects those masks explicitly. The shared PLL enable function clears
`CM_PLL_ANARST` and polls `CM_LOCK` with the selected `FLOCKB` mask
([lines 628–659][pll-enable]).

Bit 9 of `CM_LOCK` is separate from bit 9 of `A2W_PLLB_CTRL`, which belongs
to `NDIV`. The cited definitions do not assign a bit 9 field to `CM_PLLB`.

## Writes and oscillator count

The driver defines [`CM_PASSWORD`][password] as 0x5A000000 and ORs it into values
written through [`cprman_write`][write]. The BCM2711 manual independently
specifies a 0x5A password in bits 31:24 of its documented general-purpose
clock control and divider registers, section 5.4.2, tables 99–100,
pages 82–84.

[`bcm2835_measure_tcnt_mux`][measure] writes a count to `CM_OSCCOUNT` and
waits for that register to reach zero during clock measurement. It defines
no independent status fields at bits 0, 1 or 9 of `CM_OSCCOUNT`.

## Analog controls

The driver explicitly distinguishes BCM2711 from earlier hardware:
PLLA, PLLB, PLLC and PLLD lack the earlier feedback pre-divider, and
ANA1 bits 14:13 serve as VCO range bits
([lines 533–544][analog-range]). For PLLB, this field belongs to
0x7E1020F4.

## Source identities

All Linux links use `torvalds/linux` v6.12, commit
`adc218676eef25575469234709c2d87185ca223a`.

| Source | SHA-256 |
|---|---|
| [`drivers/clk/bcm/clk-bcm2835.c`][registers] | `d184f016cfc3b0416bb8b8cd752d4225f8d2e6635062c01d296a63ab7b853747` |
| [`arch/arm/boot/dts/broadcom/bcm283x.dtsi`][base] | `999bc1a10e79136b30e1f87633ba4eb2eb9e5d2b79edece0b6d5133625167447` |
| [`arch/arm/boot/dts/broadcom/bcm2711.dtsi`][compatible] | `cc411d0132e487490315e24c289b1ae2352880a04040b8f11b372a74be18c3bc` |
| [BCM2711 ARM Peripherals][manual], release 4, build 2022-01-18, `cfcff44-clean` | `d6e16ea089a1716e80621f99a26e130a2379f0a81d945dc22e4f80dc49dcdc78` |

## Open questions

- Initial state and startup sequence. Establish BCM2711 clock/reset
  prerequisites, retained register values and required ordering before
  composing these fields into an ARM release operation.
- Analog range values. Obtain a BCM2711-specific range encoding and
  operating constraints before selecting ANA1 bits 14:13.
- Oscillator-count timing. Establish the BCM2711 count rate and completion
  conditions before assigning a time interval to an OSCCOUNT value.
- Other analog blocks. The driver names offset 0x1070 `A2W_PLLH_ANA0`,
  but [its PLLH descriptor][pllh] is restricted to `SOC_BCM2835`.
  Establish a BCM2711-specific definition before naming addresses
  0x7E102070–0x7E10207C or applying PLLH fields to them.

[base]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm/boot/dts/broadcom/bcm283x.dtsi#L86-L89
[compatible]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/arch/arm/boot/dts/broadcom/bcm2711.dtsi#L638-L640
[registers]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L147-L220
[channels]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L248-L287
[pllb]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L1729-L1755
[soc-mask]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L295-L297
[analog-labels]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L768-L775
[divider-ops]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L802-L875
[pll-enable]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L628-L659
[write]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L335-L338
[password]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L40
[measure]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L345-L377
[analog-range]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L533-L544
[pllh]: https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/clk/bcm/clk-bcm2835.c#L1890-L1904
[manual]: https://datasheets.raspberrypi.org/bcm2711/bcm2711-peripherals.pdf
