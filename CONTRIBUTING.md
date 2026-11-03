# Contributing

open27xx reimplements closed firmware. Its value depends on a clean provenance for every line of code, so all contributions follow the rules below.

## Rules

- Do not commit vendor firmware, files extracted from it, disassembly, decompiler output or disassembler project files.
- Describe vendor firmware in your own words: behavior, data formats, register sequences. Offsets, addresses, sizes, digests and short identifiers such as configuration keys are facts and may be cited. Code from the vendor firmware may not.
- Write implementations from the documentation in `docs/` and from open-source code under a compatible license. Do not study the vendor binary of the component you implement.
- Name the file and version of every vendor file you describe. `scripts/blobs.sha256` identifies the exact bytes.
- Contributions that bypass secure boot, extract keys or OTP contents, or modify vendor firmware are not accepted.

## Clean-room process

1. Analysis. The vendor firmware is studied by static analysis, emulation and observation on hardware. The result is documentation in `docs/` with evidence and, where useful, test vectors.
2. Implementation. The component is written from that documentation.
3. Verification. The implementation is compared with the vendor firmware by differential tests: byte for byte for data formats, in an emulator for functions, on hardware for boot behavior.

Questions that come up during implementation are answered by improving the documentation, not by consulting the vendor binary.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r tools/requirements-dev.txt
scripts/fetch-blobs.sh --all
git config core.hooksPath .githooks
```

The development tools in `tools/requirements-dev.txt` need Python 3.10 or later.

Before you send changes:

```sh
python3 -m unittest
ruff check tools tests
shellcheck scripts/*.sh .githooks/commit-msg
reuse lint
```

## Branches

The project uses gitflow.

| Branch | Purpose |
|---|---|
| `main` | releases, tagged `vX.Y.Z` |
| `dev` | integration of finished work |
| `feature/<topic>` | new work, branched from `dev` |
| `release/vX.Y.Z` | release preparation, branched from `dev`, merged into `main` and `dev` |
| `hotfix/vX.Y.Z` | fixes for a release, branched from `main`, merged into `main` and `dev` |

Pull requests target `dev`. Versions follow [Semantic Versioning](https://semver.org/).

## Commit messages

Commit messages follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
<type>(<scope>): <summary>

<body>
```

- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `revert`.
- Scope, optional: the component, for example `eeprom`, `bootsys`, `bootmain`, `sdram`, `start4`, `usbboot`, `tools`.
- Summary: imperative mood, lower case, at most 60 characters, no trailing period.
- Body, optional: wrapped at 72 columns, says why the change is needed.
- Breaking changes: `!` after the type or scope and a `BREAKING CHANGE:` footer.
- One logical change per commit.

```text
feat(eeprom): add lz4 section writer
fix(start4): set uart divisor for 115200 baud
docs(bootsys): describe footer layout
test(eeprom): cover truncated back-references
```

`.githooks/commit-msg` checks the header.

## Documentation

- US English, present tense, short sentences.
- Hexadecimal with a `0x` prefix; sizes in bytes, or KiB and MiB.
- Offsets are relative to the start of the file unless stated otherwise.
- Points that are not yet confirmed go under "Open questions", with the way to settle them.

## Licensing

New source files start with an SPDX header:

```text
SPDX-FileCopyrightText: 2026 The open27xx Authors
SPDX-License-Identifier: GPL-2.0-or-later
```

Documentation is CC-BY-4.0 and configuration files are CC0-1.0 through `REUSE.toml`. "The open27xx Authors" are the authors recorded in the git history. By contributing you agree to license your work under these terms.
