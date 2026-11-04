// SPDX-FileCopyrightText: 2026 The open27xx Authors
// SPDX-License-Identifier: GPL-2.0-or-later

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

public class IrqP16SchemaTest {
    private static final String DI = "{\"kind\":\"di\",\"pc\":\"0x12345678\"}";
    private static final String READ = "{\"kind\":\"p16_read\",\"pc\":\"0x1234567a\","
        + "\"destination\":\"r0\",\"value\":\"0x00000001\"}";
    private static final String WRITE = "{\"kind\":\"p16_write\",\"pc\":\"0x1234567e\",\"source\":\"r23\"}";

    private static JsonObject execution(String input) {
        return JsonParser.parseString("{\"step_limit\":100,\"irq_p16\":" + input + "}").getAsJsonObject();
    }

    private static JsonObject valid() {
        return execution("{\"interrupt_arrivals\":\"none\",\"operations\":[" + DI + "," + READ + "," + WRITE + "]}");
    }

    private static JsonArray operations(JsonObject execution) {
        return execution.getAsJsonObject("irq_p16").getAsJsonArray("operations");
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("IRQ/p16 schema result differs");
        }
    }

    private static void rejected(JsonObject input, String diagnostic) {
        try {
            IrqP16Observations.parse(input);
        } catch (IllegalStateException expected) {
            require(expected.getMessage().contains(diagnostic));
            return;
        }
        throw new AssertionError("Accepted invalid IRQ/p16 input: " + input);
    }

    public static void main(String[] arguments) {
        JsonObject legacy = JsonParser.parseString("{\"step_limit\":null,\"version_input\":{},\"stubs\":[]}").getAsJsonObject();
        JsonObject original = legacy.deepCopy();
        require(IrqP16Observations.parse(legacy) == null && legacy.equals(original));
        require(IrqP16Observations.parse(new JsonObject()) == null);
        for (String value : new String[]{"null", "0", "true", "\"input\"", "[]"}) {
            rejected(execution(value), "input must be an object");
        }
        for (String value : new String[]{"{}", "{\"interrupt_arrivals\":\"none\"}", "{\"operations\":[]}",
                "{\"interrupt_arrivals\":\"none\",\"operations\":[],\"count\":1}"}) {
            rejected(execution(value), "input members");
        }
        for (String value : new String[]{"null", "0", "false", "[]", "{}", "\"none \"", "\"None\"", "\"any\""}) {
            JsonObject input = valid();
            input.getAsJsonObject("irq_p16").add("interrupt_arrivals", JsonParser.parseString(value));
            rejected(input, "IRQ/p16");
        }
        for (String value : new String[]{"null", "0", "false", "[]", "{}", "\"4\"", "-1", "1.5", "2147483648", "1e100"}) {
            JsonObject input = valid();
            input.add("step_limit", JsonParser.parseString(value));
            rejected(input, "step limit");
        }
        JsonObject missingLimit = valid();
        missingLimit.remove("step_limit");
        rejected(missingLimit, "step limit");
        JsonObject tooMany = valid();
        tooMany.addProperty("step_limit", 2);
        rejected(tooMany, "exceed step limit");
        for (String value : new String[]{"null", "0", "true", "\"operations\"", "{}", "[]", "[null]", "[0]", "[[]]", "[{}]"}) {
            JsonObject input = valid();
            input.getAsJsonObject("irq_p16").add("operations", JsonParser.parseString(value));
            rejected(input, "IRQ/p16");
        }
        for (int index = 0; index < 3; index++) {
            for (String field : operations(valid()).get(index).getAsJsonObject().keySet()) {
                JsonObject missing = valid();
                operations(missing).get(index).getAsJsonObject().remove(field);
                rejected(missing, "IRQ/p16");
                for (String value : new String[]{"null", "0", "false", "[]", "{}"}) {
                    JsonObject input = valid();
                    operations(input).get(index).getAsJsonObject().add(field, JsonParser.parseString(value));
                    rejected(input, "IRQ/p16");
                }
            }
            for (String field : new String[]{"count", "default", "source", "destination", "value"}) {
                JsonObject input = valid();
                JsonObject operation = operations(input).get(index).getAsJsonObject();
                if (!operation.has(field)) {
                    operation.addProperty(field, "0x00000000");
                    rejected(input, "occurrence members");
                }
            }
            for (String value : new String[]{"0x12345679", "0x1234", "0X12345678", "0x123456780", "12345678",
                    "0x1234567z", " 0x12345678", "0x12345678 "}) {
                JsonObject input = valid();
                operations(input).get(index).getAsJsonObject().addProperty("pc", value);
                rejected(input, "IRQ/p16");
            }
            JsonObject wrapping = valid();
            operations(wrapping).get(index).getAsJsonObject().addProperty("pc", index == 0 ? "0xFFFFFFFE" : "0xFFFFFFFC");
            rejected(wrapping, "Wrapping");
        }
        for (String kind : new String[]{"DI", "ei", "p16", "read", "p16_write "}) {
            JsonObject input = valid();
            operations(input).get(0).getAsJsonObject().addProperty("kind", kind);
            rejected(input, "kind");
        }
        for (int index = 1; index < 3; index++) {
            for (String register : new String[]{"r24", "r31", "sr", "pc", "sp", "lr", "gp", "p16", "r00", "R0", "r-1", "r0 "}) {
                JsonObject input = valid();
                operations(input).get(index).getAsJsonObject().addProperty(index == 1 ? "destination" : "source", register);
                rejected(input, "Invalid IRQ/p16");
            }
        }
        for (String value : new String[]{"0x00000002", "0xFFFFFFFF", "0x1", "0X00000001", "0x000000001", "0x0000000g"}) {
            JsonObject input = valid();
            operations(input).get(1).getAsJsonObject().addProperty("value", value);
            rejected(input, "IRQ/p16");
        }
        for (int index = 0; index < 3; index++) {
            JsonObject input = valid();
            JsonObject conflicting = operations(input).get(index).deepCopy().getAsJsonObject();
            conflicting.addProperty("pc", "0x12345678");
            if (index == 0) {
                conflicting = JsonParser.parseString(READ).getAsJsonObject();
                conflicting.addProperty("pc", "0x12345678");
            }
            operations(input).add(conflicting);
            rejected(input, "Conflicting");
        }
        for (int index = 1; index < 3; index++) {
            JsonObject input = valid();
            JsonObject conflicting = operations(input).get(index).deepCopy().getAsJsonObject();
            conflicting.addProperty(index == 1 ? "destination" : "source", "r5");
            operations(input).add(conflicting);
            rejected(input, "Conflicting");
        }
        for (int index = 0; index < 24; index++) {
            JsonObject input = valid();
            operations(input).get(1).getAsJsonObject().addProperty("destination", "r" + index);
            operations(input).get(2).getAsJsonObject().addProperty("source", "r" + index);
            JsonObject repeated = operations(input).get(1).deepCopy().getAsJsonObject();
            repeated.addProperty("value", "0x00000000");
            operations(input).add(repeated);
            operations(input).add(operations(input).get(0).deepCopy());
            operations(input).add(operations(input).get(2).deepCopy());
            input.addProperty("step_limit", 6);
            JsonObject before = input.deepCopy();
            IrqP16Observations parsed = IrqP16Observations.parse(input);
            require(input.equals(before) && parsed.consumed == 0 && parsed.operations.size() == 6 && parsed.byPc.size() == 3);
            require(parsed.operations.get(1).register.equals("r" + index));
            require(parsed.operations.get(2).register.equals("r" + index));
            require(parsed.operations.get(1).value == 1 && parsed.operations.get(3).value == 0);
            for (int occurrence = 0; occurrence < 6; occurrence++) {
                require(parsed.operations.get(occurrence).index == occurrence);
            }
            for (JsonElement operation : operations(input)) {
                operation.getAsJsonObject().addProperty("kind", "ei");
            }
            require(parsed.operations.get(0).kind.equals("di"));
            require(parsed.byPc.get(0x12345678L) == parsed.operations.get(0));
            try {
                parsed.operations.clear();
                throw new AssertionError("Mutable IRQ/p16 operations");
            } catch (UnsupportedOperationException expected) {
                require(parsed.operations.size() == 6);
            }
            try {
                parsed.byPc.clear();
                throw new AssertionError("Mutable IRQ/p16 sites");
            } catch (UnsupportedOperationException expected) {
                require(parsed.byPc.size() == 3);
            }
        }
        for (int index = 0; index < 3; index++) {
            JsonObject input = valid();
            operations(input).get(index).getAsJsonObject().addProperty("pc", index == 0 ? "0xfFfFfFfC" : "0xfFfFfFfA");
            require(IrqP16Observations.parse(input).operations.get(index).pc == (index == 0 ? 0xfffffffcL : 0xfffffffaL));
        }
        System.out.println("IRQ/p16 schema checks passed");
    }
}
