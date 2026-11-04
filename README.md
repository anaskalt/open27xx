# open27xx

Open-source boot firmware for Broadcom BCM27xx SoCs.

Before any ARM core runs, the BCM2711 and BCM2712 execute a chain of closed firmware stages on the VideoCore VPU. open27xx documents these stages and develops open replacements, verified against the vendor firmware.

The first target is the BCM2711 on the Compute Module 4. The BCM2712 follows.

## Status

Early development. Nothing here is ready for production use.

| Component | State |
|---|---|
| EEPROM image tool | lists, extracts, verifies and rebuilds BCM2711 images |
| Headless firmware analysis | repeatable imports and metadata exports |
| Documentation of the BCM2711 boot chain | scalar boot flow and emulator vectors |
| Open `start4.elf` | host build for VPU bring-up; ARM/Linux handoff unimplemented |
| bootmain, bootsys, SDRAM initialization | analysis |

## Getting started

Requirements: a POSIX shell, tar, git 2.35 or later and Python 3.9 or later.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r tools/requirements.txt
scripts/fetch-blobs.sh
python3 tools/eeprom.py list blobs/bcm2711/pieeprom-2026-10-30.bin
python3 -m unittest
```

`scripts/fetch-blobs.sh` downloads the vendor firmware used for analysis and tests into `blobs/` and checks it against `scripts/blobs.sha256`.

## Documentation

- [Architecture](docs/architecture.md): boot chain, replacement plan, code map
- [Headless analysis](docs/analysis.md): imports, memory maps and repeatability
- [BCM2711](docs/bcm2711/): [EEPROM image](docs/bcm2711/eeprom.md), [bootsys](docs/bcm2711/bootsys.md), [bootmain](docs/bcm2711/bootmain.md), [calling convention](docs/bcm2711/abi.md), [SDRAM](docs/bcm2711/sdram.md), [start4.elf](docs/bcm2711/start4.md), [USB boot](docs/bcm2711/usbboot.md), [vendor files](docs/bcm2711/vendor-files.md)
- [References](docs/references.md)
- [VPU build](src/start4/README.md): pinned dependencies, host checks and remaining runtime work

## Vendor firmware

This repository contains no vendor firmware and no code derived from it. The vendor files are fetched from their upstream repositories at pinned commits and stay outside version control.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security issues as described in [SECURITY.md](SECURITY.md).

## License

Code is licensed under GPL-2.0-or-later, documentation under CC-BY-4.0, and configuration files under CC0-1.0. Every file states its license with an SPDX identifier or through [REUSE.toml](REUSE.toml); the license texts are in [LICENSES/](LICENSES/).

Raspberry Pi is a trademark of Raspberry Pi Ltd. Broadcom and VideoCore are trademarks of Broadcom Inc. open27xx is not affiliated with or endorsed by either company.
