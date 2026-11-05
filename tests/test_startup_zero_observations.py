# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check startup capture admission and real synthetic memory observations."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StartupZeroObservationsTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("OPEN27XX_GHIDRA_HOME"),
                         "Set OPEN27XX_GHIDRA_HOME for Ghidra API checks")
    def test_admission_and_actual_observations(self):
        home = Path(os.environ["OPEN27XX_GHIDRA_HOME"])
        jars = sorted((home / "Ghidra").glob("**/lib/*.jar"))
        self.assertTrue(jars, "No Ghidra API jars under OPEN27XX_GHIDRA_HOME")
        java_home = os.environ.get("JAVA_HOME")
        javac = str(Path(java_home) / "bin/javac") if java_home else shutil.which("javac")
        java = str(Path(java_home) / "bin/java") if java_home else shutil.which("java")
        self.assertTrue(javac and java, "Ghidra API checks require a Java JDK")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="startup-zero-", dir=build) as temporary:
            classpath = os.pathsep.join(map(str, jars))
            subprocess.run([javac, "-cp", classpath, "-d", temporary,
                str(ROOT / "tools/ghidra/StartupZeroObservations.java"),
                str(ROOT / "tools/ghidra/CaptureStartupZero.java"),
                str(ROOT / "tests/StartupZeroObservationsTest.java")],
                check=True, capture_output=True, text=True, timeout=240)
            result = subprocess.run([java, "-Djava.awt.headless=true", "-Xmx1G", "-cp",
                                     temporary + os.pathsep + classpath,
                                     "StartupZeroObservationsTest"],
                                    check=True, capture_output=True, text=True, timeout=240)
            self.assertIn("Startup zero checks passed:", result.stdout)


if __name__ == "__main__":
    unittest.main()
