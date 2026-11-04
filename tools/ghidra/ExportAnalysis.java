// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later
// Export deterministic analysis metadata without instruction text.
// @category open27xx

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import com.google.gson.GsonBuilder;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressIterator;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.listing.Bookmark;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Program;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.util.GhidraProgramUtilities;

public class ExportAnalysis extends GhidraScript {
    private String address(Address value) {
        return value.getAddressSpace().getName() + ":" + value.toString(false);
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected output JSON path");
        }
        String preparation = currentProgram.getOptions(Program.PROGRAM_INFO)
            .getString("open27xx preparation", "");
        if (preparation.isEmpty() || !GhidraProgramUtilities.isAnalyzed(currentProgram)) {
            throw new IllegalStateException("Preparation or analysis did not complete");
        }
        Map<String, Object> report = new TreeMap<>();
        report.put("schema", 1);
        report.put("ghidra_version", getGhidraVersion());
        report.put("program", currentProgram.getName());
        report.put("sha256", currentProgram.getExecutableSHA256());
        report.put("format", currentProgram.getExecutableFormat());
        report.put("language", currentProgram.getLanguageID().toString());
        report.put("language_version", currentProgram.getLanguage().getVersion());
        report.put("compiler_spec", currentProgram.getCompilerSpec().getCompilerSpecID().toString());
        report.put("image_base", address(currentProgram.getImageBase()));
        report.put("preparation", preparation);
        report.put("analyzed", true);
        report.put("analysis_options", new TreeMap<>(getCurrentAnalysisOptionsAndValues(currentProgram)));

        List<String> entries = new ArrayList<>();
        AddressIterator entryIterator = currentProgram.getSymbolTable().getExternalEntryPointIterator();
        while (entryIterator.hasNext()) {
            entries.add(address(entryIterator.next()));
        }
        entries.sort(String::compareTo);
        report.put("entry_points", entries);

        List<Map<String, Object>> blocks = new ArrayList<>();
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            Map<String, Object> row = new TreeMap<>();
            row.put("name", block.getName());
            row.put("start", address(block.getStart()));
            row.put("end", address(block.getEnd()));
            row.put("size", block.getSize());
            row.put("read", block.isRead());
            row.put("write", block.isWrite());
            row.put("execute", block.isExecute());
            row.put("volatile", block.isVolatile());
            row.put("initialized", block.isInitialized());
            row.put("type", block.getType().toString());
            blocks.add(row);
        }
        blocks.sort(Comparator.comparing(row -> row.get("start").toString()));
        report.put("memory", blocks);

        List<Map<String, Object>> functions = new ArrayList<>();
        FunctionIterator functionIterator = currentProgram.getFunctionManager().getFunctions(true);
        while (functionIterator.hasNext()) {
            monitor.checkCancelled();
            Function function = functionIterator.next();
            Map<String, Object> row = new TreeMap<>();
            row.put("entry", address(function.getEntryPoint()));
            row.put("name", function.getName());
            row.put("source", function.getSymbol().getSource().toString());
            row.put("calling_convention", function.getCallingConventionName());
            row.put("thunk", function.isThunk());
            List<List<String>> ranges = new ArrayList<>();
            for (AddressRange range : function.getBody().getAddressRanges()) {
                ranges.add(List.of(address(range.getMinAddress()), address(range.getMaxAddress())));
            }
            row.put("body", ranges);
            functions.add(row);
        }
        report.put("functions", functions);
        report.put("function_count", functions.size());
        report.put("instruction_count", currentProgram.getListing().getNumInstructions());
        report.put("defined_data_count", currentProgram.getListing().getNumDefinedData());

        List<Map<String, Object>> bookmarks = new ArrayList<>();
        Iterator<Bookmark> bookmarkIterator = currentProgram.getBookmarkManager().getBookmarksIterator();
        while (bookmarkIterator.hasNext()) {
            Bookmark bookmark = bookmarkIterator.next();
            Map<String, Object> row = new TreeMap<>();
            row.put("address", address(bookmark.getAddress()));
            row.put("type", bookmark.getTypeString());
            row.put("category", bookmark.getCategory());
            row.put("comment", bookmark.getComment());
            bookmarks.add(row);
        }
        bookmarks.sort(Comparator.comparing(Object::toString));
        report.put("bookmarks", bookmarks);
        String json = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(report);
        Files.writeString(Path.of(args[0]), json + "\n", StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW);
        println("Exported " + functions.size() + " functions");
    }
}
