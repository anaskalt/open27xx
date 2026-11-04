# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run recorder schema checks against an explicitly selected Ghidra API."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ClockVersionSchemaTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("OPEN27XX_GHIDRA_HOME"),
                         "Set OPEN27XX_GHIDRA_HOME for Ghidra API schema checks")
    def test_version_input_schema(self):
        home = Path(os.environ["OPEN27XX_GHIDRA_HOME"])
        jars = sorted((home / "Ghidra").glob("**/lib/*.jar"))
        self.assertTrue(jars, "No Ghidra API jars under OPEN27XX_GHIDRA_HOME")
        java_home = os.environ.get("JAVA_HOME")
        javac = str(Path(java_home) / "bin/javac") if java_home else shutil.which("javac")
        java = str(Path(java_home) / "bin/java") if java_home else shutil.which("java")
        self.assertTrue(javac and java, "Ghidra API schema checks require a Java JDK")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="clock-version-", dir=build) as temporary:
            classpath = os.pathsep.join(map(str, jars))
            subprocess.run([javac, "-cp", classpath, "-d", temporary,
                str(ROOT / "tools/ghidra/CaptureClockVectors.java"),
                str(ROOT / "tests/ClockVersionSchemaTest.java")],
                check=True, capture_output=True, text=True)
            result = subprocess.run([java, "-cp", temporary + os.pathsep + classpath,
                                     "ClockVersionSchemaTest"],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "Clock VERSION schema checks passed")


if __name__ == "__main__":
    unittest.main()
