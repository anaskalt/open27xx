// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import java.io.ByteArrayInputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Set;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import ghidra.GhidraApplicationLayout;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.emulator.MemoryAccessFilter;
import ghidra.app.util.opinion.ElfLoader;
import ghidra.framework.Application;
import ghidra.framework.HeadlessGhidraApplicationConfiguration;
import ghidra.program.database.ProgramDB;
import ghidra.program.database.mem.FileBytes;
import ghidra.program.disassemble.Disassembler;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.lang.Language;
import ghidra.program.model.lang.LanguageID;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.util.DefaultLanguageService;
import ghidra.util.task.TaskMonitor;

public class ElfDataObservationsTest {
    private static final long CODE = 0x10001000L;
    private static final long DATA = 0x10002000L;
    private static int assertions;
    private static int rejections;

    interface Action { void run() throws Exception; }

    private static void require(boolean condition) {
        assertions++;
        if (!condition) { throw new AssertionError("ELF data observation result differs"); }
    }

    private static void rejected(Action action, String message) throws Exception {
        try {
            action.run();
        } catch (IllegalStateException expected) {
            require(expected.getMessage().contains(message));
            rejections++;
            return;
        }
        throw new AssertionError("Accepted invalid ELF data input: " + message);
    }

    private static String digest(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    private static JsonObject request() throws Exception {
        return JsonParser.parseString("{\"elf_data\":{\"regions\":[{\"address\":\"0x10002000\","
            + "\"size\":8,\"file_offset\":\"0x00000200\",\"sha256\":\""
            + digest(HexFormat.of().parseHex("9090909090909090")) + "\"}],"
            + "\"operations\":[{\"kind\":\"read\",\"pc\":\"0x10001000\",\"address\":\"0x10002004\",\"size\":4},"
            + "{\"kind\":\"write\",\"pc\":\"0x10001002\",\"address\":\"0x10002000\",\"size\":4}]}}")
            .getAsJsonObject();
    }

    private static JsonObject input(JsonObject request) { return request.getAsJsonObject("elf_data"); }
    private static JsonObject region(JsonObject request) { return input(request).getAsJsonArray("regions").get(0).getAsJsonObject(); }
    private static JsonObject operation(JsonObject request, int index) { return input(request).getAsJsonArray("operations").get(index).getAsJsonObject(); }

    private static JsonArray observations() {
        return JsonParser.parseString("[{\"address\":\"0x10002000\",\"hex\":\"9090909090909090\"},"
            + "{\"address\":\"0x2400FFF0\",\"fill\":\"a5\",\"size\":16}]").getAsJsonArray();
    }

    private static void schemaTests() throws Exception {
        JsonObject legacy = JsonParser.parseString("{\"version_input\":null,\"irq_p16\":false}").getAsJsonObject();
        JsonObject before = legacy.deepCopy();
        require(ElfDataObservations.parse(legacy) == null && legacy.equals(before));
        require(ElfDataObservations.parse(new JsonObject()) == null);
        for (String value : new String[]{"null", "0", "true", "[]", "\"data\""}) {
            JsonObject request = request();
            request.add("elf_data", JsonParser.parseString(value));
            rejected(() -> ElfDataObservations.parse(request), "must be an object");
        }
        for (String member : new String[]{"regions", "operations"}) {
            JsonObject missing = request(); input(missing).remove(member);
            rejected(() -> ElfDataObservations.parse(missing), "members");
            for (String value : new String[]{"null", "0", "true", "{}", "[]", "[null]", "[{}]"}) {
                JsonObject request = request(); input(request).add(member, JsonParser.parseString(value));
                rejected(() -> ElfDataObservations.parse(request), "ELF data");
            }
        }
        for (String field : new String[]{"address", "size", "file_offset", "sha256"}) {
            JsonObject missing = request(); region(missing).remove(field);
            rejected(() -> ElfDataObservations.parse(missing), "members");
            for (String value : new String[]{"null", "true", "[]", "{}"}) {
                JsonObject request = request(); region(request).add(field, JsonParser.parseString(value));
                rejected(() -> ElfDataObservations.parse(request), "ELF data");
            }
        }
        for (String field : new String[]{"kind", "pc", "address", "size"}) {
            JsonObject missing = request(); operation(missing, 0).remove(field);
            rejected(() -> ElfDataObservations.parse(missing), "members");
            for (String value : new String[]{"null", "true", "[]", "{}"}) {
                JsonObject request = request(); operation(request, 0).add(field, JsonParser.parseString(value));
                rejected(() -> ElfDataObservations.parse(request), "ELF data");
            }
        }
        for (String field : new String[]{"hex", "fill", "value", "registers", "default"}) {
            JsonObject outer = request(); input(outer).addProperty(field, "00");
            rejected(() -> ElfDataObservations.parse(outer), "members");
            JsonObject region = request(); region(region).addProperty(field, "00");
            rejected(() -> ElfDataObservations.parse(region), "members");
            JsonObject operation = request(); operation(operation, 0).addProperty(field, "00");
            rejected(() -> ElfDataObservations.parse(operation), "members");
        }
        for (String value : new String[]{"0", "-1", "1.5", "1e3", "1048577", "2147483648", "1e100", "\"4\""}) {
            JsonObject region = request(); region(region).add("size", JsonParser.parseString(value));
            rejected(() -> ElfDataObservations.parse(region), "size");
            JsonObject operation = request(); operation(operation, 0).add("size", JsonParser.parseString(value));
            rejected(() -> ElfDataObservations.parse(operation), "size");
        }
        for (String value : new String[]{"0X10002000", "0x10002", "10002000", "0x100020000", "0x1000200g", " 0x10002000"}) {
            for (String field : new String[]{"address", "file_offset"}) {
                JsonObject request = request(); region(request).addProperty(field, value);
                rejected(() -> ElfDataObservations.parse(request), "ELF data");
            }
        }
        for (String value : new String[]{"", "ab", "A".repeat(64), "g".repeat(64), "0".repeat(65)}) {
            JsonObject request = request(); region(request).addProperty("sha256", value);
            rejected(() -> ElfDataObservations.parse(request), "digest");
        }
        for (String value : new String[]{"read ", "READ", "execute", "modify", "supplied_read"}) {
            JsonObject request = request(); operation(request, 0).addProperty("kind", value);
            rejected(() -> ElfDataObservations.parse(request), "kind");
        }
        for (String value : new String[]{"0x10001001", "0xFFFFFFFF"}) {
            JsonObject request = request(); operation(request, 0).addProperty("pc", value);
            rejected(() -> ElfDataObservations.parse(request), "pc");
        }
        for (String field : new String[]{"address", "file_offset"}) {
            JsonObject request = request(); region(request).addProperty(field, "0xFFFFFFFC");
            rejected(() -> ElfDataObservations.parse(request), "Wrapping");
        }
        for (String value : new String[]{"0x24000000", "0x23FFFFFC", "0xE4000000", "0x7C000000", "0x0EE056AC"}) {
            JsonObject request = request(); region(request).addProperty("address", value);
            rejected(() -> ElfDataObservations.parse(request), "memory policy");
        }
        JsonObject overlap = request(); input(overlap).getAsJsonArray("regions").add(region(overlap).deepCopy());
        rejected(() -> ElfDataObservations.parse(overlap), "Overlapping");
        JsonObject unused = request(); JsonObject extra = region(unused).deepCopy();
        extra.addProperty("address", "0x10003000"); input(unused).getAsJsonArray("regions").add(extra);
        rejected(() -> ElfDataObservations.parse(unused), "Unused");
        for (String value : new String[]{"0x10001FFC", "0x10002006", "0x10002008", "0xFFFFFFFE"}) {
            JsonObject request = request(); operation(request, 0).addProperty("address", value);
            rejected(() -> ElfDataObservations.parse(request), "ELF data");
        }
        JsonObject immutable = request(); before = immutable.deepCopy();
        ElfDataObservations parsed = ElfDataObservations.parse(immutable);
        require(immutable.equals(before) && parsed.consumed == 0 && parsed.regions.size() == 1 && parsed.operations.size() == 2);
        operation(immutable, 0).addProperty("kind", "write");
        require(parsed.operations.get(0).kind().equals("read"));
        try { parsed.regions.clear(); throw new AssertionError("Mutable regions"); }
        catch (UnsupportedOperationException expected) { require(parsed.regions.size() == 1); }
        try { parsed.operations.clear(); throw new AssertionError("Mutable operations"); }
        catch (UnsupportedOperationException expected) { require(parsed.operations.size() == 2); }
    }

    private static byte[] elfBytes() {
        byte[] bytes = new byte[0x220];
        ByteBuffer b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        b.put(new byte[]{0x7f, 'E', 'L', 'F', 1, 1, 1});
        b.position(16); b.putShort((short)2).putShort((short)3).putInt(1).putInt((int)CODE).putInt(52);
        b.position(40); b.putShort((short)52).putShort((short)32).putShort((short)2);
        b.position(52); b.putInt(1).putInt(0x100).putInt((int)CODE).putInt((int)CODE).putInt(5).putInt(5).putInt(5).putInt(1);
        b.putInt(1).putInt(0x200).putInt((int)DATA).putInt((int)DATA).putInt(32).putInt(32).putInt(6).putInt(1);
        b.position(0x100); b.put(new byte[]{(byte)0x8b, 0x18, (byte)0x89, 0x18, (byte)0xc3});
        Arrays.fill(bytes, 0x200, 0x220, (byte)0x90);
        return bytes;
    }

    static final class Fixture implements AutoCloseable {
        final ProgramDB program;
        final String sourceDigest;
        final byte[] source;
        final Object consumer = new Object();
        Fixture() throws Exception { this(false); }
        Fixture(boolean distinctWords) throws Exception {
            source = elfBytes();
            if (distinctWords) {
                source[0x103] = 0x19;
                for (int i = 0; i < 4; i++) { source[0x204 + i] = (byte)(0xA1 + i); }
            }
            Language language = DefaultLanguageService.getLanguageService().getLanguage(new LanguageID("x86:LE:32:default"));
            program = new ProgramDB("elf-data-test", language, language.getDefaultCompilerSpec(), consumer);
            sourceDigest = digest(source);
            int transaction = program.startTransaction("fixture");
            try {
                program.setExecutableFormat(ElfLoader.ELF_NAME);
                program.setExecutableSHA256(sourceDigest);
                FileBytes file = program.getMemory().createFileBytes("fixture.elf", 0, source.length,
                    new ByteArrayInputStream(source), TaskMonitor.DUMMY);
                MemoryBlock code = program.getMemory().createInitializedBlock("code", address(CODE), file, 0x100, 5, false);
                code.setRead(true); code.setWrite(false); code.setExecute(true);
                MemoryBlock data = program.getMemory().createInitializedBlock("data", address(DATA), file, 0x200, 32, false);
                data.setRead(true); data.setWrite(true); data.setExecute(false);
                Disassembler.getDisassembler(program, TaskMonitor.DUMMY, null)
                    .disassemble(address(CODE), new AddressSet(address(CODE), address(CODE + 4)));
            } finally { program.endTransaction(transaction, true); }
            require(program.getListing().getInstructionAt(address(CODE)) != null);
            require(program.getListing().getInstructionAt(address(CODE + 2)) != null);
        }
        Address address(long n) { return program.getAddressFactory().getDefaultAddressSpace().getAddress(n); }
        AddressSet synthetic() { return new AddressSet(address(0x2400FFF0L), address(0x2400FFFFL)); }
        ElfDataObservations admit(JsonObject request, AddressSet forbidden, Set<Long> sites, JsonArray observations) throws Exception {
            ElfDataObservations result = ElfDataObservations.parse(request);
            result.preflight(program, sourceDigest, synthetic(), forbidden, sites, observations);
            return result;
        }
        ElfDataObservations admit() throws Exception { return admit(request(), synthetic(), Set.of(), observations()); }
        void mutated(Action change, String diagnostic) throws Exception {
            int transaction = program.startTransaction("invalid premise");
            try { change.run(); rejected(this::admit, diagnostic); }
            finally { program.endTransaction(transaction, false); }
        }
        public void close() { program.release(consumer); }
    }

    private static void admissionTests(Fixture f) throws Exception {
        require(f.admit().consumed == 0);
        f.mutated(() -> f.program.setExecutableFormat("Raw Binary"), "requires an ELF");
        f.mutated(() -> f.program.setExecutableSHA256("0".repeat(64)), "source identity");
        f.mutated(() -> f.program.getMemory().getBlock(f.address(DATA)).setRead(false), "nonexecuting block");
        f.mutated(() -> f.program.getMemory().getBlock(f.address(DATA)).setWrite(false), "nonexecuting block");
        f.mutated(() -> f.program.getMemory().getBlock(f.address(DATA)).setExecute(true), "nonexecuting block");
        f.mutated(() -> f.program.getMemory().getBlock(f.address(CODE)).setRead(false), "executable source");
        f.mutated(() -> f.program.getMemory().getBlock(f.address(CODE)).setExecute(false), "executable source");
        f.mutated(() -> f.program.getMemory().setByte(f.address(DATA), (byte)0x91), "current bytes differ");
        f.mutated(() -> {
            f.program.getMemory().removeBlock(f.program.getMemory().getBlock(f.address(DATA)), TaskMonitor.DUMMY);
            MemoryBlock block = f.program.getMemory().createUninitializedBlock("uninitialized", f.address(DATA), 32, false);
            block.setRead(true); block.setWrite(true);
        }, "nonexecuting block");
        f.mutated(() -> {
            f.program.getMemory().removeBlock(f.program.getMemory().getBlock(f.address(DATA)), TaskMonitor.DUMMY);
            MemoryBlock block = f.program.getMemory().createInitializedBlock("anonymous", f.address(DATA), 32,
                (byte)0x90, TaskMonitor.DUMMY, false);
            block.setRead(true); block.setWrite(true);
        }, "direct file backing");
        f.mutated(() -> {
            f.program.getMemory().removeBlock(f.program.getMemory().getBlock(f.address(DATA)), TaskMonitor.DUMMY);
            FileBytes file = f.program.getMemory().getAllFileBytes().get(0);
            MemoryBlock block = f.program.getMemory().createInitializedBlock("overlay", f.address(DATA), file, 0x200, 32, true);
            block.setRead(true); block.setWrite(true);
        }, "nonexecuting block");
        for (boolean join : new boolean[]{false, true}) {
            f.mutated(() -> {
                f.program.getMemory().removeBlock(f.program.getMemory().getBlock(f.address(DATA)), TaskMonitor.DUMMY);
                FileBytes file = f.program.getMemory().getAllFileBytes().get(0);
                MemoryBlock first = f.program.getMemory().createInitializedBlock("first", f.address(DATA), file, 0x200, 4, false);
                FileBytes other = f.program.getMemory().createFileBytes("second.elf", 0, f.source.length,
                    new ByteArrayInputStream(f.source), TaskMonitor.DUMMY);
                MemoryBlock second = f.program.getMemory().createInitializedBlock("second", f.address(DATA + 4), other, 0x204, 4, false);
                first.setRead(true); first.setWrite(true); second.setRead(true); second.setWrite(true);
                if (join) { f.program.getMemory().join(first, second); }
            }, join ? "direct file backing" : "nonexecuting block");
        }
        f.mutated(() -> {
            f.program.getMemory().removeBlock(f.program.getMemory().getBlock(f.address(DATA)), TaskMonitor.DUMMY);
            FileBytes file = f.program.getMemory().createFileBytes("embedded.elf", 1, f.source.length,
                new ByteArrayInputStream(f.source), TaskMonitor.DUMMY);
            MemoryBlock block = f.program.getMemory().createInitializedBlock("embedded", f.address(DATA), file, 0x200, 32, false);
            block.setRead(true); block.setWrite(true);
        }, "file mapping mismatch");
        f.mutated(() -> {
            f.program.getMemory().removeBlock(f.program.getMemory().getBlock(f.address(DATA)), TaskMonitor.DUMMY);
            MemoryBlock block = f.program.getMemory().createByteMappedBlock("mapped", f.address(DATA), f.address(CODE), 5, false);
            block.setRead(true); block.setWrite(true);
        }, "nonexecuting block");
        f.mutated(() -> {
            f.program.getMemory().removeBlock(f.program.getMemory().getBlock(f.address(DATA)), TaskMonitor.DUMMY);
            FileBytes file = f.program.getMemory().createFileBytes("different.elf", 0, 32,
                new ByteArrayInputStream(Arrays.copyOfRange(f.source, 0x200, 0x220)), TaskMonitor.DUMMY);
            MemoryBlock block = f.program.getMemory().createInitializedBlock("different", f.address(DATA), file, 0, 32, false);
            block.setRead(true); block.setWrite(true);
        }, "file mapping mismatch");
        f.mutated(() -> {
            byte[] other = f.source.clone(); other[0x80] ^= 1;
            f.program.getMemory().removeBlock(f.program.getMemory().getBlock(f.address(DATA)), TaskMonitor.DUMMY);
            FileBytes file = f.program.getMemory().createFileBytes("different.elf", 0, other.length,
                new ByteArrayInputStream(other), TaskMonitor.DUMMY);
            MemoryBlock block = f.program.getMemory().createInitializedBlock("different", f.address(DATA), file, 0x200, 32, false);
            block.setRead(true); block.setWrite(true);
        }, "original file digest");
        f.mutated(() -> {
            MemoryBlock block = f.program.getMemory().getBlock(f.address(DATA)); block.setExecute(true);
            Disassembler.getDisassembler(f.program, TaskMonitor.DUMMY, null)
                .disassemble(f.address(DATA), new AddressSet(f.address(DATA), f.address(DATA)));
            block.setExecute(false);
        }, "instruction bytes");
        f.mutated(() -> {
            MemoryBlock block = f.program.getMemory().getBlock(f.address(DATA)); block.setExecute(true);
            Disassembler.getDisassembler(f.program, TaskMonitor.DUMMY, null)
                .disassemble(f.address(DATA + 7), new AddressSet(f.address(DATA + 7), f.address(DATA + 7)));
            block.setExecute(false);
        }, "instruction bytes");
        for (String field : new String[]{"file_offset", "sha256"}) {
            JsonObject request = request(); region(request).addProperty(field, field.equals("file_offset") ? "0x00000201" : "0".repeat(64));
            rejected(() -> f.admit(request, f.synthetic(), Set.of(), observations()), field.equals("file_offset") ? "mapping mismatch" : "region digest");
        }
        AddressSet collision = f.synthetic(); collision.add(f.address(DATA + 7), f.address(DATA + 7));
        rejected(() -> f.admit(request(), collision, Set.of(), observations()), "overlaps supplied memory");
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(DATA), observations()), "overlaps supplied instruction");
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(CODE), observations()), "collides with supplied site");
        for (String pc : new String[]{"0x10001006", "0x10002000"}) {
            JsonObject request = request(); operation(request, 0).addProperty("pc", pc);
            rejected(() -> f.admit(request, f.synthetic(), Set.of(), observations()), "ELF data");
        }
        JsonObject width = request(); operation(width, 0).addProperty("size", 2);
        rejected(() -> f.admit(width, f.synthetic(), Set.of(), observations()), "matching scalar memory");
        JsonObject kind = request(); operation(kind, 0).addProperty("kind", "write");
        rejected(() -> f.admit(kind, f.synthetic(), Set.of(), observations()), "matching scalar memory");
        for (JsonArray observations : new JsonArray[]{new JsonArray(), JsonParser.parseString("[null]").getAsJsonArray()}) {
            rejected(() -> f.admit(request(), f.synthetic(), Set.of(), observations), "ELF data");
        }
        JsonArray duplicate = observations(); duplicate.add(duplicate.get(0).deepCopy());
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(), duplicate), "Duplicate");
        for (String value : new String[]{"", "90", "90909090", "909090909090909090", "zz"}) {
            JsonArray observations = observations(); observations.get(0).getAsJsonObject().addProperty("hex", value);
            rejected(() -> f.admit(request(), f.synthetic(), Set.of(), observations), "ELF data");
        }
        JsonArray outside = observations(); outside.get(0).getAsJsonObject().addProperty("address", "0x10003000");
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(), outside), "complete region");
        JsonArray partial = observations(); partial.get(0).getAsJsonObject().addProperty("address", "0x10002001");
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(), partial), "complete region");
        JsonArray synthetic = observations(); synthetic.get(1).getAsJsonObject().addProperty("address", "0x24000000");
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(), synthetic), "outside declared synthetic");
        AddressSet replyOnly = f.synthetic(); replyOnly.add(f.address(0x24000000L), f.address(0x2400000FL));
        rejected(() -> f.admit(request(), replyOnly, Set.of(), synthetic), "outside declared synthetic");
        JsonArray emptySynthetic = observations(); emptySynthetic.get(1).getAsJsonObject().addProperty("size", 0);
        require(f.admit(request(), f.synthetic(), Set.of(), emptySynthetic).consumed == 0);
        JsonArray sourceFill = observations(); sourceFill.get(0).getAsJsonObject().remove("hex");
        sourceFill.get(0).getAsJsonObject().addProperty("fill", "90");
        sourceFill.get(0).getAsJsonObject().addProperty("size", 8);
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(), sourceFill), "complete region");
        JsonArray extraMember = observations(); extraMember.get(0).getAsJsonObject().addProperty("value", 0);
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(), extraMember), "complete region");
        JsonArray wrapping = observations(); wrapping.get(0).getAsJsonObject().addProperty("address", "0xFFFFFFFC");
        rejected(() -> f.admit(request(), f.synthetic(), Set.of(), wrapping), "Wrapping");
    }

    private static void runtimeTests(Fixture f) throws Exception {
        ElfDataObservations record = f.admit(); JsonArray events = new JsonArray();
        require(!record.observe("read", CODE, 0x2400FFF0L, 4, new byte[4], events));
        rejected(() -> record.observe("read", CODE, DATA + 4, 4, new byte[4], events), "outside original instruction");
        rejected(record::finish, "Unused");
        record.beginInstruction(CODE, 7);
        rejected(() -> record.beginInstruction(CODE, 7), "outside admitted");
        rejected(() -> record.observe("read", CODE + 2, DATA + 4, 4, new byte[4], events), "outside original instruction");
        rejected(() -> record.observe("read", CODE, DATA - 1, 4, new byte[4], events), "Partial");
        rejected(() -> record.observe("read", CODE, DATA + 6, 4, new byte[4], events), "Partial");
        rejected(() -> record.observe("read", CODE, DATA + 4, 4, new byte[3], events), "Partial");
        rejected(() -> record.observe("write", CODE, DATA + 4, 4, new byte[4], events), "Unexpected");
        rejected(() -> record.observe("read", CODE, DATA, 4, new byte[4], events), "Unexpected");
        rejected(() -> record.observe("read", CODE, DATA + 4, 2, new byte[2], events), "Unexpected");
        require(record.consumed == 0 && events.isEmpty());
        require(record.observe("read", CODE, DATA + 4, 4, new byte[]{1, 2, 3, 4}, events));
        record.endInstruction();
        rejected(record::finish, "Unused");
        record.beginInstruction(CODE + 2, 8);
        require(record.observe("write", CODE + 2, DATA, 4, new byte[]{5, 6, 7, 8}, events));
        rejected(() -> record.observe("write", CODE + 2, DATA, 4, new byte[4], events), "Exhausted");
        record.endInstruction(); record.finish();
        require(record.consumed == 2 && events.size() == 2);
        JsonObject read = events.get(0).getAsJsonObject(), write = events.get(1).getAsJsonObject();
        require(read.get("kind").getAsString().equals("elf_data_read") && read.get("hex").getAsString().equals("01020304"));
        require(write.get("kind").getAsString().equals("elf_data_write") && write.get("hex").getAsString().equals("05060708"));
        require(read.get("operation_index").getAsInt() == 0 && write.get("operation_index").getAsInt() == 1);
        require(read.get("step").getAsInt() == 7 && write.get("step").getAsInt() == 8);
        rejected(() -> record.preflight(f.program, f.sourceDigest, f.synthetic(), f.synthetic(), Set.of(), observations()), "already used");
        byte[] unchanged = new byte[8]; f.program.getMemory().getBytes(f.address(DATA), unchanged);
        require(HexFormat.of().formatHex(unchanged).equals("9090909090909090"));
    }

    private static void emulatorFilterTest() throws Exception {
        try (Fixture f = new Fixture(true)) {
            JsonObject request = request();
            region(request).addProperty("sha256", digest(Arrays.copyOfRange(f.source, 0x200, 0x208)));
            ElfDataObservations record = f.admit(request, f.synthetic(), Set.of(), observations());
            JsonArray events = new JsonArray();
            boolean[] running = {false};
            EmulatorHelper emulator = new EmulatorHelper(f.program);
            try {
                emulator.writeRegister("EIP", CODE);
                emulator.writeRegister("EAX", DATA + 4);
                emulator.writeRegister("ECX", DATA);
                emulator.writeRegister("EBX", 0x12345678);
                emulator.getEmulator().addMemoryAccessFilter(new MemoryAccessFilter() {
                    protected void processRead(AddressSpace space, long address, int size, byte[] bytes) {
                        if (running[0] && space.equals(f.program.getAddressFactory().getDefaultAddressSpace())) {
                            record.observe("read", emulator.getExecutionAddress().getOffset(), address, size, bytes, events);
                        }
                    }
                    protected void processWrite(AddressSpace space, long address, int size, byte[] bytes) {
                        if (running[0] && space.equals(f.program.getAddressFactory().getDefaultAddressSpace())) {
                            require(record.observe("write", emulator.getExecutionAddress().getOffset(), address, size, bytes, events));
                        }
                    }
                });
                for (int step = 0; step < 2; step++) {
                    record.beginInstruction(emulator.getExecutionAddress().getOffset(), step);
                    running[0] = true;
                    try { require(emulator.step(TaskMonitor.DUMMY)); }
                    finally { running[0] = false; record.endInstruction(); }
                }
                record.finish();
                require(emulator.getExecutionAddress().getOffset() == CODE + 4);
                require(HexFormat.of().formatHex(emulator.readMemory(f.address(DATA), 8)).equals("a1a2a3a4a1a2a3a4"));
                require(events.size() == 2);
                require(events.get(0).getAsJsonObject().get("hex").getAsString().equals("a1a2a3a4"));
                require(events.get(1).getAsJsonObject().get("hex").getAsString().equals("a1a2a3a4"));
                require(events.get(0).getAsJsonObject().get("step").getAsInt() == 0);
                require(events.get(1).getAsJsonObject().get("step").getAsInt() == 1);
                byte[] original = new byte[8]; f.program.getMemory().getBytes(f.address(DATA), original);
                require(HexFormat.of().formatHex(original).equals("90909090a1a2a3a4"));
            } finally { emulator.dispose(); }
        }
    }

    public static void main(String[] arguments) throws Exception {
        schemaTests();
        Application.initializeApplication(new GhidraApplicationLayout(), new HeadlessGhidraApplicationConfiguration());
        try (Fixture fixture = new Fixture()) {
            admissionTests(fixture);
            runtimeTests(fixture);
        }
        emulatorFilterTest();
        System.out.println("ELF data checks passed: " + assertions + " assertions, " + rejections + " rejections");
    }
}
