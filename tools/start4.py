#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Build and check the pinned BCM2711 VPU bring-up image."""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src/start4"
BUILD = ROOT / "build/start4"
RAM_START = 0xC4000000
RAM_END = 0xC6000000
STACK_SIZE = 65536


def run(*args, cwd=None, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True).strip()


def sources():
    result = json.loads((CONFIG / "sources.json").read_text())
    for spec in result.values():
        if not re.fullmatch(r"[0-9a-f]{40}", spec["commit"]):
            raise ValueError("source revisions must be full commit identifiers")
    return result


def fetch():
    for name, spec in sources().items():
        repo = BUILD / "cache" / name
        if "files" in spec:
            repo.mkdir(parents=True, exist_ok=True)
            for filename, digest in spec["files"].items():
                path = repo / filename
                if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                    continue
                with urllib.request.urlopen(spec["raw_url"] + filename, timeout=60) as response:
                    data = response.read()
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError(f"source digest mismatch: {name}/{filename}")
                path.write_bytes(data)
            continue
        if not repo.exists():
            repo.mkdir(parents=True)
            run("git", "init", "--bare", "--quiet", str(repo))
        exists = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", spec["commit"] + "^{commit}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if exists.returncode:
            run("git", "-C", str(repo), "fetch", "--depth=1", spec["url"], spec["commit"])
        actual = run("git", "-C", str(repo), "rev-parse", spec["commit"] + "^{commit}")
        if actual != spec["commit"]:
            raise ValueError(f"source revision mismatch: {name}")
    overlay = BUILD / "cache/lk-overlay"
    recorded = run("git", "-C", str(overlay), "ls-tree", sources()["lk-overlay"]["commit"], "lk")
    if recorded.split()[2] != sources()["lk"]["commit"]:
        raise ValueError("LK revision does not match the overlay submodule")


def export(name, destination):
    revision = sources()[name]["commit"]
    data = subprocess.check_output(
        ["git", "-C", str(BUILD / "cache" / name), "archive", revision]
    )
    destination.mkdir(parents=True, exist_ok=True)
    # The archives come from the fixed upstream commits, including their notices.
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            target = destination / member.name
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("source archive path escapes its directory")
        archive.extractall(destination)


def prepare():
    work = BUILD / "work"
    if work.exists():
        shutil.rmtree(work)
    export("lk-overlay", work)
    export("lk", work / "lk")
    environment = dict(os.environ, GIT_CEILING_DIRECTORIES=str(work.parent))
    for patch in sorted((CONFIG / "patches").glob("*.patch")):
        run("git", "apply", "--check", str(patch), cwd=work, env=environment)
        run("git", "apply", str(patch), cwd=work, env=environment)
    shutil.copy2(CONFIG / "project/open27xx-start4.mk", work / "project")
    for name in ("start4.c", "start4.ld"):
        shutil.copy2(CONFIG / "platform/bcm28xx/start4" / name, work / "platform/bcm28xx/start4" / name)
    return work


def check_elf(data):
    """Check this target's bounds and the documented bootmain loader fields."""
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("expected an ELF32 little-endian image")
    fields = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    kind, machine, version, entry, phoff, shoff, _, ehsize, phsize, phnum, shsize, shnum, names = fields
    if (kind, machine, version, ehsize, phsize, shsize) != (2, 137, 1, 52, 32, 40):
        raise ValueError("unexpected executable header")
    if not phnum or not shnum or names >= shnum:
        raise ValueError("missing program or section headers")
    if phoff < 52 or phoff + phnum * phsize > len(data):
        raise ValueError("program headers extend beyond the image")
    if shoff < 52 or shoff + shnum * shsize > len(data):
        raise ValueError("section headers extend beyond the image")
    segments = []
    file_segments = []
    executable = False
    for index in range(phnum):
        ptype, offset, vaddr, _, filesz, memsz, flags, _ = struct.unpack_from(
            "<8I", data, phoff + index * phsize
        )
        if ptype == 0:
            continue
        # bootmain copies every nonzero header type, not only PT_LOAD.
        if ptype != 1:
            raise ValueError("unexpected non-load program header")
        address = vaddr | 0xC0000000
        if filesz > memsz or offset + filesz > len(data):
            raise ValueError("segment data extends beyond its bounds")
        if address < RAM_START or address + memsz > RAM_END - STACK_SIZE:
            raise ValueError("segment extends beyond the VPU memory region")
        if any(address < end and start < address + memsz for start, end in segments):
            raise ValueError("overlapping load segments")
        segments.append((address, address + memsz))
        file_segments.append((address, offset, filesz))
        executable |= bool(flags & 1 and address <= entry < address + filesz)
    if not executable:
        raise ValueError("entry point is outside executable file data")
    headers = [struct.unpack_from("<10I", data, shoff + i * shsize) for i in range(shnum)]
    string_header = headers[names]
    string_offset, string_size = string_header[4:6]
    if string_offset + string_size > len(data):
        raise ValueError("section names extend beyond the image")
    strings = data[string_offset:string_offset + string_size]
    sections = {}
    for header in headers:
        name, stype, _, address, offset, size = header[:6]
        if name >= len(strings) or b"\0" not in strings[name:]:
            raise ValueError("invalid section name")
        if stype != 8 and offset + size > len(data):
            raise ValueError("section extends beyond the image")
        label = strings[name:].split(b"\0", 1)[0].decode("ascii")
        if label and label in sections:
            raise ValueError("duplicate section name")
        sections[label] = (address, offset, size, stype)
    for label, value in ((".text.bootloader_state", 0x41545342), (".text.firmware_rev", 3)):
        if label not in sections:
            raise ValueError(f"missing loader section: {label}")
        address, offset, size, stype = sections[label]
        if stype != 1 or size != 16 or address % 4 or struct.unpack_from("<4I", data, offset) != (value, 0, 0, 0):
            raise ValueError(f"invalid loader section: {label}")
        if not any(start <= address and address + size <= start + length
                   and offset - file_offset == address - start
                   for start, file_offset, length in file_segments):
            raise ValueError(f"unloaded loader section: {label}")
    return {"entry": f"0x{entry:08X}", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def build_armstub(prefix):
    fetch()
    work = BUILD / "armstubs"
    work.mkdir(exist_ok=True)
    for filename in sources()["armstubs"]["files"]:
        shutil.copy2(BUILD / "cache/armstubs" / filename, work / filename)
    command = ["make", "-B", "armstub8-gic.bin", "CC8=" + prefix + "gcc",
               "LD8=" + prefix + "ld", "OBJCOPY8=" + prefix + "objcopy"]
    logfile = BUILD / "armstub-build.log"
    with logfile.open("w") as log:
        result = subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise ValueError(f"armstub build failed; see {logfile}")
    data = (work / "armstub8-gic.bin").read_bytes()
    if len(data) < 256 or len(data) % 256 or struct.unpack_from("<4I", data, 0xF0) != (0x5AFE570B, 0, 0, 0):
        raise ValueError("unexpected armstub header or alignment")
    shutil.copy2(work / "armstub8-gic.bin", BUILD / "armstub8-gic.bin")
    result = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
              "source": sources()["armstubs"],
              "compiler": run(prefix + "gcc", "--version").splitlines()[0],
              "linker": run(prefix + "ld", "--version").splitlines()[0]}
    (BUILD / "armstub-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def stage():
    image = BUILD / "start4.elf"
    identity = check_elf(image.read_bytes())
    directory = BUILD / "stage"
    directory.mkdir(exist_ok=True)
    if (directory / "open27xx-none.dat").exists():
        raise ValueError("the candidate fixup filename must remain absent")
    shutil.copy2(image, directory / "open27xx.elf")
    shutil.copy2(CONFIG / "config.txt.fragment", directory / "config.txt.fragment")
    (directory / "manifest.json").write_text(json.dumps(identity, indent=2) + "\n")
    print(f"staged host files in {directory}; no boot partition was modified")


def build(prefix, jobs):
    compiler = prefix + "gcc"
    compiler_version = run(compiler, "--version").splitlines()[0]
    frontend = run(compiler, "-print-prog-name=cc1plus")
    if not Path(frontend).is_file() and shutil.which(frontend) is None:
        raise ValueError("the VPU compiler must include its C++ frontend (cc1plus)")
    libgcc = Path(run(compiler, "-print-libgcc-file-name"))
    if not libgcc.is_file():
        raise ValueError("the VPU compiler must include libgcc")
    fetch()
    work = prepare()
    output = "build-open27xx-start4/lk.elf"
    command = [
        "make", "-j" + str(jobs), "PROJECT=open27xx-start4", "LKROOT=lk",
        "LKINC=. lk lk/external", "BUILDROOT=.", "TOOLCHAIN_PREFIX=" + prefix,
        "CC=" + compiler, "LD=" + prefix + "ld", "SIZE=" + prefix + "size",
        "ARCH_LDFLAGS=-L" + str(libgcc.parent), "BUILDID=open27xx-start4",
        f"MEMBASE=0x{RAM_START:X}", f"MEMSIZE=0x{RAM_END - RAM_START - STACK_SIZE:X}",
        "DEBUG=0", output,
    ]
    environment = os.environ.copy()
    environment.update(SOURCE_DATE_EPOCH="0", LC_ALL="C", TZ="UTC", GIT_CEILING_DIRECTORIES=str(work.parent))
    logfile = BUILD / "build.log"
    with logfile.open("w") as log:
        result = subprocess.run(command, cwd=work, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise ValueError(f"build failed; see {logfile}")
    temporary = BUILD / "start4.elf.tmp"
    run(prefix + "objcopy", "--strip-debug", str(work / output), str(temporary))
    data = temporary.read_bytes()
    identity = check_elf(data)
    symbols = {}
    for line in run(prefix + "nm", "--defined-only", str(work / output)).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in ("_end", "_fstack"):
            symbols[fields[2]] = int(fields[0], 16)
    if not (RAM_START < symbols.get("_end", 0) <= RAM_END - STACK_SIZE
            and symbols.get("_fstack") == RAM_END - 4):
        raise ValueError("linked image and stack symbols disagree with the allocator region")
    temporary.replace(BUILD / "start4.elf")
    inputs = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(CONFIG.rglob("*")) if path.is_file()}
    inputs["tools/start4.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest = {"artifact": identity, "sources": sources(), "compiler": compiler_version,
                "linker": run(prefix + "ld", "--version").splitlines()[0], "inputs": inputs,
                "memory": {"image_end": f"0x{symbols['_end']:08X}",
                           "allocator_end": f"0x{RAM_END - STACK_SIZE:08X}",
                           "initial_stack": f"0x{symbols['_fstack']:08X}"}}
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(identity, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="fetch the exact open-source dependencies")
    commands.add_parser("stage", help="prepare host files for review before a hardware test")
    builder = commands.add_parser("build", help="build the unsigned VPU bring-up image")
    builder.add_argument("--toolchain-prefix", default="vc4-elf-")
    builder.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    checker = commands.add_parser("check", help="check a built open image without running it")
    checker.add_argument("image", type=Path)
    armstub = commands.add_parser("armstub", help="build the separate BCM2711 ARM entry stub")
    armstub.add_argument("--toolchain-prefix", default="aarch64-linux-gnu-")
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            fetch()
        elif args.command == "stage":
            stage()
        elif args.command == "build":
            build(args.toolchain_prefix, args.jobs)
        elif args.command == "armstub":
            build_armstub(args.toolchain_prefix)
        else:
            print(json.dumps(check_elf(args.image.read_bytes()), indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"start4: {error}\n")


if __name__ == "__main__":
    main()
