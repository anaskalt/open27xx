// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later
// Capture bounded SoC initialization observations.
// @category open27xx

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;

import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.emulator.MemoryAccessFilter;
import ghidra.app.plugin.processors.sleigh.SleighLanguage;
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.framework.Application;
import ghidra.pcode.emulate.BreakCallBack;
import ghidra.pcode.emulate.EmulateExecutionState;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.pcode.pcoderaw.PcodeOpRaw;
import ghidra.program.disassemble.Disassembler;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.lang.InstructionBlock;
import ghidra.program.model.lang.Register;
import ghidra.program.model.lang.RegisterValue;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.ByteMemBufferImpl;
import ghidra.program.model.mem.MemoryAccessException;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;

public class CaptureSocInitialization extends GhidraScript {
    static final String SOURCE = "38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb";
    static final String VERSION = "ab5c7f86283ceb58b7adb269cae1d16092a31bf6";
    static final String SOURCE_EXPORT = "35915548ef69157b2dfd763249b8b9d23e02ebb2cd21cce2a08dcfd985f7848b";
    static final String PCODE = "fb1495571ffdc861f034e6f049e0e21b6651a58b662d137de367403a24aa50fd";
    static final long ENTRY = 0x0EC6221CL, TERMINAL = 0x0EC62370L;
    static final long VERSION1 = 0x0EC6221EL, VERSION2 = 0x0EC62332L;
    static final long MMIO_PC = 0x0EC6230EL, MMIO_ADDRESS = 0x7E0000B4L;
    static final StartupZeroObservations.Span UNION = span("decoder_union", ENTRY, 348);
    static final StartupZeroObservations.Span TABLE = span("table", 0x0EC62232L, 74);
    static final List<String> REGISTERS = registers();
    record Seed(StartupZeroObservations.Span span, byte[] bytes) {}
    record VersionInput(long pc, String destination, long word) {}
    record MmioInput(long pc, long address, long word) {}
    record Profile(String id, Map<String, Long> registers, Seed stack, List<Seed> memory,
                   List<VersionInput> versions, MmioInput mmio) {}
    record Region(String name, int offset, int size, int[] fields) {}
    static final List<Region> REGIONS = List.of(
        new Region("flags_a", 0x1560, 16, new int[]{4, 4, 8, 4}),
        new Region("flags_b", 0x16E0, 16, new int[]{4, 4, 8, 4}),
        new Region("ready", 0x3B890, 12, new int[]{4, 4}),
        new Region("processor", 0x3B8AC, 8, new int[]{2, 1}),
        new Region("control_mode", 0x3B920, 20, new int[]{4, 4, 12, 4}),
        new Region("diagnostic", 0xCCDB4, 12, new int[]{}),
        new Region("opaque", 0x3B480, 12, new int[]{}));

    static void check(boolean condition, String message) { StartupZeroObservations.check(condition, message); }
    static String hex(long value) { return StartupZeroObservations.hex(value); }
    static long word(JsonElement value) { return StartupZeroObservations.word(value); }
    static StartupZeroObservations.Span span(String name, long start, int size) {
        return new StartupZeroObservations.Span(name, start, size);
    }
    static List<String> registers() {
        List<String> result = new ArrayList<>();
        for (int i = 0; i < 24; i++) result.add("r" + i);
        result.addAll(List.of("gp", "sp", "lr", "r27", "r28", "r29", "sr", "pc"));
        return List.copyOf(result);
    }
    static boolean synthetic(StartupZeroObservations.Span region) {
        return (region.start() >= 0x24000000L && region.end() <= 0x25000000L)
            || (region.start() >= 0xE4000000L && region.end() <= 0xE5000000L);
    }
    static byte[] bytes(JsonElement value, int size) {
        String text = StartupZeroObservations.string(value);
        check(text.length() == size * 2 && text.matches("[0-9a-f]+"), "Invalid region bytes");
        return HexFormat.of().parseHex(text);
    }
    static JsonObject object(JsonElement value, Set<String> keys, String label) {
        return StartupZeroObservations.object(value, keys, label);
    }
    static JsonElement strictValue(com.google.gson.stream.JsonReader reader, int depth) throws Exception {
        check(depth <= 8, "Request nesting cap");
        switch (reader.peek()) {
            case BEGIN_OBJECT: {
                reader.beginObject(); JsonObject result = new JsonObject();
                while (reader.hasNext()) {
                    check(result.size() < 64, "Object member cap");
                    String name = reader.nextName(); check(!result.has(name), "Duplicate JSON member");
                    result.add(name, strictValue(reader, depth + 1));
                }
                reader.endObject(); return result;
            }
            case BEGIN_ARRAY: {
                reader.beginArray(); JsonArray result = new JsonArray();
                while (reader.hasNext()) { check(result.size() < 50, "Array cap"); result.add(strictValue(reader, depth + 1)); }
                reader.endArray(); return result;
            }
            case STRING: return new JsonPrimitive(reader.nextString());
            case NUMBER: return new JsonPrimitive(new java.math.BigDecimal(reader.nextString()));
            default: throw new IllegalStateException("Unsupported request value");
        }
    }
    static JsonObject parseRequest(String text) throws Exception {
        check(text.getBytes(StandardCharsets.UTF_8).length <= 262144, "Request byte cap");
        try (com.google.gson.stream.JsonReader reader = new com.google.gson.stream.JsonReader(new java.io.StringReader(text))) {
            reader.setLenient(false); JsonElement result = strictValue(reader, 0);
            check(reader.peek() == com.google.gson.stream.JsonToken.END_DOCUMENT && result.isJsonObject(), "Trailing or invalid request");
            return result.getAsJsonObject();
        }
    }
    static List<Profile> profiles(JsonObject request) {
        object(request, Set.of("schema_version", "source_sha256", "tool_sha256", "helper_sha256", "profiles"), "request");
        JsonElement schema = request.get("schema_version");
        check(schema.isJsonPrimitive() && schema.getAsJsonPrimitive().isNumber() && schema.getAsString().equals("1"), "Schema version");
        check(StartupZeroObservations.string(request.get("source_sha256")).equals(SOURCE), "Request source");
        for (String key : List.of("tool_sha256", "helper_sha256"))
            check(StartupZeroObservations.string(request.get(key)).matches("[0-9a-f]{64}"), "Tool digest");
        check(request.get("profiles").isJsonArray(), "Profiles array required");
        JsonArray entries = request.getAsJsonArray("profiles"); check(entries.size() > 0 && entries.size() <= 50, "Profile cap");
        List<Profile> result = new ArrayList<>(); Set<String> ids = new LinkedHashSet<>();
        Set<String> memoryNames = new LinkedHashSet<>(); REGIONS.forEach(r -> memoryNames.add(r.name));
        for (JsonElement value : entries) {
            JsonObject p = object(value, Set.of("id", "registers", "stack", "memory", "version_inputs", "mmio_inputs"), "profile");
            String id = StartupZeroObservations.string(p.get("id"));
            check(id.matches("[a-z0-9][a-z0-9-]{0,63}") && ids.add(id), "Invalid or duplicate profile ID");
            JsonObject registerValues = object(p.get("registers"), Set.copyOf(REGISTERS), "registers");
            Map<String, Long> registers = new LinkedHashMap<>();
            for (String name : REGISTERS) registers.put(name, word(registerValues.get(name)));
            long gp = registers.get("gp"), sp = registers.get("sp"), lr = registers.get("lr");
            check(registers.get("pc") == ENTRY && (sp & 3) == 0 && (gp & 3) == 0 && (lr & 1) == 0, "Entry or alignment");
            JsonObject stackValue = object(p.get("stack"), Set.of("address", "hex"), "stack");
            check(sp >= 64 && word(stackValue.get("address")) == sp - 64, "Stack geometry");
            Seed stack = new Seed(span("stack", sp - 64, 128), bytes(stackValue.get("hex"), 128));
            JsonObject memory = object(p.get("memory"), memoryNames, "memory"); List<Seed> seeds = new ArrayList<>();
            for (Region region : REGIONS) seeds.add(new Seed(span(region.name, gp + region.offset, region.size), bytes(memory.get(region.name), region.size)));
            List<Seed> all = new ArrayList<>(seeds); all.add(stack);
            for (int i = 0; i < all.size(); i++) {
                StartupZeroObservations.Span s = all.get(i).span;
                check(synthetic(s) && !s.overlaps(UNION) && !s.contains(lr, 1), "Synthetic region or sentinel overlap");
                for (int j = 0; j < i; j++) check(!s.overlaps(all.get(j).span), "Region overlap");
            }
            check(!UNION.contains(lr, 1) && !(lr >= 0x7C000000L && lr < 0x80000000L), "Invalid sentinel");
            check((seeds.get(5).bytes[4] & 255) <= 3, "Diagnostic byte outside quiet domain");
            check(p.get("version_inputs").isJsonArray() && p.get("mmio_inputs").isJsonArray(), "Observation arrays required");
            JsonArray vs = p.getAsJsonArray("version_inputs"), ms = p.getAsJsonArray("mmio_inputs");
            check((vs.size() == 1 && ms.size() == 1) || (vs.size() == 2 && ms.isEmpty()), "Conditional observation shape");
            List<VersionInput> versions = new ArrayList<>();
            for (int i = 0; i < vs.size(); i++) {
                JsonObject v = object(vs.get(i), Set.of("pc", "destination", "word"), "VERSION input");
                long pc = word(v.get("pc")); String destination = StartupZeroObservations.string(v.get("destination"));
                check(pc == (i == 0 ? VERSION1 : VERSION2) && destination.equals(i == 0 ? "r4" : "r2"), "VERSION site or destination");
                versions.add(new VersionInput(pc, destination, word(v.get("word"))));
            }
            MmioInput mmio = null;
            if (!ms.isEmpty()) {
                JsonObject m = object(ms.get(0), Set.of("pc", "address", "word"), "MMIO input");
                check(word(m.get("pc")) == MMIO_PC && word(m.get("address")) == MMIO_ADDRESS, "MMIO site or address");
                mmio = new MmioInput(MMIO_PC, MMIO_ADDRESS, word(m.get("word")));
            }
            result.add(new Profile(id, Map.copyOf(registers), stack, List.copyOf(seeds), List.copyOf(versions), mmio));
        }
        return List.copyOf(result);
    }
    static void split(List<StartupZeroObservations.Span> result, Seed seed, int[] fields) {
        int cursor = 0;
        for (int i = 0; i < fields.length; i += 2) {
            if (cursor < fields[i]) result.add(span(seed.span.name() + ".guard" + i, seed.span.start() + cursor, fields[i] - cursor));
            result.add(span(seed.span.name() + ".field" + i, seed.span.start() + fields[i], fields[i + 1]));
            cursor = fields[i] + fields[i + 1];
        }
        if (cursor < seed.span.size()) result.add(span(seed.span.name() + ".guard_end", seed.span.start() + cursor, seed.span.size() - cursor));
    }
    static List<StartupZeroObservations.Span> partition(Profile profile) {
        List<StartupZeroObservations.Span> result = new ArrayList<>();
        for (int i = 0; i < REGIONS.size(); i++) split(result, profile.memory.get(i), REGIONS.get(i).fields);
        split(result, profile.stack, new int[]{40, 24});
        return List.copyOf(result);
    }
    static Set<String> writable(Profile profile) {
        Set<String> result = new LinkedHashSet<>();
        for (StartupZeroObservations.Span s : partition(profile)) if (s.name().contains(".field")) result.add(s.name());
        return Set.copyOf(result);
    }
    static byte[] little(long value) { return ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt((int)value).array(); }

    static int decoderWidth(long pc, int length) {
        check(length == 2 || length == 4 || length == 6, "Unsupported admitted instruction length");
        if (pc == 0x0EC62334L || pc == 0x0EC6234AL || pc == 0x0EC62366L) {
            check(length == 6, "Decoder refill instruction length");
            return 13;
        }
        return Math.max(8, length + 3);
    }
    static final class Policy {
        final Profile profile;
        final StartupZeroObservations.Observer observer;
        final JsonArray events = new JsonArray(), versionEvents = new JsonArray();
        int step = -1, versionIndex, mmioCount;
        Policy(Profile profile) {
            this.profile = profile; List<StartupZeroObservations.Span> data = new ArrayList<>(partition(profile));
            data.add(TABLE); if (profile.mmio != null) data.add(span("mmio", MMIO_ADDRESS, 4));
            observer = new StartupZeroObservations.Observer(data, writable(profile));
        }
        void fail(RuntimeException failure) {
            observer.failed = true; if (observer.failure == null) observer.failure = failure.getMessage();
        }
        void begin(long pc, int nextStep, int length) {
            try {
                int width = decoderWidth(pc, length);
                check(nextStep == step + 1 && nextStep < 128 && UNION.contains(pc, width), "Step or decoder bound");
                observer.begin(pc, span("decode", pc, width)); step = nextStep;
            } catch (RuntimeException failure) { fail(failure); throw failure; }
        }
        void end() { observer.end(); }
        long consumeVersion(long pc, String destination) {
            try {
                check(observer.active && !observer.failed && observer.pc == pc && versionIndex < profile.versions.size(), "Unexpected VERSION callback");
                VersionInput input = profile.versions.get(versionIndex);
                check(input.pc == pc && input.destination.equals(destination), "VERSION sequence mismatch");
                JsonObject event = new JsonObject(); event.addProperty("index", versionIndex++); event.addProperty("step", step);
                event.addProperty("pc", hex(pc)); event.addProperty("destination", destination); event.addProperty("word", hex(input.word));
                versionEvents.add(event); return input.word;
            } catch (RuntimeException failure) { fail(failure); throw failure; }
        }
        void observe(EmulateExecutionState phase, boolean write, long location, int width, byte[] values) {
            try {
                if (!observer.active) return;
                check(!observer.failed && width > 0 && width <= 65536 && location >= 0
                    && location + width <= 0x100000000L && values.length >= width, "Access geometry");
                if (phase == EmulateExecutionState.INSTRUCTION_DECODE) {
                    check(observer.decoder.operations < 256 && observer.decoder.bytes <= 2048 - width, "Decoder budget");
                    observer.observe(phase, write, location, width, values); return;
                }
                check(phase == EmulateExecutionState.EXECUTE && observer.runtime.operations < 64
                    && observer.runtime.bytes <= 512 - width, "Runtime budget or phase");
                boolean mmio = location < 0x80000000L && location + width > 0x7C000000L;
                if (mmio) check(profile.mmio != null && !write && observer.pc == MMIO_PC
                    && location == MMIO_ADDRESS && width == 4 && mmioCount == 0
                    && Arrays.equals(Arrays.copyOf(values, 4), little(profile.mmio.word)), "Unexpected MMIO access");
                if (location < TABLE.end() && location + width > TABLE.start()) check(!write
                    && observer.pc == 0x0EC62230L && width == 2 && TABLE.contains(location, width)
                    && ((location - TABLE.start()) & 1) == 0, "Unexpected table access");
                observer.observe(phase, write, location, width, values);
                if (mmio) mmioCount++;
                JsonObject event = new JsonObject(); event.addProperty("index", events.size()); event.addProperty("step", step);
                event.addProperty("pc", hex(observer.pc)); event.addProperty("kind", write ? "write" : "read");
                event.addProperty("address", hex(location)); event.addProperty("size", width);
                event.addProperty("hex", HexFormat.of().formatHex(Arrays.copyOf(values, width))); events.add(event);
            } catch (RuntimeException failure) { fail(failure); throw failure; }
        }
        void finish() {
            try {
                check(!observer.active && !observer.failed && versionIndex == profile.versions.size()
                    && mmioCount == (profile.mmio == null ? 0 : 1), "Unconsumed observations or failed case");
            } catch (RuntimeException failure) { fail(failure); throw failure; }
        }
    }

    static String encodeOutput(JsonObject result) {
        String json = new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(result) + "\n";
        check(json.length() <= 1048576, "Output character cap"); return json;
    }

    static StartupZeroObservations.Geometry geometry() {
        return new StartupZeroObservations.Geometry(SOURCE, 2303104, 137, 52, 21, 0x231D50, 46,
            List.of(
                new StartupZeroObservations.Source(span("entry", ENTRY, 22), 0x61C1C,
                    "73839f44927b7f4732e9b30e5be6b7071a8d9c978ed1a9bdaca0462b4f6628f7", true),
                new StartupZeroObservations.Source(span("recognized", 0x0EC6227CL, 182), 0x61C7C,
                    "233e2362d8d3e991aef4c1232861d6965eee43793f5fc653cfdc2c1482267349", true),
                new StartupZeroObservations.Source(span("default", VERSION2, 64), 0x61D32,
                    "3049de857385368f7e0ddce054581921a1fa9895858265bed2e3d65f3a6fc995", true),
                new StartupZeroObservations.Source(TABLE, 0x61C32,
                    "d6acbd437cd60a2e08e85dfe5cc12ce35f2726c159501c4e1f36d011aefa9e6d", false)),
            List.of(new StartupZeroObservations.Source(UNION, 0x61C1C,
                "8b568159877f4b1e42ea444c2a751d5e901b3f0d69ea58ca51ee35ea1b465f24", true)), List.of());
    }
    static void versionOperation(int opcode, Varnode output, Varnode[] inputs, long pc) {
        check(pc == VERSION1 || pc == VERSION2, "Unadmitted VERSION site");
        check(opcode == PcodeOp.CALLOTHER && inputs.length == 1 && inputs[0].isConstant()
            && inputs[0].getSize() == 4 && inputs[0].getOffset() == 1 && output != null
            && output.getAddress().getAddressSpace().isRegisterSpace() && output.getSize() == 4
            && output.getOffset() == (pc == VERSION1 ? 16 : 8), "VERSION operation shape");
    }
    private void listingPreflight() {
        for (long pc = UNION.start(); pc < UNION.end(); pc++) {
            Instruction instruction = getInstructionAt(toAddr(pc));
            if (instruction != null) check(instruction.getLength() >= 2 && instruction.getLength() <= 10
                && (instruction.getLength() & 1) == 0 && UNION.contains(pc, instruction.getLength()), "Listing crosses admitted union");
        }
    }
    private String decode(StartupZeroObservations.Admission admission) throws Exception {
        int operations = 0; StartupZeroObservations.Source envelope = admission.geometry.envelopes().get(0);
        for (StartupZeroObservations.Source source : admission.geometry.sources()) {
            if (!source.executable()) continue;
            for (long pc = source.span().start(); pc < source.span().end();) {
                monitor.checkCancelled(); check(admission.sites.size() < 92, "Site cap");
                byte[] remaining = Arrays.copyOfRange(admission.original.get(source), (int)(pc - source.span().start()), source.span().size());
                JsonObject before = StartupZeroObservations.programContext(currentProgram, toAddr(pc));
                Instruction instruction = new PseudoDisassembler(currentProgram).disassemble(toAddr(pc), remaining);
                check(instruction != null && instruction.getAddress().equals(toAddr(pc)), "Detached decode address");
                admission.contextPolicy.detached(currentProgram, instruction);
                int length = instruction.getLength();
                check(source.span().contains(pc, length) && UNION.contains(pc, decoderWidth(pc, length)), "Instruction source bound");
                check(instruction.getDelaySlotDepth() == 0 && !instruction.isInDelaySlot()
                    && !instruction.getPrototype().hasDelaySlots() && !instruction.getPrototype().hasNext2Dependency(), "Decode dependency");
                check(Arrays.equals(instruction.getBytes(), Arrays.copyOf(remaining, length)), "Decoded bytes differ");
                PcodeOp[] code = instruction.getPcode();
                for (PcodeOp operation : code) {
                    check(++operations <= 4096 && operation.getNumInputs() <= 32, "Static operation cap");
                    check(operation.getOpcode() != PcodeOp.UNIMPLEMENTED, "Unimplemented operation");
                    if (operation.getOpcode() == PcodeOp.CALLOTHER) {
                        check(code.length == 1 && length == 2 && instruction.getFallThrough().equals(toAddr(pc + 2)), "VERSION instruction shape");
                        versionOperation(operation.getOpcode(), operation.getOutput(), operation.getInputs(), pc);
                        check("version".equals(currentProgram.getLanguage().getUserDefinedOpName(1)), "VERSION userop identity");
                    }
                }
                check(!instruction.getMnemonicString().toLowerCase(java.util.Locale.ROOT).startsWith("v")
                    || pc == VERSION1 || pc == VERSION2, "Vector instruction");
                check(before.equals(StartupZeroObservations.programContext(currentProgram, toAddr(pc))), "Decode changes context");
                check(admission.sites.put(pc, new StartupZeroObservations.Site(instruction, instruction.getBytes(), source, envelope)) == null, "Duplicate site");
                pc += length;
            }
        }
        check(admission.sites.size() == 81 && operations == 244, "Static site or operation count");
        MessageDigest hash = StartupZeroObservations.sha();
        hash.update("open27xx-soc-static-pcode-v1\0".getBytes(StandardCharsets.US_ASCII));
        admission.sites.forEach((pc, site) -> {
            hash.update(ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN).putInt((int)(long)pc).putInt(site.bytes().length).array());
            hash.update(HexFormat.of().parseHex(StartupZeroObservations.digest(StartupZeroObservations.pcodeEncoding(site.instruction()))));
        });
        String aggregate = HexFormat.of().formatHex(hash.digest()); check(aggregate.equals(PCODE), "Static p-code binding mismatch");
        admission.unchanged(); return aggregate;
    }
    static final class DecoderTraceBuffer extends ByteMemBufferImpl {
        final JsonArray reads = new JsonArray();
        final int available;
        int totalBytes, envelopeBytes;
        boolean failed;
        DecoderTraceBuffer(Address pc, byte[] bytes) {
            super(pc, bytes.clone(), false); available = bytes.length;
        }
        @Override public int getBytes(byte[] target, int offset) {
            try {
                check(!failed && offset >= 0 && target.length > 0 && offset <= available - target.length
                    && reads.size() < 32 && totalBytes <= 512 - target.length, "Decoder trace read bound");
                int count = super.getBytes(target, offset); check(count == target.length, "Incomplete decoder trace read");
                JsonObject read = new JsonObject(); read.addProperty("address", hex(getAddress().getOffset() + offset));
                read.addProperty("size", count); reads.add(read); totalBytes += count;
                envelopeBytes = Math.max(envelopeBytes, offset + count); return count;
            } catch (RuntimeException failure) { failed = true; throw failure; }
        }
        @Override public byte getByte(int offset) throws MemoryAccessException {
            byte[] value = new byte[1]; getBytes(value, offset); return value[0];
        }
    }
    private JsonArray traceDecoder(StartupZeroObservations.Admission admission) throws Exception {
        byte[] union = admission.original.get(admission.geometry.envelopes().get(0));
        check(union.length == UNION.size() && admission.sites.size() == 81, "Decoder trace source bound");
        Register contextRegister = currentProgram.getLanguage().getContextBaseRegister();
        JsonArray result = new JsonArray();
        for (Map.Entry<Long, StartupZeroObservations.Site> entry : admission.sites.entrySet()) {
            monitor.checkCancelled(); long pc = entry.getKey(); StartupZeroObservations.Site site = entry.getValue();
            JsonObject before = StartupZeroObservations.programContext(currentProgram, toAddr(pc));
            RegisterValue inputContext = pc == ENTRY ? null : new RegisterValue(contextRegister);
            admission.contextPolicy.boundary(inputContext, pc == ENTRY);
            DecoderTraceBuffer buffer = new DecoderTraceBuffer(toAddr(pc), Arrays.copyOfRange(union, (int)(pc - UNION.start()), union.length));
            Disassembler disassembler = Disassembler.getDisassembler(currentProgram.getLanguage(), currentProgram.getAddressFactory(), monitor, null);
            InstructionBlock block = disassembler.pseudoDisassembleBlock(buffer, inputContext, 1);
            check(!buffer.failed && block != null && block.getInstructionCount() == 1 && block.getInstructionConflict() == null,
                "Decoder trace block failure at " + hex(pc));
            Instruction instruction = block.getInstructionAt(toAddr(pc));
            check(instruction != null && instruction.getLength() == site.bytes().length
                && Arrays.equals(instruction.getBytes(), site.bytes()), "Decoder trace instruction mismatch");
            admission.contextPolicy.detached(currentProgram, instruction);
            byte[] code = StartupZeroObservations.pcodeEncoding(instruction);
            check(Arrays.equals(code, StartupZeroObservations.pcodeEncoding(site.instruction())), "Decoder trace p-code mismatch");
            check(StartupZeroObservations.context(instruction.getRegisterValue(contextRegister))
                .equals(StartupZeroObservations.context(site.instruction().getRegisterValue(contextRegister))), "Decoder trace context mismatch");
            check(!buffer.failed && buffer.reads.size() > 0 && UNION.contains(pc, buffer.envelopeBytes)
                && before.equals(StartupZeroObservations.programContext(currentProgram, toAddr(pc))), "Decoder trace preservation");
            JsonObject row = new JsonObject(); row.addProperty("pc", hex(pc)); row.addProperty("length", instruction.getLength());
            row.addProperty("pcode_sha256", StartupZeroObservations.digest(code)); row.add("input_context", StartupZeroObservations.context(inputContext));
            row.add("instruction_context", StartupZeroObservations.context(instruction.getRegisterValue(contextRegister)));
            row.add("reads", buffer.reads); row.addProperty("read_bytes", buffer.totalBytes);
            row.addProperty("envelope_start", hex(pc)); row.addProperty("envelope_bytes", buffer.envelopeBytes);
            result.add(row);
        }
        check(result.size() == 81, "Decoder trace count"); admission.unchanged(); return result;
    }
    static final class ContextPool {
        final JsonArray values = new JsonArray();
        final Map<String, Integer> ids = new LinkedHashMap<>();
        int id(JsonElement value) {
            String key = value.toString(); Integer present = ids.get(key); if (present != null) return present;
            check(values.size() < 2, "Context form cap"); int id = values.size(); values.add(value); ids.put(key, id); return id;
        }
    }
    private JsonObject registers(EmulatorHelper emulator) {
        JsonObject result = new JsonObject();
        for (String name : REGISTERS) result.addProperty(name, hex(emulator.readRegister(name).longValue() & 0xFFFFFFFFL));
        return result;
    }
    private void seed(EmulatorHelper emulator, Seed seed) {
        emulator.writeMemory(toAddr(seed.span.start()), seed.bytes);
        check(Arrays.equals(seed.bytes, emulator.readMemory(toAddr(seed.span.start()), seed.span.size())), "Seed readback mismatch");
    }
    private JsonObject capture(StartupZeroObservations.Admission admission, Profile profile, ContextPool contexts) throws Exception {
        admission.unchanged();
        check(currentProgram.getMemory().getBlock(toAddr(profile.registers.get("lr"))) == null, "Return sentinel is mapped");
        List<Seed> seeds = new ArrayList<>(profile.memory); seeds.add(profile.stack);
        for (Seed seed : seeds) for (ghidra.program.model.mem.MemoryBlock block : currentProgram.getMemory().getBlocks())
            check(seed.span.end() <= block.getStart().getOffset() || seed.span.start() > block.getEnd().getOffset(), "Synthetic seed overlaps mapped memory");
        Set<String> aliases = new LinkedHashSet<>();
        for (String name : REGISTERS) {
            Register register = currentProgram.getRegister(name);
            check(register != null && register.getBitLength() == 32 && !register.isProcessorContext()
                && aliases.add(register.getAddress().toString()), "Register binding");
        }
        Policy policy = new Policy(profile); EmulatorHelper emulator = new EmulatorHelper(currentProgram);
        int steps = 0; long last = -1;
        try {
            emulator.setMemoryFaultHandler(new MemoryFaultHandler() {
                public boolean uninitializedRead(Address address, int size, byte[] buffer, int offset) {
                    IllegalStateException failure = new IllegalStateException("Uninitialized memory " + address + " width " + size);
                    policy.fail(failure); throw failure;
                }
                public boolean unknownAddress(Address address, boolean write) {
                    IllegalStateException failure = new IllegalStateException("Unknown memory " + address);
                    policy.fail(failure); throw failure;
                }
            });
            emulator.getEmulator().addMemoryAccessFilter(new MemoryAccessFilter() {
                private void access(AddressSpace space, boolean write, long offset, int size, byte[] values) {
                    if (!space.isMemorySpace()) return;
                    try {
                        check(space.equals(currentProgram.getAddressFactory().getDefaultAddressSpace()), "Nondefault memory space");
                        policy.observe(emulator.getEmulateExecutionState(), write, offset, size, values);
                    } catch (RuntimeException failure) { policy.fail(failure); throw failure; }
                }
                protected void processRead(AddressSpace space, long offset, int size, byte[] values) { access(space, false, offset, size, values); }
                protected void processWrite(AddressSpace space, long offset, int size, byte[] values) { access(space, true, offset, size, values); }
            });
            emulator.registerCallOtherCallback("version", new BreakCallBack() {
                public boolean pcodeCallback(PcodeOpRaw operation) {
                    try {
                        long pc = emulator.getExecutionAddress().getOffset();
                        check(operation.getAddress().equals(toAddr(pc)), "VERSION execution address");
                        Varnode[] inputs = new Varnode[operation.getNumInputs()];
                        for (int i = 0; i < inputs.length; i++) inputs[i] = operation.getInput(i);
                        versionOperation(operation.getOpcode(), operation.getOutput(), inputs, pc);
                        long value = policy.consumeVersion(pc, pc == VERSION1 ? "r4" : "r2");
                        emulate.getMemoryState().setValue(operation.getOutput(), value); return true;
                    } catch (RuntimeException failure) { policy.fail(failure); throw failure; }
                }
            });
            JsonObject result = new JsonObject(); result.addProperty("id", profile.id);
            admission.contextPolicy.boundary(emulator.getEmulator().getContextRegisterValue(), true);
            result.addProperty("context_before_seed", contexts.id(StartupZeroObservations.context(emulator.getEmulator().getContextRegisterValue())));
            for (String name : REGISTERS) emulator.writeRegister(name, profile.registers.get(name));
            for (Seed memory : profile.memory) seed(emulator, memory); seed(emulator, profile.stack);
            if (profile.mmio != null) seed(emulator, new Seed(span("mmio", MMIO_ADDRESS, 4), little(profile.mmio.word)));
            admission.contextPolicy.boundary(emulator.getEmulator().getContextRegisterValue(), true);
            JsonObject initial = registers(emulator); result.add("initial_registers", initial);
            for (String name : REGISTERS) check(word(initial.get(name)) == profile.registers.get(name), "Register seed readback");
            JsonObject initialMemory = new JsonObject(); for (Seed memory : profile.memory) initialMemory.addProperty(memory.span.name(), HexFormat.of().formatHex(memory.bytes));
            result.add("initial_memory", initialMemory); result.addProperty("stack_initial_hex", HexFormat.of().formatHex(profile.stack.bytes));
            Map<Long, Long> counts = new TreeMap<>(); Map<String, JsonObject> transitions = new LinkedHashMap<>();
            while (emulator.getExecutionAddress().getOffset() != profile.registers.get("lr")) {
                monitor.checkCancelled(); long pc = emulator.getExecutionAddress().getOffset();
                check(steps < 128, "Instruction budget"); StartupZeroObservations.Site site = admission.sites.get(pc);
                check(site != null, "Execution leaves admitted sites at " + hex(pc));
                check(Arrays.equals(site.bytes(), emulator.readMemory(toAddr(pc), site.bytes().length)), "Instruction bytes changed");
                for (PcodeOp operation : site.instruction().getPcode()) check(operation.getOpcode() != PcodeOp.CALL
                    && operation.getOpcode() != PcodeOp.CALLIND, "Diagnostic call is outside the quiet domain");
                admission.contextPolicy.boundary(emulator.getEmulator().getContextRegisterValue(), steps == 0);
                int before = contexts.id(StartupZeroObservations.context(emulator.getEmulator().getContextRegisterValue()));
                int previousVersion = policy.versionIndex; policy.begin(pc, steps, site.bytes().length);
                try { check(emulator.step(monitor), "Emulation failed: " + (policy.observer.failure == null ? emulator.getLastError() : policy.observer.failure)); }
                finally { policy.end(); }
                check(!policy.observer.failed, "Invalid observation");
                long next = emulator.getExecutionAddress().getOffset();
                boolean version = pc == VERSION1 || pc == VERSION2;
                check(policy.versionIndex == previousVersion + (version ? 1 : 0), "VERSION consumption count");
                if (version) check(next == pc + 2, "VERSION natural fallthrough");
                admission.contextPolicy.boundary(emulator.getEmulator().getContextRegisterValue(), false);
                int after = contexts.id(StartupZeroObservations.context(emulator.getEmulator().getContextRegisterValue()));
                String key = hex(pc) + ":" + before + ":" + after;
                JsonObject transition = transitions.get(key);
                if (transition == null) {
                    check(transitions.size() < 162, "Context transition cap"); transition = new JsonObject();
                    transition.addProperty("pc", hex(pc)); transition.addProperty("before", before); transition.addProperty("after", after);
                    transition.addProperty("count", 0); transitions.put(key, transition);
                }
                transition.addProperty("count", transition.get("count").getAsInt() + 1);
                counts.merge(pc, 1L, Math::addExact); steps++; last = pc;
                if (next == profile.registers.get("lr")) check(pc == TERMINAL
                    && Arrays.stream(site.instruction().getPcode()).anyMatch(op -> op.getOpcode() == PcodeOp.RETURN), "Sentinel without terminal RETURN");
                else check(admission.sites.containsKey(next), "Unadmitted next PC " + hex(next));
            }
            check(steps > 0 && last == TERMINAL, "Missing terminal return"); policy.finish();
            result.addProperty("completed_instructions", steps); result.addProperty("last_pc", hex(last));
            result.addProperty("return_reason", "terminal_return"); result.add("registers", registers(emulator));
            result.addProperty("context_after_return", contexts.id(StartupZeroObservations.context(emulator.getEmulator().getContextRegisterValue())));
            JsonObject perPc = new JsonObject(); counts.forEach((pc, count) -> perPc.addProperty(hex(pc), count)); result.add("per_pc", perPc);
            JsonArray variants = new JsonArray(); transitions.values().forEach(variants::add); result.add("contexts", variants);
            long eventsBefore = policy.observer.runtime.operations; String digestBefore = policy.observer.runtime.digest();
            JsonObject finalMemory = new JsonObject(); List<Seed> all = new ArrayList<>(profile.memory); all.add(profile.stack);
            for (Seed seed : all) {
                byte[] actual = emulator.readMemory(toAddr(seed.span.start()), seed.span.size()); check(actual != null && actual.length == seed.bytes.length, "Final readback");
                for (StartupZeroObservations.Span guard : partition(profile)) if (!writable(profile).contains(guard.name())
                        && seed.span.contains(guard.start(), guard.size())) {
                    int offset = (int)(guard.start() - seed.span.start());
                    check(Arrays.equals(Arrays.copyOfRange(seed.bytes, offset, offset + guard.size()), Arrays.copyOfRange(actual, offset, offset + guard.size())), "Read-only guard changed");
                }
                if (seed == profile.stack) result.addProperty("stack_hex", HexFormat.of().formatHex(actual));
                else finalMemory.addProperty(seed.span.name(), HexFormat.of().formatHex(actual));
            }
            result.add("memory", finalMemory);
            for (Map.Entry<StartupZeroObservations.Source, byte[]> source : admission.original.entrySet()) check(Arrays.equals(source.getValue(),
                emulator.readMemory(toAddr(source.getKey().span().start()), source.getKey().span().size())), "Emulator source changed");
            if (profile.mmio != null) check(Arrays.equals(little(profile.mmio.word), emulator.readMemory(toAddr(MMIO_ADDRESS), 4)), "MMIO seed changed");
            check(eventsBefore == policy.observer.runtime.operations && digestBefore.equals(policy.observer.runtime.digest()), "Readback entered runtime stream");
            result.add("data_events", policy.events); result.add("version_events", policy.versionEvents);
            JsonObject accesses = new JsonObject(); accesses.add("data_stream", policy.observer.runtime.json()); accesses.add("decoder_stream", policy.observer.decoder.json());
            result.add("accesses", accesses); admission.unchanged();
            result.addProperty("program_source_listing_context_unchanged", true); result.addProperty("emulator_sources_unchanged", true);
            return result;
        } catch (Exception failure) {
            throw new IllegalStateException(profile.id + " PC " + hex(policy.observer.pc) + " steps " + steps + ": " + failure.getMessage(), failure);
        } finally { emulator.dispose(); }
    }

    static final Map<String, String> MODULE = Map.ofEntries(
        Map.entry("data/languages/vc4.cspec", "c0bb18dc4057e7f94f9579f4ecca6de8de70974a6d9e3e24bce9ab1ea503f2ca"),
        Map.entry("data/languages/vc4.ldefs", "096641cff0203e0f7f2e5c568d1ef7bc3c9c4923bda3138e5009c06fc2e19850"),
        Map.entry("data/languages/vc4.opinion", "82d118a436e87164dbc75f892d3c2eaf2e91c619597fa5663ac31416a9d7cd01"),
        Map.entry("data/languages/vc4.pspec", "02d6a7c0095d942ec5acff9f8cc90c84f680101255a2ac008cf265610b69c810"),
        Map.entry("data/languages/vc4.sla", "2303eea79ede697a37318068af1514de75ff64d9fcf2965623e2ab417e93bb56"),
        Map.entry("data/languages/vc4.slaspec", "a3cc3f596d63a268440a659baa6fcf92e15900ec7ca1b8c2c733203d45236131"),
        Map.entry("extension.properties", "02920d405faa1eca9b40e4e0bb0dc0b47e4278327ea89ef74bbaeafdeb92084f"),
        Map.entry("lib/VideoCoreIV.jar", "c6deada2fac53b8ea6523dbda77597b128006674616f140f04df23264c6d1aa3"));
    private JsonObject moduleEvidence() throws Exception {
        check(Application.getApplicationVersion().equals("12.2") && currentProgram.getLanguageID().toString().equals("vc4:LE:32:default")
            && currentProgram.getCompilerSpec().getCompilerSpecID().toString().equals("default"), "Runtime language binding");
        check(currentProgram.getRegister("LowBitCodeMode") == null, "Low-bit code mode");
        SleighLanguage language = (SleighLanguage)currentProgram.getLanguage();
        Path sla = Path.of(language.getLanguageDescription().getLanguageFile().getSlaFile().getAbsolutePath()).toRealPath();
        Path module = sla.getParent().getParent().getParent();
        check(sla.equals(module.resolve("data/languages/vc4.sla").toRealPath()), "Loaded SLA path");
        JsonObject result = new JsonObject();
        for (String name : new java.util.TreeSet<>(MODULE.keySet())) {
            String digest = StartupZeroObservations.digest(Files.readAllBytes(module.resolve(name)));
            check(digest.equals(MODULE.get(name)), "Module digest: " + name); result.addProperty(name, digest);
        }
        return result;
    }
    private JsonObject apiEvidence() throws Exception {
        Map<String, String> expected = Map.of(
            "Emulation.jar", "77e57fb79721ffb04677de4334a4b500175ce31979c8c1a2f6cf08444c8dafcf",
            "SoftwareModeling.jar", "eeef2e265dde1c15e8bed2fb1d072f468fbd417985b4cb1c889045afff470821",
            "Base.jar", "5c84cdc76fa482f1c2a116b7ced52e581aaadb858a2312ec4bfa38d68b7f9121");
        JsonObject result = new JsonObject();
        for (Class<?> type : List.of(EmulatorHelper.class, PseudoDisassembler.class, GhidraScript.class)) {
            Path jar = Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
            check(Files.isRegularFile(jar) && Files.size(jar) <= 268435456, "API archive bound");
            MessageDigest hash = StartupZeroObservations.sha();
            try (java.io.InputStream stream = Files.newInputStream(jar)) {
                byte[] buffer = new byte[65536]; int size;
                while ((size = stream.read(buffer)) >= 0) hash.update(buffer, 0, size);
            }
            String digest = HexFormat.of().formatHex(hash.digest()), name = jar.getFileName().toString();
            check(digest.equals(expected.get(name)), "Loaded API digest"); result.addProperty(name, digest);
        }
        return result;
    }
    public void run() throws Exception {
        String[] args = getScriptArgs(); boolean trace = args.length == 3 && args[0].equals("trace-decoder");
        check(args.length == 2 || trace, "Expected optional trace-decoder, request and output paths");
        int first = trace ? 1 : 0;
        Path requestPath = Path.of(args[first]), output = Path.of(args[first + 1]); check(!Files.exists(output), "Output exists");
        check(Files.size(requestPath) <= 262144, "Request byte cap"); byte[] requestBytes = Files.readAllBytes(requestPath);
        JsonObject request = parseRequest(new String(requestBytes, StandardCharsets.UTF_8)); List<Profile> profiles = profiles(request);
        Path script = Path.of(getSourceFile().getAbsolutePath()), helper = script.resolveSibling("StartupZeroObservations.java");
        String toolHash = StartupZeroObservations.digest(Files.readAllBytes(script)), helperHash = StartupZeroObservations.digest(Files.readAllBytes(helper));
        check(toolHash.equals(request.get("tool_sha256").getAsString()) && helperHash.equals(request.get("helper_sha256").getAsString()), "Tool/helper digest");
        JsonObject result = new JsonObject(); result.addProperty("schema_version", 1); result.addProperty("source_file", "start4.elf");
        result.addProperty("source_version", VERSION); result.addProperty("source_sha256", SOURCE); result.addProperty("source_export_sha256", SOURCE_EXPORT);
        result.addProperty("request_sha256", StartupZeroObservations.digest(requestBytes)); result.addProperty("tool_sha256", toolHash); result.addProperty("helper_sha256", helperHash);
        result.addProperty("ghidra_version", Application.getApplicationVersion()); result.addProperty("java_version", System.getProperty("java.version"));
        result.add("module_sha256", moduleEvidence()); result.add("loaded_api_sha256", apiEvidence());
        listingPreflight(); StartupZeroObservations.Admission admission = new StartupZeroObservations.Admission(currentProgram, geometry(), monitor,
            new StartupZeroObservations.Vc4ContextPolicy());
        result.addProperty("static_pcode_sha256", decode(admission)); result.add("source_ranges", admission.sourceEvidence);
        result.add("sites", StartupZeroObservations.siteEvidence(admission));
        result.addProperty("initial_program_snapshot_sha256", StartupZeroObservations.digest(admission.initialSnapshot.toString().getBytes(StandardCharsets.UTF_8)));
        if (trace) {
            result.add("decoder_traces", traceDecoder(admission)); result.addProperty("decoder_trace_completed", true);
            result.addProperty("pcode_executed", false);
        } else {
            ContextPool contexts = new ContextPool(); JsonArray cases = new JsonArray();
            for (Profile profile : profiles) cases.add(capture(admission, profile, contexts));
            result.add("cases", cases); result.add("context_forms", contexts.values); result.addProperty("capture_completed", true);
        }
        result.addProperty("expected_result_comparison", "not_performed"); admission.unchanged();
        check(result.get("module_sha256").equals(moduleEvidence()) && result.get("loaded_api_sha256").equals(apiEvidence())
            && toolHash.equals(StartupZeroObservations.digest(Files.readAllBytes(script)))
            && helperHash.equals(StartupZeroObservations.digest(Files.readAllBytes(helper))), "Final tool binding");
        Files.writeString(output, encodeOutput(result), StandardOpenOption.CREATE_NEW);
        println(trace ? "SOC_INITIALIZATION_DECODER_TRACE_OK" : "SOC_INITIALIZATION_CAPTURE_OK");
    }
}
