// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import ghidra.app.util.opinion.ElfLoader;
import ghidra.program.database.mem.FileBytes;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Program;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.mem.MemoryBlockSourceInfo;
import ghidra.program.model.mem.MemoryBlockType;
import ghidra.program.model.pcode.PcodeOp;

final class ElfDataObservations {
    static final int MAX_SIZE = 1048576;
    private static final long CLOCK_CELL = 0x0EE056B0L;

    record Region(long address, int size, long fileOffset, String sha256) {
        long end() { return address + size; }
        boolean contains(long start, int length) {
            return length > 0 && start >= address && start + length <= end();
        }
        boolean intersects(long start, int length) {
            return length > 0 && start < end() && start + length > address;
        }
    }

    record Operation(String kind, long pc, long address, int size, int index) {}

    final List<Region> regions;
    final List<Operation> operations;
    int consumed;
    private boolean admitted;
    private boolean active;
    private long activePc;
    private int activeStep;

    private ElfDataObservations(List<Region> regions, List<Operation> operations) {
        this.regions = List.copyOf(regions);
        this.operations = List.copyOf(operations);
    }

    private static void check(boolean value, String diagnostic) {
        if (!value) { throw new IllegalStateException(diagnostic); }
    }

    private static String hex(long value) { return String.format("0x%08X", value); }

    private static JsonObject object(JsonElement value, Set<String> keys, String field) {
        check(value != null && value.isJsonObject(), "ELF data " + field + " must be an object");
        JsonObject result = value.getAsJsonObject();
        check(result.keySet().equals(keys), "Invalid ELF data " + field + " members");
        return result;
    }

    private static String string(JsonElement value, String field) {
        check(value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString(),
            "ELF data " + field + " must be a string");
        return value.getAsString();
    }

    private static long word(JsonElement value, String field) {
        String text = string(value, field);
        check(text.matches("0x[0-9a-fA-F]{8}"), "Invalid ELF data " + field);
        return Long.parseUnsignedLong(text.substring(2), 16);
    }

    private static int size(JsonElement value) {
        check(value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber(),
            "ELF data size must be an integer");
        String text = value.getAsString();
        check(text.matches("[1-9][0-9]{0,6}"), "Invalid ELF data size");
        int result = Integer.parseInt(text);
        check(result <= MAX_SIZE, "Invalid ELF data size");
        return result;
    }

    private static boolean intersects(long a, long n, long b, long m) {
        return n > 0 && m > 0 && a < b + m && b < a + n;
    }

    private static boolean synthetic(long address, int size) {
        return (address == CLOCK_CELL && size == 4)
            || (address >= 0x24000000L && address + size <= 0x25000000L)
            || (address >= 0xE4000000L && address + size <= 0xE5000000L);
    }

    static ElfDataObservations parse(JsonObject execution) {
        if (!execution.has("elf_data")) { return null; }
        JsonObject input = object(execution.get("elf_data"), Set.of("regions", "operations"), "input");
        check(input.get("regions").isJsonArray() && !input.getAsJsonArray("regions").isEmpty(),
            "ELF data regions must be a nonempty array");
        check(input.get("operations").isJsonArray() && !input.getAsJsonArray("operations").isEmpty(),
            "ELF data operations must be a nonempty array");
        List<Region> regions = new ArrayList<>();
        for (JsonElement value : input.getAsJsonArray("regions")) {
            JsonObject region = object(value, Set.of("address", "size", "file_offset", "sha256"), "region");
            long address = word(region.get("address"), "region address");
            int length = size(region.get("size"));
            long offset = word(region.get("file_offset"), "file offset");
            String digest = string(region.get("sha256"), "digest");
            check(digest.matches("[0-9a-f]{64}"), "Invalid ELF data digest");
            check(address + length <= 0x100000000L && offset + length <= 0x100000000L,
                "Wrapping ELF data region");
            check(!intersects(address, length, 0x24000000L, 0x1000000L)
                    && !intersects(address, length, 0xE4000000L, 0x1000000L)
                    && !intersects(address, length, 0x7C000000L, 0x4000000L)
                    && !intersects(address, length, CLOCK_CELL, 4),
                "ELF data region overlaps an existing memory policy");
            for (Region other : regions) {
                check(!other.intersects(address, length), "Overlapping ELF data regions");
            }
            regions.add(new Region(address, length, offset, digest));
        }
        List<Operation> operations = new ArrayList<>();
        Set<Region> used = new HashSet<>();
        for (JsonElement value : input.getAsJsonArray("operations")) {
            JsonObject operation = object(value, Set.of("kind", "pc", "address", "size"), "operation");
            String kind = string(operation.get("kind"), "kind");
            check(kind.equals("read") || kind.equals("write"), "Invalid ELF data kind");
            long pc = word(operation.get("pc"), "pc");
            check((pc & 1) == 0 && pc + 2 <= 0x100000000L, "Invalid ELF data pc alignment/extent");
            long address = word(operation.get("address"), "operation address");
            int length = size(operation.get("size"));
            check(address + length <= 0x100000000L, "Wrapping ELF data operation");
            Region containing = null;
            for (Region region : regions) {
                if (region.contains(address, length)) { containing = region; }
            }
            check(containing != null, "ELF data operation outside declared region");
            used.add(containing);
            operations.add(new Operation(kind, pc, address, length, operations.size()));
        }
        check(used.size() == regions.size(), "Unused ELF data region");
        return new ElfDataObservations(regions, operations);
    }

    private static String digest(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    private static String originalDigest(FileBytes file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[65536];
        for (long offset = 0; offset < file.getSize();) {
            int count = (int)Math.min(buffer.length, file.getSize() - offset);
            check(file.getOriginalBytes(offset, buffer, 0, count) == count, "Short ELF data source read");
            digest.update(buffer, 0, count);
            offset += count;
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    void preflight(Program program, String sourceDigest, AddressSet syntheticMemory, AddressSet forbiddenMemory,
            Set<Long> forbiddenSites, JsonArray observations) throws Exception {
        check(!admitted && !active && consumed == 0, "ELF data preflight already used");
        check(sourceDigest != null && sourceDigest.matches("[0-9a-f]{64}")
                && sourceDigest.equals(program.getExecutableSHA256()), "ELF data source identity mismatch");
        check(ElfLoader.ELF_NAME.equals(program.getExecutableFormat()), "ELF data requires an ELF program");
        Map<FileBytes, String> fileDigests = new HashMap<>();
        for (Region region : regions) {
            Address start = program.getAddressFactory().getDefaultAddressSpace().getAddress(region.address);
            Address end = start.addNoWrap(region.size - 1);
            check(start.isMemoryAddress() && !start.getAddressSpace().isOverlaySpace()
                    && start.getAddressSpace().getName().equals("ram"), "ELF data requires normal RAM space");
            MemoryBlock block = program.getMemory().getBlock(start);
            check(block != null && block.contains(end) && block.getType() == MemoryBlockType.DEFAULT
                    && block.isInitialized() && block.isRead() && block.isWrite() && !block.isExecute(),
                "ELF data requires initialized readable writable nonexecuting block");
            check(!forbiddenMemory.intersects(start, end), "ELF data overlaps supplied memory");
            for (long pc : forbiddenSites) {
                check(!region.contains(pc, 1), "ELF data overlaps supplied instruction site");
            }
            check(program.getListing().getInstructionContaining(start) == null
                    && !program.getListing().getInstructions(new AddressSet(start, end), true).hasNext(),
                "ELF data overlaps instruction bytes");
            MemoryBlockSourceInfo selected = null;
            for (MemoryBlockSourceInfo info : block.getSourceInfos()) {
                if (info.contains(start) && info.contains(end)) {
                    check(selected == null, "Ambiguous ELF data source mapping");
                    selected = info;
                }
            }
            check(selected != null && selected.getFileBytes().isPresent()
                    && selected.getMappedRange().isEmpty() && selected.getByteMappingScheme().isEmpty(),
                "ELF data requires direct file backing");
            FileBytes file = selected.getFileBytes().get();
            long offset = selected.getFileBytesOffset(start);
            check(file.getFileOffset() == 0 && offset >= 0 && offset == region.fileOffset
                    && selected.getFileBytesOffset(end) == offset + region.size - 1
                    && offset <= file.getSize() - region.size, "ELF data file mapping mismatch");
            if (!fileDigests.containsKey(file)) { fileDigests.put(file, originalDigest(file)); }
            check(sourceDigest.equals(fileDigests.get(file)), "ELF data original file digest mismatch");
            byte[] original = new byte[region.size];
            byte[] current = new byte[region.size];
            check(file.getOriginalBytes(offset, original) == region.size
                    && program.getMemory().getBytes(start, current) == region.size, "Short ELF data region read");
            check(Arrays.equals(original, current), "ELF data current bytes differ from original file");
            check(digest(original).equals(region.sha256), "ELF data region digest mismatch");
        }
        for (Operation operation : operations) {
            check(!forbiddenSites.contains(operation.pc), "ELF data operation collides with supplied site");
            Address address = program.getAddressFactory().getDefaultAddressSpace().getAddress(operation.pc);
            Instruction instruction = program.getListing().getInstructionAt(address);
            check(instruction != null, "Missing ELF data instruction at " + hex(operation.pc));
            Address last = address.addNoWrap(instruction.getLength() - 1);
            MemoryBlock block = program.getMemory().getBlock(address);
            check(block != null && block.contains(last) && block.isInitialized() && block.isRead()
                    && block.isExecute(), "ELF data site requires executable source bytes");
            boolean matching = false;
            for (PcodeOp code : instruction.getPcode()) {
                if (code.getNumInputs() == 0 || !code.getInput(0).isConstant()
                        || code.getInput(0).getOffset() != program.getAddressFactory().getDefaultAddressSpace().getSpaceID()) {
                    continue;
                }
                matching |= operation.kind.equals("read") && code.getOpcode() == PcodeOp.LOAD
                    && code.getOutput() != null && code.getOutput().getSize() == operation.size;
                matching |= operation.kind.equals("write") && code.getOpcode() == PcodeOp.STORE
                    && code.getNumInputs() == 3 && code.getInput(2).getSize() == operation.size;
            }
            check(matching, "ELF data site lacks matching scalar memory operation");
        }
        check(observations != null, "Missing ELF data final observations");
        Set<Region> observed = new HashSet<>();
        for (JsonElement value : observations) {
            check(value.isJsonObject(), "Invalid ELF data final observation");
            JsonObject observation = value.getAsJsonObject();
            long address = word(observation.get("address"), "observation address");
            int length;
            if (observation.has("hex")) {
                check(!observation.has("fill") && !observation.has("size"), "Ambiguous ELF data observation");
                String bytes = string(observation.get("hex"), "observation bytes");
                check(bytes.matches("(?:[0-9a-fA-F]{2})*"), "Invalid ELF data observation bytes");
                length = bytes.length() / 2;
            } else {
                String fill = string(observation.get("fill"), "observation fill");
                check(fill.matches("[0-9a-fA-F]{2}"), "Invalid ELF data observation fill");
                JsonElement count = observation.get("size");
                check(count != null && count.isJsonPrimitive() && count.getAsJsonPrimitive().isNumber()
                        && count.getAsString().matches("0|[1-9][0-9]{0,6}"), "Invalid ELF data observation size");
                length = Integer.parseInt(count.getAsString());
                check(length <= MAX_SIZE, "Invalid ELF data observation size");
            }
            check(address + length <= 0x100000000L, "Wrapping ELF data observation");
            if (synthetic(address, length)) {
                Address start = program.getAddressFactory().getDefaultAddressSpace().getAddress(address);
                check(length == 0 || syntheticMemory.contains(start, start.addNoWrap(length - 1)),
                    "Observation outside declared synthetic memory");
                continue;
            }
            Region selected = null;
            for (Region region : regions) {
                if (region.address == address && region.size == length) { selected = region; }
            }
            check(selected != null && observation.keySet().equals(Set.of("address", "hex")),
                "ELF data observation must cover one complete region");
            check(observed.add(selected), "Duplicate ELF data final observation");
        }
        check(observed.size() == regions.size(), "Missing ELF data final region observation");
        admitted = true;
    }

    boolean contains(long address, int size) {
        return regions.stream().anyMatch(region -> region.contains(address, size));
    }

    void beginInstruction(long pc, int step) {
        check(admitted && !active, "ELF data instruction outside admitted execution");
        active = true;
        activePc = pc;
        activeStep = step;
    }

    void endInstruction() { active = false; }

    boolean observe(String kind, long pc, long address, int size, byte[] values, JsonArray events) {
        if (!regions.stream().anyMatch(region -> region.intersects(address, size))) { return false; }
        check(admitted && active && pc == activePc, "ELF data access outside original instruction");
        check(size > 0 && values.length >= size && contains(address, size), "Partial ELF data region access");
        check(consumed < operations.size(), "Exhausted ELF data access at " + hex(pc));
        Operation expected = operations.get(consumed);
        check(expected.kind.equals(kind) && expected.pc == pc && expected.address == address
                && expected.size == size, "Unexpected ELF data access at " + hex(pc) + " address " + hex(address));
        JsonObject event = new JsonObject();
        event.addProperty("kind", "elf_data_" + kind);
        event.addProperty("pc", hex(pc));
        event.addProperty("address", hex(address));
        event.addProperty("hex", HexFormat.of().formatHex(Arrays.copyOf(values, size)));
        event.addProperty("operation_index", consumed++);
        event.addProperty("step", activeStep);
        events.add(event);
        return true;
    }

    void finish() {
        check(admitted && !active && consumed == operations.size(), "Unused ELF data operations");
    }
}
