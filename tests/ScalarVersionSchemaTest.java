// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

public class ScalarVersionSchemaTest {
    private static final String SITE = "{\"pc\":\"0x12345678\",\"destination\":\"r0\"}";

    private static JsonObject execution(String input) {
        return JsonParser.parseString("{\"version_input\":" + input + "}").getAsJsonObject();
    }

    private static JsonObject valid() {
        return execution("{\"word\":\"0xaBcDeF01\",\"sites\":[" + SITE + "]}");
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("VERSION schema result differs");
        }
    }

    private static void rejected(JsonObject execution) {
        try {
            CaptureScalarVectors.parseVersionInput(execution);
        } catch (IllegalStateException expected) {
            return;
        }
        throw new AssertionError("Accepted invalid VERSION input: " + execution);
    }

    public static void main(String[] arguments) {
        require(CaptureScalarVectors.parseVersionInput(new JsonObject()) == null);
        for (String invalid : new String[]{"null", "0", "true", "\"value\"", "[]", "{}",
                "{\"word\":\"0x00000000\"}", "{\"sites\":[]}",
                "{\"word\":\"0x00000000\",\"sites\":[],\"count\":1}"}) {
            rejected(execution(invalid));
        }
        for (String invalid : new String[]{"null", "0", "false", "[]", "{}", "\"0x0\"",
                "\"0X00000000\"", "\"0x100000000\"", "\"0x0000000g\"",
                "\" 0x00000000\"", "\"0x00000000 \""}) {
            JsonObject input = valid();
            input.getAsJsonObject("version_input").add("word", JsonParser.parseString(invalid));
            rejected(input);
        }
        for (String invalid : new String[]{"null", "0", "false", "\"sites\"", "{}", "[]",
                "[null]", "[0]", "[[]]", "[{}]",
                "[{\"pc\":\"0x12345678\"}]", "[{\"destination\":\"r0\"}]"}) {
            JsonObject input = valid();
            input.getAsJsonObject("version_input").add("sites", JsonParser.parseString(invalid));
            rejected(input);
        }
        for (String field : new String[]{"pc", "destination"}) {
            for (String invalid : new String[]{"null", "0", "false", "[]", "{}"}) {
                JsonObject input = valid();
                input.getAsJsonObject("version_input").getAsJsonArray("sites").get(0)
                    .getAsJsonObject().add(field, JsonParser.parseString(invalid));
                rejected(input);
            }
        }
        for (String pc : new String[]{"0x12345679", "0x1234", "0X12345678", "0x123456780",
                "12345678", "0x1234567z"}) {
            JsonObject input = valid();
            input.getAsJsonObject("version_input").getAsJsonArray("sites").get(0)
                .getAsJsonObject().addProperty("pc", pc);
            rejected(input);
        }
        for (String destination : new String[]{"r24", "r25", "r31", "sr", "pc", "sp", "lr",
                "gp", "r00", "R0", "r-1", "r0 "}) {
            JsonObject input = valid();
            input.getAsJsonObject("version_input").getAsJsonArray("sites").get(0)
                .getAsJsonObject().addProperty("destination", destination);
            rejected(input);
        }
        JsonObject extra = valid();
        extra.getAsJsonObject("version_input").getAsJsonArray("sites").get(0)
            .getAsJsonObject().addProperty("count", 1);
        rejected(extra);
        JsonObject duplicate = valid();
        duplicate.getAsJsonObject("version_input").getAsJsonArray("sites").add(JsonParser.parseString(SITE));
        rejected(duplicate);

        for (String word : new String[]{"0x00000000", "0x00000040", "0xffffffff", "0xaBcDeF01"}) {
            JsonObject input = valid();
            JsonObject plan = input.getAsJsonObject("version_input");
            plan.addProperty("word", word);
            JsonArray sites = plan.getAsJsonArray("sites");
            sites.remove(0);
            for (int index = 0; index < 24; index++) {
                JsonObject site = new JsonObject();
                site.addProperty("pc", String.format("0x%08X", 0x12345678 + 2 * index));
                site.addProperty("destination", "r" + index);
                sites.add(site);
            }
            CaptureScalarVectors.VersionInput parsed = CaptureScalarVectors.parseVersionInput(input);
            require(parsed.word == Long.parseUnsignedLong(word.substring(2), 16));
            require(parsed.consumed == 0 && parsed.pending == null && parsed.sites.size() == 24);
            for (int index = 0; index < 24; index++) {
                CaptureScalarVectors.VersionSite site = parsed.sites.get(index);
                require(site.index == index && site.pc == 0x12345678L + 2 * index
                    && site.destination.equals("r" + index) && parsed.byPc.get(site.pc) == site);
            }
            for (JsonElement site : sites) {
                site.getAsJsonObject().addProperty("destination", "sr");
            }
            plan.addProperty("word", "0x00000000");
            require(parsed.word == Long.parseUnsignedLong(word.substring(2), 16));
            require(parsed.sites.get(0).destination.equals("r0"));
        }
        System.out.println("VERSION schema checks passed");
    }
}
