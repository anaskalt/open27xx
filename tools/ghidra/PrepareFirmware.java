// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later
// Prepare firmware memory before automatic analysis.
// @category open27xx

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.ArrayDataType;
import ghidra.program.model.data.ByteDataType;
import ghidra.program.model.listing.Program;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

public class PrepareFirmware extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1 || !(args[0].equals("raw") || args[0].equals("elf"))) {
            throw new IllegalArgumentException("Expected raw or elf");
        }
        if (!currentProgram.getLanguageID().toString().equals("vc4:LE:32:default")) {
            throw new IllegalArgumentException("Expected vc4:LE:32:default");
        }
        resetAllAnalysisOptions(currentProgram);
        Memory memory = currentProgram.getMemory();
        if (args[0].equals("raw")) {
            MemoryBlock body = memory.getBlock(toAddr(0x80000000L));
            if (body == null || body.getSize() <= 796 || memory.getBlocks().length != 1) {
                throw new IllegalArgumentException("Unexpected raw memory layout");
            }
            Address footer = body.getEnd().subtract(283);
            if (Integer.toUnsignedLong(memory.getInt(footer)) != body.getSize() - 284) {
                throw new IllegalArgumentException("Footer length does not match the raw file");
            }
            for (int offset = 0; offset < 512; offset++) {
                if (memory.getByte(body.getStart().add(offset)) != 0) {
                    throw new IllegalArgumentException("Raw prefix is not 512 zero bytes");
                }
            }
            memory.split(body, footer);
            memory.split(body, toAddr(0x80000200L));
            MemoryBlock prefix = memory.getBlock(toAddr(0x80000000L));
            body = memory.getBlock(toAddr(0x80000200L));
            MemoryBlock trailer = memory.getBlock(footer);
            prefix.setName("prefix");
            prefix.setExecute(false);
            body.setName("body");
            body.setExecute(true);
            trailer.setName("footer");
            trailer.setExecute(false);
            createData(prefix.getStart(), new ArrayDataType(ByteDataType.dataType, 512, 1));
            createData(footer, new ArrayDataType(ByteDataType.dataType, 284, 1));
            // The candidate entry is explicit so analysis cannot silently choose a different base.
            Address entry = toAddr(0x80000200L);
            addEntryPoint(entry);
            disassemble(entry);
            createFunction(entry, "provisional_entry");
        } else if (!currentProgram.getExecutableFormat().equals("Executable and Linking Format (ELF)")) {
            throw new IllegalArgumentException("ELF input requires the ELF loader");
        }
        // BCM2711 ARM Peripherals, revision 4, section 1.2.4, page 6.
        MemoryBlock peripherals = memory.createUninitializedBlock(
            "main_peripherals", toAddr(0x7C000000L), 0x04000000L, false);
        peripherals.setRead(true);
        peripherals.setWrite(true);
        peripherals.setExecute(false);
        peripherals.setVolatile(true);
        peripherals.setComment("BCM2711 legacy master main peripherals; uninitialized MMIO");
        currentProgram.getOptions(Program.PROGRAM_INFO).setString("open27xx preparation", args[0]);
    }
}
