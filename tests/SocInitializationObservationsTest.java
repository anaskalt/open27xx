// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import java.lang.reflect.Proxy;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

import com.google.gson.JsonArray;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import ghidra.app.plugin.processors.sleigh.ParserWalker;
import ghidra.app.plugin.processors.sleigh.pattern.PatternBlock;
import ghidra.app.util.PseudoInstruction;
import ghidra.pcode.emulate.EmulateExecutionState;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.address.GenericAddressSpace;
import ghidra.program.model.lang.InstructionPrototype;
import ghidra.program.model.lang.Register;
import ghidra.program.model.lang.RegisterValue;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.ByteMemBufferImpl;
import ghidra.program.model.mem.MemoryAccessException;
import ghidra.program.model.mem.WrappedMemBuffer;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;

public class SocInitializationObservationsTest {
    private static final String SOURCE =
        "38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb";
    private static final long ENTRY = 0x0EC6221CL, FIRST = 0x0EC6221EL;
    private static final long SECOND = 0x0EC62332L, SWITCH = 0x0EC62230L;
    private static final long TABLE = 0x0EC62232L, LOAD = 0x0EC6230EL;
    private static final long MMIO = 0x7E0000B4L, GP = 0x24020000L;
    private static final long SP = 0x24010080L, STOP = 0x24000000L;
    private static final long V1 = 0xA5000123L, V2 = 0xFFFFFFBFL, M = 0xA5B6C701L;
    private static final String[] NAMES = {
        "flags_a", "flags_b", "ready", "processor", "control_mode", "diagnostic", "opaque"
    };
    private static final int[] OFFSETS = {0x1560, 0x16E0, 0x3B890, 0x3B8AC, 0x3B920, 0xCCDB4, 0x3B480};
    private static final int[] SIZES = {16, 16, 12, 8, 20, 12, 12};
    private static int assertions, rejections;

    interface Action { void run() throws Exception; }
    static void require(boolean value, String label) {
        assertions++;
        if (!value) throw new AssertionError(label);
    }
    static void rejected(Action action, String label) throws Exception {
        try { action.run(); }
        catch (IllegalStateException expected) { assertions++; rejections++; return; }
        throw new AssertionError("Accepted: " + label);
    }
    static void rejectedJson(Action action, String label) throws Exception {
        try { action.run(); }
        catch (IllegalStateException | java.io.IOException expected) { assertions++; rejections++; return; }
        throw new AssertionError("Accepted JSON: " + label);
    }
    static String hex(long value) { return String.format("0x%08X", value); }
    static byte[] word(long value) {
        return ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt((int)value).array();
    }
    static JsonObject version(long pc, String destination, long value) {
        JsonObject input = new JsonObject();
        input.addProperty("pc", hex(pc)); input.addProperty("destination", destination);
        input.addProperty("word", hex(value)); return input;
    }
    static JsonObject profileJson(boolean withMmio) {
        JsonObject profile = new JsonObject(); profile.addProperty("id", withMmio ? "quiet-mmio" : "quiet-version");
        JsonObject registers = new JsonObject();
        for (int i = 0; i < 24; i++) registers.addProperty("r" + i, hex(0x11110000L + i * 0x101));
        registers.addProperty("gp", hex(GP)); registers.addProperty("sp", hex(SP));
        registers.addProperty("lr", hex(STOP)); registers.addProperty("r27", "0x27272727");
        registers.addProperty("r28", "0x28282828"); registers.addProperty("r29", "0x29292929");
        registers.addProperty("sr", "0x13579BDA"); registers.addProperty("pc", hex(ENTRY));
        profile.add("registers", registers);
        JsonObject stack = new JsonObject(); stack.addProperty("address", hex(SP - 64));
        stack.addProperty("hex", "a5".repeat(128)); profile.add("stack", stack);
        JsonObject memory = new JsonObject();
        for (int i = 0; i < NAMES.length; i++) {
            byte[] bytes = new byte[SIZES[i]]; Arrays.fill(bytes, (byte)(0x80 + i));
            if (NAMES[i].equals("diagnostic")) bytes[4] = 3;
            memory.addProperty(NAMES[i], HexFormat.of().formatHex(bytes));
        }
        profile.add("memory", memory);
        JsonArray versions = new JsonArray(); versions.add(version(FIRST, "r4", V1));
        if (!withMmio) versions.add(version(SECOND, "r2", V2));
        profile.add("version_inputs", versions);
        JsonArray mmio = new JsonArray();
        if (withMmio) {
            JsonObject input = new JsonObject(); input.addProperty("pc", hex(LOAD));
            input.addProperty("address", hex(MMIO)); input.addProperty("word", hex(M)); mmio.add(input);
        }
        profile.add("mmio_inputs", mmio); return profile;
    }
    static JsonObject request(JsonObject profile) {
        JsonObject input = new JsonObject(); input.addProperty("schema_version", 1);
        input.addProperty("source_sha256", SOURCE); input.addProperty("tool_sha256", "1".repeat(64));
        input.addProperty("helper_sha256", "2".repeat(64));
        JsonArray profiles = new JsonArray(); profiles.add(profile); input.add("profiles", profiles); return input;
    }
    static CaptureSocInitialization.Profile profile(boolean withMmio) {
        return CaptureSocInitialization.profiles(request(profileJson(withMmio))).get(0);
    }
    static void invalid(Consumer<JsonObject> mutation, String label) throws Exception {
        JsonObject input = request(profileJson(false)); mutation.accept(input);
        rejected(() -> CaptureSocInitialization.profiles(input), label);
    }
    static void invalidProfile(Consumer<JsonObject> mutation, String label) throws Exception {
        invalid(input -> mutation.accept(input.getAsJsonArray("profiles").get(0).getAsJsonObject()), label);
    }
    static void moveStack(JsonObject p, long sp) {
        p.getAsJsonObject("registers").addProperty("sp", hex(sp));
        p.getAsJsonObject("stack").addProperty("address", hex(sp - 64));
    }

    static void requestTests() throws Exception {
        for (boolean withMmio : new boolean[]{false, true}) {
            JsonObject input = request(profileJson(withMmio)); String before = input.toString();
            var profiles = CaptureSocInitialization.profiles(CaptureSocInitialization.parseRequest(before));
            var p = profiles.get(0);
            require(profiles.size() == 1 && p.registers().size() == 32, "Complete scalar seed");
            require(p.registers().get("gp") == GP && p.registers().get("sp") == SP, "Address seeds");
            require(p.stack().span().start() == SP - 64 && p.stack().bytes().length == 128, "Guarded stack");
            require(p.memory().size() == 7, "Seven guarded data regions");
            for (int i = 0; i < NAMES.length; i++) {
                final String name = NAMES[i];
                var seed = p.memory().stream().filter(s -> s.span().name().equals(name)).findFirst().orElseThrow();
                require(seed.span().start() == GP + OFFSETS[i] && seed.span().size() == SIZES[i]
                    && seed.bytes().length == SIZES[i], "Bound region " + name);
            }
            require(p.versions().size() == (withMmio ? 1 : 2), "Conditional VERSION count");
            require(p.versions().get(0).pc() == FIRST && p.versions().get(0).word() == V1
                && p.versions().get(0).destination().equals("r4"), "First independent VERSION");
            if (!withMmio) require(p.versions().get(1).word() == V2, "Second independent VERSION");
            require((p.mmio() != null) == withMmio, "Conditional MMIO declaration");
            if (withMmio) require(p.mmio().pc() == LOAD && p.mmio().address() == MMIO
                && p.mmio().word() == M, "Exact MMIO input");
            require(input.toString().equals(before), "Parsing preserves request");
        }
        JsonObject fifty = request(profileJson(false)); JsonArray cases = new JsonArray();
        for (int i = 0; i < 50; i++) {
            JsonObject p = profileJson((i & 1) == 0); p.addProperty("id", "quiet-" + i); cases.add(p);
        }
        fifty.add("profiles", cases);
        require(CaptureSocInitialization.profiles(fifty).size() == 50, "Fifty-profile boundary");
        JsonObject extra = profileJson(false); extra.addProperty("id", "quiet-extra"); cases.add(extra);
        rejected(() -> CaptureSocInitialization.profiles(fifty), "Profile count above fifty");
        invalid(p -> p.add("profiles", new JsonArray()), "Empty profiles");
        invalid(p -> p.getAsJsonArray("profiles").add(p.getAsJsonArray("profiles").get(0).deepCopy()), "Duplicate ID");
        invalid(p -> p.addProperty("schema_version", "1"), "String schema version");
        invalid(p -> p.addProperty("schema_version", 2), "Wrong schema version");
        invalid(p -> p.addProperty("source_sha256", "0".repeat(64)), "Source mismatch");
        for (String field : List.of("tool_sha256", "helper_sha256")) {
            invalid(p -> p.addProperty(field, "F".repeat(64)), "Noncanonical digest");
            invalid(p -> p.addProperty(field, "1".repeat(63)), "Short digest");
        }
        for (String key : List.of("expected", "context", "stubs", "source_ranges")) {
            invalid(p -> p.addProperty(key, "extra"), "Unrequested top-level input");
            invalidProfile(p -> p.addProperty(key, "extra"), "Unrequested profile input");
        }
        invalidProfile(p -> p.addProperty("id", ""), "Empty ID");
        for (String key : List.of("r0", "r23", "gp", "sp", "lr", "r29", "sr", "pc"))
            invalidProfile(p -> p.getAsJsonObject("registers").remove(key), "Missing scalar " + key);
        invalidProfile(p -> p.getAsJsonObject("registers").addProperty("contextreg", "0x00000000"), "Context seeding");
        for (String word : List.of("0xabcdef01", "0x000000001", "0x1", "-1", "4294967296"))
            invalidProfile(p -> p.getAsJsonObject("registers").addProperty("r0", word), "Noncanonical scalar");
        invalidProfile(p -> p.getAsJsonObject("registers").addProperty("r0", 1), "Numeric scalar");
        invalidProfile(p -> p.getAsJsonObject("registers").addProperty("pc", hex(FIRST)), "Wrong entry");
        invalidProfile(p -> p.getAsJsonObject("registers").addProperty("gp", "0xFFFFFFF0"), "GP wrap");
        invalidProfile(p -> p.getAsJsonObject("registers").addProperty("gp", "0x10000000"), "GP outside synthetic RAM");
        invalidProfile(p -> p.getAsJsonObject("registers").addProperty("gp", hex(GP + 2)), "Unaligned GP");
        invalidProfile(p -> moveStack(p, SP + 2), "Unaligned SP");
        invalidProfile(p -> moveStack(p, 0x20), "Stack underflow");
        invalidProfile(p -> p.getAsJsonObject("stack").addProperty("address", hex(SP - 60)), "Stack location mismatch");
        invalidProfile(p -> p.getAsJsonObject("stack").addProperty("hex", "00".repeat(127)), "Short stack seed");
        invalidProfile(p -> p.getAsJsonObject("stack").addProperty("hex", "00".repeat(129)), "Long stack seed");
        for (int offset : OFFSETS)
            invalidProfile(p -> moveStack(p, GP + offset + 64), "Stack and guarded region overlap");
        invalidProfile(p -> moveStack(p, GP + 0x3B488), "Saved LR aliases watched opaque word");
        for (long sentinel : new long[]{STOP + 1, ENTRY, SP - 4, GP + 0x1564, GP + 0x3B484, MMIO})
            invalidProfile(p -> p.getAsJsonObject("registers").addProperty("lr", hex(sentinel)), "Invalid sentinel");
        for (int i = 0; i < NAMES.length; i++) {
            final String name = NAMES[i]; final int size = SIZES[i];
            invalidProfile(p -> p.getAsJsonObject("memory").remove(name), "Missing region");
            invalidProfile(p -> p.getAsJsonObject("memory").addProperty(name, "00".repeat(size - 1)), "Short region");
        }
        invalidProfile(p -> p.getAsJsonObject("memory").addProperty("extra", "00"), "Extra region");
        invalidProfile(p -> p.getAsJsonObject("memory").addProperty("ready", "gg".repeat(12)), "Invalid seed hex");
        for (int level : new int[]{4, 128, 255}) {
            byte[] bytes = new byte[12]; bytes[4] = (byte)level;
            invalidProfile(p -> p.getAsJsonObject("memory").addProperty("diagnostic", HexFormat.of().formatHex(bytes)), "Nonquiet diagnostic");
        }
        for (int level : new int[]{0, 1, 2, 3}) {
            JsonObject p = profileJson(false); byte[] bytes = new byte[12]; bytes[4] = (byte)level;
            p.getAsJsonObject("memory").addProperty("diagnostic", HexFormat.of().formatHex(bytes));
            require(CaptureSocInitialization.profiles(request(p)).size() == 1, "Quiet diagnostic admitted");
        }
        invalidProfile(p -> p.getAsJsonArray("version_inputs").remove(0), "Missing first VERSION");
        invalidProfile(p -> p.getAsJsonArray("version_inputs").remove(1), "Missing conditional input");
        invalidProfile(p -> p.getAsJsonArray("version_inputs").add(version(SECOND, "r2", V2)), "Duplicate VERSION");
        invalidProfile(p -> p.getAsJsonArray("version_inputs").get(0).getAsJsonObject().addProperty("destination", "gp"), "Wrong VERSION register");
        invalidProfile(p -> p.getAsJsonArray("version_inputs").get(1).getAsJsonObject().addProperty("pc", hex(FIRST)), "Wrong second VERSION site");
        invalidProfile(p -> p.getAsJsonArray("version_inputs").get(0).getAsJsonObject().addProperty("width", 4), "Extra VERSION member");
        invalidProfile(p -> p.getAsJsonArray("mmio_inputs").add(profileJson(true).getAsJsonArray("mmio_inputs").get(0)), "Both conditional branches supplied");
        for (String key : List.of("pc", "address", "word")) {
            JsonObject p = profileJson(true); p.getAsJsonArray("mmio_inputs").get(0).getAsJsonObject().remove(key);
            rejected(() -> CaptureSocInitialization.profiles(request(p)), "Missing MMIO member");
        }
        for (String key : List.of("pc", "address")) {
            JsonObject p = profileJson(true); p.getAsJsonArray("mmio_inputs").get(0).getAsJsonObject().addProperty(key, "0x00000000");
            rejected(() -> CaptureSocInitialization.profiles(request(p)), "Wrong MMIO location");
        }
        JsonObject duplicate = profileJson(true);
        duplicate.getAsJsonArray("mmio_inputs").add(duplicate.getAsJsonArray("mmio_inputs").get(0).deepCopy());
        rejected(() -> CaptureSocInitialization.profiles(request(duplicate)), "Duplicate MMIO");
        rejected(() -> CaptureSocInitialization.parseRequest("{\"a\":1,\"a\":2}"), "Duplicate JSON key");
        rejected(() -> CaptureSocInitialization.parseRequest("{\"registers\":{\"r0\":1,\"r0\":2}}"), "Nested duplicate key");
        rejectedJson(() -> CaptureSocInitialization.parseRequest(request(profileJson(false)) + " {}"), "Trailing JSON");
        require(CaptureSocInitialization.parseRequest("{}" + " ".repeat(262142)).size() == 0, "Request byte boundary");
        rejected(() -> CaptureSocInitialization.parseRequest("{}" + " ".repeat(262143)), "Request size cap");
        rejected(() -> CaptureSocInitialization.parseRequest("{\"a\":".repeat(10) + "1" + "}".repeat(10)), "Nesting cap");
    }

    static void partitionTests() {
        var p = profile(false); var spans = CaptureSocInitialization.partition(p);
        Set<String> writable = CaptureSocInitialization.writable(p);
        List<StartupZeroObservations.Span> parents = new ArrayList<>(); parents.add(p.stack().span());
        for (var seed : p.memory()) parents.add(seed.span());
        long all = 0, mutable = 0;
        for (int i = 0; i < spans.size(); i++) {
            var s = spans.get(i); all += s.size();
            require(parents.stream().filter(x -> x.contains(s.start(), s.size())).count() == 1, "Partition belongs to one seed");
            for (int j = 0; j < i; j++) require(!s.overlaps(spans.get(j)), "Partitions never overlap");
            if (writable.contains(s.name())) mutable += s.size();
        }
        require(all == 224 && mutable == 53, "Exact seeded and writable bytes");
        long[][] expected = {{SP - 24, 24}, {GP + 0x1564, 4}, {GP + 0x1568, 4},
            {GP + 0x16E4, 4}, {GP + 0x16E8, 4}, {GP + 0x3B894, 4},
            {GP + 0x3B8AE, 1}, {GP + 0x3B924, 4}, {GP + 0x3B92C, 4}};
        require(writable.size() == expected.length, "Only declared writable fields");
        for (long[] e : expected) require(spans.stream().anyMatch(s -> s.start() == e[0]
            && s.size() == e[1] && writable.contains(s.name())), "Exact writable field");
        for (var parent : parents) {
            int covered = spans.stream().filter(s -> parent.contains(s.start(), s.size())).mapToInt(StartupZeroObservations.Span::size).sum();
            require(covered == parent.size(), "No unobserved guard holes");
        }
    }

    static CaptureSocInitialization.Policy policy(boolean withMmio) { return new CaptureSocInitialization.Policy(profile(withMmio)); }
    static void failed(CaptureSocInitialization.Policy p, Action action, String label) throws Exception {
        rejected(action, label); require(p.observer.failed, "Sticky rejection: " + label);
        p.end(); rejected(p::finish, "No successful result after rejection");
    }
    static void versionAndMmioTests() throws Exception {
        var version = policy(false);
        version.begin(FIRST, 0, 2); require(version.consumeVersion(FIRST, "r4") == V1, "First input consumed"); version.end();
        version.begin(SECOND, 1, 2); require(version.consumeVersion(SECOND, "r2") == V2, "Independent second input consumed"); version.end();
        version.finish(); require(version.observer.runtime.operations == 0, "VERSION is not a memory event");
        require(version.versionEvents.equals(JsonParser.parseString("""
            [{"index":0,"step":0,"pc":"0x0EC6221E","destination":"r4","word":"0xA5000123"},
             {"index":1,"step":1,"pc":"0x0EC62332","destination":"r2","word":"0xFFFFFFBF"}]
            """)), "Ordered independent VERSION evidence");
        var mmio = policy(true); mmio.begin(FIRST, 0, 2); mmio.consumeVersion(FIRST, "r4"); mmio.end();
        byte[] supplied = word(M), before = supplied.clone();
        mmio.begin(LOAD, 1, 2); mmio.observe(EmulateExecutionState.EXECUTE, false, MMIO, 4, supplied); mmio.end();
        mmio.finish(); require(Arrays.equals(supplied, before), "MMIO observation does not edit buffer");
        require(mmio.observer.runtime.operations == 1 && mmio.observer.runtime.bytes == 4, "MMIO counted once");
        var absent = policy(false); failed(absent, absent::finish, "Unconsumed VERSION inputs");
        var reorder = policy(false); reorder.begin(SECOND, 0, 2);
        failed(reorder, () -> reorder.consumeVersion(SECOND, "r2"), "Reordered VERSION");
        var wrong = policy(false); wrong.begin(FIRST, 0, 2);
        failed(wrong, () -> wrong.consumeVersion(FIRST, "r2"), "Wrong VERSION destination");
        var site = policy(false); site.begin(ENTRY, 0, 2);
        failed(site, () -> site.consumeVersion(FIRST, "r4"), "VERSION at wrong active PC");
        var inactive = policy(false);
        failed(inactive, () -> inactive.consumeVersion(FIRST, "r4"), "Inactive VERSION callback");
        var repeat = policy(false); repeat.begin(FIRST, 0, 2); repeat.consumeVersion(FIRST, "r4");
        failed(repeat, () -> repeat.consumeVersion(FIRST, "r4"), "Repeated VERSION");
        var unused = policy(true); unused.begin(FIRST, 0, 2); unused.consumeVersion(FIRST, "r4"); unused.end();
        failed(unused, unused::finish, "Unconsumed MMIO");
        for (int kind = 0; kind < 6; kind++) {
            var p = policy(kind != 0); p.begin(kind == 1 ? ENTRY : LOAD, 0, 2);
            final int k = kind;
            failed(p, () -> p.observe(EmulateExecutionState.EXECUTE, k == 2,
                k == 3 ? MMIO + 4 : MMIO, k == 4 ? 2 : 4, word(k == 5 ? M ^ 1 : M)), "Invalid MMIO form " + kind);
        }
        var twice = policy(true); twice.begin(LOAD, 0, 2); twice.observe(EmulateExecutionState.EXECUTE, false, MMIO, 4, word(M));
        failed(twice, () -> twice.observe(EmulateExecutionState.EXECUTE, false, MMIO, 4, word(M)), "Repeated MMIO");
    }

    static void accessTests() throws Exception {
        var p = policy(false);
        p.observe(EmulateExecutionState.STOPPED, true, GP + 0x1564, 4, word(1));
        require(p.observer.runtime.operations == 0, "Inactive seeding is excluded");
        p.begin(0x0EC62296L, 0, 4);
        p.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, 0x0EC62296L, 8, new byte[8]);
        p.observe(EmulateExecutionState.EXECUTE, true, GP + 0x1564, 4, word(0x11223344));
        p.observe(EmulateExecutionState.EXECUTE, false, GP + 0x1560, 4, word(0x80808080L)); p.end();
        require(p.observer.runtime.operations == 2 && p.observer.runtime.bytes == 8
            && p.observer.decoder.operations == 1, "Separate data and decoder streams");
        require(p.events.equals(JsonParser.parseString("""
            [{"index":0,"step":0,"pc":"0x0EC62296","kind":"write","address":"0x24021564","size":4,"hex":"44332211"},
             {"index":1,"step":0,"pc":"0x0EC62296","kind":"read","address":"0x24021560","size":4,"hex":"80808080"}]
            """)), "Ordered data evidence excludes decoder reads");
        long reads = p.observer.coverage.values().stream().mapToLong(c -> c.reads.cardinality()).sum();
        long writes = p.observer.coverage.values().stream().mapToLong(c -> c.writes.cardinality()).sum();
        require(reads == 4 && writes == 4, "Guard reads and field writes tracked separately");
        for (long address : new long[]{SP - 25, SP, GP + 0x1560, GP + 0x1563, GP + 0x1565,
                GP + 0x3B8AD, GP + 0x3B484, GP + 0xCCDB8, TABLE, 0x0EC62372L}) {
            var bad = policy(false); bad.begin(ENTRY, 0, 2);
            failed(bad, () -> bad.observe(EmulateExecutionState.EXECUTE, true, address, 4, word(1)), "Guard or crossed-field write");
        }
        var merged = policy(false); merged.begin(ENTRY, 0, 2);
        failed(merged, () -> merged.observe(EmulateExecutionState.EXECUTE, true, GP + 0x1564, 8, new byte[8]), "Write across adjacent fields");
        var frame = policy(false); frame.begin(ENTRY, 0, 2);
        frame.observe(EmulateExecutionState.EXECUTE, true, SP - 24, 24, new byte[24]); frame.end();
        require(frame.observer.runtime.bytes == 24, "Entire admitted frame is writable");
        var table = policy(false); table.begin(SWITCH, 0, 2);
        table.observe(EmulateExecutionState.EXECUTE, false, TABLE, 2, new byte[]{0x12, 0x34});
        table.observe(EmulateExecutionState.EXECUTE, false, TABLE + 72, 2, new byte[]{0x56, 0x78}); table.end();
        require(table.observer.runtime.operations == 2, "First and last table entries admitted");
        for (int kind = 0; kind < 6; kind++) {
            var bad = policy(false); bad.begin(kind == 0 ? ENTRY : SWITCH, 0, 2); final int k = kind;
            failed(bad, () -> bad.observe(EmulateExecutionState.EXECUTE, k == 1,
                TABLE + (k == 2 ? 73 : k == 3 ? -1 : k == 5 ? 1 : 0), k == 4 ? 4 : 2, new byte[4]), "Invalid table read " + kind);
        }
        for (long location : new long[]{ENTRY - 1, ENTRY + 8, 0x0EC62372L}) {
            var bad = policy(false); bad.begin(ENTRY, 0, 2);
            failed(bad, () -> bad.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, location, 1, new byte[1]), "Per-PC decoder window");
        }
        var last = policy(false); last.begin(0x0EC62370L, 0, 2);
        last.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, 0x0EC62370L, 8, new byte[8]); last.end();
        require(last.observer.decoder.bytes == 8, "Terminal decoder transport admitted");
        var transport = policy(false); transport.begin(0x0EC62370L, 0, 2);
        failed(transport, () -> transport.observe(EmulateExecutionState.EXECUTE, false, 0x0EC62372L, 1, new byte[1]), "Transport is not runtime data");
        var decodeWrite = policy(false); decodeWrite.begin(ENTRY, 0, 2);
        failed(decodeWrite, () -> decodeWrite.observe(EmulateExecutionState.INSTRUCTION_DECODE, true, ENTRY, 1, new byte[1]), "Decoder write");
        var stopped = policy(false); stopped.begin(ENTRY, 0, 2);
        failed(stopped, () -> stopped.observe(EmulateExecutionState.STOPPED, false, GP + 0x1564, 4, word(0)), "Unexpected active phase");
    }

    static void budgetTests() throws Exception {
        var operations = policy(false); operations.begin(ENTRY, 0, 2);
        for (int i = 0; i < 64; i++) operations.observe(EmulateExecutionState.EXECUTE, false, SP - 24, 1, new byte[1]);
        require(operations.observer.runtime.operations == 64, "Data event boundary");
        failed(operations, () -> operations.observe(EmulateExecutionState.EXECUTE, false, SP - 24, 1, new byte[1]), "Data event cap");
        var bytes = policy(false); bytes.begin(ENTRY, 0, 2);
        for (int i = 0; i < 32; i++) bytes.observe(EmulateExecutionState.EXECUTE, false, SP - 24, 16, new byte[16]);
        require(bytes.observer.runtime.bytes == 512, "Data byte boundary");
        failed(bytes, () -> bytes.observe(EmulateExecutionState.EXECUTE, false, SP - 24, 1, new byte[1]), "Data byte cap");
        for (int width : new int[]{1, 8}) {
            var decoder = policy(false); decoder.begin(ENTRY, 0, 2);
            for (int i = 0; i < 256; i++) decoder.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, ENTRY, width, new byte[width]);
            require(decoder.observer.decoder.operations == 256 && decoder.observer.decoder.bytes == 256L * width, "Decoder budget boundary");
            failed(decoder, () -> decoder.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, ENTRY, 1, new byte[1]), "Decoder cap");
        }
        var steps = policy(false);
        for (int i = 0; i < 128; i++) { steps.begin(ENTRY, i, 2); steps.end(); }
        failed(steps, () -> steps.begin(ENTRY, 128, 2), "Instruction cap");
        for (int step : new int[]{-1, 1, Integer.MAX_VALUE}) {
            var bad = policy(false); failed(bad, () -> bad.begin(ENTRY, step, 2), "Nonconsecutive first step");
        }
        var repeat = policy(false); repeat.begin(ENTRY, 0, 2); repeat.end();
        failed(repeat, () -> repeat.begin(ENTRY, 0, 2), "Repeated step number");
        for (long pc : new long[]{ENTRY - 2, 0x0EC62372L, 0xFFFFFFFFL}) {
            var bad = policy(false); failed(bad, () -> bad.begin(pc, 0, 2), "Unbound decoder window");
        }
    }

    static InstructionPrototype prototype(int length) {
        return (InstructionPrototype)Proxy.newProxyInstance(InstructionPrototype.class.getClassLoader(),
            new Class<?>[]{InstructionPrototype.class}, (proxy, method, args) -> {
                switch (method.getName()) {
                    case "getLength": return length;
                    case "getDelaySlotByteCount": return 0;
                    case "hasNext2Dependency": return false;
                    default: throw new UnsupportedOperationException(method.getName());
                }
            });
    }
    static ByteMemBufferImpl policyBuffer(long pc, CaptureSocInitialization.Policy policy) {
        AddressSpace ram = new GenericAddressSpace("ram", 32, AddressSpace.TYPE_RAM, 0);
        return new ByteMemBufferImpl(ram.getAddress(pc), new byte[32], false) {
            @Override public int getBytes(byte[] bytes, int offset) {
                int count = super.getBytes(bytes, offset); require(count == bytes.length, "Complete synthetic API read");
                policy.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, pc + offset, count, bytes); return count;
            }
        };
    }
    static ParserWalker patternWalker(WrappedMemBuffer wrapped) {
        return new ParserWalker(null) {
            @Override public int getInstructionBytes(int offset, int size) throws MemoryAccessException {
                byte[] bytes = new byte[size]; require(wrapped.getBytes(bytes, offset) == size, "Complete pattern read");
                int value = 0; for (byte item : bytes) value = (value << 8) | (item & 255); return value;
            }
        };
    }
    static void decoderPolicyTests() throws Exception {
        for (int length : new int[]{2, 4, 6}) {
            long pc = length == 2 ? ENTRY : length == 4 ? 0x0EC62296L : 0x0EC62222L;
            var p = policy(false); p.begin(pc, 0, length); ByteMemBufferImpl buffer = policyBuffer(pc, p);
            new PseudoInstruction(buffer.getAddress(), prototype(length), new WrappedMemBuffer(buffer, 8, 0), null);
            require(p.observer.decoder.operations == (length == 6 ? 2 : 1)
                && p.observer.decoder.bytes == (length == 6 ? 17 : 8), "Actual constructor reads pass runtime policy");
            int overbound = length == 6 ? 10 : 9;
            failed(p, () -> p.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, pc, overbound, new byte[overbound]),
                "Reject read beyond constructor envelope");
        }
        for (long pc : new long[]{0x0EC62334L, 0x0EC6234AL, 0x0EC62366L}) {
            var p = policy(false); p.begin(pc, 0, 6); ByteMemBufferImpl buffer = policyBuffer(pc, p);
            WrappedMemBuffer wrapped = new WrappedMemBuffer(buffer, 8, 0);
            require(new PatternBlock(5, 0x04000000, 0).isInstructionMatch(patternWalker(wrapped)), "Selected pattern refill admitted");
            new PseudoInstruction(buffer.getAddress(), prototype(6), wrapped, null);
            require(p.observer.decoder.operations == 3 && p.observer.decoder.bytes == 25,
                "Initial cache, shifted refill and constructor reads admitted");
            failed(p, () -> p.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, pc + 5, 9, new byte[9]),
                "Shifted read may not exceed 13 bytes");
            for (int length : new int[]{2, 4}) {
                var wrong = policy(false); failed(wrong, () -> wrong.begin(pc, 0, length), "Refill site requires six-byte instruction");
            }
        }
        var nonrefill = policy(false); nonrefill.begin(0x0EC62222L, 0, 6);
        failed(nonrefill, () -> nonrefill.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, 0x0EC62227L, 8, new byte[8]),
            "Other six-byte instructions do not admit refill span");
        var terminal = policy(false); terminal.begin(0x0EC62370L, 0, 2);
        ByteMemBufferImpl terminalBuffer = policyBuffer(0x0EC62370L, terminal);
        new PseudoInstruction(terminalBuffer.getAddress(), prototype(2), new WrappedMemBuffer(terminalBuffer, 8, 0), null);
        failed(terminal, () -> terminal.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, 0x0EC62370L, 9, new byte[9]),
            "Terminal decoder envelope remains eight bytes");
        for (int length : new int[]{-1, 0, 1, 3, 5, 7, 8, 10, Integer.MAX_VALUE}) {
            var invalid = policy(false); failed(invalid, () -> invalid.begin(ENTRY, 0, length), "Reject unadmitted instruction length");
        }
    }
    static void decoderApiTests() throws Exception {
        AddressSpace ram = new GenericAddressSpace("ram", 32, AddressSpace.TYPE_RAM, 0);
        for (int length : new int[]{2, 4, 6}) {
            int bound = Math.max(8, length + 3);
            var buffer = new CaptureSocInitialization.DecoderTraceBuffer(ram.getAddress(ENTRY), new byte[bound]);
            WrappedMemBuffer wrapped = new WrappedMemBuffer(buffer, 8, 0);
            PseudoInstruction instruction = new PseudoInstruction(ram.getAddress(ENTRY), prototype(length), wrapped, null);
            require(instruction.getLength() == length && instruction.getBytes().length == length, "Actual pseudo instruction length");
            require(buffer.reads.size() == (length == 6 ? 2 : 1) && buffer.envelopeBytes == bound,
                "Actual constructor and initial cache reads");
            require(buffer.reads.get(0).getAsJsonObject().get("size").getAsInt() == 8, "Wrapped initial prefetch");
            if (length == 6) require(buffer.reads.get(1).getAsJsonObject().get("size").getAsInt() == 9,
                "Six-byte pseudo instruction requests nine bytes");
            rejected(() -> buffer.getBytes(new byte[bound + 1], 0), "Constructor envelope overrun");
            require(buffer.failed, "Trace read failure is sticky");
        }
        var shifted = new CaptureSocInitialization.DecoderTraceBuffer(ram.getAddress(ENTRY), new byte[13]);
        WrappedMemBuffer wrapped = new WrappedMemBuffer(shifted, 8, 0);
        require(new PatternBlock(5, 0x04000000, 0).isInstructionMatch(patternWalker(wrapped)), "Actual normalized pattern match");
        require(shifted.reads.size() == 2 && shifted.envelopeBytes == 13 && shifted.totalBytes == 16,
            "Shifted four-byte pattern causes eight-byte refill");
        JsonObject refill = shifted.reads.get(1).getAsJsonObject();
        require(refill.get("address").getAsString().equals("0x0EC62221") && refill.get("size").getAsInt() == 8,
            "Exact refill address and width");
        var narrow = new CaptureSocInitialization.DecoderTraceBuffer(ram.getAddress(ENTRY), new byte[9]);
        WrappedMemBuffer narrowWrapped = new WrappedMemBuffer(narrow, 8, 0);
        rejected(() -> narrowWrapped.getBytes(new byte[4], 5), "Constructor width does not admit shifted refill");
        var terminal = new CaptureSocInitialization.DecoderTraceBuffer(ram.getAddress(0x0EC62370L), new byte[8]);
        new PseudoInstruction(ram.getAddress(0x0EC62370L), prototype(2), new WrappedMemBuffer(terminal, 8, 0), null);
        require(terminal.envelopeBytes == 8, "Terminal uses exactly existing transport");
        rejected(() -> terminal.getBytes(new byte[9], 0), "Terminal ninth byte is unbound");
        var count = new CaptureSocInitialization.DecoderTraceBuffer(ram.getAddress(ENTRY), new byte[8]);
        for (int i = 0; i < 32; i++) count.getBytes(new byte[8], 0);
        rejected(() -> count.getBytes(new byte[1], 0), "Static trace request cap");
        var volume = new CaptureSocInitialization.DecoderTraceBuffer(ram.getAddress(ENTRY), new byte[256]);
        volume.getBytes(new byte[256], 0); volume.getBytes(new byte[256], 0);
        rejected(() -> volume.getBytes(new byte[1], 0), "Static trace byte cap");
        for (int offset : new int[]{-1, 8}) {
            var invalid = new CaptureSocInitialization.DecoderTraceBuffer(ram.getAddress(ENTRY), new byte[8]);
            rejected(() -> invalid.getByte(offset), "Static trace byte outside source");
        }
    }
    static Instruction instruction(PcodeOp... operations) {
        return (Instruction)Proxy.newProxyInstance(Instruction.class.getClassLoader(), new Class<?>[]{Instruction.class},
            (proxy, method, args) -> {
                if (method.getName().equals("getPcode")) return operations;
                throw new UnsupportedOperationException(method.getName());
            });
    }
    static void encodingAndContextTests() throws Exception {
        AddressSpace ram = new GenericAddressSpace("ram", 32, AddressSpace.TYPE_RAM, 0);
        AddressSpace constant = new GenericAddressSpace("const", 64, AddressSpace.TYPE_CONSTANT, 1);
        AddressSpace registers = new GenericAddressSpace("register", 32, AddressSpace.TYPE_REGISTER, 2);
        PcodeOp operation = new PcodeOp(ram.getAddress(0x1000), 0, PcodeOp.COPY,
            new Varnode[]{new Varnode(constant.getAddress(0x11223344), 4)});
        byte[] domain = "open27xx-startup-pcode-v1\0".getBytes(StandardCharsets.US_ASCII);
        byte[] body = HexFormat.of().parseHex("0100000001000000000105000000636f6e7374443322110000000004000000");
        byte[] expected = Arrays.copyOf(domain, domain.length + body.length);
        System.arraycopy(body, 0, expected, domain.length, body.length);
        require(Arrays.equals(StartupZeroObservations.pcodeEncoding(instruction(operation)), expected), "Canonical synthetic p-code encoding");
        PcodeOp narrow = new PcodeOp(ram.getAddress(0x1000), 0, PcodeOp.COPY,
            new Varnode[]{new Varnode(constant.getAddress(0x11223344), 2)});
        require(!Arrays.equals(StartupZeroObservations.pcodeEncoding(instruction(narrow)), expected), "Operand width contributes to binding");
        Varnode userop = new Varnode(constant.getAddress(1), 4);
        Varnode r4 = new Varnode(registers.getAddress(16), 4), r2 = new Varnode(registers.getAddress(8), 4);
        CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, r4, new Varnode[]{userop}, FIRST);
        CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, r2, new Varnode[]{userop}, SECOND);
        require(true, "Both exact VERSION operation shapes admitted");
        rejected(() -> CaptureSocInitialization.versionOperation(PcodeOp.COPY, r4, new Varnode[]{userop}, FIRST), "Wrong VERSION opcode");
        rejected(() -> CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, r4, new Varnode[]{userop}, ENTRY), "Wrong VERSION operation site");
        rejected(() -> CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, r2, new Varnode[]{userop}, FIRST), "Wrong VERSION output offset");
        rejected(() -> CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, null, new Varnode[]{userop}, FIRST), "Missing VERSION output");
        for (Varnode output : new Varnode[]{new Varnode(registers.getAddress(16), 2), new Varnode(ram.getAddress(16), 4)})
            rejected(() -> CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, output, new Varnode[]{userop}, FIRST), "Wrong VERSION output width or space");
        for (Varnode input : new Varnode[]{new Varnode(constant.getAddress(2), 4),
                new Varnode(constant.getAddress(1), 2), new Varnode(registers.getAddress(1), 4)})
            rejected(() -> CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, r4, new Varnode[]{input}, FIRST), "Wrong VERSION userop identity");
        rejected(() -> CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, r4, new Varnode[0], FIRST), "Missing VERSION userop");
        rejected(() -> CaptureSocInitialization.versionOperation(PcodeOp.CALLOTHER, r4, new Varnode[]{userop, userop}, FIRST), "Extra VERSION input");
        Register register = new Register("contextreg", "", registers.getAddress(0), 4, true, Register.TYPE_CONTEXT);
        var contextPolicy = new StartupZeroObservations.Vc4ContextPolicy();
        RegisterValue unknown = new RegisterValue(register, new byte[8]);
        contextPolicy.boundary(null, true); contextPolicy.boundary(unknown, false);
        JsonObject contexts = new JsonObject(); contexts.add("initial", StartupZeroObservations.context(null));
        contexts.add("current", StartupZeroObservations.context(unknown));
        String encoded = CaptureSocInitialization.encodeOutput(contexts);
        JsonObject decoded = JsonParser.parseString(encoded).getAsJsonObject();
        require(decoded.get("initial").isJsonNull(), "Initial null context is explicit");
        require(decoded.getAsJsonObject("current").get("mask_value_bytes").getAsString().equals("0000000000000000"), "Unknown mask remains explicit");
        var pool = new CaptureSocInitialization.ContextPool();
        require(pool.id(JsonNull.INSTANCE) == 0 && pool.id(JsonNull.INSTANCE) == 0, "Null context deduplicated");
        require(pool.id(StartupZeroObservations.context(unknown)) == 1
            && pool.id(StartupZeroObservations.context(unknown)) == 1 && pool.values.size() == 2, "Unknown context deduplicated separately");
        JsonObject third = new JsonObject(); third.addProperty("mask_value_bytes", "00000000ffffffff");
        rejected(() -> pool.id(third), "Third context form exceeds bound");
        require(pool.values.size() == 2, "Context cap preserves prior records");
        rejected(() -> contextPolicy.boundary(unknown, true), "Known object is not initial null");
        rejected(() -> contextPolicy.boundary(null, false), "Missing later context");
        for (int position : new int[]{0, 3, 4, 7}) {
            byte[] bytes = new byte[8]; bytes[position] = 1; RegisterValue changed = new RegisterValue(register, bytes);
            rejected(() -> contextPolicy.boundary(changed, false), "Changed context mask or value");
        }
        JsonObject output = new JsonObject(); output.add("unknown", JsonNull.INSTANCE); output.addProperty("padding", "");
        int base = CaptureSocInitialization.encodeOutput(output).length();
        output.addProperty("padding", "x".repeat(1048576 - base));
        require(CaptureSocInitialization.encodeOutput(output).length() == 1048576, "Output cap boundary");
        output.addProperty("padding", "x".repeat(1048577 - base));
        rejected(() -> CaptureSocInitialization.encodeOutput(output), "Output cap exceeded");
    }

    public static void main(String[] args) throws Exception {
        requestTests(); partitionTests(); versionAndMmioTests(); accessTests(); budgetTests(); decoderApiTests(); decoderPolicyTests(); encodingAndContextTests();
        System.out.println("SoC observation checks passed: " + assertions + " assertions, " + rejections + " rejections");
    }
}
