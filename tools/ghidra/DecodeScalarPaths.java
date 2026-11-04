// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later
// Define instruction metadata at explicit scalar entry points.
// @category open27xx

import java.util.ArrayList;
import java.util.List;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;

public class DecodeScalarPaths extends GhidraScript {
    private void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalArgumentException(message);
        }
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        check(args.length >= 2, "Expected source SHA-256 and instruction addresses");
        check(args[0].matches("[0-9a-fA-F]{64}"), "Invalid source SHA-256");
        check(args[0].equalsIgnoreCase(currentProgram.getExecutableSHA256()),
            "Source SHA-256 mismatch");
        check(currentProgram.getLanguageID().toString().equals("vc4:LE:32:default"),
            "Expected vc4:LE:32:default");

        AddressSet executable = new AddressSet();
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            if (block.isInitialized() && block.isRead() && block.isExecute()
                    && !block.isVolatile() && !block.isMapped() && !block.isOverlay()) {
                executable.add(block.getStart(), block.getEnd());
            }
        }
        List<Address> starts = new ArrayList<>();
        for (int index = 1; index < args.length; index++) {
            check(args[index].matches("0x[0-9a-fA-F]{1,8}"), "Invalid instruction address");
            long offset = Long.parseUnsignedLong(args[index].substring(2), 16);
            check((offset & 1) == 0, "Unaligned instruction address");
            Address address = toAddr(offset);
            check(executable.contains(address),
                "Instruction address requires initialized executable memory");
            Instruction containing = getInstructionContaining(address);
            check(containing == null || containing.getAddress().equals(address),
                "Address lies inside an existing instruction");
            check(currentProgram.getListing().getDefinedDataContaining(address) == null,
                "Address contains defined data");
            starts.add(address);
        }

        // Restrict flow discovery so data and peripheral blocks remain untouched.
        for (Address address : starts) {
            monitor.checkCancelled();
            if (getInstructionAt(address) == null) {
                DisassembleCommand command = new DisassembleCommand(address, executable, true);
                command.enableCodeAnalysis(false);
                check(command.applyTo(currentProgram, monitor), "Instruction decoding failed");
            }
            check(getInstructionAt(address) != null, "No instruction at requested address");
        }
        println("Prepared " + starts.size() + " instruction entry points");
    }
}
