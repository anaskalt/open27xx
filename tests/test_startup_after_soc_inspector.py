# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check post-SoC source bounds, context and p-code failure isolation."""

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
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.address.GenericAddressSpace;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;

public class PostSocInspectorTest {
    static final String SOURCE = "38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb";
    static int checks;
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        checks++;
    }
    static void rejectOptions(String... args) {
        try { InspectStartupInitialization.selectOptions(args); }
        catch (IllegalStateException expected) { checks++; return; }
        throw new AssertionError("Accepted options: " + Arrays.toString(args));
    }
    static void rejectCode(InspectStartupInitialization.RangeSet source, PcodeOp[] code) {
        try { InspectStartupInitialization.validatePcode(source, code); }
        catch (IllegalStateException expected) { checks++; return; }
        throw new AssertionError("Accepted unimplemented p-code");
    }
    static JsonObject context(String bytes) {
        JsonObject context = new JsonObject(); context.addProperty("register", "contextreg");
        context.addProperty("mask_value_bytes", bytes); return context;
    }
    public static void main(String[] args) {
        var options = InspectStartupInitialization.selectOptions(new String[]{SOURCE, "out.json", "pseudo", "post-soc"});
        var selected = options.source();
        check(options.mode().equals("pseudo") && !selected.arrival() && !selected.prefix(), "Independent fixed descriptor");
        long[][] ranges = {{0x0EC3689EL,32,0x3629E},{0x0EC3694EL,2,0x3634E},
            {0x0EC9BB62L,52,0x9B562},{0x0EE055B8L,4,0x204F98}};
        String[] hashes = {
            "9f4cbfbe1383bd4a93393214d46f572318cac55fc97269c07f5e8b315963613b",
            "ffd2b38b328fe2e10d03587fb8dad5dd902305255aa5d7ec9e6a56ea6c0bdc62",
            "d687c5ef87eb345471664e27a0db02facb5cf99860f1925ea6afae02853d352b",
            "1912c8284cab3593631677b89ce67380dce7acb80673b046d3812391643254f7"};
        check(selected.codeRanges()==3 && selected.ranges().length==4 && selected.hashes().length==4, "Three code and one data range");
        long codeBytes=0, dataBytes=0;
        for (int i=0;i<ranges.length;i++) {
            check(Arrays.equals(selected.ranges()[i],ranges[i]), "Exact range " + i);
            check(selected.hashes()[i].equals(hashes[i]), "Exact hash " + i);
            if (i<selected.codeRanges()) codeBytes+=ranges[i][1]; else dataBytes+=ranges[i][1];
        }
        check(codeBytes==86 && dataBytes==4, "Fixed byte budgets");
        check(InspectStartupInitialization.selectOptions(new String[]{SOURCE,"other.json","pseudo","post-soc"}).source()==selected,
            "Descriptor identity is stable");
        AddressSpace ram=new GenericAddressSpace("ram",32,AddressSpace.TYPE_RAM,0);
        AddressSpace constants=new GenericAddressSpace("const",64,AddressSpace.TYPE_CONSTANT,1);
        PcodeOp ordinary=new PcodeOp(ram.getAddress(0x1000),0,PcodeOp.COPY,
            new Varnode[]{new Varnode(constants.getAddress(7),4)},new Varnode(ram.getAddress(0x2000),4));
        PcodeOp unsupported=new PcodeOp(ram.getAddress(0x1002),0,PcodeOp.UNIMPLEMENTED);
        PcodeOp[][] accepted={new PcodeOp[0],new PcodeOp[]{ordinary}};
        PcodeOp[][] rejected={new PcodeOp[]{unsupported},new PcodeOp[]{ordinary,unsupported},new PcodeOp[]{unsupported,ordinary}};
        for (PcodeOp[] code:accepted) {
            PcodeOp[] before=code.clone(); InspectStartupInitialization.validatePcode(selected,code);
            check(Arrays.equals(before,code), "Valid p-code is not mutated");
        }
        for (PcodeOp[] code:rejected) {
            PcodeOp[] before=code.clone(); rejectCode(selected,code);
            check(Arrays.equals(before,code), "Rejected p-code is not mutated");
        }
        for (String name:new String[]{"initializer","arrival","continuation","soc"}) {
            var legacy=InspectStartupInitialization.selectOptions(new String[]{SOURCE,"out.json","pseudo",name}).source();
            check(legacy!=selected, "Legacy descriptor remains distinct");
            for (PcodeOp[][] family:new PcodeOp[][][]{accepted,rejected}) for (PcodeOp[] code:family) {
                PcodeOp[] before=code.clone(); InspectStartupInitialization.validatePcode(legacy,code);
                check(Arrays.equals(before,code), "New gate preserves legacy policy " + name);
            }
        }
        var initializer=InspectStartupInitialization.selectOptions(new String[]{SOURCE,"out.json"}).source();
        for (String value:new String[]{"0000000000000000","00000000a5a5a5a5","8000000180000001"}) {
            JsonObject out=new JsonObject(), decoder=new JsonObject();
            decoder.add("current",JsonNull.INSTANCE); decoder.add("default",context(value));
            decoder.add("nondefault",JsonNull.INSTANCE); decoder.add("disassembly_default",context(value));
            out.add("decoder_context",decoder); out.add("instruction_context",context(value));
            out.add("missing",JsonNull.INSTANCE); String before=out.toString();
            String encoded=InspectStartupInitialization.outputJson(out,selected);
            check(encoded.endsWith("\n"),"Trailing newline");
            check(JsonParser.parseString(encoded).equals(out),"Exact explicit-null and mask/value round trip");
            check(out.toString().equals(before),"Context input remains unchanged");
            for (String name:new String[]{"arrival","continuation","soc"}) {
                var legacy=InspectStartupInitialization.selectOptions(new String[]{SOURCE,"out.json","pseudo",name}).source();
                check(encoded.equals(InspectStartupInitialization.outputJson(out,legacy)),"Legacy explicit context policy");
            }
            JsonObject old=JsonParser.parseString(InspectStartupInitialization.outputJson(out,initializer)).getAsJsonObject();
            check(!old.has("missing") && !old.getAsJsonObject("decoder_context").has("current"),"Initializer still omits nulls");
            check(old.get("instruction_context").equals(context(value)),"Initializer preserves stored values");
        }
        JsonObject unknown=new JsonObject(); unknown.add("instruction_context",JsonNull.INSTANCE);
        check(JsonParser.parseString(InspectStartupInitialization.outputJson(unknown,selected)).equals(unknown),"Null actual context remains explicit");
        rejectOptions(); rejectOptions(SOURCE);
        rejectOptions("incorrect","out.json","pseudo","post-soc");
        rejectOptions(SOURCE,"out.json","listing","post-soc");
        rejectOptions(SOURCE,"out.json","post-soc");
        rejectOptions(SOURCE,"out.json","PSEUDO","post-soc");
        rejectOptions(SOURCE,"out.json","pseudo","POST-SOC");
        rejectOptions(SOURCE,"out.json","pseudo","unknown");
        rejectOptions(SOURCE,"out.json","pseudo","post-soc","extra");
        rejectOptions(SOURCE,"out.json","pseudo","post-soc","0x0EC3689E","32");
        System.out.println("Post-SoC inspector checks passed: " + checks);
    }
}
'''


class PostSocInspectorTest(unittest.TestCase):
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
        with tempfile.TemporaryDirectory(prefix="post-soc-", dir=build) as temporary:
            harness = Path(temporary) / "PostSocInspectorTest.java"
            harness.write_text(HARNESS)
            classpath = os.pathsep.join(map(str, jars))
            compiled = subprocess.run([javac, "-cp", classpath, "-d", temporary,
                str(ROOT / "tools/ghidra/InspectStartupInitialization.java"), str(harness)],
                check=False, capture_output=True, text=True, timeout=240)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([java, "-Djava.awt.headless=true", "-Xmx256m", "-cp",
                                     temporary + os.pathsep + classpath,
                                     "PostSocInspectorTest"],
                                    check=False, capture_output=True, text=True, timeout=240)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Post-SoC inspector checks passed:", result.stdout)


if __name__ == "__main__":
    unittest.main()
