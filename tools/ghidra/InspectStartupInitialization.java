// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Locale;

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
import ghidra.program.model.lang.InsufficientBytesException;
import ghidra.program.model.lang.UnknownContextException;
import ghidra.program.model.lang.UnknownInstructionException;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.mem.MemoryBlockSourceInfo;
import ghidra.program.model.mem.MemoryBlockType;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;
import ghidra.program.model.symbol.FlowType;

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

    record RangeSet(long[][] ranges, String[] hashes, int codeRanges, boolean arrival, boolean prefix) {}
    record Options(String mode, RangeSet source) {}

    private static final RangeSet INITIALIZER = new RangeSet(RANGES, HASHES, 2, false, false);
    private static final RangeSet ARRIVAL = new RangeSet(new long[][] {
        {0xCEC00200L, 92, 0x7E0},
        {0x0EC2CB90L, 54, 0x2C590},
        {0x0EC2FCCCL, 2, 0x2F6CC},
        {0x0EC36AECL, 30, 0x364EC},
        {0x0EC2FCD0L, 2, 0x2F6D0},
        {0x0EC87EE8L, 12, 0x878E8},
        {0x0EC87F2EL, 12, 0x8792E},
        {0xCEC00280L, 32, 0x860},
        {0x0EE02C64L, 4, 0x202644},
        {0x0EDE886CL, 4, 0x1E824C},
        {0x0EE055B0L, 4, 0x204F90},
        {0xCEC02000L, 4, 0x231AA0}
    }, new String[] {
        "bd46add3c73cade1f1fcf1137785450f3bc8833bc2f4742d9b48d0e4fdfca8a5",
        "f7736d845625abac0e22b14420b2a5c620332660bab4146881d5dd2baff5a120",
        "89389ee14c6495d62c5c4d1ab627f415099e5101e21cc66af492011f88adf1c4",
        "3e320b280e8fc578c3b6df3b43c3fdf438be4b39dae2a7ed3f5a40a9765d9e34",
        "89389ee14c6495d62c5c4d1ab627f415099e5101e21cc66af492011f88adf1c4",
        "6e1f081df5d71a050896bc646cb244f1e7cd14bd6f813e5b70572370682bb65d",
        "34b575e40de3a25ed3a7ae5512326e15093c49d899a2b58ba0dac8fb2810d3c5",
        "813b174aea266e1320ef17d8bc4e514e8bb21ae8b7d810f3d5c9e1518041eb6e",
        "18e883521833e53164252b410f0d7d981de95051a4b04d660852f044bb13f5df",
        "d73741d437ad0db079de429777fd87f0a169db5223ecb76fd40fc7b6f4b985d6",
        "0dad4d2f118ec49157ae35927954de925a5dd17a8f759c2c90051f264d1d5831",
        "c0a694d0d434fedd659912c1858f11a03a90dc3711fdcc2c843478946dabe5d0"
    }, 7, true, false);
    private static final RangeSet CONTINUATION = new RangeSet(new long[][] {
        {0x0ED4A08CL, 64, 0x149A8C}
    }, new String[] {
        "7e14b716ed728805159a08dde64a420567b4b5d7b15251cee986cb194c872c8b"
    }, 1, false, true);
    private static final RangeSet SOC = new RangeSet(new long[][] {
        {0x0EC6221CL, 22, 0x61C1C},
        {0x0EC6227CL, 182, 0x61C7C},
        {0x0EC62332L, 64, 0x61D32},
        {0x0EC62232L, 74, 0x61C32}
    }, new String[] {
        "73839f44927b7f4732e9b30e5be6b7071a8d9c978ed1a9bdaca0462b4f6628f7",
        "233e2362d8d3e991aef4c1232861d6965eee43793f5fc653cfdc2c1482267349",
        "3049de857385368f7e0ddce054581921a1fa9895858265bed2e3d65f3a6fc995",
        "d6acbd437cd60a2e08e85dfe5cc12ce35f2726c159501c4e1f36d011aefa9e6d"
    }, 3, false, false);
    private RangeSet sourceSet = INITIALIZER;

    private static void check(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    static Options selectOptions(String[] args) {
        check(args.length >= 2 && args.length <= 4 && args[0].equals(SOURCE), "Invalid arguments");
        String mode = args.length >= 3 ? args[2] : "listing";
        check(mode.equals("listing") || mode.equals("pseudo"), "Invalid decode mode");
        String name = args.length == 4 ? args[3] : "initializer";
        check(name.equals("initializer") || name.equals("arrival") || name.equals("continuation")
            || name.equals("soc"),
            "Invalid range set");
        if (name.equals("continuation")) {
            check(mode.equals("pseudo"), "Continuation requires pseudo mode");
            return new Options(mode, CONTINUATION);
        }
        if (name.equals("soc")) {
            check(mode.equals("pseudo"), "SoC inspection requires pseudo mode");
            return new Options(mode, SOC);
        }
        return new Options(mode, name.equals("arrival") ? ARRIVAL : INITIALIZER);
    }

    static String outputJson(JsonObject out, RangeSet source) {
        GsonBuilder builder = new GsonBuilder().setPrettyPrinting();
        if (source.arrival() || source.prefix() || source == SOC) builder.serializeNulls();
        return builder.create().toJson(out) + "\n";
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

    private Register contextRegister() {
        Register base = currentProgram.getProgramContext().getBaseContextRegister();
        check(base != null && base.getName().equals("contextreg") && base.getBitLength() == 32,
            "Unexpected decoder context register");
        return base;
    }

    private JsonObject contextAt(Address address) {
        Register base = contextRegister();
        JsonObject out = new JsonObject();
        out.add("current", contextValue(currentProgram.getProgramContext().getRegisterValue(base, address)));
        out.add("default", contextValue(currentProgram.getProgramContext().getDefaultValue(base, address)));
        out.add("nondefault", contextValue(currentProgram.getProgramContext().getNonDefaultValue(base, address)));
        out.add("disassembly_default", contextValue(currentProgram.getProgramContext().getDefaultDisassemblyContext()));
        return out;
    }

    private JsonArray listingSnapshot() throws Exception {
        JsonArray snapshot = new JsonArray();
        for (int index = 0; index < sourceSet.codeRanges(); index++) {
            long[] range = sourceSet.ranges()[index];
            long end = range[0] + range[1];
            for (long pc = range[0]; pc < end; pc += 2) {
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
                    if (sourceSet.arrival() || sourceSet == SOC) item.add("instruction_context",
                        contextValue(instruction.getRegisterValue(contextRegister())));
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
        long[] spec = sourceSet.ranges()[index];
        int size = (int)spec[1];
        Address first = toAddr(spec[0]), last = first.addNoWrap(size - 1);
        MemoryBlock block = currentProgram.getMemory().getBlock(first);
        check(block != null && block.contains(last) && block.isInitialized()
            && block.isRead() && block.getType() == MemoryBlockType.DEFAULT
            && !block.isOverlay() && !block.isMapped(), "Invalid block at " + first);
        if (index < sourceSet.codeRanges()) check(block.isExecute(), "Nonexecuting code block at " + first);
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
        check(digest(current).equals(sourceSet.hashes()[index]), "Range digest mismatch at " + first);
        JsonObject out = new JsonObject();
        out.addProperty("address", hex(spec[0]));
        out.addProperty("bytes", size);
        out.addProperty("file_offset", hex(spec[2]));
        out.addProperty("sha256", sourceSet.hashes()[index]);
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
        if (sourceSet == SOC) out.addProperty("kind",
            index < sourceSet.codeRanges() ? "code" : "uninterpreted_data");
        return out;
    }

    static String prefixLimitReason(int instructions, int bytes) {
        check(instructions >= 0 && instructions <= 16 && bytes >= 0 && bytes <= 64,
            "Invalid prefix counters");
        if (bytes == 64) return "source_window_end";
        return instructions == 16 ? "instruction_limit" : null;
    }

    static String prefixStopReason(String mnemonic, FlowType flow, PcodeOp[] code, boolean sequential) {
        check(mnemonic != null && flow != null && code != null, "Missing instruction metadata");
        String name = mnemonic.toLowerCase(Locale.ROOT);
        if (name.startsWith("v") || name.equals("swi") || name.equals("rti")) return "unsupported_instruction";
        for (PcodeOp op : code) {
            if (op.getOpcode() == PcodeOp.CALLOTHER || op.getOpcode() == PcodeOp.UNIMPLEMENTED)
                return "unsupported_pcode";
        }
        for (PcodeOp op : code) {
            int opcode = op.getOpcode();
            if (opcode == PcodeOp.CALL || opcode == PcodeOp.CALLIND
                || opcode == PcodeOp.RETURN || opcode == PcodeOp.BRANCHIND) return "pcode_control_flow";
            if (opcode == PcodeOp.BRANCH || opcode == PcodeOp.CBRANCH) {
                check(op.getNumInputs() >= 1, "Missing branch target");
                if (!op.getInput(0).isConstant()) return "pcode_external_control";
            }
        }
        if (flow.isCall() || flow.isJump() || flow.isTerminal() || flow.isOverride()) return "instruction_control_flow";
        return sequential ? null : "fallthrough_boundary";
    }

    private JsonArray prefixListingSnapshot(byte[] range) throws Exception {
        JsonArray snapshot = new JsonArray();
        long start = sourceSet.ranges()[0][0], end = start + range.length;
        for (long pc = start; pc < end; pc += 2) {
            Address address = toAddr(pc);
            Instruction ins = getInstructionAt(address);
            JsonObject item = new JsonObject();
            item.addProperty("pc", hex(pc));
            item.addProperty("present", ins != null);
            item.add("context", contextAt(address));
            if (ins != null) {
                int length = ins.getLength();
                check(length >= 2 && length <= 10 && (length & 1) == 0, "Invalid listing length");
                item.addProperty("length", length);
                item.add("instruction_context", contextValue(ins.getRegisterValue(contextRegister())));
                boolean crossing = pc + length > end;
                item.addProperty("crosses_envelope", crossing);
                if (!crossing) {
                    byte[] bytes = Arrays.copyOfRange(range, (int)(pc - start), (int)(pc - start) + length);
                    check(Arrays.equals(ins.getBytes(), bytes), "Listing bytes differ at " + address);
                    item.addProperty("bytes", HexFormat.of().formatHex(bytes));
                    item.addProperty("text", ins.toString());
                }
            }
            snapshot.add(item);
        }
        return snapshot;
    }

    private void inspectPrefix(JsonObject out, Path output) throws Exception {
        JsonArray ranges = new JsonArray();
        ranges.add(inspectRange(0));
        byte[] range = HexFormat.of().parseHex(ranges.get(0).getAsJsonObject().get("hex").getAsString());
        JsonArray before = prefixListingSnapshot(range);
        out.addProperty("range_set", "continuation");
        out.addProperty("inspection_kind", "bounded_prefix");
        out.addProperty("function_complete", false);
        out.addProperty("listing_context_before_sha256", digest(before.toString().getBytes(StandardCharsets.UTF_8)));
        out.add("ranges", ranges);
        long start = sourceSet.ranges()[0][0], end = start + range.length, pc = start;
        JsonArray sites = new JsonArray();
        JsonObject stop = new JsonObject();
        int operations = 0;
        String reason;
        while (true) {
            monitor.checkCancelled();
            reason = prefixLimitReason(sites.size(), (int)(pc - start));
            stop.addProperty("pc", hex(pc));
            stop.addProperty("terminal_site_included", false);
            if (reason != null) break;
            Address address = toAddr(pc);
            JsonObject context = contextAt(address);
            Instruction ins;
            try {
                ins = new PseudoDisassembler(currentProgram).disassemble(address,
                    Arrays.copyOfRange(range, (int)(pc - start), range.length));
            }
            catch (InsufficientBytesException | UnknownInstructionException | UnknownContextException failure) {
                check(context.equals(contextAt(address)), "Decoder context changed at " + address);
                reason = failure instanceof InsufficientBytesException ? "insufficient_source_bytes"
                    : failure instanceof UnknownContextException ? "unknown_context" : "unknown_instruction";
                stop.add("decoder_context", context);
                break;
            }
            check(context.equals(contextAt(address)), "Decoder context changed at " + address);
            if (ins == null) {
                reason = "unknown_instruction";
                stop.add("decoder_context", context);
                break;
            }
            check(ins.getAddress().equals(address), "Pseudo decode changed address");
            int length = ins.getLength();
            check(length >= 2 && length <= 10 && (length & 1) == 0 && pc + length <= end,
                "Instruction crosses prefix envelope at " + address);
            byte[] bytes = ins.getBytes();
            check(Arrays.equals(bytes, Arrays.copyOfRange(range, (int)(pc - start),
                (int)(pc - start) + length)), "Instruction bytes differ at " + address);
            JsonObject site = new JsonObject();
            site.addProperty("pc", hex(pc));
            site.addProperty("bytes", HexFormat.of().formatHex(bytes));
            site.addProperty("length", length);
            site.add("decoder_context", context);
            site.add("instruction_context", contextValue(ins.getRegisterValue(contextRegister())));
            site.addProperty("text", ins.toString());
            if (ins.getDelaySlotDepth() != 0 || ins.isInDelaySlot() || ins.getPrototype().hasDelaySlots()
                || ins.getPrototype().hasNext2Dependency()) {
                site.addProperty("pcode_available", false);
                site.add("pcode", JsonNull.INSTANCE);
                reason = "unsupported_decode_dependency";
            }
            else {
                Address fallthrough = ins.getFallThrough();
                site.addProperty("fallthrough", fallthrough == null ? null : fallthrough.toString());
                PcodeOp[] code = ins.getPcode();
                JsonArray emitted = new JsonArray();
                for (PcodeOp op : code) {
                    check(++operations <= 4096, "P-code cap exceeded");
                    check(op.getNumInputs() <= 32, "P-code input cap exceeded");
                    JsonObject operation = new JsonObject();
                    operation.addProperty("opcode", op.getMnemonic());
                    operation.add("output", node(op.getOutput()));
                    JsonArray inputs = new JsonArray();
                    for (Varnode n : op.getInputs()) inputs.add(node(n));
                    operation.add("inputs", inputs);
                    if (op.getOpcode() == PcodeOp.CALLOTHER) {
                        check(op.getNumInputs() >= 1, "Missing user operation identifier");
                        operation.addProperty("userop", currentProgram.getLanguage().getUserDefinedOpName((int)op.getInput(0).getOffset()));
                    }
                    emitted.add(operation);
                }
                site.addProperty("pcode_available", true);
                site.add("pcode", emitted);
                reason = prefixStopReason(ins.getMnemonicString(), ins.getFlowType(), code,
                    fallthrough != null && fallthrough.equals(address.addNoWrap(length)));
            }
            sites.add(site);
            pc += length;
            if (reason != null) {
                stop.addProperty("terminal_site_included", true);
                break;
            }
        }
        byte[] current = new byte[range.length];
        check(currentProgram.getMemory().getBytes(toAddr(start), current) == current.length
            && Arrays.equals(range, current), "Current prefix bytes changed");
        check(before.equals(prefixListingSnapshot(range)), "Prefix listing or context changed");
        stop.addProperty("reason", reason);
        stop.addProperty("instructions", sites.size());
        stop.addProperty("bytes_consumed", pc - start);
        out.add("stop", stop);
        out.add("sites", sites);
        out.addProperty("instructions", sites.size());
        out.addProperty("pcode_operations", operations);
        out.addProperty("selected_current_bytes_unchanged", true);
        out.addProperty("selected_listing_context_unchanged", true);
        String json = outputJson(out, sourceSet);
        check(json.length() <= 1048576, "Output cap exceeded");
        Files.writeString(output, json, StandardOpenOption.CREATE_NEW);
        println("STARTUP_CONTINUATION_PREFIX_OK");
    }

    public void run() throws Exception {
        String[] args = getScriptArgs();
        Options options = selectOptions(args);
        sourceSet = options.source();
        String mode = options.mode();
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
        if (sourceSet.arrival()) out.addProperty("range_set", "arrival");
        if (sourceSet == SOC) {
            out.addProperty("range_set", "soc");
            out.addProperty("inspection_kind", "fixed_ranges");
            out.addProperty("function_complete", false);
        }
        check(currentProgram.getRegister("LowBitCodeMode") == null, "Unexpected low-bit code mode");
        if (sourceSet.prefix()) {
            inspectPrefix(out, output);
            return;
        }
        JsonArray listingBefore = listingSnapshot();
        out.addProperty("listing_context_before_sha256",
            digest(listingBefore.toString().getBytes(StandardCharsets.UTF_8)));
        JsonArray ranges = new JsonArray();
        for (int i = 0; i < sourceSet.ranges().length; i++) ranges.add(inspectRange(i));
        out.add("ranges", ranges);
        JsonArray sites = new JsonArray();
        int operations = 0;
        for (int index = 0; index < sourceSet.codeRanges(); index++) {
            long[] spec = sourceSet.ranges()[index];
            long start = spec[0], end = start + spec[1];
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
                if (sourceSet.arrival() || sourceSet == SOC) site.add("instruction_context",
                    contextValue(ins.getRegisterValue(contextRegister())));
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
        for (int index = 0; index < sourceSet.ranges().length; index++) {
            long[] spec = sourceSet.ranges()[index];
            byte[] now = new byte[(int)spec[1]];
            check(currentProgram.getMemory().getBytes(toAddr(spec[0]), now) == now.length
                && digest(now).equals(sourceSet.hashes()[index]), "Current range changed during export");
        }
        check(listingBefore.equals(listingSnapshot()), "Selected listing or context changed during export");
        out.add("sites", sites);
        out.addProperty("instructions", sites.size());
        out.addProperty("pcode_operations", operations);
        out.addProperty("selected_current_bytes_unchanged", true);
        out.addProperty("selected_listing_context_unchanged", true);
        String json = outputJson(out, sourceSet);
        check(json.length() <= 1048576, "Output cap exceeded");
        Files.writeString(output, json, StandardOpenOption.CREATE_NEW);
        println(sourceSet == SOC ? "SOC_INITIALIZATION_STATIC_PCODE_OK" : "STARTUP_INITIALIZATION_STATIC_PCODE_OK");
    }
}
