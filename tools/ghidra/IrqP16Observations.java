// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import ghidra.app.emulator.EmulatorHelper;
import ghidra.pcode.emulate.BreakCallBack;
import ghidra.pcode.pcoderaw.PcodeOpRaw;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Program;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;

final class IrqP16Observations {
    static final class Occurrence {
        final String kind;
        final long pc;
        final String register;
        final long value;
        final int index;

        Occurrence(String kind, long pc, String register, long value, int index) {
            this.kind = kind;
            this.pc = pc;
            this.register = register;
            this.value = value;
            this.index = index;
        }

        int length() {
            return kind.equals("di") ? 2 : 4;
        }
    }

    final List<Occurrence> operations;
    final Map<Long, Occurrence> byPc;
    int consumed;
    private Program program;
    private JsonArray events;
    private Occurrence pending;
    private long[] before;
    private int step;
    private boolean callbackConsumed;

    private IrqP16Observations(List<Occurrence> operations, Map<Long, Occurrence> byPc) {
        this.operations = List.copyOf(operations);
        this.byPc = Map.copyOf(byPc);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private static String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private static String string(JsonElement value, String field) {
        check(value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString(),
            "IRQ/p16 " + field + " must be a string");
        return value.getAsString();
    }

    private static long word(JsonElement value, String field) {
        String text = string(value, field);
        check(text.matches("0x[0-9a-fA-F]{8}"), "Invalid IRQ/p16 " + field);
        return Long.parseUnsignedLong(text.substring(2), 16);
    }

    static IrqP16Observations parse(JsonObject execution) {
        if (!execution.has("irq_p16")) {
            return null;
        }
        JsonElement element = execution.get("irq_p16");
        check(element.isJsonObject(), "IRQ/p16 input must be an object");
        JsonObject input = element.getAsJsonObject();
        check(input.keySet().equals(Set.of("interrupt_arrivals", "operations")),
            "Invalid IRQ/p16 input members");
        check(string(input.get("interrupt_arrivals"), "interrupt_arrivals").equals("none"),
            "IRQ/p16 requires no interrupt arrivals");
        JsonElement limit = execution.get("step_limit");
        check(limit != null && limit.isJsonPrimitive() && limit.getAsJsonPrimitive().isNumber(),
            "IRQ/p16 step limit must be a positive integer");
        int stepLimit;
        try {
            stepLimit = limit.getAsBigDecimal().intValueExact();
        } catch (ArithmeticException | NumberFormatException invalid) {
            throw new IllegalStateException("IRQ/p16 step limit must be a positive integer", invalid);
        }
        check(stepLimit > 0, "IRQ/p16 step limit must be a positive integer");
        check(input.get("operations").isJsonArray(), "IRQ/p16 operations must be an array");
        JsonArray entries = input.getAsJsonArray("operations");
        check(!entries.isEmpty(), "IRQ/p16 operations must not be empty");
        check(entries.size() <= stepLimit, "IRQ/p16 operations exceed step limit");
        List<Occurrence> operations = new ArrayList<>();
        Map<Long, Occurrence> byPc = new HashMap<>();
        for (JsonElement entry : entries) {
            check(entry.isJsonObject(), "IRQ/p16 occurrence must be an object");
            JsonObject occurrence = entry.getAsJsonObject();
            String kind = string(occurrence.get("kind"), "kind");
            Set<String> members;
            switch (kind) {
                case "di": members = Set.of("kind", "pc"); break;
                case "p16_read": members = Set.of("kind", "pc", "destination", "value"); break;
                case "p16_write": members = Set.of("kind", "pc", "source"); break;
                default: throw new IllegalStateException("Invalid IRQ/p16 kind");
            }
            check(occurrence.keySet().equals(members), "Invalid IRQ/p16 occurrence members");
            long pc = word(occurrence.get("pc"), "pc");
            check((pc & 1) == 0, "Unaligned IRQ/p16 pc");
            String register = null;
            long value = 0;
            if (!kind.equals("di")) {
                String field = kind.equals("p16_read") ? "destination" : "source";
                register = string(occurrence.get(field), field);
                check(register.matches("r(?:[0-9]|1[0-9]|2[0-3])"), "Invalid IRQ/p16 " + field);
            }
            if (kind.equals("p16_read")) {
                value = word(occurrence.get("value"), "value");
                check(value <= 1, "IRQ/p16 read value must be zero or one");
            }
            Occurrence declared = new Occurrence(kind, pc, register, value, operations.size());
            check(pc + declared.length() <= 0xffffffffL, "Wrapping IRQ/p16 instruction span");
            Occurrence previous = byPc.putIfAbsent(pc, declared);
            check(previous == null || (previous.kind.equals(kind)
                    && java.util.Objects.equals(previous.register, register)),
                "Conflicting IRQ/p16 occurrence binding at " + hex(pc));
            operations.add(declared);
        }
        return new IrqP16Observations(operations, byPc);
    }

    private Address address(long pc) {
        return program.getAddressFactory().getDefaultAddressSpace().getAddress(pc);
    }

    private static boolean overlapsP16(Varnode node) {
        return node != null && node.isRegister() && node.getOffset() < 0x244
            && node.getOffset() + node.getSize() > 0x240;
    }

    private static boolean node(Varnode node, int space, long offset, int size) {
        return node != null && node.getAddress().getAddressSpace().getType() == space
            && node.getOffset() == offset && node.getSize() == size;
    }

    private static boolean operation(PcodeOp operation, int opcode, Varnode output, Varnode... inputs) {
        return operation.getOpcode() == opcode && java.util.Objects.equals(operation.getOutput(), output)
            && Arrays.equals(operation.getInputs(), inputs);
    }

    private Varnode register(long offset) {
        return new Varnode(program.getAddressFactory().getRegisterSpace().getAddress(offset), 4);
    }

    private Varnode unique(long offset) {
        return new Varnode(program.getAddressFactory().getUniqueSpace().getAddress(offset), 4);
    }

    private Varnode constant(long value, int size) {
        return new Varnode(program.getAddressFactory().getConstantSpace().getAddress(value), size);
    }

    private void disableOperation(PcodeOp operation, long pc) {
        check(operation.getOpcode() == PcodeOp.CALLOTHER && operation.getNumInputs() == 1
                && node(operation.getInput(0), AddressSpace.TYPE_CONSTANT, 4, 4)
                && operation.getOutput() == null
                && "irq_disable".equals(program.getLanguage().getUserDefinedOpName(4)),
            "IRQ/p16 irq_disable operation mismatch at " + hex(pc));
    }

    private Instruction instruction(Occurrence site, EmulatorHelper emulator) throws Exception {
        Address start = address(site.pc);
        for (int offset = 0; offset < site.length(); offset++) {
            MemoryBlock block = program.getMemory().getBlock(start.addNoWrap(offset));
            check(block != null && block.isInitialized() && block.isRead() && block.isExecute(),
                "IRQ/p16 site requires initialized readable executable bytes at " + hex(site.pc));
        }
        Instruction instruction = program.getListing().getInstructionAt(start);
        check(instruction != null, "Missing IRQ/p16 instruction at " + hex(site.pc));
        check(instruction.getLength() == site.length()
                && start.addNoWrap(site.length()).equals(instruction.getFallThrough()),
            "IRQ/p16 instruction length or fallthrough mismatch at " + hex(site.pc));
        PcodeOp[] ops = instruction.getPcode();
        byte[] expected;
        if (site.kind.equals("di")) {
            expected = new byte[]{5, 0};
            check(instruction.getMnemonicString().equalsIgnoreCase("di") && instruction.getNumOperands() == 0,
                "IRQ/p16 decoded DI mismatch at " + hex(site.pc));
            check(ops.length == 5
                    && operation(ops[0], PcodeOp.INT_AND, unique(0x8300), register(0x78), constant(0xbfffffffL, 4))
                    && operation(ops[1], PcodeOp.INT_ZEXT, unique(0x8400), constant(0, 1))
                    && operation(ops[2], PcodeOp.INT_LEFT, unique(0x8500), unique(0x8400), constant(0x1e, 4))
                    && operation(ops[3], PcodeOp.INT_OR, register(0x78), unique(0x8300), unique(0x8500)),
                "IRQ/p16 DI compiled shape mismatch at " + hex(site.pc));
            disableOperation(ops[4], site.pc);
        } else {
            boolean read = site.kind.equals("p16_read");
            int index = Integer.parseInt(site.register.substring(1));
            expected = read ? new byte[]{(byte)(0x20 | index), (byte)0xcc, 0x10, 0}
                : new byte[]{0x10, (byte)0xcc, (byte)index, 0};
            Register ordinary = program.getRegister(site.register);
            Register p16 = program.getRegister("p16");
            check(ordinary != null && ordinary.getBitLength() == 32 && ordinary.getOffset() == 4 * index
                    && p16 != null && p16.getBitLength() == 32 && p16.getOffset() == 0x240,
                "IRQ/p16 register binding mismatch at " + hex(site.pc));
            check(instruction.getMnemonicString().equalsIgnoreCase("mov") && instruction.getNumOperands() == 2
                    && Arrays.equals(instruction.getOpObjects(0), new Object[]{read ? ordinary : p16})
                    && Arrays.equals(instruction.getOpObjects(1), new Object[]{read ? p16 : ordinary}),
                "IRQ/p16 decoded COPY operands mismatch at " + hex(site.pc));
            check(ops.length == 1 && operation(ops[0], PcodeOp.COPY,
                    register(read ? 4 * index : 0x240), register(read ? 0x240 : 4 * index)),
                "IRQ/p16 COPY compiled shape mismatch at " + hex(site.pc));
        }
        check(Arrays.equals(instruction.getBytes(), expected),
            "IRQ/p16 original instruction bytes mismatch at " + hex(site.pc));
        if (emulator != null) {
            check(Arrays.equals(expected, emulator.readMemory(start, site.length())),
                "IRQ/p16 instruction bytes differ at " + hex(site.pc));
        }
        return instruction;
    }

    void preflight(Program program, AddressSetView declaredMemory, Set<Long> stubs,
            Set<Long> versionSites, List<JsonObject> assignments) throws Exception {
        this.program = program;
        check(program.getLanguageID().toString().equals("vc4:LE:32:default")
                && program.getCompilerSpec().getCompilerSpecID().toString().equals("default"),
            "IRQ/p16 requires vc4:LE:32:default and the default compiler specification");
        for (JsonObject registers : assignments) {
            for (String name : registers.keySet()) {
                Register register = program.getRegister(name);
                check(register == null || !overlapsP16(new Varnode(register.getAddress(), register.getNumBytes())),
                    "IRQ/p16 register assignment overlaps p16: " + name);
            }
        }
        for (Occurrence site : operations) {
            check(!stubs.contains(site.pc), "IRQ/p16 site collides with stub at " + hex(site.pc));
            check(!versionSites.contains(site.pc), "IRQ/p16 site collides with VERSION at " + hex(site.pc));
            check(!declaredMemory.intersects(address(site.pc), address(site.pc + site.length() - 1)),
                "Declared memory overlaps IRQ/p16 instruction at " + hex(site.pc));
            instruction(site, null);
        }
    }

    void install(EmulatorHelper emulator, JsonArray events) {
        this.events = events;
        emulator.registerCallOtherCallback("irq_disable", new BreakCallBack() {
            @Override
            public boolean pcodeCallback(PcodeOpRaw operation) {
                check(pending != null && pending.kind.equals("di") && !callbackConsumed
                        && operation.getAddress().equals(address(pending.pc))
                        && emulator.getExecutionAddress().equals(address(pending.pc)),
                    "Unexpected IRQ/p16 irq_disable callback");
                disableOperation(operation, pending.pc);
                long sr = emulator.readRegister("sr").longValue() & 0xffffffffL;
                check(sr == (before[30] & 0xbfffffffL),
                    "IRQ/p16 DI SR mask mismatch at " + hex(pending.pc));
                JsonObject event = event("irq_disable");
                event.addProperty("sr_before", hex(before[30]));
                event.addProperty("sr_after", hex(sr));
                events.add(event);
                callbackConsumed = true;
                consumed++;
                return true;
            }
        });
    }

    private static String ordinaryName(int index) {
        if (index < 24 || index >= 27 && index < 30) {
            return "r" + index;
        }
        return new String[]{"gp", "sp", "lr", "sr"}[index == 30 ? 3 : index - 24];
    }

    private JsonObject event(String kind) {
        JsonObject event = new JsonObject();
        event.addProperty("kind", kind);
        event.addProperty("pc", hex(pending.pc));
        event.addProperty("operation_index", pending.index);
        event.addProperty("step", step);
        return event;
    }

    boolean before(Instruction instruction, EmulatorHelper emulator, int step) throws Exception {
        long pc = instruction.getAddress().getOffset();
        boolean relevant = byPc.containsKey(pc) || instruction.getMnemonicString().equalsIgnoreCase("di");
        for (PcodeOp operation : instruction.getPcode()) {
            relevant |= overlapsP16(operation.getOutput());
            for (Varnode input : operation.getInputs()) {
                relevant |= overlapsP16(input);
            }
            relevant |= operation.getOpcode() == PcodeOp.CALLOTHER && operation.getNumInputs() > 0
                && node(operation.getInput(0), AddressSpace.TYPE_CONSTANT, 4, 4);
        }
        if (!relevant) {
            return false;
        }
        check(byPc.containsKey(pc), "Undeclared IRQ/p16 instruction at " + hex(pc));
        boolean remaining = false;
        for (int index = consumed; index < operations.size(); index++) {
            remaining |= operations.get(index).pc == pc;
        }
        check(remaining, "Exhausted IRQ/p16 occurrence at " + hex(pc));
        check(operations.get(consumed).pc == pc, "Reordered IRQ/p16 occurrence at " + hex(pc));
        check(pending == null, "Unconsumed IRQ/p16 instruction");
        Occurrence site = operations.get(consumed);
        instruction(site, emulator);
        pending = site;
        this.step = step;
        callbackConsumed = false;
        before = new long[31];
        for (int index = 0; index < before.length; index++) {
            before[index] = emulator.readRegister(ordinaryName(index)).longValue() & 0xffffffffL;
        }
        if (site.kind.equals("p16_read")) {
            emulator.writeRegister("p16", site.value);
        }
        return true;
    }

    void after(EmulatorHelper emulator) {
        check(pending != null, "Missing IRQ/p16 pending instruction");
        Occurrence site = pending;
        check(emulator.getExecutionAddress().equals(address(site.pc + site.length())),
            "IRQ/p16 did not reach natural fallthrough at " + hex(site.pc));
        for (int index = 0; index < before.length; index++) {
            long expected = before[index];
            if (site.kind.equals("di") && index == 30) {
                expected &= 0xbfffffffL;
            } else if (site.kind.equals("p16_read") && ordinaryName(index).equals(site.register)) {
                expected = site.value;
            }
            check((emulator.readRegister(ordinaryName(index)).longValue() & 0xffffffffL) == expected,
                "IRQ/p16 register preservation mismatch for " + ordinaryName(index) + " at " + hex(site.pc));
        }
        if (site.kind.equals("di")) {
            check(callbackConsumed && consumed == site.index + 1,
                "IRQ/p16 irq_disable callback was not consumed at " + hex(site.pc));
        } else {
            JsonObject event = event(site.kind);
            if (site.kind.equals("p16_read")) {
                event.addProperty("destination", site.register);
                event.addProperty("value", hex(site.value));
            } else {
                long value = emulator.readRegister("p16").longValue() & 0xffffffffL;
                check(value == before[Integer.parseInt(site.register.substring(1))],
                    "IRQ/p16 natural write mismatch at " + hex(site.pc));
                event.addProperty("source", site.register);
                event.addProperty("value", hex(value));
            }
            events.add(event);
            consumed++;
        }
        pending = null;
    }

    void finish() {
        check(pending == null && consumed == operations.size(), "Unused IRQ/p16 occurrences");
    }
}
