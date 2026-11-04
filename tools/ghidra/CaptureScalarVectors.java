// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later
// Capture scalar observations from synthetic firmware fixtures.
// @category open27xx

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.emulator.MemoryAccessFilter;
import ghidra.app.script.GhidraScript;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.pcode.PcodeOp;

public class CaptureScalarVectors extends GhidraScript {
    private String fault;
    private AddressSet allowedMemory;

    private static long number(JsonElement value) {
        return Long.parseUnsignedLong(value.getAsString().substring(2), 16);
    }

    private static String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private static boolean synthetic(long address, int size) {
        return (address >= 0x24000000L && address + size <= 0x25000000L)
            || (address >= 0xE4000000L && address + size <= 0xE5000000L);
    }

    private void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private void registers(EmulatorHelper emulator, JsonObject values) {
        for (Map.Entry<String, JsonElement> value : values.entrySet()) {
            emulator.writeRegister(value.getKey(), number(value.getValue()));
        }
    }

    private byte[] bytes(JsonObject region) {
        if (region.has("hex")) {
            check(!region.has("fill") && !region.has("size"), "Ambiguous memory region");
            return HexFormat.of().parseHex(region.get("hex").getAsString());
        }
        byte[] fill = HexFormat.of().parseHex(region.get("fill").getAsString());
        check(fill.length == 1, "Fill must contain one byte");
        int size = region.get("size").getAsInt();
        check(size >= 0 && size <= 1048576, "Invalid fill size");
        byte[] result = new byte[size];
        Arrays.fill(result, fill[0]);
        return result;
    }

    private void memory(EmulatorHelper emulator, JsonArray regions) {
        for (JsonElement value : regions) {
            JsonObject region = value.getAsJsonObject();
            long address = number(region.get("address"));
            byte[] bytes = bytes(region);
            check(synthetic(address, bytes.length), "Fixture memory must use synthetic RAM");
            check(bytes.length == 0 || allowedMemory.contains(toAddr(address), toAddr(address + bytes.length - 1)),
                "Write outside declared synthetic memory");
            emulator.writeMemory(toAddr(address), bytes);
        }
    }

    private void capture(JsonObject fixture) throws Exception {
        String id = fixture.get("id").getAsString();
        JsonObject setup = fixture.getAsJsonObject("setup");
        JsonObject execution = fixture.getAsJsonObject("execution");
        check(execution.getAsJsonArray("mmio_responses").isEmpty(), "MMIO reads are unsupported");
        long stop = number(execution.get("return_address"));
        JsonArray events = new JsonArray();
        Map<Long, JsonObject> stubs = new HashMap<>();
        Map<Long, Integer> consumed = new HashMap<>();
        for (JsonElement element : execution.getAsJsonArray("stubs")) {
            JsonObject stub = element.getAsJsonObject();
            long entry = number(stub.get("entry"));
            check(stubs.put(entry, stub) == null, "Duplicate stub");
            consumed.put(entry, 0);
        }
        EmulatorHelper emulator = new EmulatorHelper(currentProgram);
        fault = null;
        allowedMemory = new AddressSet();
        for (JsonElement element : setup.getAsJsonArray("memory")) {
            JsonObject region = element.getAsJsonObject();
            long start = number(region.get("address"));
            int size = bytes(region).length;
            if (size > 0) {
                allowedMemory.add(toAddr(start), toAddr(start + size - 1));
            }
        }
        try {
            emulator.setMemoryFaultHandler(new MemoryFaultHandler() {
                public boolean uninitializedRead(Address address, int size, byte[] buffer, int offset) {
                    fault = "Uninitialized read " + address + " size " + size;
                    return false;
                }
                public boolean unknownAddress(Address address, boolean write) {
                    fault = "Unknown address " + address + " write " + write;
                    return false;
                }
            });
            long initial = number(setup.get("register_default"));
            for (int index = 0; index < 24; index++) {
                emulator.writeRegister("r" + index, initial);
            }
            for (String register : new String[]{"gp", "sp", "lr", "r27", "r28", "r29", "sr"}) {
                emulator.writeRegister(register, initial);
            }
            memory(emulator, setup.getAsJsonArray("memory"));
            registers(emulator, setup.getAsJsonObject("registers"));
            emulator.writeRegister("lr", stop);
            emulator.writeRegister("pc", number(fixture.getAsJsonObject("function").get("entry")));
            emulator.enableMemoryWriteTracking(true);
            emulator.getEmulator().addMemoryAccessFilter(new MemoryAccessFilter() {
                protected void processRead(AddressSpace space, long offset, int size, byte[] values) {
                    if (space.isMemorySpace() && offset >= 0x7C000000L && offset < 0x80000000L) {
                        throw new IllegalStateException("Unexpected MMIO read " + hex(offset));
                    }
                }
                protected void processWrite(AddressSpace space, long offset, int size, byte[] values) {
                    if (!space.isMemorySpace() || size == 0) {
                        return;
                    }
                    if (offset >= 0x7C000000L && offset + size <= 0x80000000L) {
                        JsonObject event = new JsonObject();
                        event.addProperty("kind", "mmio_write");
                        event.addProperty("address", hex(offset));
                        event.addProperty("hex", HexFormat.of().formatHex(Arrays.copyOf(values, size)));
                        events.add(event);
                    } else {
                        check(allowedMemory.contains(space.getAddress(offset), space.getAddress(offset + size - 1)),
                            id + ": write outside declared memory " + hex(offset) + " size " + size);
                    }
                }
            });
            int steps = 0;
            while (emulator.getExecutionAddress().getOffset() != stop) {
                monitor.checkCancelled();
                long pc = emulator.getExecutionAddress().getOffset();
                JsonObject stub = stubs.get(pc);
                if (stub != null) {
                    int index = consumed.get(pc);
                    JsonArray replies = stub.getAsJsonArray("replies");
                    check(index < replies.size(), id + ": exhausted stub " + hex(pc));
                    JsonObject event = new JsonObject();
                    event.addProperty("kind", "stub");
                    event.addProperty("entry", hex(pc));
                    JsonArray arguments = new JsonArray();
                    for (int argument = 0; argument < 6; argument++) {
                        arguments.add(hex(emulator.readRegister("r" + argument).longValue()));
                    }
                    event.add("arguments", arguments);
                    event.addProperty("reply_index", index);
                    events.add(event);
                    JsonObject reply = replies.get(index).getAsJsonObject();
                    long returnAddress = emulator.readRegister("lr").longValue();
                    memory(emulator, reply.getAsJsonArray("memory"));
                    registers(emulator, reply.getAsJsonObject("registers"));
                    emulator.writeRegister("pc", returnAddress);
                    consumed.put(pc, index + 1);
                    continue;
                }
                check(steps < execution.get("step_limit").getAsInt(), id + ": step limit at " + hex(pc));
                Instruction instruction = getInstructionAt(toAddr(pc));
                check(instruction != null, id + ": missing instruction at " + hex(pc));
                check(Arrays.equals(instruction.getBytes(), emulator.readMemory(toAddr(pc), instruction.getLength())),
                    id + ": instruction bytes differ at " + hex(pc));
                check(!instruction.getMnemonicString().toLowerCase().startsWith("v"),
                    id + ": vector instruction at " + hex(pc));
                for (PcodeOp operation : instruction.getPcode()) {
                    check(operation.getOpcode() != PcodeOp.CALLOTHER,
                        id + ": unsupported operation at " + hex(pc));
                }
                steps++;
                check(emulator.step(monitor), id + ": " + fault + " at " + hex(pc) + " " + emulator.getLastError());
                check(fault == null, id + ": " + fault + " at " + hex(pc));
            }
            for (Map.Entry<Long, JsonObject> stub : stubs.entrySet()) {
                check(consumed.get(stub.getKey()) == stub.getValue().getAsJsonArray("replies").size(),
                    id + ": unused replies for " + hex(stub.getKey()));
            }
            for (AddressRange range : emulator.getTrackedMemoryWriteSet()) {
                long start = range.getMinAddress().getOffset();
                long end = range.getMaxAddress().getOffset();
                if (range.getMinAddress().isMemoryAddress()) {
                    check(allowedMemory.contains(range.getMinAddress(), range.getMaxAddress())
                        || (start >= 0x7C000000L && end < 0x80000000L),
                        id + ": write outside declared memory " + range);
                }
            }
            JsonObject expected = fixture.getAsJsonObject("expected");
            JsonObject results = new JsonObject();
            for (String register : expected.getAsJsonObject("registers").keySet()) {
                results.addProperty(register, hex(emulator.readRegister(register).longValue()));
            }
            JsonArray observations = new JsonArray();
            for (JsonElement element : expected.getAsJsonArray("memory")) {
                JsonObject region = element.getAsJsonObject();
                long address = number(region.get("address"));
                int size = bytes(region).length;
                check(synthetic(address, size), "Observations must use synthetic RAM");
                check(size == 0 || allowedMemory.contains(toAddr(address), toAddr(address + size - 1)),
                    "Observation outside declared synthetic memory");
                JsonObject observation = new JsonObject();
                observation.addProperty("address", hex(address));
                observation.addProperty("hex", HexFormat.of().formatHex(emulator.readMemory(toAddr(address), size)));
                observations.add(observation);
            }
            expected.add("registers", results);
            expected.add("memory", observations);
            expected.add("events", events);
            fixture.addProperty("steps", steps);
            println(id + ": " + steps + " instructions");
        } finally {
            emulator.dispose();
        }
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        check(args.length == 2, "Expected input fixture and output JSON paths");
        JsonObject document = JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonObject();
        check(document.get("schema").getAsInt() == 1, "Unsupported schema");
        check(currentProgram.getExecutableSHA256().equals(document.getAsJsonObject("source").get("sha256").getAsString()),
            "Firmware digest mismatch");
        check(currentProgram.getLanguageID().toString().equals("vc4:LE:32:default"), "Wrong language");
        for (JsonElement element : document.getAsJsonArray("cases")) {
            capture(element.getAsJsonObject());
        }
        String json = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(document);
        Files.writeString(Path.of(args[1]), json + "\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
    }
}
