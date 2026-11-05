// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.BitSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;

import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.emulator.MemoryAccessFilter;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.opinion.ElfLoader;
import ghidra.pcode.emulate.EmulateExecutionState;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.program.database.mem.FileBytes;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.lang.Register;
import ghidra.program.model.lang.RegisterValue;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Program;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.mem.MemoryBlockSourceInfo;
import ghidra.program.model.mem.MemoryBlockType;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;
import ghidra.util.task.TaskMonitor;

final class StartupZeroObservations {
    static final int MAX_STEPS = 600000, MAX_OPERATIONS = 600000, MAX_BYTES = 8388608;
    static final int MAX_OUTPUT = 1048576, CHUNK = 65536;
    static final String DATA_DOMAIN = "open27xx-startup-data-v1\0";
    static final String DECODE_DOMAIN = "open27xx-startup-decode-v1\0";

    record Span(String name, long start, int size) {
        Span {
            check(name != null && !name.isEmpty() && start >= 0 && size > 0
                && start + size <= 0x100000000L, "Invalid span");
        }
        long end() { return start + size; }
        boolean contains(long address, int width) {
            return width > 0 && address >= start && address + width <= end();
        }
        boolean overlaps(Span other) { return start < other.end() && other.start < end(); }
    }
    record Source(Span span, int offset, String sha256, boolean executable) {}
    record Allocation(Span span, int phIndex, int shIndex, int fileOffset,
                      String phSha256, String shSha256) {}
    record Geometry(String sha256, int fileSize, int machine, int phOffset, int phCount,
                    int shOffset, int shCount, List<Source> sources,
                    List<Source> envelopes, List<Allocation> allocations) {}
    record Profile(String id, Map<String, Long> registers, Span stack, byte stackFill,
                   byte bssFill, long sentinel) {}
    record Site(Instruction instruction, byte[] bytes, Source source, Source envelope) {}

    interface ContextPolicy {
        default void program(Program program, Address address) {}
        default void detached(Program program, Instruction instruction) {}
        default void boundary(RegisterValue value, boolean initial) {}
    }
    static final ContextPolicy NATIVE_CONTEXT = new ContextPolicy() {};
    static final class Vc4ContextPolicy implements ContextPolicy {
        static void zero(RegisterValue value, boolean nullable) {
            if (nullable && value == null) return;
            check(value != null && value.getRegister().getName().equals("contextreg")
                && value.getRegister().getBitLength() == 32
                && Arrays.equals(value.toBytes(), new byte[8]), "Unadmitted decoder context");
        }
        public void program(Program program, Address address) {
            Register base = program.getProgramContext().getBaseContextRegister();
            check(base != null && base.getName().equals("contextreg") && base.getBitLength() == 32, "Decoder context register");
            check(program.getProgramContext().getRegisterValue(base, address) == null
                && program.getProgramContext().getDefaultValue(base, address) == null
                && program.getProgramContext().getNonDefaultValue(base, address) == null, "Unadmitted ProgramContext");
            zero(program.getProgramContext().getDefaultDisassemblyContext(), false);
            Instruction listing = program.getListing().getInstructionAt(address);
            if (listing != null) zero(listing.getRegisterValue(base), true);
        }
        public void detached(Program program, Instruction instruction) {
            zero(instruction.getRegisterValue(program.getProgramContext().getBaseContextRegister()), false);
        }
        public void boundary(RegisterValue value, boolean initial) {
            if (initial) check(value == null, "Initial emulator context must be null");
            else zero(value, false);
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
    static String hex(long value) { return String.format("0x%08X", value); }
    static MessageDigest sha() {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch (Exception exception) { throw new IllegalStateException(exception); }
    }
    static String digest(byte[] bytes) { return HexFormat.of().formatHex(sha().digest(bytes)); }
    static JsonObject object(JsonElement value, Set<String> keys, String label) {
        check(value != null && value.isJsonObject(), "Invalid " + label);
        JsonObject result = value.getAsJsonObject();
        check(result.keySet().equals(keys), "Unexpected " + label + " members");
        return result;
    }
    static String string(JsonElement value) {
        check(value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString(),
            "Expected string");
        return value.getAsString();
    }
    static long word(JsonElement value) {
        String text = string(value);
        check(text.matches("0x[0-9A-F]{8}"), "Expected canonical word");
        return Long.parseUnsignedLong(text.substring(2), 16);
    }
    static JsonElement context(RegisterValue value) {
        if (value == null) return JsonNull.INSTANCE;
        JsonObject result = new JsonObject();
        result.addProperty("register", value.getRegister().getName());
        result.addProperty("bit_length", value.getRegister().getBitLength());
        result.addProperty("mask_value_bytes", HexFormat.of().formatHex(value.toBytes()));
        return result;
    }
    static JsonObject programContext(Program program, Address address) {
        JsonObject result = new JsonObject();
        Register base = program.getProgramContext().getBaseContextRegister();
        result.add("current", context(base == null ? null : program.getProgramContext().getRegisterValue(base, address)));
        result.add("default", context(base == null ? null : program.getProgramContext().getDefaultValue(base, address)));
        result.add("nondefault", context(base == null ? null : program.getProgramContext().getNonDefaultValue(base, address)));
        result.add("disassembly_default", context(program.getProgramContext().getDefaultDisassemblyContext()));
        return result;
    }
    static Address address(Program program, long value) {
        return program.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    static final class Admission {
        final Program program;
        final Geometry geometry;
        final ContextPolicy contextPolicy;
        final FileBytes file;
        final Map<Source, byte[]> original = new LinkedHashMap<>();
        final Map<Long, Site> sites = new TreeMap<>();
        final JsonArray initialSnapshot;
        final JsonArray sourceEvidence = new JsonArray();
        final JsonArray allocationEvidence = new JsonArray();

        Admission(Program program, Geometry geometry, TaskMonitor monitor) throws Exception {
            this(program, geometry, monitor, NATIVE_CONTEXT);
        }
        Admission(Program program, Geometry geometry, TaskMonitor monitor, ContextPolicy contextPolicy) throws Exception {
            this.program = program;
            this.geometry = geometry;
            this.contextPolicy = contextPolicy;
            check(geometry.fileSize > 0 && geometry.fileSize <= 4194304, "Source size cap");
            check(ElfLoader.ELF_NAME.equals(program.getExecutableFormat()), "Requires ELF");
            check(geometry.sha256.equals(program.getExecutableSHA256()), "Source property mismatch");
            check(program.getAddressFactory().getDefaultAddressSpace().isMemorySpace()
                && !program.getAddressFactory().getDefaultAddressSpace().isOverlaySpace(), "Default RAM required");
            List<FileBytes> files = program.getMemory().getAllFileBytes();
            check(files.size() == 1, "Ambiguous original FileBytes");
            file = files.get(0);
            check(file.getFileOffset() == 0 && file.getSize() == geometry.fileSize, "Original FileBytes size/offset");
            MessageDigest full = sha();
            byte[] buffer = new byte[CHUNK];
            for (int offset = 0; offset < geometry.fileSize;) {
                monitor.checkCancelled();
                int count = Math.min(buffer.length, geometry.fileSize - offset);
                check(file.getOriginalBytes(offset, buffer, 0, count) == count, "Short original source");
                full.update(buffer, 0, count); offset += count;
            }
            check(HexFormat.of().formatHex(full.digest()).equals(geometry.sha256), "Original source digest");
            byte[] header = readOriginal(0, 52);
            check(Arrays.equals(Arrays.copyOf(header, 7), new byte[]{0x7F, 'E', 'L', 'F', 1, 1, 1}), "ELF identity");
            ByteBuffer h = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN);
            check(Short.toUnsignedInt(h.getShort(16)) == 2 && Short.toUnsignedInt(h.getShort(18)) == geometry.machine
                && h.getInt(20) == 1 && Short.toUnsignedInt(h.getShort(40)) == 52, "ELF header mismatch");
            check(Integer.toUnsignedLong(h.getInt(28)) == geometry.phOffset && h.getShort(42) == 32
                && Short.toUnsignedInt(h.getShort(44)) == geometry.phCount
                && Integer.toUnsignedLong(h.getInt(32)) == geometry.shOffset && h.getShort(46) == 40
                && Short.toUnsignedInt(h.getShort(48)) == geometry.shCount, "ELF table metadata mismatch");
            check(geometry.phOffset >= 52 && geometry.phCount > 0 && geometry.phCount <= 128
                && (long)geometry.phOffset + 32L * geometry.phCount <= geometry.fileSize
                && geometry.shOffset >= 52 && geometry.shCount > 0 && geometry.shCount <= 256
                && (long)geometry.shOffset + 40L * geometry.shCount <= geometry.fileSize, "ELF table bounds");
            List<Source> all = new ArrayList<>(geometry.sources); all.addAll(geometry.envelopes);
            for (Source source : all) bindSource(source);
            for (int i = 0; i < geometry.allocations.size(); i++) {
                Allocation allocation = geometry.allocations.get(i);
                for (int j = 0; j < i; j++) check(!allocation.span.overlaps(geometry.allocations.get(j).span), "Allocation overlap");
                for (Source source : all) check(!allocation.span.overlaps(source.span), "Allocation/source overlap");
                bindAllocation(allocation);
            }
            initialSnapshot = snapshot();
        }
        byte[] readOriginal(int offset, int size) throws Exception {
            check(offset >= 0 && size > 0 && (long)offset + size <= geometry.fileSize, "Original range bounds");
            byte[] bytes = new byte[size];
            check(file.getOriginalBytes(offset, bytes) == size, "Short original range");
            return bytes;
        }
        void bindSource(Source source) throws Exception {
            Span span = source.span;
            Address start = address(program, span.start), end = address(program, span.end() - 1);
            MemoryBlock block = program.getMemory().getBlock(start);
            check(block != null && block.contains(end) && block.getType() == MemoryBlockType.DEFAULT
                && block.isInitialized() && block.isRead() && !block.isOverlay() && !block.isMapped()
                && (!source.executable || block.isExecute()), "Source block mismatch");
            check(block.getSourceInfos().size() <= 16, "Source descriptor cap");
            MemoryBlockSourceInfo selected = null;
            for (MemoryBlockSourceInfo info : block.getSourceInfos()) {
                if (info.contains(start) && info.contains(end)) {
                    check(selected == null, "Ambiguous direct source"); selected = info;
                }
            }
            check(selected != null && selected.getFileBytes().isPresent() && selected.getFileBytes().get().equals(file)
                && selected.getMappedRange().isEmpty() && selected.getByteMappingScheme().isEmpty()
                && selected.getFileBytesOffset(start) == source.offset
                && selected.getFileBytesOffset(end) == (long)source.offset + span.size - 1, "Direct source mapping mismatch");
            byte[] bytes = readOriginal(source.offset, span.size), current = new byte[span.size];
            check(program.getMemory().getBytes(start, current) == current.length && Arrays.equals(bytes, current), "Current source differs");
            check(digest(bytes).equals(source.sha256), "Source range digest");
            original.put(source, bytes);
            JsonObject evidence = spanJson(span);
            evidence.addProperty("file_offset", hex(source.offset)); evidence.addProperty("sha256", source.sha256);
            evidence.add("block", blockSnapshot(block)); sourceEvidence.add(evidence);
        }
        void bindAllocation(Allocation allocation) throws Exception {
            check(allocation.phIndex >= 0 && allocation.phIndex < geometry.phCount
                && allocation.shIndex >= 0 && allocation.shIndex < geometry.shCount, "Header index");
            int phOffset = geometry.phOffset + allocation.phIndex * 32;
            int shOffset = geometry.shOffset + allocation.shIndex * 40;
            byte[] phBytes = readOriginal(phOffset, 32), shBytes = readOriginal(shOffset, 40);
            check(digest(phBytes).equals(allocation.phSha256) && digest(shBytes).equals(allocation.shSha256), "Allocation header digest");
            ByteBuffer ph = ByteBuffer.wrap(phBytes).order(ByteOrder.LITTLE_ENDIAN);
            ByteBuffer sh = ByteBuffer.wrap(shBytes).order(ByteOrder.LITTLE_ENDIAN);
            Span span = allocation.span;
            check(ph.getInt(0) == 1 && Integer.toUnsignedLong(ph.getInt(4)) == allocation.fileOffset
                && Integer.toUnsignedLong(ph.getInt(8)) == span.start && Integer.toUnsignedLong(ph.getInt(12)) == span.start
                && ph.getInt(16) == 0 && Integer.toUnsignedLong(ph.getInt(20)) == span.size
                && ph.getInt(24) == 6 && ph.getInt(28) == 32, "Zero-file-size PT_LOAD mismatch");
            check(sh.getInt(4) == 8 && sh.getInt(8) == 3 && Integer.toUnsignedLong(sh.getInt(12)) == span.start
                && Integer.toUnsignedLong(sh.getInt(16)) == allocation.fileOffset
                && Integer.toUnsignedLong(sh.getInt(20)) == span.size && sh.getInt(32) == 32, "NOBITS mismatch");
            MemoryBlock block = allocationBlock(span);
            JsonObject evidence = spanJson(span);
            evidence.addProperty("program_header_offset", hex(phOffset)); evidence.addProperty("program_header_sha256", digest(phBytes));
            evidence.addProperty("section_header_offset", hex(shOffset)); evidence.addProperty("section_header_sha256", digest(shBytes));
            evidence.add("block", blockSnapshot(block)); allocationEvidence.add(evidence);
        }
        MemoryBlock allocationBlock(Span span) {
            Address start = address(program, span.start), end = address(program, span.end() - 1);
            MemoryBlock block = program.getMemory().getBlock(start);
            check(block != null && block.getStart().equals(start) && block.getEnd().equals(end)
                && block.getType() == MemoryBlockType.DEFAULT && !block.isOverlay() && !block.isMapped()
                && !block.isInitialized() && block.isRead() && block.isWrite() && !block.isExecute(), "Uninitialized allocation block mismatch");
            check(program.getListing().getInstructionContaining(start) == null
                && !program.getListing().getInstructions(new AddressSet(start, end), true).hasNext(), "Allocation overlaps instruction");
            return block;
        }
        void decode(int instructionCap) throws Exception {
            check(sites.isEmpty(), "Already decoded");
            for (Source source : geometry.sources) {
                if (!source.executable) continue;
                for (long pc = source.span.start; pc < source.span.end();) {
                    check(sites.size() < instructionCap, "Instruction site cap");
                    byte[] remaining = Arrays.copyOfRange(original.get(source), (int)(pc - source.span.start), source.span.size);
                    Instruction instruction = new PseudoDisassembler(program).disassemble(address(program, pc), remaining);
                    check(instruction != null && instruction.getAddress().equals(address(program, pc)), "Detached decode failed");
                    contextPolicy.detached(program, instruction);
                    int size = instruction.getLength();
                    check(size > 0 && size <= 16 && source.span.contains(pc, size), "Instruction crosses source range");
                    check(instruction.getDelaySlotDepth() == 0 && !instruction.isInDelaySlot()
                        && !instruction.getPrototype().hasDelaySlots() && !instruction.getPrototype().hasNext2Dependency(), "Unsupported decode dependency");
                    for (PcodeOp operation : instruction.getPcode()) check(operation.getOpcode() != PcodeOp.CALLOTHER, "Unsupported user operation");
                    check(!instruction.getMnemonicString().toLowerCase().startsWith("v"), "Vector instruction");
                    check(Arrays.equals(instruction.getBytes(), Arrays.copyOf(remaining, size)), "Detached bytes differ");
                    Source envelope = null;
                    for (Source candidate : geometry.envelopes) if (candidate.span.contains(pc, size)) {
                        check(envelope == null, "Ambiguous decoder envelope"); envelope = candidate;
                    }
                    check(envelope != null && sites.put(pc, new Site(instruction, instruction.getBytes(), source, envelope)) == null, "Missing envelope or duplicate site");
                    pc += size;
                }
            }
            unchanged();
        }
        JsonArray snapshot() throws Exception {
            JsonArray result = new JsonArray();
            for (Source source : original.keySet()) {
                byte[] bytes = new byte[source.span.size];
                check(program.getMemory().getBytes(address(program, source.span.start), bytes) == bytes.length, "Short snapshot source");
                JsonObject range = spanJson(source.span); range.addProperty("sha256", digest(bytes));
                range.add("block", blockSnapshot(program.getMemory().getBlock(address(program, source.span.start))));
                JsonArray listing = new JsonArray();
                for (long pc = source.span.start; pc < source.span.end(); pc++) {
                    Address location = address(program, pc);
                    contextPolicy.program(program, location);
                    JsonObject item = new JsonObject(); item.addProperty("pc", hex(pc));
                    Instruction ins = program.getListing().getInstructionAt(location);
                    item.addProperty("present", ins != null);
                    if (ins != null) {
                        item.addProperty("length", ins.getLength()); item.addProperty("bytes", HexFormat.of().formatHex(ins.getBytes()));
                        Register base = program.getProgramContext().getBaseContextRegister();
                        item.add("listing_input_context", context(base == null ? null : ins.getRegisterValue(base)));
                    }
                    item.add("context", programContext(program, location)); listing.add(item);
                }
                range.add("listing_context", listing); result.add(range);
            }
            for (Allocation allocation : geometry.allocations) result.add(blockSnapshot(allocationBlock(allocation.span)));
            return result;
        }
        void unchanged() throws Exception { check(initialSnapshot.equals(snapshot()), "Program source/listing/context changed"); }
    }

    static JsonObject spanJson(Span span) {
        JsonObject result = new JsonObject(); result.addProperty("name", span.name);
        result.addProperty("address", hex(span.start)); result.addProperty("size", span.size); return result;
    }
    static JsonObject blockSnapshot(MemoryBlock block) {
        JsonObject result = new JsonObject();
        result.addProperty("name", block.getName()); result.addProperty("start", block.getStart().toString()); result.addProperty("end", block.getEnd().toString());
        result.addProperty("initialized", block.isInitialized()); result.addProperty("read", block.isRead());
        result.addProperty("write", block.isWrite()); result.addProperty("execute", block.isExecute());
        result.addProperty("type", block.getType().toString()); result.addProperty("overlay", block.isOverlay()); result.addProperty("mapped", block.isMapped());
        JsonArray sources = new JsonArray();
        check(block.getSourceInfos().size() <= 16, "Block source cap");
        for (MemoryBlockSourceInfo info : block.getSourceInfos()) {
            JsonObject source = new JsonObject(); source.addProperty("min", info.getMinAddress().toString()); source.addProperty("max", info.getMaxAddress().toString());
            source.addProperty("file_backed", info.getFileBytes().isPresent());
            source.addProperty("mapped", info.getMappedRange().isPresent()); source.addProperty("byte_mapping", info.getByteMappingScheme().isPresent());
            if (info.getFileBytes().isPresent()) {
                source.addProperty("file_offset", info.getFileBytesOffset(info.getMinAddress()));
                source.addProperty("file_size", info.getFileBytes().get().getSize());
            }
            sources.add(source);
        }
        result.add("sources", sources); return result;
    }

    static final class Stream {
        final MessageDigest hash = sha();
        long operations, bytes, reads, writes, readBytes, writeBytes;
        Stream(String domain) { hash.update(domain.getBytes(StandardCharsets.US_ASCII)); }
        void event(long pc, boolean write, long address, int width, byte[] values) {
            check(pc >= 0 && pc <= 0xFFFFFFFFL && address >= 0 && width > 0 && width <= CHUNK
                && address + width <= 0x100000000L && values.length >= width, "Invalid event geometry");
            check(operations < MAX_OPERATIONS && bytes <= MAX_BYTES - width, "Access budget exhausted");
            byte[] head = ByteBuffer.allocate(21).order(ByteOrder.LITTLE_ENDIAN).putLong(operations)
                .putInt((int)pc).put((byte)(write ? 1 : 0)).putInt((int)address).putInt(width).array();
            hash.update(head); hash.update(values, 0, width);
            operations = Math.addExact(operations, 1); bytes = Math.addExact(bytes, width);
            if (write) { writes++; writeBytes += width; } else { reads++; readBytes += width; }
        }
        String digest() {
            try { return HexFormat.of().formatHex(((MessageDigest)hash.clone()).digest()); }
            catch (CloneNotSupportedException exception) { throw new IllegalStateException(exception); }
        }
        JsonObject json() {
            JsonObject result = new JsonObject(); result.addProperty("operations", operations); result.addProperty("bytes", bytes);
            result.addProperty("read_operations", reads); result.addProperty("write_operations", writes);
            result.addProperty("read_bytes", readBytes); result.addProperty("write_bytes", writeBytes);
            result.addProperty("sha256", digest()); return result;
        }
    }
    static final class Coverage {
        final Span span;
        final BitSet reads = new BitSet(), writes = new BitSet();
        long duplicateReads, duplicateWrites;
        Coverage(Span span) { this.span = span; }
        void observe(boolean write, long address, int width) {
            int offset = (int)(address - span.start);
            BitSet set = write ? writes : reads;
            if (write) duplicateWrites += set.get(offset, offset + width).cardinality();
            else duplicateReads += set.get(offset, offset + width).cardinality();
            set.set(offset, offset + width);
        }
        JsonObject json() {
            JsonObject result = spanJson(span);
            result.addProperty("unique_read_bytes", reads.cardinality()); result.addProperty("unique_written_bytes", writes.cardinality());
            result.addProperty("duplicate_written_bytes", duplicateWrites);
            result.addProperty("duplicate_read_bytes", duplicateReads);
            int size = (span.size + 7) / 8;
            result.addProperty("read_coverage_sha256", digest(Arrays.copyOf(reads.toByteArray(), size)));
            result.addProperty("write_coverage_sha256", digest(Arrays.copyOf(writes.toByteArray(), size)));
            return result;
        }
    }
    static final class Observer {
        final List<Span> data;
        final Set<String> writable;
        final Map<String, Coverage> coverage = new LinkedHashMap<>();
        final Stream runtime = new Stream(DATA_DOMAIN), decoder = new Stream(DECODE_DOMAIN);
        final Map<String, long[]> histogram = new TreeMap<>();
        boolean active, failed;
        String failure;
        long pc;
        Span envelope;
        Observer(List<Span> data, Set<String> writable) {
            this.data = List.copyOf(data); this.writable = Set.copyOf(writable);
            for (Span span : data) check(coverage.put(span.name, new Coverage(span)) == null, "Duplicate region name");
        }
        void begin(long pc, Span envelope) { check(!active && !failed, "Observer lifecycle"); this.pc = pc; this.envelope = envelope; active = true; }
        void end() { active = false; }
        void observe(EmulateExecutionState phase, boolean write, long location, int width, byte[] values) {
            try {
                if (!active) return;
                check(!failed, "Case already invalid");
                if (phase == EmulateExecutionState.INSTRUCTION_DECODE) {
                    check(!write && envelope.contains(location, width),
                        "Decoder envelope violation at " + hex(location) + " width " + width + " write " + write);
                    decoder.event(pc, false, location, width, values); return;
                }
                check(phase == EmulateExecutionState.EXECUTE, "Unexpected memory phase");
                Span selected = null;
                for (Span span : data) if (span.contains(location, width)) { check(selected == null, "Ambiguous data access"); selected = span; }
                check(selected != null && (!write || writable.contains(selected.name)),
                    "Runtime memory violation at " + hex(location) + " width " + width + " write " + write);
                runtime.event(pc, write, location, width, values);
                coverage.get(selected.name).observe(write, location, width);
                String key = selected.name + ":" + hex(pc) + ":" + (write ? "write" : "read") + ":" + width;
                check(histogram.containsKey(key) || histogram.size() < 4096, "Histogram cap");
                long[] counts = histogram.computeIfAbsent(key, ignored -> new long[2]);
                counts[0] = Math.addExact(counts[0], 1); counts[1] = Math.addExact(counts[1], width);
            } catch (RuntimeException exception) { failed = true; if (failure == null) failure = exception.getMessage(); throw exception; }
        }
        JsonObject json() {
            check(!active && !failed, "Invalid case has no successful observations");
            JsonObject result = new JsonObject(); result.add("data_stream", runtime.json()); result.add("decoder_stream", decoder.json());
            JsonArray regions = new JsonArray(); for (Coverage value : coverage.values()) regions.add(value.json()); result.add("coverage", regions);
            JsonObject counts = new JsonObject(); histogram.forEach((key, value) -> {
                JsonObject item = new JsonObject(); item.addProperty("operations", value[0]); item.addProperty("bytes", value[1]); counts.add(key, item);
            }); result.add("by_region_pc_kind_width", counts); return result;
        }
    }

    interface Reader { byte[] read(long address, int size) throws Exception; }
    static JsonObject scan(Span span, Reader reader) throws Exception {
        MessageDigest actual = sha(), zero = sha(); long nonzero = 0; Long first = null;
        for (int offset = 0; offset < span.size;) {
            int width = Math.min(CHUNK, span.size - offset);
            byte[] bytes = reader.read(span.start + offset, width);
            check(bytes != null && bytes.length == width, "Short complete observation");
            actual.update(bytes); zero.update(new byte[width]);
            for (int i = 0; i < width; i++) if (bytes[i] != 0) { nonzero++; if (first == null) first = (long)offset + i; }
            offset += width;
        }
        JsonObject result = spanJson(span); result.addProperty("sha256", HexFormat.of().formatHex(actual.digest()));
        result.addProperty("zero_sha256", HexFormat.of().formatHex(zero.digest())); result.addProperty("all_zero", nonzero == 0);
        result.addProperty("nonzero_bytes", nonzero); result.add("first_nonzero_offset", first == null ? JsonNull.INSTANCE : new com.google.gson.JsonPrimitive(first));
        return result;
    }
    static JsonObject seed(EmulatorHelper emulator, Program program, Span span, byte fill) throws Exception {
        check(!emulator.getEmulator().isExecuting(), "Seed during execution");
        MessageDigest expected = sha();
        for (int offset = 0; offset < span.size;) {
            byte[] bytes = new byte[Math.min(CHUNK, span.size - offset)]; Arrays.fill(bytes, fill);
            emulator.writeMemory(address(program, span.start + offset), bytes); expected.update(bytes); offset += bytes.length;
        }
        JsonObject observed = scan(span, (location, width) -> emulator.readMemory(address(program, location), width));
        check(observed.get("sha256").getAsString().equals(HexFormat.of().formatHex(expected.digest())), "Seed readback mismatch");
        observed.addProperty("fill", String.format("%02x", fill & 255)); return observed;
    }

    static byte[] pcodeEncoding(Instruction instruction) {
        java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
        bytes.writeBytes("open27xx-startup-pcode-v1\0".getBytes(StandardCharsets.US_ASCII));
        for (PcodeOp operation : instruction.getPcode()) {
            bytes.writeBytes(ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN)
                .putInt(operation.getOpcode()).putInt(operation.getNumInputs()).array());
            List<Varnode> nodes = new ArrayList<>(); nodes.add(operation.getOutput()); nodes.addAll(Arrays.asList(operation.getInputs()));
            for (Varnode node : nodes) {
                bytes.write(node == null ? 0 : 1);
                if (node != null) {
                    byte[] name = node.getAddress().getAddressSpace().getName().getBytes(StandardCharsets.UTF_8);
                    bytes.writeBytes(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(name.length).array()); bytes.writeBytes(name);
                    bytes.writeBytes(ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN).putLong(node.getOffset()).putInt(node.getSize()).array());
                }
            }
        }
        return bytes.toByteArray();
    }
    static JsonArray siteEvidence(Admission admission) {
        JsonArray sites = new JsonArray();
        admission.sites.forEach((pc, site) -> {
            JsonObject value = new JsonObject(); value.addProperty("pc", hex(pc)); value.addProperty("length", site.bytes.length);
            value.addProperty("bytes_sha256", digest(site.bytes)); value.addProperty("pcode_sha256", digest(pcodeEncoding(site.instruction)));
            value.addProperty("listing_present", admission.program.getListing().getInstructionAt(address(admission.program, pc)) != null);
            value.add("program_context", programContext(admission.program, address(admission.program, pc)));
            Register base = admission.program.getProgramContext().getBaseContextRegister();
            Instruction listing = admission.program.getListing().getInstructionAt(address(admission.program, pc));
            value.add("listing_input_context", context(listing == null || base == null ? null : listing.getRegisterValue(base)));
            value.add("detached_context", context(base == null ? null : site.instruction.getRegisterValue(base))); sites.add(value);
        }); return sites;
    }
    static void validateProfile(Admission admission, Profile profile) {
        check(profile.stack.size == 128 && (profile.stack.start & 3) == 0
            && ((profile.stack.start >= 0x24000000L && profile.stack.end() <= 0x25000000L)
                || (profile.stack.start >= 0xE4000000L && profile.stack.end() <= 0xE5000000L)), "Invalid synthetic stack");
        check(profile.bssFill != 0, "Zero BSS poison");
        check(profile.sentinel >= 0 && profile.sentinel <= 0xFFFFFFFFL
            && !profile.stack.contains(profile.sentinel, 1), "Return sentinel overlaps stack");
        check(admission.program.getMemory().getBlock(address(admission.program, profile.sentinel)) == null, "Return sentinel is mapped");
        for (Allocation allocation : admission.geometry.allocations) {
            check(!allocation.span.overlaps(profile.stack) && !allocation.span.contains(profile.sentinel, 1), "Stack/sentinel allocation overlap");
        }
        for (Source source : admission.original.keySet()) check(!source.span.overlaps(profile.stack)
            && !source.span.contains(profile.sentinel, 1), "Stack/sentinel source overlap");
        Set<String> offsets = new java.util.HashSet<>();
        for (Map.Entry<String, Long> entry : profile.registers.entrySet()) {
            Register reg = admission.program.getRegister(entry.getKey());
            check(reg != null && !reg.isProcessorContext() && reg.getBitLength() == 32
                && offsets.add(reg.getAddress().toString()), "Register alias or unsupported register");
        }
    }
    static JsonObject capture(Admission admission, Profile profile, long entry, long terminal,
            TaskMonitor monitor) throws Exception {
        return capture(admission, profile, entry, terminal, monitor, MAX_STEPS);
    }
    static JsonObject capture(Admission admission, Profile profile, long entry, long terminal,
            TaskMonitor monitor, int stepLimit) throws Exception {
        check(stepLimit > 0 && stepLimit <= MAX_STEPS, "Invalid instruction budget");
        validateProfile(admission, profile); admission.unchanged();
        Program program = admission.program;
        List<Span> data = new ArrayList<>(); Set<String> writes = new java.util.HashSet<>();
        for (Source source : admission.geometry.sources) if (!source.executable) data.add(source.span);
        for (Allocation allocation : admission.geometry.allocations) { data.add(allocation.span); writes.add(allocation.span.name); }
        data.add(profile.stack); writes.add(profile.stack.name);
        Observer observer = new Observer(data, writes);
        EmulatorHelper emulator = new EmulatorHelper(program);
        int steps = 0;
        try {
            emulator.setMemoryFaultHandler(new MemoryFaultHandler() {
                public boolean uninitializedRead(Address address, int size, byte[] buffer, int offset) {
                    observer.failed = true;
                    throw new IllegalStateException("Uninitialized memory " + address + " width " + size);
                }
                public boolean unknownAddress(Address address, boolean write) {
                    observer.failed = true;
                    throw new IllegalStateException("Unknown memory " + address + " write " + write);
                }
            });
            emulator.getEmulator().addMemoryAccessFilter(new MemoryAccessFilter() {
                protected void processRead(AddressSpace space, long offset, int size, byte[] values) {
                    if (space.isMemorySpace()) {
                        check(space.equals(program.getAddressFactory().getDefaultAddressSpace()), "Nondefault memory space");
                        observer.observe(emulator.getEmulateExecutionState(), false, offset, size, values);
                    }
                }
                protected void processWrite(AddressSpace space, long offset, int size, byte[] values) {
                    if (space.isMemorySpace()) {
                        check(space.equals(program.getAddressFactory().getDefaultAddressSpace()), "Nondefault memory space");
                        observer.observe(emulator.getEmulateExecutionState(), true, offset, size, values);
                    }
                }
            });
            JsonObject output = new JsonObject(); output.addProperty("id", profile.id);
            admission.contextPolicy.boundary(emulator.getEmulator().getContextRegisterValue(), true);
            output.add("context_before_seed", context(emulator.getEmulator().getContextRegisterValue()));
            for (Map.Entry<String, Long> input : profile.registers.entrySet()) emulator.writeRegister(input.getKey(), input.getValue());
            check(emulator.getExecutionAddress().getOffset() == entry, "Entry register mismatch");
            JsonArray seeds = new JsonArray();
            for (Allocation allocation : admission.geometry.allocations) seeds.add(seed(emulator, program, allocation.span, profile.bssFill));
            seeds.add(seed(emulator, program, profile.stack, profile.stackFill)); output.add("seed_readback", seeds);
            admission.contextPolicy.boundary(emulator.getEmulator().getContextRegisterValue(), true);
            output.add("context_before_first_step", context(emulator.getEmulator().getContextRegisterValue()));
            JsonObject initialRegisters = new JsonObject();
            for (String name : profile.registers.keySet()) initialRegisters.addProperty(name, hex(emulator.readRegister(name).longValue() & 0xFFFFFFFFL));
            output.add("initial_registers", initialRegisters);
            Map<Long, Long> multiplicity = new TreeMap<>();
            Map<String, JsonObject> contexts = new LinkedHashMap<>();
            Map<Long, Set<String>> contextKeys = new TreeMap<>();
            JsonArray transfers = new JsonArray();
            long last = -1;
            while (emulator.getExecutionAddress().getOffset() != profile.sentinel) {
                monitor.checkCancelled();
                long pc = emulator.getExecutionAddress().getOffset();
                check(steps < stepLimit, "Instruction budget exhausted at " + hex(pc));
                Site site = admission.sites.get(pc); check(site != null, "Execution leaves selected sites at " + hex(pc));
                check(Arrays.equals(site.bytes, emulator.readMemory(address(program, pc), site.bytes.length)), "Instruction bytes changed at " + hex(pc));
                JsonElement before = context(emulator.getEmulator().getContextRegisterValue());
                admission.contextPolicy.boundary(emulator.getEmulator().getContextRegisterValue(), steps == 0);
                observer.begin(pc, site.envelope.span);
                try {
                    boolean completed = emulator.step(monitor);
                    check(completed, "Emulation failed at " + hex(pc) + ": "
                        + (observer.failure == null ? emulator.getLastError() : observer.failure));
                }
                finally { observer.end(); }
                check(!observer.failed, "Invalid memory observation");
                steps++; last = pc;
                multiplicity.merge(pc, 1L, Math::addExact);
                JsonElement after = context(emulator.getEmulator().getContextRegisterValue());
                admission.contextPolicy.boundary(emulator.getEmulator().getContextRegisterValue(), false);
                String key = hex(pc) + ":" + before + ":" + after;
                Set<String> variants = contextKeys.computeIfAbsent(pc, ignored -> new java.util.HashSet<>());
                variants.add(key); check(variants.size() <= 2 && contexts.size() <= 2 * admission.sites.size(), "Context variant cap");
                JsonObject state = contexts.get(key);
                if (state == null) {
                    state = new JsonObject(); state.addProperty("pc", hex(pc)); state.add("before", before); state.add("after", after);
                    state.addProperty("count", 0); contexts.put(key, state);
                }
                state.addProperty("count", Math.addExact(state.get("count").getAsLong(), 1));
                long next = emulator.getExecutionAddress().getOffset();
                boolean control = Arrays.stream(site.instruction.getPcode()).anyMatch(op -> op.getOpcode() == PcodeOp.CALL
                    || op.getOpcode() == PcodeOp.CALLIND || op.getOpcode() == PcodeOp.RETURN);
                if (control) {
                    check(transfers.size() < 64, "Control transfer cap");
                    JsonObject transfer = new JsonObject(); transfer.addProperty("step", steps - 1);
                    transfer.addProperty("pc", hex(pc)); transfer.addProperty("next_pc", hex(next)); transfers.add(transfer);
                }
                if (next == profile.sentinel) check(pc == terminal
                    && Arrays.stream(site.instruction.getPcode()).anyMatch(op -> op.getOpcode() == PcodeOp.RETURN), "Sentinel reached without terminal RETURN");
                else check(admission.sites.containsKey(next), "Unexpected next PC " + hex(next));
            }
            check(steps > 0 && last == terminal, "No completed terminal return");
            output.addProperty("completed_instructions", steps); output.addProperty("last_pc", hex(last));
            output.addProperty("return_reason", "terminal_return"); output.add("control_transfers", transfers);
            JsonObject counts = new JsonObject(); multiplicity.forEach((pc, count) -> counts.addProperty(hex(pc), count)); output.add("per_pc", counts);
            JsonArray states = new JsonArray(); contexts.values().forEach(states::add); output.add("context_variants", states);
            output.add("context_after_return", context(emulator.getEmulator().getContextRegisterValue()));
            JsonObject registers = new JsonObject();
            for (String name : profile.registers.keySet()) registers.addProperty(name, hex(emulator.readRegister(name).longValue() & 0xFFFFFFFFL));
            output.add("registers", registers);
            long priorOperations = observer.runtime.operations; String priorDigest = observer.runtime.digest();
            JsonArray finals = new JsonArray();
            for (Allocation allocation : admission.geometry.allocations) finals.add(scan(allocation.span,
                (location, size) -> emulator.readMemory(address(program, location), size)));
            output.add("bss", finals);
            output.addProperty("stack_hex", HexFormat.of().formatHex(emulator.readMemory(address(program, profile.stack.start), profile.stack.size)));
            for (Map.Entry<Source, byte[]> source : admission.original.entrySet()) check(Arrays.equals(source.getValue(),
                emulator.readMemory(address(program, source.getKey().span.start), source.getKey().span.size)), "Emulator source changed");
            check(observer.runtime.operations == priorOperations && observer.runtime.digest().equals(priorDigest), "Final reads entered runtime stream");
            output.add("accesses", observer.json()); admission.unchanged();
            output.addProperty("program_source_listing_context_unchanged", true); output.addProperty("emulator_sources_unchanged", true);
            return output;
        } catch (Exception exception) {
            throw new IllegalStateException("PC " + hex(observer.pc) + ", completed instructions " + steps
                + ", data operations " + observer.runtime.operations + ", data bytes " + observer.runtime.bytes
                + ", decoder operations " + observer.decoder.operations + ": " + exception.getMessage(), exception);
        } finally { emulator.dispose(); }
    }
}
