# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check bounded prefix policy with synthetic API objects and no project."""

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
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.address.GenericAddressSpace;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;
import ghidra.program.model.symbol.FlowType;
import ghidra.program.model.symbol.RefType;
import java.util.Objects;

public class StartupContinuationInspectorTest {
    private static final String SOURCE =
        "38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb";
    private static final AddressSpace RAM =
        new GenericAddressSpace("ram", 32, AddressSpace.TYPE_RAM, 0);
    private static final AddressSpace CONSTANT =
        new GenericAddressSpace("const", 64, AddressSpace.TYPE_CONSTANT, 1);
    private static final AddressSpace REGISTER =
        new GenericAddressSpace("register", 32, AddressSpace.TYPE_REGISTER, 2);
    private static final Address PC = RAM.getAddress(0x1000);
    private static int checks;

    private static void check(boolean value, String label) {
        if (!value) throw new AssertionError(label);
        checks++;
    }

    private static void reject(Runnable action, String label) {
        try {
            action.run();
        }
        catch (IllegalStateException expected) {
            checks++;
            return;
        }
        throw new AssertionError(label);
    }

    private static Varnode value(AddressSpace space, long offset) {
        return new Varnode(space.getAddress(offset), 4);
    }

    private static PcodeOp op(int opcode, Varnode... inputs) {
        return new PcodeOp(PC, 0, opcode, inputs);
    }

    private static void stop(String expected, String mnemonic, FlowType flow,
                             boolean sequential, PcodeOp... code) {
        String actual = InspectStartupInitialization.prefixStopReason(
            mnemonic, flow, code, sequential);
        check(Objects.equals(expected, actual), mnemonic + ": " + actual + " != " + expected);
    }

    private static void selectionAndContext() {
        var selected = InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json", "pseudo", "continuation"});
        check(selected.mode().equals("pseudo"), "prefix mode");
        check(selected.source().prefix() && !selected.source().arrival(), "distinct prefix flag");
        check(selected.source().codeRanges() == 1, "one code envelope");
        check(selected.source().ranges().length == 1, "no secondary ranges");
        check(selected.source().hashes().length == 1, "one bound hash");
        long[] range = selected.source().ranges()[0];
        check(range[0] == 0x0ED4A08CL && range[1] == 64 && range[2] == 0x149A8C,
            "fixed envelope geometry");
        check(selected.source().hashes()[0].equals(
            "7e14b716ed728805159a08dde64a420567b4b5d7b15251cee986cb194c872c8b"),
            "fixed envelope digest");
        for (String mode : new String[] {"listing", "pseudo"}) {
            var initializer = InspectStartupInitialization.selectOptions(
                new String[] {SOURCE, "output.json", mode, "initializer"});
            var arrival = InspectStartupInitialization.selectOptions(
                new String[] {SOURCE, "output.json", mode, "arrival"});
            check(!initializer.source().prefix() && !initializer.source().arrival(),
                "initializer flags remain separate");
            check(!arrival.source().prefix() && arrival.source().arrival(), "arrival flags unchanged");
            check(initializer.source() != selected.source() && arrival.source() != selected.source(),
                "distinct source selections");
        }
        reject(() -> InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json", "listing", "continuation"}), "listing prefix accepted");
        reject(() -> InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json", "pseudo", "Continuation"}), "case-folded set accepted");
        reject(() -> InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json", "continuation"}), "set accepted as mode");
        reject(() -> InspectStartupInitialization.selectOptions(
            new String[] {SOURCE, "output.json", "pseudo", "continuation", "extra"}), "extra argument accepted");

        for (String bits : new String[] {"0000000000000000", "00000000a5a5a5a5", "8000000180000001"}) {
            JsonObject context = new JsonObject();
            context.addProperty("register", "contextreg");
            context.addProperty("mask_value_bytes", bits);
            JsonObject program = new JsonObject();
            program.add("current", JsonNull.INSTANCE);
            program.add("default", JsonNull.INSTANCE);
            program.add("nondefault", JsonNull.INSTANCE);
            program.add("disassembly_default", context.deepCopy());
            JsonObject out = new JsonObject();
            out.add("decoder_context", program);
            out.add("instruction_context", context.deepCopy());
            out.add("pcode", JsonNull.INSTANCE);
            out.addProperty("function_complete", false);
            String before = out.toString();
            String json = InspectStartupInitialization.outputJson(out, selected.source());
            JsonObject result = JsonParser.parseString(json).getAsJsonObject();
            check(result.get("instruction_context").equals(context), "instruction context bits retained");
            check(result.get("decoder_context").equals(program), "all program context fields retained");
            check(result.get("pcode").isJsonNull(), "unavailable p-code remains null");
            check(!result.get("function_complete").getAsBoolean(), "partial result flag retained");
            check(json.endsWith("\n") && out.toString().equals(before), "serialization is nonmutating");
        }
        JsonObject absent = new JsonObject();
        absent.add("instruction_context", JsonNull.INSTANCE);
        check(JsonParser.parseString(InspectStartupInitialization.outputJson(absent,
            selected.source())).getAsJsonObject().get("instruction_context").isJsonNull(),
            "absent instruction context remains null");
    }

    private static void flowBoundaries() {
        Varnode target = value(RAM, 0x2000), next = value(RAM, 0x1004);
        Varnode indirect = value(REGISTER, 0), condition = value(REGISTER, 4);
        Varnode internal = value(CONSTANT, 2);
        stop(null, "nop", RefType.FALL_THROUGH, true);
        stop(null, "add", RefType.FALL_THROUGH, true, op(PcodeOp.INT_ADD, indirect, internal));
        stop("fallthrough_boundary", "nop", RefType.FALL_THROUGH, false);
        for (int opcode : new int[] {PcodeOp.CALL, PcodeOp.CALLIND, PcodeOp.RETURN, PcodeOp.BRANCHIND}) {
            stop("pcode_control_flow", "control", RefType.FALL_THROUGH, true,
                op(opcode, opcode == PcodeOp.CALL ? target : indirect));
        }
        for (int opcode : new int[] {PcodeOp.BRANCH, PcodeOp.CBRANCH}) {
            stop("pcode_external_control", "b", RefType.FALL_THROUGH, true, op(opcode, target, condition));
            stop("pcode_external_control", "mov.eq", RefType.FALL_THROUGH, true,
                op(opcode, next, condition));
            stop(null, "conditional-scalar", RefType.FALL_THROUGH, true, op(opcode, internal, condition));
            stop("instruction_control_flow", "b", RefType.CONDITIONAL_JUMP, true,
                op(opcode, internal, condition));
            reject(() -> InspectStartupInitialization.prefixStopReason("b", RefType.FALL_THROUGH,
                new PcodeOp[] {op(opcode)}, true), "missing branch operand accepted");
        }
        for (FlowType flow : new FlowType[] {
            RefType.UNCONDITIONAL_JUMP, RefType.CONDITIONAL_JUMP, RefType.COMPUTED_JUMP,
            RefType.CONDITIONAL_COMPUTED_JUMP, RefType.UNCONDITIONAL_CALL,
            RefType.CONDITIONAL_CALL, RefType.COMPUTED_CALL, RefType.CONDITIONAL_COMPUTED_CALL,
            RefType.TERMINATOR, RefType.CONDITIONAL_TERMINATOR, RefType.CALL_TERMINATOR,
            RefType.COMPUTED_CALL_TERMINATOR, RefType.JUMP_TERMINATOR,
            RefType.CALL_OVERRIDE_UNCONDITIONAL, RefType.JUMP_OVERRIDE_UNCONDITIONAL,
            RefType.CALLOTHER_OVERRIDE_CALL, RefType.CALLOTHER_OVERRIDE_JUMP}) {
            stop("instruction_control_flow", "flow", flow, true);
        }
        stop("unsupported_pcode", "unknown", RefType.FALL_THROUGH, true,
            op(PcodeOp.UNIMPLEMENTED));
        stop("unsupported_pcode", "service", RefType.FALL_THROUGH, true,
            op(PcodeOp.CALLOTHER, internal));
        stop("unsupported_pcode", "mixed", RefType.COMPUTED_CALL, true,
            op(PcodeOp.CALLIND, indirect), op(PcodeOp.CALLOTHER, internal));
        for (String mnemonic : new String[] {"vadd", "VADD", "version", "swi", "SWI", "rti", "RTI"}) {
            stop("unsupported_instruction", mnemonic, RefType.FALL_THROUGH, true);
        }
        reject(() -> InspectStartupInitialization.prefixStopReason(null, RefType.FALL_THROUGH,
            new PcodeOp[0], true), "null mnemonic accepted");
        reject(() -> InspectStartupInitialization.prefixStopReason("nop", null,
            new PcodeOp[0], true), "null flow accepted");
        reject(() -> InspectStartupInitialization.prefixStopReason("nop", RefType.FALL_THROUGH,
            null, true), "null p-code accepted");
    }

    private static void budgets() {
        check(InspectStartupInitialization.prefixLimitReason(0, 0) == null, "empty prefix starts");
        check(InspectStartupInitialization.prefixLimitReason(15, 62) == null, "last bounded decode permitted");
        check(InspectStartupInitialization.prefixLimitReason(16, 32).equals("instruction_limit"),
            "sixteen short instructions stop before byte limit");
        check(InspectStartupInitialization.prefixLimitReason(8, 64).equals("source_window_end"),
            "byte envelope stops before instruction limit");
        check(InspectStartupInitialization.prefixLimitReason(16, 64).equals("source_window_end"),
            "coincident bounds report exhausted envelope");
        for (int[] counters : new int[][] {{-1, 0}, {17, 32}, {0, -1}, {8, 65}}) {
            reject(() -> InspectStartupInitialization.prefixLimitReason(counters[0], counters[1]),
                "out-of-bound counters accepted");
        }
    }

    public static void main(String[] args) {
        selectionAndContext();
        flowBoundaries();
        budgets();
        System.out.println("Startup continuation inspector checks passed: " + checks);
    }
}
'''


class StartupContinuationInspectorTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("OPEN27XX_GHIDRA_HOME"),
                         "Set OPEN27XX_GHIDRA_HOME for Ghidra API checks")
    def test_selection_context_and_prefix_boundaries(self):
        home = Path(os.environ["OPEN27XX_GHIDRA_HOME"])
        jars = sorted((home / "Ghidra").glob("**/lib/*.jar"))
        self.assertTrue(jars, "No Ghidra API jars under OPEN27XX_GHIDRA_HOME")
        java_home = os.environ.get("JAVA_HOME")
        javac = str(Path(java_home) / "bin/javac") if java_home else shutil.which("javac")
        java = str(Path(java_home) / "bin/java") if java_home else shutil.which("java")
        self.assertTrue(javac and java, "Ghidra API checks require a Java JDK")
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="startup-continuation-", dir=build) as temporary:
            harness = Path(temporary) / "StartupContinuationInspectorTest.java"
            harness.write_text(HARNESS)
            classpath = os.pathsep.join(map(str, jars))
            compiled = subprocess.run([javac, "-cp", classpath, "-d", temporary,
                str(ROOT / "tools/ghidra/InspectStartupInitialization.java"), str(harness)],
                check=False, capture_output=True, text=True, timeout=240)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([java, "-Djava.awt.headless=true", "-Xmx256m", "-cp",
                                     temporary + os.pathsep + classpath,
                                     "StartupContinuationInspectorTest"],
                                    check=False, capture_output=True, text=True, timeout=240)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Startup continuation inspector checks passed:", result.stdout)


if __name__ == "__main__":
    unittest.main()
