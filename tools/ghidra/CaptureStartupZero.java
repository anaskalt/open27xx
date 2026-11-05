// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later
// Capture bounded original-address startup memory observations.
// @category open27xx

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import ghidra.app.plugin.processors.sleigh.SleighLanguage;
import ghidra.app.script.GhidraScript;
import ghidra.framework.Application;

public class CaptureStartupZero extends GhidraScript {
    static final String SOURCE = "38b179897c4514ad11bc915c3fd2d4b68c51e05df2e42240717655ab92d91aeb";
    static final String VERSION = "ab5c7f86283ceb58b7adb269cae1d16092a31bf6";
    static final long ENTRY = 0x0EC3D740L, GP = 0x0EE04140L, TERMINAL = 0x0EC3D77CL;
    static final List<String> REGISTERS = registers();
    private static List<String> registers() {
        List<String> result = new ArrayList<>();
        for (int i = 0; i < 24; i++) result.add("r" + i);
        result.addAll(List.of("gp", "sp", "lr", "r27", "r28", "r29", "sr", "pc"));
        return List.copyOf(result);
    }
    static StartupZeroObservations.Span span(String name, long address, int size) {
        return new StartupZeroObservations.Span(name, address, size);
    }
    static StartupZeroObservations.Geometry geometry() {
        return new StartupZeroObservations.Geometry(SOURCE, 2303104, 137, 52, 21, 0x231D50, 46,
            List.of(
                new StartupZeroObservations.Source(span("initializer", 0x0EC3D740L, 182), 0x0003D140,
                    "c2685500b62add4f36d06ef8420d6ac719e33c1b6dd088ca9ce824848c0194d1", true),
                new StartupZeroObservations.Source(span("completion", 0x0EC3D7F6L, 2), 0x0003D1F6,
                    "89389ee14c6495d62c5c4d1ab627f415099e5101e21cc66af492011f88adf1c4", true),
                new StartupZeroObservations.Source(span("table", 0x0EDD7870L, 36), 0x001D7270,
                    "7440d26c9e005d33d45380214fe4d8536aa5b266f7494c9c2e972be16b542626", false),
                new StartupZeroObservations.Source(span("fill_entry", 0x0ED1FDF0L, 4), 0x0011F7F0,
                    "cb445a2435e6986911d09398f3a4fd8d6e601d9b166331993f8038cdd5eafa6e", true),
                new StartupZeroObservations.Source(span("fill_body", 0x0ED1FE14L, 56), 0x0011F814,
                    "53b507ec19bbc050f208616bbbd6e7673141b97a6b94a93e005c99d00d0c6cec", true)
            ), List.of(
                new StartupZeroObservations.Source(span("decode_0", 0x0EC3D740L, 190), 0x0003D140,
                    "e1d77749eaf3b4dad7f7fb9841637362bcbfea65d72727590af5f064fd4b8f73", true),
                new StartupZeroObservations.Source(span("decode_1", 0x0ED1FDF0L, 8), 0x0011F7F0,
                    "a720a04041fbc087d4ab808dae533362836815fc6a35aedb3c99675189869c91", true),
                new StartupZeroObservations.Source(span("decode_2", 0x0ED1FE14L, 62), 0x0011F814,
                    "c9347899f7ee787235f43fc5031b95426b3c1a6aa92c59ff9a61ef0e32b14efb", true)
            ), List.of(
                new StartupZeroObservations.Allocation(span("bss_0", 0x0EE056A0L, 2352), 13, 29, 2117760,
                    "e0ee8e0f47ff1f976075d8ec884a37b02c1c0bcc3e7b0606f2f4a41489d6eef0",
                    "f931b87a3a9b2cde3955998d46a35203e51f9077fb878fab24c45c3dae2d1fc8"),
                new StartupZeroObservations.Allocation(span("bss_1", 0x0EE33200L, 2048), 17, 34, 2300576,
                    "68a248cf3ff71695d16cb4f759071cd95155f717e17ec7813b02a3a3d5221a91",
                    "14b564dd270654195b447534901e1ee3c7bfdbe36b960864616aba4214b184c2"),
                new StartupZeroObservations.Allocation(span("bss_2", 0x0EE33A00L, 1011288), 18, 35, 2300576,
                    "16f2928748650ea1e0a111f14262fa1ee3ea8162a5ae96aa1b0e7fc4b76e796b",
                    "f3a8423d09fefb4b50888c33692544fb7893d0214fe2e631356398d13da13eb4")
            ));
    }
    static final Map<String, String> MODULE = Map.ofEntries(
        Map.entry("data/languages/vc4.cspec", "c0bb18dc4057e7f94f9579f4ecca6de8de70974a6d9e3e24bce9ab1ea503f2ca"),
        Map.entry("data/languages/vc4.ldefs", "096641cff0203e0f7f2e5c568d1ef7bc3c9c4923bda3138e5009c06fc2e19850"),
        Map.entry("data/languages/vc4.opinion", "82d118a436e87164dbc75f892d3c2eaf2e91c619597fa5663ac31416a9d7cd01"),
        Map.entry("data/languages/vc4.pspec", "02d6a7c0095d942ec5acff9f8cc90c84f680101255a2ac008cf265610b69c810"),
        Map.entry("data/languages/vc4.sla", "2303eea79ede697a37318068af1514de75ff64d9fcf2965623e2ab417e93bb56"),
        Map.entry("data/languages/vc4.slaspec", "a3cc3f596d63a268440a659baa6fcf92e15900ec7ca1b8c2c733203d45236131"),
        Map.entry("extension.properties", "02920d405faa1eca9b40e4e0bb0dc0b47e4278327ea89ef74bbaeafdeb92084f"),
        Map.entry("lib/VideoCoreIV.jar", "c6deada2fac53b8ea6523dbda77597b128006674616f140f04df23264c6d1aa3")
    );
    static JsonObject expectedProfile(int index) {
        StartupZeroObservations.check(index == 0 || index == 1, "Profile index");
        boolean first = index == 0;
        long sp = first ? 0x24010080L : 0x24010280L, lr = first ? 0x24000000L : 0x24000004L;
        JsonObject profile = new JsonObject(); profile.addProperty("id", first ? "poison-a" : "poison-b");
        JsonObject registers = new JsonObject();
        for (int i = 0; i < 32; i++) {
            long value = (first ? 0x11110000L : 0xEEEE0000L) + i * (first ? 0x101 : 0x303);
            String name = REGISTERS.get(i);
            if (name.equals("gp")) value = GP;
            if (name.equals("sp")) value = sp;
            if (name.equals("lr")) value = lr;
            if (name.equals("sr")) value = first ? 0x13579BDAL : 0xA5A5A5A5L;
            if (name.equals("pc")) value = ENTRY;
            registers.addProperty(name, StartupZeroObservations.hex(value));
        }
        profile.add("registers", registers);
        JsonObject stack = new JsonObject(); stack.addProperty("start", StartupZeroObservations.hex(sp - 64));
        stack.addProperty("size", 128); stack.addProperty("fill", first ? "3c" : "c3"); profile.add("stack", stack);
        profile.addProperty("bss_poison", first ? "a5" : "5a");
        profile.addProperty("return_sentinel", StartupZeroObservations.hex(lr)); return profile;
    }
    static List<StartupZeroObservations.Profile> profiles(JsonObject request) {
        StartupZeroObservations.object(request, Set.of("schema_version", "source_sha256", "tool_sha256", "helper_sha256", "profiles"), "request");
        StartupZeroObservations.check(request.get("schema_version").isJsonPrimitive()
            && request.get("schema_version").getAsJsonPrimitive().isNumber()
            && request.get("schema_version").getAsString().equals("1"), "Schema version");
        StartupZeroObservations.check(StartupZeroObservations.string(request.get("source_sha256")).equals(SOURCE), "Request source");
        for (String field : List.of("tool_sha256", "helper_sha256")) StartupZeroObservations.check(
            StartupZeroObservations.string(request.get(field)).matches("[0-9a-f]{64}"), "Request tool digest");
        StartupZeroObservations.check(request.get("profiles").isJsonArray() && request.getAsJsonArray("profiles").size() == 2, "Exactly two profiles required");
        List<StartupZeroObservations.Profile> result = new ArrayList<>();
        for (int i = 0; i < 2; i++) {
            JsonObject expected = expectedProfile(i);
            StartupZeroObservations.check(expected.equals(request.getAsJsonArray("profiles").get(i)), "Frozen profile mismatch");
            Map<String, Long> registers = new LinkedHashMap<>();
            for (String name : REGISTERS) registers.put(name, StartupZeroObservations.word(expected.getAsJsonObject("registers").get(name)));
            JsonObject stack = expected.getAsJsonObject("stack");
            result.add(new StartupZeroObservations.Profile(expected.get("id").getAsString(), registers,
                span("stack", StartupZeroObservations.word(stack.get("start")), 128),
                HexFormat.of().parseHex(stack.get("fill").getAsString())[0],
                HexFormat.of().parseHex(expected.get("bss_poison").getAsString())[0],
                StartupZeroObservations.word(expected.get("return_sentinel"))));
        }
        return result;
    }
    static JsonElement strictValue(com.google.gson.stream.JsonReader reader, int depth) throws Exception {
        StartupZeroObservations.check(depth <= 8, "Request nesting cap");
        switch (reader.peek()) {
            case BEGIN_OBJECT: {
                reader.beginObject(); JsonObject object = new JsonObject();
                while (reader.hasNext()) {
                    String name = reader.nextName(); StartupZeroObservations.check(!object.has(name), "Duplicate JSON member");
                    object.add(name, strictValue(reader, depth + 1));
                }
                reader.endObject(); return object;
            }
            case BEGIN_ARRAY: {
                reader.beginArray(); JsonArray array = new JsonArray();
                while (reader.hasNext()) { StartupZeroObservations.check(array.size() < 128, "Request array cap"); array.add(strictValue(reader, depth + 1)); }
                reader.endArray(); return array;
            }
            case STRING: return new com.google.gson.JsonPrimitive(reader.nextString());
            case NUMBER: return new com.google.gson.JsonPrimitive(new java.math.BigDecimal(reader.nextString()));
            default: throw new IllegalStateException("Unsupported request value");
        }
    }
    static JsonObject parseRequest(String text) throws Exception {
        StartupZeroObservations.check(text.getBytes(StandardCharsets.UTF_8).length <= 16384, "Request byte cap");
        try (com.google.gson.stream.JsonReader reader = new com.google.gson.stream.JsonReader(new java.io.StringReader(text))) {
            reader.setLenient(false);
            JsonElement result = strictValue(reader, 0);
            StartupZeroObservations.check(reader.peek() == com.google.gson.stream.JsonToken.END_DOCUMENT && result.isJsonObject(), "Trailing or invalid request");
            return result.getAsJsonObject();
        }
    }
    static String encodeOutput(JsonObject result) {
        String json = new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(result) + "\n";
        StartupZeroObservations.check(json.getBytes(StandardCharsets.UTF_8).length <= StartupZeroObservations.MAX_OUTPUT, "Output byte cap");
        return json;
    }
    private JsonObject moduleEvidence() throws Exception {
        StartupZeroObservations.check(Application.getApplicationVersion().equals("12.2"), "Requires Ghidra 12.2");
        StartupZeroObservations.check(currentProgram.getLanguageID().toString().equals("vc4:LE:32:default")
            && currentProgram.getCompilerSpec().getCompilerSpecID().toString().equals("default"), "Language/compiler mismatch");
        StartupZeroObservations.check(currentProgram.getRegister("LowBitCodeMode") == null, "Unexpected low-bit code mode");
        SleighLanguage language = (SleighLanguage)currentProgram.getLanguage();
        Path sla = Path.of(language.getLanguageDescription().getLanguageFile().getSlaFile().getAbsolutePath()).toRealPath();
        Path module = sla.getParent().getParent().getParent();
        StartupZeroObservations.check(sla.equals(module.resolve("data/languages/vc4.sla").toRealPath()), "Loaded SLA path mismatch");
        JsonObject evidence = new JsonObject();
        for (String name : new java.util.TreeSet<>(MODULE.keySet())) {
            byte[] bytes = Files.readAllBytes(module.resolve(name));
            String hash = StartupZeroObservations.digest(bytes);
            StartupZeroObservations.check(hash.equals(MODULE.get(name)), "Installed module mismatch: " + name);
            evidence.addProperty(name, hash);
        }
        return evidence;
    }
    private JsonObject apiEvidence() throws Exception {
        JsonObject evidence = new JsonObject();
        for (Class<?> type : List.of(ghidra.app.emulator.EmulatorHelper.class,
                ghidra.app.util.PseudoDisassembler.class, GhidraScript.class)) {
            Path jar = Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
            StartupZeroObservations.check(Files.isRegularFile(jar) && Files.size(jar) <= 268435456, "Loaded API archive bound");
            java.security.MessageDigest hash = StartupZeroObservations.sha();
            try (java.io.InputStream stream = Files.newInputStream(jar)) {
                byte[] buffer = new byte[65536]; int size;
                while ((size = stream.read(buffer)) >= 0) hash.update(buffer, 0, size);
            }
            evidence.addProperty(jar.getFileName().toString(), HexFormat.of().formatHex(hash.digest()));
        }
        return evidence;
    }
    public void run() throws Exception {
        String[] args = getScriptArgs(); StartupZeroObservations.check(args.length == 2, "Expected request and output paths");
        Path input = Path.of(args[0]), output = Path.of(args[1]);
        StartupZeroObservations.check(!Files.exists(output) && !Files.exists(Path.of(args[1] + ".failure.json")), "Output already exists");
        StartupZeroObservations.check(Files.size(input) <= 16384, "Request byte cap");
        byte[] requestBytes = Files.readAllBytes(input);
        JsonObject request = parseRequest(new String(requestBytes, StandardCharsets.UTF_8));
        List<StartupZeroObservations.Profile> profiles = profiles(request);
        Path script = Path.of(getSourceFile().getAbsolutePath());
        String toolHash = StartupZeroObservations.digest(Files.readAllBytes(script));
        String helperHash = StartupZeroObservations.digest(Files.readAllBytes(script.resolveSibling("StartupZeroObservations.java")));
        StartupZeroObservations.check(toolHash.equals(request.get("tool_sha256").getAsString())
            && helperHash.equals(request.get("helper_sha256").getAsString()), "Tool/helper binding mismatch");
        JsonObject result = new JsonObject(); result.addProperty("schema_version", 1);
        result.addProperty("source_sha256", SOURCE); result.addProperty("source_file", "start4.elf"); result.addProperty("source_version", VERSION);
        result.addProperty("request_sha256", StartupZeroObservations.digest(requestBytes));
        result.addProperty("tool_sha256", toolHash); result.addProperty("helper_sha256", helperHash);
        result.addProperty("ghidra_version", Application.getApplicationVersion()); result.addProperty("java_version", System.getProperty("java.version"));
        result.add("module_sha256", moduleEvidence());
        result.add("loaded_api_sha256", apiEvidence());
        String phase = "admission", profileId = "none";
        try {
            StartupZeroObservations.Admission admission = new StartupZeroObservations.Admission(currentProgram, geometry(), monitor,
                new StartupZeroObservations.Vc4ContextPolicy());
            admission.decode(75); StartupZeroObservations.check(admission.sites.size() == 75, "Selected instruction count");
            result.add("source_ranges", admission.sourceEvidence); result.add("allocations", admission.allocationEvidence);
            result.add("sites", StartupZeroObservations.siteEvidence(admission));
            result.addProperty("initial_program_snapshot_sha256", StartupZeroObservations.digest(admission.initialSnapshot.toString().getBytes(StandardCharsets.UTF_8)));
            StartupZeroObservations.check(admission.sites.containsKey(TERMINAL)
                && java.util.Arrays.stream(admission.sites.get(TERMINAL).instruction().getPcode())
                    .anyMatch(op -> op.getOpcode() == ghidra.program.model.pcode.PcodeOp.RETURN), "Terminal RETURN binding");
            JsonArray cases = new JsonArray(); phase = "capture";
            for (StartupZeroObservations.Profile profile : profiles) {
                profileId = profile.id(); cases.add(StartupZeroObservations.capture(admission, profile, ENTRY, TERMINAL, monitor));
            }
            result.add("cases", cases); result.addProperty("capture_completed", true); result.addProperty("expected_result_comparison", "not_performed");
            phase = "final_binding"; admission.unchanged();
            StartupZeroObservations.check(result.get("module_sha256").equals(moduleEvidence())
                && result.get("loaded_api_sha256").equals(apiEvidence())
                && toolHash.equals(StartupZeroObservations.digest(Files.readAllBytes(script)))
                && helperHash.equals(StartupZeroObservations.digest(Files.readAllBytes(script.resolveSibling("StartupZeroObservations.java")))), "Final tool/module binding mismatch");
            String json = encodeOutput(result);
            Files.writeString(output, json, StandardOpenOption.CREATE_NEW);
            println("STARTUP_ZERO_CAPTURE_COMPLETE");
        } catch (Exception exception) {
            JsonObject failure = new JsonObject(); failure.addProperty("capture_completed", false); failure.addProperty("phase", phase); failure.addProperty("profile", profileId);
            failure.addProperty("source_sha256", SOURCE); failure.addProperty("request_sha256", result.get("request_sha256").getAsString());
            failure.addProperty("tool_sha256", toolHash); failure.addProperty("helper_sha256", helperHash); failure.add("module_sha256", result.get("module_sha256"));
            failure.add("loaded_api_sha256", result.get("loaded_api_sha256"));
            String diagnostic = String.valueOf(exception.getMessage()); failure.addProperty("diagnostic", diagnostic.substring(0, Math.min(2048, diagnostic.length())));
            Files.writeString(Path.of(args[1] + ".failure.json"), new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(failure) + "\n", StandardOpenOption.CREATE_NEW);
            throw exception;
        }
    }
}
