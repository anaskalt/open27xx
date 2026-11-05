# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check static inspector selection and context JSON without a project."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

public class StartupArrivalInspectorTest {
    private static final String SOURCE =
        "38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb";
    private static int checks;

    private static void check(boolean value) {
        if (!value) throw new AssertionError("Check " + checks);
        checks++;
    }

    private static void reject(String... args) {
        try {
            InspectStartupInitialization.selectOptions(args);
        }
        catch (IllegalStateException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Accepted invalid arguments");
    }

    public static void main(String[] args) {
        var defaults = InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json"});
        check(defaults.mode().equals("listing"));
        check(!defaults.source().arrival());
        check(defaults.source().codeRanges() == 2);
        check(defaults.source().ranges().length == 3);
        for (String mode : new String[] {"listing", "pseudo"}) {
            var legacy = InspectStartupInitialization.selectOptions(
                new String[] {SOURCE, "output.json", mode});
            var explicit = InspectStartupInitialization.selectOptions(
                new String[] {SOURCE, "output.json", mode, "initializer"});
            check(legacy.mode().equals(mode) && explicit.mode().equals(mode));
            check(legacy.source() == defaults.source() && explicit.source() == defaults.source());
            var arrival = InspectStartupInitialization.selectOptions(
                new String[] {SOURCE, "output.json", mode, "arrival"});
            check(arrival.mode().equals(mode) && arrival.source().arrival());
            check(arrival.source() != defaults.source());
            check(arrival.source().codeRanges() == 7);
            check(arrival.source().ranges().length == 12);
            check(arrival.source().hashes().length == arrival.source().ranges().length);
            long code = 0, data = 0;
            for (int i = 0; i < arrival.source().ranges().length; i++) {
                long size = arrival.source().ranges()[i][1];
                if (i < arrival.source().codeRanges()) code += size;
                else data += size;
            }
            check(code == 204 && data == 48);

            JsonObject out = new JsonObject();
            out.add("missing", JsonNull.INSTANCE);
            JsonObject context = new JsonObject();
            context.addProperty("register", "contextreg");
            context.addProperty("mask_value_bytes", "8000000180000001");
            out.add("instruction_context", context);
            JsonObject program = new JsonObject();
            program.add("current", JsonNull.INSTANCE);
            program.add("disassembly_default", context.deepCopy());
            out.add("decoder_context", program);
            String before = out.toString();
            String oldJson = InspectStartupInitialization.outputJson(out, legacy.source());
            check(oldJson.equals("""
                {
                  "instruction_context": {
                    "register": "contextreg",
                    "mask_value_bytes": "8000000180000001"
                  },
                  "decoder_context": {
                    "disassembly_default": {
                      "register": "contextreg",
                      "mask_value_bytes": "8000000180000001"
                    }
                  }
                }
                """));
            check(oldJson.equals(InspectStartupInitialization.outputJson(out, explicit.source())));
            check(oldJson.equals(InspectStartupInitialization.outputJson(out, defaults.source())));
            var oldObject = JsonParser.parseString(oldJson).getAsJsonObject();
            check(!oldObject.has("missing"));
            check(!oldObject.getAsJsonObject("decoder_context").has("current"));
            check(oldObject.get("instruction_context").equals(context));
            String newJson = InspectStartupInitialization.outputJson(out, arrival.source());
            var newObject = JsonParser.parseString(newJson).getAsJsonObject();
            check(newObject.get("missing").isJsonNull());
            check(newObject.getAsJsonObject("decoder_context").get("current").isJsonNull());
            check(newObject.get("instruction_context").equals(context));
            check(newObject.getAsJsonObject("decoder_context").get("disassembly_default").equals(context));
            check(newJson.endsWith("\n") && oldJson.endsWith("\n"));
            check(out.toString().equals(before));
            JsonObject absent = new JsonObject();
            absent.add("instruction_context", JsonNull.INSTANCE);
            check(InspectStartupInitialization.outputJson(absent, legacy.source()).equals("{}\n"));
            check(JsonParser.parseString(InspectStartupInitialization.outputJson(absent,
                arrival.source())).getAsJsonObject().get("instruction_context").isJsonNull());
        }
        reject();
        reject(SOURCE);
        reject("incorrect", "output.json");
        reject(SOURCE, "output.json", "arrival");
        reject(SOURCE, "output.json", "PSEUDO");
        reject(SOURCE, "output.json", "pseudo", "");
        reject(SOURCE, "output.json", "pseudo", "Arrival");
        reject(SOURCE, "output.json", "pseudo", "unknown");
        reject(SOURCE, "output.json", "pseudo", "arrival", "extra");
        System.out.println("Startup arrival inspector checks passed: " + checks);
    }
}
'''


class StartupArrivalInspectorTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("OPEN27XX_GHIDRA_HOME"),
                         "Set OPEN27XX_GHIDRA_HOME for Ghidra API checks")
    def test_selection_and_context_serialization(self):
        home = Path(os.environ["OPEN27XX_GHIDRA_HOME"])
        jars = sorted((home / "Ghidra").glob("**/lib/*.jar"))
        self.assertTrue(jars, "No Ghidra API jars under OPEN27XX_GHIDRA_HOME")
        java_home = os.environ.get("JAVA_HOME")
        javac = str(Path(java_home) / "bin/javac") if java_home else shutil.which("javac")
        java = str(Path(java_home) / "bin/java") if java_home else shutil.which("java")
        self.assertTrue(javac and java, "Ghidra API checks require a Java JDK")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="startup-arrival-", dir=build) as temporary:
            harness = Path(temporary) / "StartupArrivalInspectorTest.java"
            harness.write_text(HARNESS)
            classpath = os.pathsep.join(map(str, jars))
            compiled = subprocess.run([javac, "-cp", classpath, "-d", temporary,
                str(ROOT / "tools/ghidra/InspectStartupInitialization.java"), str(harness)],
                check=False, capture_output=True, text=True, timeout=240)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([java, "-Djava.awt.headless=true", "-Xmx256m", "-cp",
                                     temporary + os.pathsep + classpath,
                                     "StartupArrivalInspectorTest"],
                                    check=False, capture_output=True, text=True, timeout=240)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Startup arrival inspector checks passed:", result.stdout)


if __name__ == "__main__":
    unittest.main()
