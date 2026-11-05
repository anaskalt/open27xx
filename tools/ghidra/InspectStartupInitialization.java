// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;

import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.opinion.ElfLoader;
import ghidra.program.database.mem.FileBytes;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.lang.RegisterValue;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.mem.MemoryBlockSourceInfo;
import ghidra.program.model.mem.MemoryBlockType;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;

// start4.elf, raspberrypi/firmware ab5c7f86283ceb58b7adb269cae1d16092a31bf6.
// Exact ranges keep this inspection separate from automatic disassembly.
public class InspectStartupInitialization extends GhidraScript {
    private static final String VERSION = "ab5c7f86283ceb58b7adb269cae1d16092a31bf6";
    private static final String SOURCE = "38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb";
    private static final long SOURCE_SIZE = 2303104;
    private static final long[][] RANGES = {
        {0x0EC3D740L, 182, 0x3D140},
        {0x0EC3D7F6L, 2, 0x3D1F6},
        {0x0EDD7870L, 36, 0x1D7270}
    };
    private static final String[] HASHES = {
        "c2685500b62add4f36d06ef8420d6ac719e33c1b6dd088ca9ce824848c0194d1",
        "89389ee14c6495d62c5c4d1ab627f415099e5101e21cc66af492011f88adf1c4",
        "7440d26c9e005d33d45380214fe4d8536aa5b266f7494c9c2e972be16b542626"
    };

    private void check(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    private String digest(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    private String hex(long value) { return String.format("0x%08X", value); }

    private JsonElement contextValue(RegisterValue value) {
        if (value == null) return JsonNull.INSTANCE;
        JsonObject out = new JsonObject();
        out.addProperty("register", value.getRegister().getName());
        out.addProperty("mask_value_bytes", HexFormat.of().formatHex(value.toBytes()));
        return out;
    }

    private JsonObject contextAt(Address address) {
        Register base = currentProgram.getProgramContext().getBaseContextRegister();
        check(base != null && base.getName().equals("contextreg") && base.getBitLength() == 32,
            "Unexpected decoder context register");
        JsonObject out = new JsonObject();
        out.add("current", contextValue(currentProgram.getProgramContext().getRegisterValue(base, address)));
        out.add("default", contextValue(currentProgram.getProgramContext().getDefaultValue(base, address)));
        out.add("nondefault", contextValue(currentProgram.getProgramContext().getNonDefaultValue(base, address)));
        out.add("disassembly_default", contextValue(currentProgram.getProgramContext().getDefaultDisassemblyContext()));
        return out;
    }

    private JsonArray listingSnapshot() throws Exception {
        JsonArray snapshot = new JsonArray();
        for (int index = 0; index < 2; index++) {
            long end = RANGES[index][0] + RANGES[index][1];
            for (long pc = RANGES[index][0]; pc < end; pc += 2) {
                JsonObject item = new JsonObject();
                item.addProperty("pc", hex(pc));
                Instruction instruction = getInstructionAt(toAddr(pc));
                item.addProperty("present", instruction != null);
                if (instruction != null) {
                    check(instruction.getLength() >= 2 && instruction.getLength() <= 10
                        && pc + instruction.getLength() <= end, "Existing listing crosses exact range");
                    item.addProperty("length", instruction.getLength());
                    item.addProperty("bytes", HexFormat.of().formatHex(instruction.getBytes()));
                    item.addProperty("text", instruction.toString());
                }
                item.add("context", contextAt(toAddr(pc)));
                snapshot.add(item);
            }
        }
        return snapshot;
    }

    private JsonObject node(Varnode n) {
        if (n == null) return null;
        JsonObject out = new JsonObject();
        out.addProperty("space", n.getAddress().getAddressSpace().getName());
        out.addProperty("offset", String.format("0x%X", n.getOffset()));
        out.addProperty("size", n.getSize());
        Register register = currentProgram.getRegister(n.getAddress(), n.getSize());
        if (register != null) out.addProperty("register", register.getName());
        return out;
    }

    private JsonObject inspectRange(int index) throws Exception {
        long[] spec = RANGES[index];
        int size = (int)spec[1];
        Address first = toAddr(spec[0]), last = first.addNoWrap(size - 1);
        MemoryBlock block = currentProgram.getMemory().getBlock(first);
        check(block != null && block.contains(last) && block.isInitialized()
            && block.isRead() && block.getType() == MemoryBlockType.DEFAULT
            && !block.isOverlay() && !block.isMapped(), "Invalid block at " + first);
        if (index < 2) check(block.isExecute(), "Nonexecuting code block at " + first);
        check(block.getSourceInfos().size() <= 16, "Source-info cap exceeded");
        MemoryBlockSourceInfo selected = null;
        for (MemoryBlockSourceInfo info : block.getSourceInfos()) {
            if (info.contains(first) && info.contains(last)) {
                check(selected == null, "Ambiguous source at " + first);
                selected = info;
            }
        }
        check(selected != null && selected.getFileBytes().isPresent()
            && selected.getMappedRange().isEmpty() && selected.getByteMappingScheme().isEmpty(),
            "Missing direct source at " + first);
        FileBytes file = selected.getFileBytes().get();
        check(file.getFileOffset() == 0 && file.getSize() == SOURCE_SIZE
            && selected.getFileBytesOffset(first) == spec[2]
            && selected.getFileBytesOffset(last) == spec[2] + size - 1,
            "Incorrect file mapping at " + first);
        MessageDigest full = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[65536];
        for (long offset = 0; offset < SOURCE_SIZE;) {
            monitor.checkCancelled();
            int count = (int)Math.min(buffer.length, SOURCE_SIZE - offset);
            check(file.getOriginalBytes(offset, buffer, 0, count) == count, "Short source read");
            full.update(buffer, 0, count);
            offset += count;
        }
        check(HexFormat.of().formatHex(full.digest()).equals(SOURCE), "Original file digest mismatch");
        byte[] original = new byte[size], current = new byte[size];
        check(file.getOriginalBytes(spec[2], original) == size
            && currentProgram.getMemory().getBytes(first, current) == size, "Short range read");
        check(Arrays.equals(original, current), "Current bytes differ at " + first);
        check(digest(current).equals(HASHES[index]), "Range digest mismatch at " + first);
        JsonObject out = new JsonObject();
        out.addProperty("address", hex(spec[0]));
        out.addProperty("bytes", size);
        out.addProperty("file_offset", hex(spec[2]));
        out.addProperty("sha256", HASHES[index]);
        out.addProperty("hex", HexFormat.of().formatHex(current));
        out.addProperty("original_file_sha256", SOURCE);
        out.addProperty("original_file_bytes", SOURCE_SIZE);
        out.addProperty("current_equals_original", true);
        out.addProperty("direct_file_backing", true);
        out.addProperty("block_name", block.getName());
        out.addProperty("block_start", block.getStart().toString());
        out.addProperty("block_end", block.getEnd().toString());
        out.addProperty("read", block.isRead());
        out.addProperty("write", block.isWrite());
        out.addProperty("execute", block.isExecute());
        return out;
    }

    public void run() throws Exception {
        String[] args = getScriptArgs();
        check((args.length == 2 || args.length == 3) && args[0].equals(SOURCE), "Invalid arguments");
        String mode = args.length == 3 ? args[2] : "listing";
        check(mode.equals("listing") || mode.equals("pseudo"), "Invalid decode mode");
        check(currentProgram.getExecutableSHA256().equals(SOURCE), "Program source mismatch");
        check(currentProgram.getExecutableFormat().equals(ElfLoader.ELF_NAME), "Not ELF");
        check(currentProgram.getLanguageID().toString().equals("vc4:LE:32:default"), "Wrong language");
        check(currentProgram.getCompilerSpec().getCompilerSpecID().toString().equals("default"), "Wrong compiler");
        Path output = Path.of(args[1]);
        check(!Files.exists(output), "Output already exists");
        JsonObject out = new JsonObject();
        out.addProperty("file", "start4.elf");
        out.addProperty("repository", "raspberrypi/firmware");
        out.addProperty("version", VERSION);
        out.addProperty("sha256", SOURCE);
        out.addProperty("language", currentProgram.getLanguageID().toString());
        out.addProperty("compiler", currentProgram.getCompilerSpec().getCompilerSpecID().toString());
        out.addProperty("decode_mode", mode);
        check(currentProgram.getRegister("LowBitCodeMode") == null, "Unexpected low-bit code mode");
        JsonArray listingBefore = listingSnapshot();
        out.addProperty("listing_context_before_sha256",
            digest(listingBefore.toString().getBytes(StandardCharsets.UTF_8)));
        JsonArray ranges = new JsonArray();
        for (int i = 0; i < RANGES.length; i++) ranges.add(inspectRange(i));
        out.add("ranges", ranges);
        JsonArray sites = new JsonArray();
        int operations = 0;
        for (int index = 0; index < 2; index++) {
            long start = RANGES[index][0], end = start + RANGES[index][1];
            byte[] range = HexFormat.of().parseHex(ranges.get(index).getAsJsonObject().get("hex").getAsString());
            for (long pc = start; pc < end;) {
                monitor.checkCancelled();
                check(sites.size() < 92, "Instruction cap exceeded");
                Address address = toAddr(pc);
                JsonObject context = contextAt(address);
                Instruction ins;
                if (mode.equals("pseudo")) {
                    byte[] remaining = Arrays.copyOfRange(range, (int)(pc - start), range.length);
                    ins = new PseudoDisassembler(currentProgram).disassemble(address, remaining);
                    check(ins != null, "Pseudo decode failed at " + address);
                    check(ins.getAddress().equals(address), "Pseudo decode changed address");
                    check(ins.getDelaySlotDepth() == 0 && !ins.isInDelaySlot() && !ins.getPrototype().hasDelaySlots()
                        && !ins.getPrototype().hasNext2Dependency(), "Unsupported decode dependency at " + address);
                    check(context.equals(contextAt(address)), "Decoder context changed at " + address);
                }
                else {
                    ins = getInstructionAt(address);
                    check(ins != null, "Missing original listing at " + address);
                }
                int length = ins.getLength();
                check(length >= 2 && length <= 10 && (length & 1) == 0 && pc + length <= end,
                    "Instruction crosses exact range at " + address);
                byte[] bytes = ins.getBytes();
                check(Arrays.equals(bytes, Arrays.copyOfRange(range, (int)(pc - start),
                    (int)(pc - start) + length)), "Listing bytes differ at " + address);
                JsonObject site = new JsonObject();
                site.addProperty("pc", hex(pc));
                site.addProperty("bytes", HexFormat.of().formatHex(bytes));
                site.addProperty("length", length);
                site.add("decoder_context", context);
                site.addProperty("text", ins.toString());
                site.addProperty("fallthrough", ins.getFallThrough() == null ? null : ins.getFallThrough().toString());
                JsonArray code = new JsonArray();
                for (PcodeOp op : ins.getPcode()) {
                    check(++operations <= 4096, "P-code cap exceeded");
                    check(op.getNumInputs() <= 32, "P-code input cap exceeded");
                    JsonObject operation = new JsonObject();
                    operation.addProperty("opcode", op.getMnemonic());
                    operation.add("output", node(op.getOutput()));
                    JsonArray inputs = new JsonArray();
                    for (Varnode n : op.getInputs()) inputs.add(node(n));
                    operation.add("inputs", inputs);
                    if (op.getOpcode() == PcodeOp.CALLOTHER) operation.addProperty("userop",
                        currentProgram.getLanguage().getUserDefinedOpName((int)op.getInput(0).getOffset()));
                    code.add(operation);
                }
                site.add("pcode", code);
                sites.add(site);
                pc += length;
            }
        }
        for (int index = 0; index < RANGES.length; index++) {
            byte[] now = new byte[(int)RANGES[index][1]];
            check(currentProgram.getMemory().getBytes(toAddr(RANGES[index][0]), now) == now.length
                && digest(now).equals(HASHES[index]), "Current range changed during export");
        }
        check(listingBefore.equals(listingSnapshot()), "Selected listing or context changed during export");
        out.add("sites", sites);
        out.addProperty("instructions", sites.size());
        out.addProperty("pcode_operations", operations);
        out.addProperty("selected_current_bytes_unchanged", true);
        out.addProperty("selected_listing_context_unchanged", true);
        String json = new GsonBuilder().setPrettyPrinting().create().toJson(out) + "\n";
        check(json.length() <= 1048576, "Output cap exceeded");
        Files.writeString(output, json, StandardOpenOption.CREATE_NEW);
        println("STARTUP_INITIALIZATION_STATIC_PCODE_OK");
    }
}
