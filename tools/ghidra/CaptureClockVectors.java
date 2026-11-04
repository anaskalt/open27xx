// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later
// Capture scalar observations from synthetic firmware fixtures.
// @category open27xx

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.emulator.MemoryAccessFilter;
import ghidra.app.script.GhidraScript;
import ghidra.pcode.emulate.BreakCallBack;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.pcode.pcoderaw.PcodeOpRaw;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.mem.MemoryBlock;

public class CaptureClockVectors extends GhidraScript {
    private String fault;
    private AddressSet allowedMemory;
    private static final long CLOCK_CELL = 0x0EE056B0L;

    private static long number(JsonElement value) {
        return Long.parseUnsignedLong(value.getAsString().substring(2), 16);
    }

    private static String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private static boolean synthetic(long address, int size) {
        if (address == CLOCK_CELL && size == 4) { return true; }
        return (address >= 0x24000000L && address + size <= 0x25000000L)
            || (address >= 0xE4000000L && address + size <= 0xE5000000L);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    static final class VersionSite {
        final long pc;
        final String destination;
        final int index;

        VersionSite(long pc, String destination, int index) {
            this.pc = pc;
            this.destination = destination;
            this.index = index;
        }
    }

    static final class VersionInput {
        final long word;
        final List<VersionSite> sites;
        final Map<Long, VersionSite> byPc;
        int consumed;
        VersionSite pending;
        int step;

        VersionInput(long word, List<VersionSite> sites, Map<Long, VersionSite> byPc) {
            this.word = word;
            this.sites = List.copyOf(sites);
            this.byPc = Map.copyOf(byPc);
        }
    }

    private static String versionString(JsonElement value, String field) {
        check(value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString(),
            "VERSION " + field + " must be a string");
        return value.getAsString();
    }

    private static long versionWord(JsonElement value, String field) {
        String text = versionString(value, field);
        check(text.matches("0x[0-9a-fA-F]{8}"), "Invalid VERSION " + field);
        return Long.parseUnsignedLong(text.substring(2), 16);
    }

    static VersionInput parseVersionInput(JsonObject execution) {
        if (!execution.has("version_input")) {
            return null;
        }
        JsonElement value = execution.get("version_input");
        check(value.isJsonObject(), "VERSION input must be an object");
        JsonObject input = value.getAsJsonObject();
        check(input.keySet().equals(Set.of("word", "sites")), "Invalid VERSION input members");
        long word = versionWord(input.get("word"), "word");
        check(input.get("sites").isJsonArray(), "VERSION sites must be an array");
        JsonArray entries = input.getAsJsonArray("sites");
        check(!entries.isEmpty(), "VERSION sites must not be empty");
        List<VersionSite> sites = new ArrayList<>();
        Map<Long, VersionSite> byPc = new HashMap<>();
        for (JsonElement entry : entries) {
            check(entry.isJsonObject(), "VERSION site must be an object");
            JsonObject site = entry.getAsJsonObject();
            check(site.keySet().equals(Set.of("pc", "destination")), "Invalid VERSION site members");
            long pc = versionWord(site.get("pc"), "pc");
            check((pc & 1) == 0, "Unaligned VERSION pc");
            String destination = versionString(site.get("destination"), "destination");
            check(destination.matches("r(?:[0-9]|1[0-9]|2[0-3])"), "Invalid VERSION destination");
            VersionSite declared = new VersionSite(pc, destination, sites.size());
            check(byPc.put(pc, declared) == null, "Duplicate VERSION site");
            sites.add(declared);
        }
        return new VersionInput(word, sites, byPc);
    }

    private void versionOperation(PcodeOp operation, VersionSite site) {
        Register destination = currentProgram.getRegister(site.destination);
        check(destination != null && destination.getBitLength() == 32,
            "Invalid VERSION destination register at " + hex(site.pc));
        check(operation.getOpcode() == PcodeOp.CALLOTHER && operation.getNumInputs() == 1
                && operation.getInput(0).isConstant() && operation.getInput(0).getSize() == 4
                && operation.getInput(0).getOffset() == 1
                && "version".equals(currentProgram.getLanguage().getUserDefinedOpName(1))
                && operation.getOutput() != null && operation.getOutput().isRegister()
                && operation.getOutput().getSize() == 4
                && operation.getOutput().getAddress().equals(destination.getAddress()),
            "VERSION operation mismatch at " + hex(site.pc));
    }

    private Instruction versionInstruction(VersionSite site, EmulatorHelper emulator) throws Exception {
        Address address = toAddr(site.pc);
        for (int index = 0; index < 2; index++) {
            MemoryBlock block = currentProgram.getMemory().getBlock(address.addNoWrap(index));
            check(block != null && block.isInitialized() && block.isRead() && block.isExecute(),
                "VERSION site requires initialized readable executable bytes at " + hex(site.pc));
        }
        check(!allowedMemory.intersects(address, address.addNoWrap(1)),
            "Synthetic memory overlaps VERSION instruction at " + hex(site.pc));
        Instruction instruction = getInstructionAt(address);
        check(instruction != null, "Missing VERSION instruction at " + hex(site.pc));
        int register = Integer.parseInt(site.destination.substring(1));
        check(instruction.getLength() == 2 && instruction.getMnemonicString().equalsIgnoreCase("version")
                && Arrays.equals(instruction.getBytes(), new byte[]{(byte)(0xE0 | register), 0})
                && address.addNoWrap(2).equals(instruction.getFallThrough()),
            "VERSION instruction mismatch at " + hex(site.pc));
        Object[] operands = instruction.getOpObjects(0);
        check(instruction.getNumOperands() == 1 && operands.length == 1
                && operands[0] instanceof Register
                && operands[0].equals(currentProgram.getRegister(site.destination)),
            "VERSION decoded destination mismatch at " + hex(site.pc));
        PcodeOp[] operations = instruction.getPcode();
        check(operations.length == 1, "VERSION operation count mismatch at " + hex(site.pc));
        versionOperation(operations[0], site);
        if (emulator != null) {
            check(Arrays.equals(instruction.getBytes(), emulator.readMemory(address, 2)),
                "VERSION instruction bytes differ at " + hex(site.pc));
        }
        return instruction;
    }

    private void validateVersionInput(VersionInput input, Map<Long, JsonObject> stubs) throws Exception {
        if (input == null) {
            return;
        }
        check(currentProgram.getCompilerSpec().getCompilerSpecID().toString().equals("default"),
            "VERSION requires the default compiler specification");
        for (VersionSite site : input.sites) {
            check(!stubs.containsKey(site.pc), "VERSION site collides with stub at " + hex(site.pc));
            versionInstruction(site, null);
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
        JsonArray mmio = execution.getAsJsonArray("mmio_responses");
        final int[] mmioIndex = {0};
        final boolean[] injecting = {false};
        final boolean[] executing = {false};
        for (JsonElement response : mmio) {
            JsonObject r = response.getAsJsonObject();
            long a = number(r.get("address"));
            check(a >= 0x7C000000L && a + 4 <= 0x80000000L, "Invalid MMIO address");
            check(HexFormat.of().parseHex(r.get("hex").getAsString()).length == 4, "Expected word response");
            check(getInstructionAt(toAddr(number(r.get("pc")))) != null, "Missing response instruction");
        }
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
        VersionInput version = parseVersionInput(execution);
        validateVersionInput(version, stubs);
        EmulatorHelper emulator = new EmulatorHelper(currentProgram);
        try {
            if (version != null) {
                emulator.registerCallOtherCallback("version", new BreakCallBack() {
                    @Override
                    public boolean pcodeCallback(PcodeOpRaw operation) {
                        VersionSite site = version.pending;
                        check(site != null && operation.getAddress().equals(toAddr(site.pc))
                                && emulator.getExecutionAddress().getOffset() == site.pc,
                            "Unexpected VERSION callback");
                        versionOperation(operation, site);
                        emulate.getMemoryState().setValue(operation.getOutput(), version.word);
                        JsonObject event = new JsonObject();
                        event.addProperty("kind", "version");
                        event.addProperty("pc", hex(site.pc));
                        event.addProperty("destination", site.destination);
                        event.addProperty("value", hex(version.word));
                        event.addProperty("site_index", site.index);
                        event.addProperty("step", version.step);
                        events.add(event);
                        version.consumed++;
                        version.pending = null;
                        return true;
                    }
                });
            }
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
                    if (executing[0] && space.isMemorySpace() && offset < CLOCK_CELL + 4 && offset + size > CLOCK_CELL) {
                        check(offset == CLOCK_CELL && size == 4, "Partial clock cell read");
                        check(allowedMemory.contains(toAddr(offset), toAddr(offset + size - 1)), "Undeclared clock cell read");
                        JsonObject event = new JsonObject();
                        event.addProperty("kind", "elf_ram_read");
                        event.addProperty("pc", hex(emulator.getExecutionAddress().getOffset()));
                        event.addProperty("address", hex(offset));
                        event.addProperty("hex", HexFormat.of().formatHex(Arrays.copyOf(values, size)));
                        events.add(event);
                    }
                    if (space.isMemorySpace() && offset >= 0x7C000000L && offset < 0x80000000L) {
                        check(mmioIndex[0] < mmio.size(), "Unscripted MMIO read " + hex(offset));
                        JsonObject reply = mmio.get(mmioIndex[0]).getAsJsonObject();
                        long pc = emulator.getExecutionAddress().getOffset();
                        check(pc == number(reply.get("pc")) && offset == number(reply.get("address")) && size == 4,
                            "Mismatched MMIO read at " + hex(pc) + " address " + hex(offset));
                        check(Arrays.equals(values, HexFormat.of().parseHex(reply.get("hex").getAsString())),
                            "Mismatched supplied MMIO bytes");
                        JsonObject event = reply.deepCopy();
                        event.addProperty("kind", "supplied_mmio_read");
                        event.addProperty("reply_index", mmioIndex[0]++);
                        events.add(event);
                    }
                }
                protected void processWrite(AddressSpace space, long offset, int size, byte[] values) {
                    if (injecting[0] || !space.isMemorySpace() || size == 0) {
                        return;
                    }
                    if (offset >= 0x7C000000L && offset + size <= 0x80000000L) {
                        boolean declared = false;
                        for (JsonElement allowed : execution.getAsJsonArray("mmio_write_addresses")) {
                            declared |= offset == number(allowed) && size == 4;
                        }
                        check(declared, "Undeclared MMIO write " + hex(offset));
                        JsonObject event = new JsonObject();
                        event.addProperty("kind", "mmio_write");
                        event.addProperty("pc", hex(emulator.getExecutionAddress().getOffset()));
                        event.addProperty("address", hex(offset));
                        event.addProperty("hex", HexFormat.of().formatHex(Arrays.copyOf(values, size)));
                        events.add(event);
                    } else {
                        if (offset < CLOCK_CELL + 4 && offset + size > CLOCK_CELL) {
                            check(offset == CLOCK_CELL && size == 4, "Partial clock cell write");
                            JsonObject event = new JsonObject();
                            event.addProperty("kind", "elf_ram_write");
                            event.addProperty("pc", hex(emulator.getExecutionAddress().getOffset()));
                            event.addProperty("address", hex(offset));
                            event.addProperty("hex", HexFormat.of().formatHex(Arrays.copyOf(values, size)));
                            events.add(event);
                        }
                        check(allowedMemory.contains(space.getAddress(offset), space.getAddress(offset + size - 1)),
                            id + ": write outside declared memory " + hex(offset) + " size " + size);
                    }
                }
            });
            int steps = 0;
            executing[0] = true;
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
                VersionSite site = version == null ? null : version.byPc.get(pc);
                boolean versionInstruction = version != null
                    && (site != null || instruction.getMnemonicString().equalsIgnoreCase("version"));
                if (versionInstruction) {
                    check(site != null, id + ": undeclared VERSION site at " + hex(pc));
                    check(site.index >= version.consumed, id + ": exhausted VERSION site at " + hex(pc));
                    check(site.index == version.consumed, id + ": reordered VERSION site at " + hex(pc));
                    versionInstruction(site, emulator);
                    version.pending = site;
                    version.step = steps;
                } else {
                    check(!instruction.getMnemonicString().toLowerCase().startsWith("v"),
                        id + ": vector instruction at " + hex(pc));
                    for (PcodeOp operation : instruction.getPcode()) {
                        check(operation.getOpcode() != PcodeOp.CALLOTHER,
                            id + ": unsupported operation at " + hex(pc));
                    }
                }
                if (mmioIndex[0] < mmio.size()) {
                    JsonObject reply = mmio.get(mmioIndex[0]).getAsJsonObject();
                    if (pc == number(reply.get("pc"))) {
                        injecting[0] = true;
                        try {
                            emulator.writeMemory(toAddr(number(reply.get("address"))),
                                HexFormat.of().parseHex(reply.get("hex").getAsString()));
                        } finally { injecting[0] = false; }
                    }
                }
                check(emulator.step(monitor), id + ": " + fault + " at " + hex(pc) + " " + emulator.getLastError());
                check(fault == null, id + ": " + fault + " at " + hex(pc));
                if (versionInstruction) {
                    check(version.pending == null && version.consumed == site.index + 1,
                        id + ": VERSION callback was not consumed at " + hex(pc));
                    check(emulator.getExecutionAddress().equals(instruction.getFallThrough()),
                        id + ": VERSION did not reach natural fallthrough at " + hex(pc));
                }
                steps++;
            }
            check(version == null || version.consumed == version.sites.size(), id + ": unused VERSION sites");
            executing[0] = false;
            check(mmioIndex[0] == mmio.size(), id + ": unused MMIO replies");
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
        MemoryBlock block = currentProgram.getMemory().getBlock(toAddr(CLOCK_CELL));
        check(block != null && block.contains(toAddr(CLOCK_CELL + 3)), "Clock cell is not mapped");
        check(block.getStart().getOffset() == 0x0EE056A0L && block.getEnd().getOffset() == 0x0EE05FCFL,
            "Unexpected clock cell block bounds");
        check(!block.isInitialized() && block.isRead() && block.isWrite() && !block.isExecute(),
            "Clock cell must be uninitialized non-executable read/write ELF RAM");
        for (int i = 0; i < 4; i++) {
            check(getInstructionContaining(toAddr(CLOCK_CELL + i)) == null, "Clock cell overlaps instruction bytes");
        }
        check(currentProgram.getExecutableSHA256().equals("38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb"),
            "Unexpected clock cell source identity");
        check(currentProgram.getMemory().getInt(toAddr(0x0EDDD694L)) == CLOCK_CELL,
            "Unexpected clock descriptor pointer");
        for (JsonElement element : document.getAsJsonArray("cases")) {
            capture(element.getAsJsonObject());
        }
        String json = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(document);
        Files.writeString(Path.of(args[1]), json + "\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
    }
}
