/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "arm_mapping.h"

struct span {
    const void *pointer;
    size_t length;
};

static enum arm_mapping_status validate_spans(const struct span *spans,
                                              size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        if (spans[left].pointer == NULL && spans[left].length != 0)
            return ARM_MAPPING_INVALID;
        if (spans[left].length > UINTPTR_MAX - (uintptr_t)spans[left].pointer)
            return ARM_MAPPING_BOUNDS;
    }
    for (left = 0; left < count; ++left) {
        uintptr_t a = (uintptr_t)spans[left].pointer;
        if (spans[left].length == 0)
            continue;
        for (right = left + 1; right < count; ++right) {
            uintptr_t b = (uintptr_t)spans[right].pointer;
            if (spans[right].length != 0
                    && (a < b ? b - a < spans[left].length
                              : a - b < spans[right].length))
                return ARM_MAPPING_OVERLAP;
        }
    }
    return ARM_MAPPING_OK;
}

static int matches_arguments(const struct arm_mapping_inputs *inputs,
                             uint32_t offset, uint32_t base, uint32_t length) {
    return inputs->offset == offset && inputs->base == base && inputs->length == length;
}

static enum arm_mapping_status validate_profile(
    const struct arm_mapping_inputs *inputs, const struct arm_mapping_state *state,
    const uint8_t *table, size_t table_length, const struct arm_mapping_plan *plan) {
    static const uint32_t rejected[6][3] = {
        {UINT32_C(0x40000000), UINT32_C(0x7E000000), UINT32_C(0x01000000)},
        {0, UINT32_C(0x7E000000), 0},
        {0, UINT32_C(0x7E000000), 1},
        {0, 0, UINT32_C(0x01000000)},
        {0, UINT32_C(0x7E000001), UINT32_C(0x01000000)},
        {1, UINT32_C(0x7E000000), UINT32_C(0x01000000)}};
    size_t index;
    int standard = matches_arguments(inputs, 0, UINT32_C(0x7E000000), UINT32_C(0x01000000));
    int repeat;
    if (inputs->handle == 0)
        return standard ? ARM_MAPPING_OK : ARM_MAPPING_UNSUPPORTED;
    if (inputs->handle != ARM_MAPPING_HANDLE)
        return ARM_MAPPING_UNSUPPORTED;
    if (state == NULL || plan == NULL)
        return ARM_MAPPING_INVALID;
    if (plan->acquire == NULL || plan->release == NULL)
        return ARM_MAPPING_INVALID;
    if (state->active == 1)
        return standard ? ARM_MAPPING_OK : ARM_MAPPING_UNSUPPORTED;
    if (state->active != 0 || state->capacity != UINT32_C(0x400))
        return ARM_MAPPING_UNSUPPORTED;
    for (index = 0; index < 6; ++index)
        if (matches_arguments(inputs, rejected[index][0], rejected[index][1], rejected[index][2]))
            return ARM_MAPPING_OK;
    repeat = matches_arguments(inputs, UINT32_C(0x3F000000),
                               UINT32_C(0x40000000), UINT32_C(0x01000000));
    if (!standard && !repeat && !matches_arguments(inputs, UINT32_C(0xFF000000),
                                                   UINT32_C(0x7E000000), UINT32_C(0x01000000)))
        return ARM_MAPPING_UNSUPPORTED;
    if (table == NULL)
        return ARM_MAPPING_INVALID;
    if (table_length < ARM_MAPPING_TABLE_BYTES)
        return ARM_MAPPING_BOUNDS;
    if (state->marker != (uint32_t)repeat || state->selection > 1
            || (!standard && state->selection != 1))
        return ARM_MAPPING_UNSUPPORTED;
    if (state->selection == 0) {
        if (state->service_index != 1)
            return ARM_MAPPING_UNSUPPORTED;
        if (plan->service == NULL)
            return ARM_MAPPING_INVALID;
    }
    for (index = 0; index < ARM_MAPPING_TABLE_BYTES; ++index) {
        uint8_t expected = repeat ? (index % 2 == 0 ? 0xF0 : 0x03)
                                  : (index % 2 == 0 ? 0xA5 : 0x5A);
        if (table[index] != expected)
            return ARM_MAPPING_UNSUPPORTED;
    }
    return ARM_MAPPING_OK;
}

static void write_entry(uint8_t *table, uint32_t index, uint32_t value) {
    table[index * 2] = (uint8_t)value;
    table[index * 2 + 1] = (uint8_t)(value >> 8);
}

static uint32_t prepare_table(const struct arm_mapping_inputs *inputs,
                              struct arm_mapping_state *state, uint8_t *table,
                              const struct arm_mapping_plan *plan) {
    uint32_t bound, step, position, index, value;
    if (state->active != 0)
        return UINT32_C(0xFFFFFFFE);
    bound = (uint32_t)(state->capacity << 20);
    step = bound >> 6;
    if ((uint32_t)(inputs->offset + inputs->length) > bound || inputs->length == 0
            || inputs->length % step != 0 || inputs->base == 0
            || inputs->base % step != 0 || inputs->offset % step != 0)
        return UINT32_C(0xFFFFFFFD);
    if (state->marker == 0) {
        value = inputs->base >> 21;
        for (index = 0; index < ARM_MAPPING_ENTRIES; ++index)
            write_entry(table, index, value);
        state->marker = 1;
    }
    for (position = 0; position < inputs->length; position += step) {
        index = (uint32_t)(position + inputs->offset) / step;
        value = (uint32_t)(position + inputs->base) >> 21;
        if (index >= ARM_MAPPING_ENTRIES)
            return UINT32_C(0xFFFFFFFC);
        write_entry(table, index, value);
    }
    if (state->selection == 0) {
        uint32_t arguments[6] = {state->service_index, UINT32_C(0xE403B498), 0, 0, 0, 0};
        plan->service(plan->context, UINT32_C(0x0ED65284), arguments, 6, 7);
    }
    return 0;
}

enum arm_mapping_status arm_mapping_prepare(
    const struct arm_mapping_inputs *inputs, struct arm_mapping_state *state,
    uint8_t *table, size_t table_length, const struct arm_mapping_plan *plan,
    uint32_t *raw_result) {
    struct span spans[5] = {{inputs, sizeof(*inputs)},
        {state, state != NULL ? sizeof(*state) : 0}, {table, table_length},
        {plan, plan != NULL ? sizeof(*plan) : 0}, {raw_result, sizeof(*raw_result)}};
    enum arm_mapping_status status = validate_spans(spans, 5);
    uint32_t mutex_identity = UINT32_C(0xE403B470), raw;
    if (status != ARM_MAPPING_OK)
        return status;
    status = validate_profile(inputs, state, table, table_length, plan);
    if (status != ARM_MAPPING_OK)
        return status;
    if (inputs->handle == 0) {
        *raw_result = UINT32_MAX;
        return ARM_MAPPING_OK;
    }
    plan->acquire(plan->context, UINT32_C(0x0ED64D02), &mutex_identity, 1, 0);
    raw = prepare_table(inputs, state, table, plan);
    plan->release(plan->context, UINT32_C(0x0ED64D3A), &mutex_identity, 1, 0);
    *raw_result = raw;
    return ARM_MAPPING_OK;
}
