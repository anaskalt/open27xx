// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import java.io.ByteArrayInputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import ghidra.GhidraApplicationLayout;
import ghidra.framework.Application;
import ghidra.framework.HeadlessGhidraApplicationConfiguration;
import ghidra.pcode.emulate.EmulateExecutionState;
import ghidra.program.database.ProgramDB;
import ghidra.program.database.mem.FileBytes;
import ghidra.program.model.lang.Language;
import ghidra.program.model.lang.LanguageID;
import ghidra.program.model.lang.Register;
import ghidra.program.model.lang.RegisterValue;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.address.GenericAddressSpace;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.util.DefaultLanguageService;
import ghidra.app.util.opinion.ElfLoader;
import ghidra.util.task.TaskMonitor;

public class StartupZeroObservationsTest {
    private static int assertions, rejections;
    private static final long CODE = 0x10001000L, TABLE = 0x10002000L, BSS = 0x10003000L;
    private static final int BSS_SIZE = 65540;
    private static final long STACK = 0x24010040L, STOP = 0x24000000L;
    interface Action { void run() throws Exception; }
    static void require(boolean value) { assertions++; if (!value) throw new AssertionError("Assertion " + assertions); }
    static void rejected(Action action, String diagnostic) throws Exception {
        try { action.run(); throw new AssertionError("Accepted: " + diagnostic); }
        catch (IllegalStateException exception) {
            if (!exception.getMessage().contains(diagnostic)) throw new AssertionError("Expected " + diagnostic + ", got " + exception, exception);
            assertions++; rejections++;
        }
    }
    static StartupZeroObservations.Span span(String name, long address, int size) { return new StartupZeroObservations.Span(name, address, size); }
    static String digest(byte[] bytes) { return StartupZeroObservations.digest(bytes); }
    static byte[] fixtureBytes() {
        byte[] bytes = new byte[0x400]; ByteBuffer b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        b.put(new byte[]{0x7F, 'E', 'L', 'F', 1, 1, 1});
        b.position(16); b.putShort((short)2).putShort((short)3).putInt(1).putInt((int)CODE).putInt(52).putInt(0x300);
        b.position(40); b.putShort((short)52).putShort((short)32).putShort((short)3).putShort((short)40).putShort((short)3);
        b.position(52); b.putInt(1).putInt(0x100).putInt((int)CODE).putInt((int)CODE).putInt(24).putInt(24).putInt(5).putInt(1);
        b.putInt(1).putInt(0x240).putInt((int)BSS).putInt((int)BSS).putInt(0).putInt(BSS_SIZE).putInt(6).putInt(32);
        b.putInt(1).putInt(0x240).putInt((int)BSS + BSS_SIZE).putInt((int)BSS + BSS_SIZE).putInt(0).putInt(8).putInt(6).putInt(32);
        b.position(0x328); b.putInt(0).putInt(8).putInt(3).putInt((int)BSS).putInt(0x240).putInt(BSS_SIZE).putInt(0).putInt(0).putInt(32).putInt(1);
        b.putInt(0).putInt(8).putInt(3).putInt((int)BSS + BSS_SIZE).putInt(0x240).putInt(8).putInt(0).putInt(0).putInt(32).putInt(1);
        b.position(0x100); b.put(new byte[]{0x52, (byte)0x8B, 0x18, (byte)0x89, 0x19, (byte)0x89, 0x19,
            0x31, (byte)0xDB, (byte)0xEB, 1, (byte)0xC3, (byte)0x89, 0x19, (byte)0xEB, (byte)0xFB});
        b.position(0x200); b.put(new byte[]{1, 2, 3, 4}); return bytes;
    }
    static final class Fixture implements AutoCloseable {
        final ProgramDB program;
        final byte[] source;
        final Object owner = new Object();
        final StartupZeroObservations.Geometry geometry;
        Fixture() throws Exception { this(fixtureBytes()); }
        Fixture(byte[] source) throws Exception {
            this.source = source;
            Language language = DefaultLanguageService.getLanguageService().getLanguage(new LanguageID("x86:LE:32:default"));
            program = new ProgramDB("startup-zero-host", language, language.getDefaultCompilerSpec(), owner);
            geometry = new StartupZeroObservations.Geometry(digest(source), source.length, 3, 52, 3, 0x300, 3,
                List.of(source("code", CODE, 16, 0x100, true), source("table", TABLE, 4, 0x200, false)),
                List.of(source("transport", CODE, 24, 0x100, true)),
                List.of(allocation("bss0", BSS, BSS_SIZE, 1), allocation("bss1", BSS + BSS_SIZE, 8, 2)));
            int transaction = program.startTransaction("synthetic fixture");
            try {
                program.setExecutableFormat(ElfLoader.ELF_NAME); program.setExecutableSHA256(digest(source));
                FileBytes file = program.getMemory().createFileBytes("fixture.elf", 0, source.length, new ByteArrayInputStream(source), TaskMonitor.DUMMY);
                MemoryBlock code = program.getMemory().createInitializedBlock("code", StartupZeroObservations.address(program, CODE), file, 0x100, 24, false);
                code.setRead(true); code.setExecute(true); code.setWrite(false);
                MemoryBlock table = program.getMemory().createInitializedBlock("table", StartupZeroObservations.address(program, TABLE), file, 0x200, 4, false);
                table.setRead(true); table.setWrite(false); table.setExecute(false);
                bss("bss0", BSS, BSS_SIZE, false, false); bss("bss1", BSS + BSS_SIZE, 8, false, false);
            } finally { program.endTransaction(transaction, true); }
        }
        StartupZeroObservations.Source source(String name, long address, int size, int offset, boolean executable) {
            return new StartupZeroObservations.Source(span(name, address, size), offset, digest(Arrays.copyOfRange(source, offset, offset + size)), executable);
        }
        StartupZeroObservations.Allocation allocation(String name, long address, int size, int index) {
            return new StartupZeroObservations.Allocation(span(name, address, size), index, index, 0x240,
                digest(Arrays.copyOfRange(source, 52 + index * 32, 84 + index * 32)), digest(Arrays.copyOfRange(source, 0x300 + index * 40, 0x328 + index * 40)));
        }
        void bss(String name, long address, int size, boolean initialized, boolean overlay) throws Exception {
            MemoryBlock block = initialized ? program.getMemory().createInitializedBlock(name, StartupZeroObservations.address(program, address), size,
                (byte)0, TaskMonitor.DUMMY, overlay) : program.getMemory().createUninitializedBlock(name, StartupZeroObservations.address(program, address), size, overlay);
            block.setRead(true); block.setWrite(true); block.setExecute(false);
        }
        StartupZeroObservations.Admission admit() throws Exception { return new StartupZeroObservations.Admission(program, geometry, TaskMonitor.DUMMY); }
        void mutated(Action action, String diagnostic) throws Exception {
            int transaction = program.startTransaction("invalid fixture");
            try { action.run(); rejected(this::admit, diagnostic); } finally { program.endTransaction(transaction, false); }
        }
        public void close() { program.release(owner); }
    }
    static JsonObject request() {
        JsonObject request = new JsonObject(); request.addProperty("schema_version", 1); request.addProperty("source_sha256", CaptureStartupZero.SOURCE);
        request.addProperty("tool_sha256", "1".repeat(64)); request.addProperty("helper_sha256", "2".repeat(64));
        JsonArray profiles = new JsonArray(); profiles.add(CaptureStartupZero.expectedProfile(0)); profiles.add(CaptureStartupZero.expectedProfile(1)); request.add("profiles", profiles); return request;
    }
    static void schemaTests() throws Exception {
        require(CaptureStartupZero.profiles(request()).size() == 2);
        require(CaptureStartupZero.profiles(CaptureStartupZero.parseRequest(request().toString())).get(1).bssFill() == (byte)0x5A);
        for (String field : List.of("context", "stubs", "expected", "source_ranges")) {
            JsonObject input = request(); input.addProperty(field, 0); rejected(() -> CaptureStartupZero.profiles(input), "Unexpected");
        }
        for (String field : List.of("r0", "gp", "sp", "lr", "pc", "sr")) {
            JsonObject input = request(); input.getAsJsonArray("profiles").get(0).getAsJsonObject().getAsJsonObject("registers").remove(field);
            rejected(() -> CaptureStartupZero.profiles(input), "Frozen profile");
        }
        JsonObject wrong = request(); wrong.getAsJsonArray("profiles").get(1).getAsJsonObject().addProperty("bss_poison", "00");
        rejected(() -> CaptureStartupZero.profiles(wrong), "Frozen profile");
        rejected(() -> CaptureStartupZero.parseRequest("{\"a\":1,\"a\":2}"), "Duplicate");
        rejected(() -> CaptureStartupZero.parseRequest("{\"registers\":{\"r0\":\"0\",\"r0\":\"1\"}}"), "Duplicate");
        rejected(() -> CaptureStartupZero.parseRequest(" ".repeat(16385)), "byte cap");
        rejected(() -> span("wrap", 0xFFFFFFFCL, 8), "Invalid span");
        require(StartupZeroObservations.context(null).isJsonNull());
        JsonObject oversized = new JsonObject(); oversized.addProperty("value", "x".repeat(StartupZeroObservations.MAX_OUTPUT));
        rejected(() -> CaptureStartupZero.encodeOutput(oversized), "Output byte cap");
    }
    static void admissionTests() throws Exception {
        try (Fixture f = new Fixture()) {
            StartupZeroObservations.Admission admission = f.admit(); admission.decode(9); require(admission.sites.size() == 9); admission.unchanged();
            require(f.program.getListing().getNumInstructions() == 0);
            f.mutated(() -> f.program.setExecutableSHA256("0".repeat(64)), "Source property");
            f.mutated(() -> f.program.getMemory().setByte(StartupZeroObservations.address(f.program, CODE), (byte)0x90), "Current source");
            f.mutated(() -> f.program.getMemory().getBlock(StartupZeroObservations.address(f.program, BSS)).setExecute(true), "allocation block");
            f.mutated(() -> f.program.getMemory().createFileBytes("duplicate", 0, f.source.length, new ByteArrayInputStream(f.source), TaskMonitor.DUMMY), "Ambiguous");
            for (boolean initialized : new boolean[]{false, true}) f.mutated(() -> {
                f.program.getMemory().removeBlock(f.program.getMemory().getBlock(StartupZeroObservations.address(f.program, BSS)), TaskMonitor.DUMMY);
                f.bss("replacement", BSS, initialized ? BSS_SIZE : BSS_SIZE - 1, initialized, false);
            }, "allocation block");
            f.mutated(() -> {
                f.program.getMemory().removeBlock(f.program.getMemory().getBlock(StartupZeroObservations.address(f.program, BSS)), TaskMonitor.DUMMY);
                f.bss("replacement", BSS, BSS_SIZE, false, true);
            }, "allocation block");
        }
        for (int offset : new int[]{52 + 32 + 16, 0x328 + 4, 0x328 + 20}) {
            byte[] source = fixtureBytes(); source[offset] ^= 1;
            try (Fixture f = new Fixture(source)) { rejected(f::admit, offset < 0x300 ? "PT_LOAD" : "NOBITS"); }
        }
        byte[] changedHeader = fixtureBytes(); changedHeader[28] ^= 1;
        try (Fixture f = new Fixture(changedHeader)) { rejected(f::admit, "table metadata"); }
        byte[] alteredOriginal = fixtureBytes(); alteredOriginal[0x280] = 1;
        try (Fixture f = new Fixture(alteredOriginal)) {
            StartupZeroObservations.Geometry g = f.geometry;
            StartupZeroObservations.Geometry originalIdentity = new StartupZeroObservations.Geometry(digest(fixtureBytes()),
                g.fileSize(), g.machine(), g.phOffset(), g.phCount(), g.shOffset(), g.shCount(), g.sources(), g.envelopes(), g.allocations());
            int transaction = f.program.startTransaction("source property");
            try { f.program.setExecutableSHA256(originalIdentity.sha256()); } finally { f.program.endTransaction(transaction, true); }
            rejected(() -> new StartupZeroObservations.Admission(f.program, originalIdentity, TaskMonitor.DUMMY), "Original source digest");
        }
    }
    static void streamTests() throws Exception {
        StartupZeroObservations.Stream stream = new StartupZeroObservations.Stream(StartupZeroObservations.DATA_DOMAIN);
        stream.event(0x12345678, true, 0xAABBCCDDL, 2, new byte[]{0x11, 0x22});
        byte[] domain = "open27xx-startup-data-v1\0".getBytes(StandardCharsets.US_ASCII);
        byte[] event = HexFormat.of().parseHex("00000000000000007856341201ddccbbaa020000001122");
        byte[] literal = Arrays.copyOf(domain, domain.length + event.length); System.arraycopy(event, 0, literal, domain.length, event.length);
        require(stream.digest().equals(digest(literal)) && stream.operations == 1 && stream.bytes == 2);
        StartupZeroObservations.Stream reverse = new StartupZeroObservations.Stream(StartupZeroObservations.DATA_DOMAIN);
        reverse.event(0x12345678, true, 0xAABBCCDDL, 2, new byte[]{0x22, 0x11}); require(!stream.digest().equals(reverse.digest()));
        rejected(() -> stream.event(0, false, 0xFFFFFFFFL, 2, new byte[2]), "geometry");
        stream.operations = StartupZeroObservations.MAX_OPERATIONS; rejected(() -> stream.event(0, false, 0, 1, new byte[1]), "budget");
        stream.operations = 0; stream.bytes = StartupZeroObservations.MAX_BYTES; rejected(() -> stream.event(0, false, 0, 1, new byte[1]), "budget");
        StartupZeroObservations.Stream forward = new StartupZeroObservations.Stream(StartupZeroObservations.DATA_DOMAIN);
        StartupZeroObservations.Stream reordered = new StartupZeroObservations.Stream(StartupZeroObservations.DATA_DOMAIN);
        for (long location : new long[]{BSS, BSS + 4, BSS}) forward.event(CODE, true, location, 4, new byte[4]);
        for (long location : new long[]{BSS + 4, BSS, BSS}) reordered.event(CODE, true, location, 4, new byte[4]);
        require(forward.bytes == reordered.bytes && !forward.digest().equals(reordered.digest()));
    }
    static void contextTests() throws Exception {
        Register register = new Register("contextreg", "", new GenericAddressSpace("register", 32,
            AddressSpace.TYPE_REGISTER, 0).getAddress(0), 4, true, Register.TYPE_CONTEXT);
        RegisterValue unknown = new RegisterValue(register, new byte[8]);
        StartupZeroObservations.Vc4ContextPolicy policy = new StartupZeroObservations.Vc4ContextPolicy();
        policy.boundary(null, true); policy.boundary(unknown, false);
        require(StartupZeroObservations.context(unknown).getAsJsonObject().get("mask_value_bytes").getAsString().equals("0000000000000000"));
        rejected(() -> policy.boundary(unknown, true), "must be null");
        rejected(() -> policy.boundary(null, false), "Unadmitted decoder");
        for (int position : new int[]{0, 3, 4, 7}) {
            byte[] value = new byte[8]; value[position] = 1;
            RegisterValue invalid = new RegisterValue(register, value);
            rejected(() -> policy.boundary(invalid, false), "Unadmitted decoder");
        }
    }
    static StartupZeroObservations.Observer observer() {
        return new StartupZeroObservations.Observer(List.of(span("a", BSS, 8), span("b", BSS + 8, 8), span("table", TABLE, 4)), Set.of("a", "b"));
    }
    static void observerTests() throws Exception {
        StartupZeroObservations.Observer r = observer(); r.observe(EmulateExecutionState.STOPPED, true, BSS, 4, new byte[4]); require(r.runtime.operations == 0);
        r.begin(CODE, span("transport", CODE, 24)); r.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, CODE, 8, new byte[8]);
        r.observe(EmulateExecutionState.EXECUTE, true, BSS, 4, new byte[4]); r.observe(EmulateExecutionState.EXECUTE, true, BSS + 2, 4, new byte[4]);
        r.observe(EmulateExecutionState.EXECUTE, false, BSS + 1, 4, new byte[4]); r.observe(EmulateExecutionState.EXECUTE, false, BSS + 3, 4, new byte[4]); r.end();
        require(r.decoder.operations == 1 && r.runtime.operations == 4 && r.runtime.bytes == 16);
        require(r.coverage.get("a").writes.cardinality() == 6 && r.coverage.get("a").duplicateWrites == 2);
        require(r.coverage.get("a").reads.cardinality() == 6 && r.coverage.get("a").duplicateReads == 2);
        require(r.json().getAsJsonArray("coverage").get(0).getAsJsonObject().get("duplicate_read_bytes").getAsLong() == 2);
        for (long address : new long[]{BSS - 1, BSS + 6, TABLE, CODE}) {
            StartupZeroObservations.Observer bad = observer(); bad.begin(CODE, span("transport", CODE, 24));
            rejected(() -> bad.observe(EmulateExecutionState.EXECUTE, true, address, 4, new byte[4]), "Runtime memory"); bad.end(); require(bad.failed); rejected(bad::json, "Invalid case");
        }
        StartupZeroObservations.Observer bad = observer(); bad.begin(CODE, span("transport", CODE, 24));
        rejected(() -> bad.observe(EmulateExecutionState.INSTRUCTION_DECODE, false, CODE + 23, 2, new byte[2]), "envelope");
        StartupZeroObservations.Observer write = observer(); write.begin(CODE, span("transport", CODE, 24));
        rejected(() -> write.observe(EmulateExecutionState.INSTRUCTION_DECODE, true, CODE, 1, new byte[1]), "envelope");
    }
    static void fullScanTests() throws Exception {
        byte[] bytes = new byte[StartupZeroObservations.CHUNK + 7]; StartupZeroObservations.Span span = span("large", BSS, bytes.length);
        JsonObject zeros = StartupZeroObservations.scan(span, (address, size) -> Arrays.copyOfRange(bytes, (int)(address - BSS), (int)(address - BSS) + size));
        require(zeros.get("sha256").getAsString().equals(digest(bytes)) && zeros.get("all_zero").getAsBoolean());
        for (int offset : new int[]{0, bytes.length / 2, StartupZeroObservations.CHUNK, bytes.length - 1}) {
            bytes[offset] = 1; JsonObject actual = StartupZeroObservations.scan(span, (address, size) -> Arrays.copyOfRange(bytes, (int)(address - BSS), (int)(address - BSS) + size));
            require(!actual.get("all_zero").getAsBoolean() && actual.get("first_nonzero_offset").getAsInt() == offset && actual.get("nonzero_bytes").getAsLong() == 1);
            require(actual.get("sha256").getAsString().equals(digest(bytes))); bytes[offset] = 0;
        }
        rejected(() -> StartupZeroObservations.scan(span, (address, size) -> new byte[size - 1]), "Short complete");
    }
    static StartupZeroObservations.Profile profile(byte poison) {
        Map<String, Long> registers = new LinkedHashMap<>();
        registers.put("EAX", TABLE); registers.put("ECX", BSS); registers.put("EDX", STOP); registers.put("EBX", 0x11223344L);
        registers.put("ESP", STACK + 64); registers.put("EBP", 0x33445566L); registers.put("ESI", 0x55667788L); registers.put("EDI", 0x778899AAL);
        registers.put("EFLAGS", 0L); registers.put("EIP", CODE);
        return new StartupZeroObservations.Profile("host", registers, span("stack", STACK, 128), (byte)0x3C, poison, STOP);
    }
    static void integrationTests() throws Exception {
        try (Fixture f = new Fixture()) {
            StartupZeroObservations.Admission admission = f.admit(); admission.decode(9);
            for (byte poison : new byte[]{(byte)0xA5, 0x5A}) {
                JsonObject result = StartupZeroObservations.capture(admission, profile(poison), CODE, CODE + 11, TaskMonitor.DUMMY);
                require(result.get("completed_instructions").getAsInt() == 9);
                require(result.getAsJsonObject("per_pc").get("0x1000100E").getAsLong() == 1
                    && result.get("last_pc").getAsString().equals("0x1000100B"));
                JsonObject data = result.getAsJsonObject("accesses").getAsJsonObject("data_stream");
                require(data.get("read_operations").getAsLong() == 2 && data.get("write_operations").getAsLong() == 4);
                require(data.get("read_bytes").getAsLong() == 8 && data.get("write_bytes").getAsLong() == 16);
                byte[] events = HexFormat.of().parseHex(
                    "000000000000000000100010017c0001240400000000000024"
                    + "01000000000000000110001000002000100400000001020304"
                    + "02000000000000000310001001003000100400000001020304"
                    + "03000000000000000510001001003000100400000001020304"
                    + "04000000000000000c10001001003000100400000000000000"
                    + "05000000000000000b100010007c0001240400000000000024");
                byte[] domain = "open27xx-startup-data-v1\0".getBytes(StandardCharsets.US_ASCII);
                byte[] literal = Arrays.copyOf(domain, domain.length + events.length);
                System.arraycopy(events, 0, literal, domain.length, events.length);
                require(data.get("sha256").getAsString().equals(digest(literal)));
                require(result.getAsJsonObject("accesses").getAsJsonObject("decoder_stream").get("operations").getAsLong() > 0);
                require(result.getAsJsonArray("bss").get(0).getAsJsonObject().get("nonzero_bytes").getAsInt() == BSS_SIZE - 4);
                require(result.getAsJsonObject("registers").get("EIP").getAsString().equals("0x24000000"));
                require(!f.program.getMemory().getBlock(StartupZeroObservations.address(f.program, BSS)).isInitialized());
            }
            StartupZeroObservations.Profile bad = profile((byte)0xA5); bad.registers().put("ECX", TABLE);
            rejected(() -> StartupZeroObservations.capture(admission, bad, CODE, CODE + 11, TaskMonitor.DUMMY), "Runtime memory");
            StartupZeroObservations.Profile missing = profile((byte)0xA5); missing.registers().put("EAX", TABLE + 0x100);
            rejected(() -> StartupZeroObservations.capture(admission, missing, CODE, CODE + 11, TaskMonitor.DUMMY), "Uninitialized");
            rejected(() -> StartupZeroObservations.capture(admission, profile((byte)0xA5), CODE, CODE + 14, TaskMonitor.DUMMY), "terminal RETURN");
            StartupZeroObservations.Profile codeRead = profile((byte)0xA5); codeRead.registers().put("EAX", CODE);
            rejected(() -> StartupZeroObservations.capture(admission, codeRead, CODE, CODE + 11, TaskMonitor.DUMMY), "Runtime memory");
            StartupZeroObservations.Profile crossing = profile((byte)0xA5); crossing.registers().put("ECX", BSS + BSS_SIZE - 2);
            rejected(() -> StartupZeroObservations.capture(admission, crossing, CODE, CODE + 11, TaskMonitor.DUMMY), "Runtime memory");
            rejected(() -> StartupZeroObservations.capture(admission, profile((byte)0xA5), CODE, CODE + 11, TaskMonitor.DUMMY, 3), "Instruction budget exhausted");
            StartupZeroObservations.Site site = admission.sites.get(CODE);
            admission.sites.put(CODE, new StartupZeroObservations.Site(site.instruction(), site.bytes(), site.source(), f.source("short", CODE, 1, 0x100, true)));
            rejected(() -> StartupZeroObservations.capture(admission, profile((byte)0xA5), CODE, CODE + 11, TaskMonitor.DUMMY), "Decoder envelope");
            admission.sites.put(CODE, site); admission.unchanged();
        }
    }
    public static void main(String[] args) throws Exception {
        schemaTests(); streamTests(); contextTests(); observerTests(); fullScanTests();
        Application.initializeApplication(new GhidraApplicationLayout(), new HeadlessGhidraApplicationConfiguration());
        admissionTests(); integrationTests();
        System.out.println("Startup zero checks passed: " + assertions + " assertions, " + rejections + " rejections");
    }
}
