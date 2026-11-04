/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "clock_composition.h"
#include "clock_driver_internal.h"

#define HANDLE UINT32_C(0xC10C1234)
#define TABLE UINT32_C(0x0EDE7F04)
#define RATE UINT64_C(600000000)
#define SOURCE_RATE UINT64_C(1200000000)

struct span {
    const void *pointer;
    size_t length;
};

static enum clock_driver_status validate_spans(const struct span *spans,
                                              size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        if (spans[left].pointer == NULL)
            return CLOCK_DRIVER_INVALID;
        if (spans[left].length > UINTPTR_MAX - (uintptr_t)spans[left].pointer)
            return CLOCK_DRIVER_BOUNDS;
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
                return CLOCK_DRIVER_OVERLAP;
        }
    }
    return CLOCK_DRIVER_OK;
}

static void write32(uint8_t *bytes, uint32_t word) {
    size_t index;
    for (index = 0; index < 4; ++index)
        bytes[index] = (uint8_t)(word >> (8 * index));
}

static void write64(uint8_t *bytes, uint64_t word) {
    write32(bytes, (uint32_t)word);
    write32(bytes + 4, (uint32_t)(word >> 32));
}

static enum clock_driver_status validate_entry(
    const struct clock_composition_inputs *inputs, const uint8_t *manager,
    const struct clock_request_state *state, const uint32_t *cell) {
    const struct clock_request_inputs *request = &inputs->request;
    size_t index;
    if (request->identifier != 0x30 || request->requested != RATE
            || request->argument3 != 0 || request->argument4 != 0
            || request->skip != 0 || request->selection != 1
            || request->comparison_handle != HANDLE || request->planner_input != 1200
            || state->initialized != 1 || state->divider_miss != 0
            || state->source_miss != 0 || *cell != 0)
        return CLOCK_DRIVER_UNSUPPORTED;
    for (index = 0; index < 3; ++index)
        if (request->override_heads[index] != 0)
            return CLOCK_DRIVER_UNSUPPORTED;
    for (index = 0; index < CLOCK_REQUEST_MISS_BYTES; ++index)
        if (state->descriptor_miss[index] != 0)
            return CLOCK_DRIVER_UNSUPPORTED;
    for (index = 0; index < CLOCK_REQUEST_STATE_BYTES; ++index) {
        uint8_t expected = 0;
        if (index >= 4 && index < 8)
            expected = (uint8_t)(TABLE >> (8 * (index - 4)));
        else if (index >= 8 && index < 12)
            expected = (uint8_t)(HANDLE >> (8 * (index - 8)));
        else if (index >= 0x334 && index < 0x33C)
            expected = (uint8_t)(UINT64_C(500000000) >> (8 * (index - 0x334)));
        if (manager[index] != expected)
            return CLOCK_DRIVER_UNSUPPORTED;
    }
    return CLOCK_DRIVER_OK;
}

enum clock_driver_status clock_composition_execute(
    const struct clock_composition_inputs *inputs,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *state,
    struct clock_source_state *source, struct clock_divider_state *divider,
    uint32_t *cell, uint8_t *output, size_t output_length,
    const struct clock_composition_plan *plan,
    struct clock_composition_result *result) {
    struct span spans[11] = {{inputs, sizeof(*inputs)}, {manager, manager_length},
        {state, sizeof(*state)}, {source, sizeof(*source)}, {divider, sizeof(*divider)},
        {cell, sizeof(*cell)}, {output, output_length}, {plan, sizeof(*plan)},
        {result, sizeof(*result)}, {NULL, 0}, {NULL, 0}};
    struct clock_source_inputs source_inputs;
    struct clock_word_inputs word_inputs;
    struct clock_divider_inputs divider_inputs;
    struct clock_composition_result actual;
    enum clock_driver_status status = validate_spans(spans, 9);
    uint32_t arguments[7];
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (manager_length < CLOCK_REQUEST_STATE_BYTES || output_length < CLOCK_REQUEST_OUTPUT_BYTES)
        return CLOCK_DRIVER_BOUNDS;
    if (plan->source.count > SIZE_MAX / sizeof(*plan->source.reads)
            || plan->divider.count > SIZE_MAX / sizeof(*plan->divider.reads))
        return CLOCK_DRIVER_BOUNDS;
    spans[9].pointer = plan->source.reads;
    spans[9].length = plan->source.count * sizeof(*plan->source.reads);
    spans[10].pointer = plan->divider.reads;
    spans[10].length = plan->divider.count * sizeof(*plan->divider.reads);
    status = validate_spans(spans, 11);
    if (status != CLOCK_DRIVER_OK)
        return status;
    status = validate_entry(inputs, manager, state, cell);
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (plan->acquire == NULL || plan->diagnostic == NULL || plan->release == NULL)
        return CLOCK_DRIVER_INVALID;
    if (plan->source.count < 7 || plan->divider.count < 5)
        return CLOCK_DRIVER_BOUNDS;
    if ((plan->source.count != 7 && plan->source.count != 2006)
            || plan->source.reads[0].word != 0 || plan->source.reads[1].word != 0x20016
            || plan->divider.count != 5 || plan->divider.reads[0].word != 5
            || plan->divider.reads[4].word != 0x00345678)
        return CLOCK_DRIVER_UNSUPPORTED;

    source_inputs = (struct clock_source_inputs){HANDLE, HANDLE, 2, SOURCE_RATE,
        inputs->request.selection, inputs->helper_selection, inputs->helper_gate,
        inputs->helper_input, inputs->diagnostic};
    /* The leaf's unreachable enable field is an internal compatibility value. */
    word_inputs = (struct clock_word_inputs){HANDLE, HANDLE, 0x30, 7, 5,
        UINT32_C(0x3F800000), 0, inputs->diagnostic, 0};
    divider_inputs = (struct clock_divider_inputs){HANDLE, HANDLE, 5, 2,
        inputs->request.selection};
    status = clock_source_preflight(&source_inputs, source, &plan->source, &actual.source_raw);
    if (status != CLOCK_DRIVER_OK)
        return status;
    status = clock_word_preflight(&word_inputs, cell, &plan->word, &actual.word_raw);
    if (status != CLOCK_DRIVER_OK)
        return status;
    status = clock_divider_preflight(&divider_inputs, divider, &plan->divider, &actual.divider_raw);
    if (status != CLOCK_DRIVER_OK)
        return status;

    arguments[0] = inputs->request.mutex_identity;
    plan->acquire(plan->context, CLOCK_REQUEST_ACQUIRE, UINT32_C(0x0ED64D02), arguments, 1, 0);
    arguments[0] = 0x4000;
    arguments[1] = UINT32_C(0x0EC7EF38);
    arguments[2] = inputs->request.identifier;
    arguments[3] = (uint32_t)inputs->request.requested;
    arguments[4] = (uint32_t)(inputs->request.requested >> 32);
    arguments[5] = inputs->request.argument3;
    arguments[6] = inputs->request.argument4;
    plan->diagnostic(plan->context, CLOCK_REQUEST_DIAGNOSTIC, UINT32_C(0x0ED17442),
                     arguments, 7, 0);
    state->descriptor_miss[0x30] = 1;
    state->divider_miss = 0x20;
    state->source_miss = 0x80;
    write32(manager + 0x188, divider_inputs.count);
    /* Complete preflight and preserving observers make these dispatches infallible. */
    (void)clock_source_program(&source_inputs, source, &plan->source, &actual.source_raw);
    write64(manager + 0x44, source_inputs.requested);
    write64(manager + 0x11C, inputs->request.requested);
    (void)clock_word_program(&word_inputs, cell, &plan->word, &actual.word_raw);
    (void)clock_divider_program(&divider_inputs, divider, &plan->divider, &actual.divider_raw);
    write64(manager + 0x334, inputs->request.requested);
    write64(output, inputs->request.requested);
    arguments[0] = inputs->request.mutex_identity;
    plan->release(plan->context, CLOCK_REQUEST_RELEASE, UINT32_C(0x0ED64D3A), arguments, 1, 0);
    actual.manager_raw = 0;
    *result = actual;
    return CLOCK_DRIVER_OK;
}
