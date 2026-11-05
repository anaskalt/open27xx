# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check fixed SoC inspection ranges and context JSON without a project."""

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
import java.util.Arrays;

public class SocInitializationInspectorTest {
    private static final String SOURCE =
        "38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb";
    private static int checks;

    private static void check(boolean value, String label) {
        if (!value) throw new AssertionError(label);
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
        throw new AssertionError("Accepted invalid arguments: " + Arrays.toString(args));
    }

    private static JsonObject context(String maskValue) {
        JsonObject out = new JsonObject();
        out.addProperty("register", "contextreg");
        out.addProperty("mask_value_bytes", maskValue);
        return out;
    }

    public static void main(String[] args) {
        var selected = InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json", "pseudo", "soc"});
        var soc = selected.source();
        check(selected.mode().equals("pseudo"), "SoC mode");
        check(!soc.arrival() && !soc.prefix(), "Fixed ranges retain separate semantics");
        check(soc.codeRanges() == 3, "Three code ranges");
        check(soc.ranges().length == 4 && soc.hashes().length == 4, "Four bound ranges");
        long[][] expectedRanges = {
            {0x0EC6221CL, 22, 0x61C1C},
            {0x0EC6227CL, 182, 0x61C7C},
            {0x0EC62332L, 64, 0x61D32},
            {0x0EC62232L, 74, 0x61C32}
        };
        String[] expectedHashes = {
            "73839f44927b7f4732e9b30e5be6b7071a8d9c978ed1a9bdaca0462b4f6628f7",
            "233e2362d8d3e991aef4c1232861d6965eee43793f5fc653cfdc2c1482267349",
            "3049de857385368f7e0ddce054581921a1fa9895858265bed2e3d65f3a6fc995",
            "d6acbd437cd60a2e08e85dfe5cc12ce35f2726c159501c4e1f36d011aefa9e6d"
        };
        long codeBytes = 0, dataBytes = 0;
        for (int i = 0; i < expectedRanges.length; i++) {
            long[] range = soc.ranges()[i];
            check(Arrays.equals(range, expectedRanges[i]), "Exact range " + i);
            check(soc.hashes()[i].equals(expectedHashes[i]), "Exact digest " + i);
            if (i < soc.codeRanges()) codeBytes += range[1];
            else dataBytes += range[1];
            for (int j = 0; j < i; j++) {
                long[] previous = soc.ranges()[j];
                check(range[0] + range[1] <= previous[0]
                    || previous[0] + previous[1] <= range[0], "Disjoint addresses");
                check(range[2] + range[1] <= previous[2]
                    || previous[2] + previous[1] <= range[2], "Disjoint file offsets");
            }
        }
        check(codeBytes == 268 && dataBytes == 74, "Code and data bounds");
        check(soc.ranges()[0][0] + soc.ranges()[0][1] == soc.ranges()[3][0],
            "Data begins at the first code boundary");
        check(soc.ranges()[3][0] + soc.ranges()[3][1] == soc.ranges()[1][0],
            "Data ends at the second code boundary");
        check(soc.ranges()[1][0] + soc.ranges()[1][1] == soc.ranges()[2][0],
            "Adjacent code ranges remain distinct");
        check(soc.ranges()[2][0] + soc.ranges()[2][1] == 0x0EC62372L,
            "Final exact boundary");
        check(InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "another.json", "pseudo", "soc"}).source() == soc,
            "Output path does not change descriptor identity");

        var defaults = InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json"});
        check(defaults.mode().equals("listing"), "Legacy default mode");
        var initializer = defaults.source();
        check(!initializer.arrival() && !initializer.prefix(), "Legacy initializer flags");
        check(initializer != soc, "Distinct descriptors despite equal flags");
        check(initializer.codeRanges() == 2 && initializer.ranges().length == 3,
            "Legacy initializer shape");
        var continuation = InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json", "pseudo", "continuation"}).source();
        check(continuation != soc && continuation != initializer, "Separate prefix descriptor");
        check(!continuation.arrival() && continuation.prefix(), "Legacy prefix flags");
        check(continuation.codeRanges() == 1 && continuation.ranges().length == 1,
            "Legacy prefix shape");
        var arrival = InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json", "pseudo", "arrival"}).source();
        check(arrival != soc && arrival != initializer && arrival != continuation,
            "Separate arrival descriptor");
        check(arrival.arrival() && !arrival.prefix(), "Legacy arrival flags");
        check(arrival.codeRanges() == 7 && arrival.ranges().length == 12,
            "Legacy arrival shape");
        for (String mode : new String[] {"listing", "pseudo"}) {
            check(InspectStartupInitialization.selectOptions(
                new String[] {SOURCE, "output.json", mode}).source() == initializer,
                "Implicit initializer remains stable");
            check(InspectStartupInitialization.selectOptions(
                new String[] {SOURCE, "output.json", mode, "initializer"}).source() == initializer,
                "Explicit initializer remains stable");
            check(InspectStartupInitialization.selectOptions(
                new String[] {SOURCE, "output.json", mode, "arrival"}).source() == arrival,
                "Both arrival modes remain stable");
        }

        for (String maskValue : new String[] {
                "0000000000000000", "00000000a5a5a5a5", "8000000180000001"}) {
            JsonObject out = new JsonObject();
            out.add("missing", JsonNull.INSTANCE);
            out.add("instruction_context", context(maskValue));
            JsonObject decoder = new JsonObject();
            decoder.add("current", JsonNull.INSTANCE);
            decoder.add("default", context(maskValue));
            decoder.add("nondefault", JsonNull.INSTANCE);
            decoder.add("disassembly_default", context(maskValue));
            out.add("decoder_context", decoder);
            String before = out.toString();
            String serialized = InspectStartupInitialization.outputJson(out, soc);
            JsonObject parsed = JsonParser.parseString(serialized).getAsJsonObject();
            check(serialized.endsWith("\n"), "Trailing newline");
            check(parsed.equals(out), "Exact null and context round trip");
            check(parsed.get("missing").isJsonNull(), "Top-level null is explicit");
            check(parsed.getAsJsonObject("decoder_context").get("current").isJsonNull(),
                "Unknown current context remains null");
            check(parsed.getAsJsonObject("decoder_context").get("nondefault").isJsonNull(),
                "Unknown nondefault context remains null");
            check(parsed.getAsJsonObject("instruction_context").get("mask_value_bytes")
                .getAsString().equals(maskValue), "Context mask and stored value are preserved");
            check(serialized.equals(InspectStartupInitialization.outputJson(out, arrival)),
                "Arrival retains explicit null serialization");
            check(serialized.equals(InspectStartupInitialization.outputJson(out, continuation)),
                "Prefix retains explicit null serialization");
            JsonObject legacy = JsonParser.parseString(
                InspectStartupInitialization.outputJson(out, initializer)).getAsJsonObject();
            check(!legacy.has("missing"), "Legacy top-level null omission");
            check(!legacy.getAsJsonObject("decoder_context").has("current")
                && !legacy.getAsJsonObject("decoder_context").has("nondefault"),
                "Legacy nested null omission");
            check(legacy.get("instruction_context").equals(context(maskValue)),
                "Legacy context value is preserved");
            check(out.toString().equals(before), "Serialization does not mutate input");
        }
        JsonObject absent = new JsonObject();
        absent.add("instruction_context", JsonNull.INSTANCE);
        check(InspectStartupInitialization.outputJson(absent, soc).equals("""
            {
              "instruction_context": null
            }
            """), "Unknown instruction context is explicit");
        check(InspectStartupInitialization.outputJson(absent, initializer).equals("{}\n"),
            "Equal flags do not enable initializer nulls");

        reject();
        reject(SOURCE);
        reject("incorrect", "output.json", "pseudo", "soc");
        reject(SOURCE, "output.json", "soc");
        reject(SOURCE, "output.json", "listing", "soc");
        reject(SOURCE, "output.json", "PSEUDO", "soc");
        reject(SOURCE, "output.json", "", "soc");
        reject(SOURCE, "output.json", "pseudo", "SOC");
        reject(SOURCE, "output.json", "pseudo", "");
        reject(SOURCE, "output.json", "pseudo", "unknown");
        reject(SOURCE, "output.json", "pseudo", "soc", "extra");
        reject(SOURCE, "output.json", "pseudo", "soc", "0x0EC6221C", "22");
        reject(SOURCE, "output.json", "listing", "continuation");
        System.out.println("SoC initialization inspector checks passed: " + checks);
    }
}
'''


class SocInitializationInspectorTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("OPEN27XX_GHIDRA_HOME"),
                         "Set OPEN27XX_GHIDRA_HOME for Ghidra API checks")
    def test_selection_ranges_and_context(self):
        home = Path(os.environ["OPEN27XX_GHIDRA_HOME"])
        jars = sorted((home / "Ghidra").glob("**/lib/*.jar"))
        self.assertTrue(jars, "No Ghidra API jars under OPEN27XX_GHIDRA_HOME")
        java_home = os.environ.get("JAVA_HOME")
        javac = str(Path(java_home) / "bin/javac") if java_home else shutil.which("javac")
        java = str(Path(java_home) / "bin/java") if java_home else shutil.which("java")
        self.assertTrue(javac and java, "Ghidra API checks require a Java JDK")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="soc-initialization-", dir=build) as temporary:
            harness = Path(temporary) / "SocInitializationInspectorTest.java"
            harness.write_text(HARNESS)
            classpath = os.pathsep.join(map(str, jars))
            compiled = subprocess.run([javac, "-cp", classpath, "-d", temporary,
                str(ROOT / "tools/ghidra/InspectStartupInitialization.java"), str(harness)],
                check=False, capture_output=True, text=True, timeout=240)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([java, "-Djava.awt.headless=true", "-Xmx256m", "-cp",
                                     temporary + os.pathsep + classpath,
                                     "SocInitializationInspectorTest"],
                                    check=False, capture_output=True, text=True, timeout=240)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SoC initialization inspector checks passed:", result.stdout)


if __name__ == "__main__":
    unittest.main()
