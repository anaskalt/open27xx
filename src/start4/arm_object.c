/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "arm_object_internal.h"

struct span {
    const void *pointer;
    size_t length;
};

static enum arm_object_status validate_spans(const struct span *spans,
                                             size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        if (spans[left].pointer == NULL && spans[left].length != 0)
            return ARM_OBJECT_INVALID;
        if (spans[left].length > UINTPTR_MAX - (uintptr_t)spans[left].pointer)
            return ARM_OBJECT_BOUNDS;
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
                return ARM_OBJECT_OVERLAP;
        }
    }
    return ARM_OBJECT_OK;
}

static uint32_t read_word(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8
        | (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static void write_word(uint8_t *bytes, uint32_t word) {
    size_t index;
    for (index = 0; index < 4; ++index)
        bytes[index] = (uint8_t)(word >> (index * 8));
}

static int matches_profile(const uint8_t *records, unsigned profile) {
    static const uint32_t retained[7] = {0, UINT32_C(0x55667788),
        UINT32_C(0x11223344), UINT32_C(0xAABBCCDD), UINT32_C(0x89ABCDEF),
        UINT32_C(0xDEADBEEF), UINT32_C(0x76543210)};
    size_t index, field;
    for (index = 0; index < ARM_OBJECT_RECORDS; ++index) {
        for (field = 0; field < 7; ++field) {
            uint32_t expected = 0;
            if (profile == 1 && index == 0 && field == 0)
                expected = ARM_OBJECT_RECORD_BASE;
            if (profile == 2 && field == 0)
                expected = ARM_OBJECT_RECORD_BASE + ARM_OBJECT_RECORD_SIZE * index;
            if (profile == 2 && field == 1)
                expected = (uint32_t)index;
            if (profile == 3 && index == 0)
                expected = retained[field];
            if (read_word(records + ARM_OBJECT_RECORD_SIZE * index + field * 4)
                    != expected)
                return 0;
        }
    }
    return 1;
}

enum arm_object_status arm_object_register_preflight(
    uint32_t output_present, uint8_t *records, size_t records_length,
    uint32_t *object_output, const struct arm_object_plan *plan,
    uint32_t *raw_result, unsigned *profile_output) {
    struct span spans[4] = {{records, records_length},
        {object_output, object_output != NULL || output_present ? sizeof(*object_output) : 0},
        {plan, plan != NULL || output_present ? sizeof(*plan) : 0},
        {raw_result, sizeof(*raw_result)}};
    enum arm_object_status status = validate_spans(spans, 4);
    unsigned profile;
    if (status != ARM_OBJECT_OK)
        return status;
    if (output_present > 1)
        return ARM_OBJECT_UNSUPPORTED;
    if (!output_present)
        return ARM_OBJECT_OK;
    if (records == NULL)
        return ARM_OBJECT_INVALID;
    if (records_length < ARM_OBJECT_RECORD_BYTES)
        return ARM_OBJECT_BOUNDS;
    if (*object_output != UINT32_C(0xA5A5A5A5))
        return ARM_OBJECT_UNSUPPORTED;
    for (profile = 0; profile < 4; ++profile)
        if (matches_profile(records, profile))
            break;
    if (profile == 4)
        return ARM_OBJECT_UNSUPPORTED;
    if (plan->acquire == NULL || plan->release == NULL
            || (profile != 2 && plan->diagnostic == NULL))
        return ARM_OBJECT_INVALID;
    *profile_output = profile;
    return ARM_OBJECT_OK;
}

void arm_object_register_validated(
    uint32_t output_present, uint8_t *records, uint32_t *object_output,
    const struct arm_object_plan *plan, uint32_t *raw_result) {
    size_t selected;
    uint32_t mutex_identity = UINT32_C(0xE40DA4C0), raw = UINT32_MAX;
    if (!output_present) {
        *raw_result = UINT32_MAX;
        return;
    }

    *object_output = 0;
    plan->acquire(plan->context, UINT32_C(0x0ED64D02), &mutex_identity, 1, 0);
    for (selected = 0; selected < ARM_OBJECT_RECORDS; ++selected)
        if (read_word(records + selected * ARM_OBJECT_RECORD_SIZE) == 0)
            break;
    if (selected < ARM_OBJECT_RECORDS) {
        uint8_t *record = records + selected * ARM_OBJECT_RECORD_SIZE;
        uint32_t identity = ARM_OBJECT_RECORD_BASE + selected * ARM_OBJECT_RECORD_SIZE;
        uint32_t arguments[3] = {UINT32_C(0x4000), UINT32_C(0x0ED7C990), identity};
        write_word(record, identity);
        write_word(record + 4, (uint32_t)selected);
        write_word(record + 20, ARM_OBJECT_METADATA0);
        write_word(record + 24, ARM_OBJECT_METADATA1);
        *object_output = identity;
        plan->diagnostic(plan->context, UINT32_C(0x0ED17442), arguments, 3, 0);
        raw = 0;
    }
    plan->release(plan->context, UINT32_C(0x0ED64D3A), &mutex_identity, 1, 0);
    *raw_result = raw;
}

enum arm_object_status arm_object_register(
    uint32_t output_present, uint8_t *records, size_t records_length,
    uint32_t *object_output, const struct arm_object_plan *plan,
    uint32_t *raw_result) {
    unsigned profile;
    enum arm_object_status status = arm_object_register_preflight(
        output_present, records, records_length, object_output, plan,
        raw_result, &profile);
    if (status != ARM_OBJECT_OK)
        return status;
    arm_object_register_validated(output_present, records, object_output, plan, raw_result);
    return ARM_OBJECT_OK;
}

enum arm_object_status arm_object_reopen(
    uint32_t parameter_word, uint8_t parameter_byte,
    struct arm_object_open_state *state, uint32_t *handle_output,
    const struct arm_object_plan *plan, uint32_t *raw_result) {
    struct span spans[4] = {{state, sizeof(*state)},
        {handle_output, sizeof(*handle_output)}, {plan, sizeof(*plan)},
        {raw_result, sizeof(*raw_result)}};
    enum arm_object_status status = validate_spans(spans, 4);
    uint32_t mutex_identity = UINT32_C(0xE403B470);
    if (status != ARM_OBJECT_OK)
        return status;
    if (parameter_word != UINT32_C(0x400) || parameter_byte != 2
            || state->count != 1 || state->object != UINT32_C(0x11223344)
            || *handle_output != UINT32_C(0xA5A5A5A5))
        return ARM_OBJECT_UNSUPPORTED;
    if (plan->acquire == NULL || plan->release == NULL)
        return ARM_OBJECT_INVALID;

    plan->acquire(plan->context, UINT32_C(0x0ED64D02), &mutex_identity, 1, 0);
    ++state->count;
    plan->release(plan->context, UINT32_C(0x0ED64D3A), &mutex_identity, 1, 0);
    *handle_output = ARM_OBJECT_HANDLE;
    *raw_result = 0;
    return ARM_OBJECT_OK;
}
