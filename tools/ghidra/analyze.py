#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Import BCM2711 firmware into a fresh Ghidra project and export metadata."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ghidra-home", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    for name in ("bootsys", "bootmain", "recovery", "start4"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    launcher = args.ghidra_home / "support" / "analyzeHeadless"
    if not launcher.is_file():
        parser.error("Ghidra headless launcher does not exist")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.project_name):
        parser.error("project name must contain letters, digits, underscores or hyphens")
    for suffix in (".gpr", ".rep", ".lock"):
        if (args.project_dir / (args.project_name + suffix)).exists():
            parser.error("project already exists; choose a fresh project name")
    if args.output_dir.exists():
        parser.error("output directory already exists; choose a fresh directory")
    inputs = {name: getattr(args, name).resolve() for name in
              ("bootmain", "start4", "bootsys", "recovery")}
    for path in inputs.values():
        if not path.is_file():
            parser.error("input is not a regular file: " + str(path))
    if len({path.name for path in inputs.values()}) != len(inputs):
        parser.error("input basenames must be distinct within the project")
    scripts = Path(__file__).resolve().parent
    manifest = {
        "schema": 1,
        "inputs": {name: {"file": path.name, "size": path.stat().st_size,
                          "sha256": sha256(path)} for name, path in inputs.items()},
        "scripts": {name: sha256(scripts / name) for name in
                    ("analyze.py", "PrepareFirmware.java", "ExportAnalysis.java")},
    }
    args.project_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True)
    output = args.output_dir.resolve()
    for name, path in inputs.items():
        mode = "raw" if name in ("bootsys", "recovery") else "elf"
        report_path = output / (name + ".json")
        command = [str(launcher), str(args.project_dir.absolute()), args.project_name,
                   "-import", str(path), "-scriptPath", str(scripts),
                   "-preScript", "PrepareFirmware.java", mode,
                   "-postScript", "ExportAnalysis.java", str(report_path),
                   "-max-cpu", "1", "-log", str(output / (name + ".log")),
                   "-scriptlog", str(output / (name + "-script.log"))]
        if mode == "raw":
            command += ["-loader", "BinaryLoader", "-processor", "vc4:LE:32:default",
                        "-loader-baseAddr", "0x80000000"]
        print("Analyzing " + name, flush=True)
        with (output / (name + "-console.log")).open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True,
                           env={**os.environ, "GHIDRA_HEADLESS_MAXMEM": "2G"})
        if not report_path.is_file():
            raise RuntimeError("Missing analysis report; inspect " + name + "-console.log")
        report = json.loads(report_path.read_text())
        if (not report["analyzed"] or report["language"] != "vc4:LE:32:default"
                or report["sha256"] != manifest["inputs"][name]["sha256"]):
            raise RuntimeError("Analysis report does not match input: " + name)
        manifest["inputs"][name]["report_sha256"] = sha256(report_path)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("Analysis complete: " + str(output), flush=True)


if __name__ == "__main__":
    main()
