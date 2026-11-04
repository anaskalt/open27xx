/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "clock_request.h"

#define TABLE 0x04u
#define HANDLE 0x08u
#define REFERENCE 0x24u
#define SOURCE 0x44u
#define DIVIDER_RATE 0x11Cu
#define DIVIDER_COUNT 0x188u
#define REQUESTED 0x334u
#define NOTIFICATIONS 0x464u
#define RATE UINT64_C(600000000)

struct span {
    const void *pointer;
    size_t length;
};

static enum clock_request_status validate_spans(const struct span *spans,
                                               size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left)
        if (spans[left].pointer == NULL
                || spans[left].length > UINTPTR_MAX - (uintptr_t)spans[left].pointer)
            return CLOCK_REQUEST_INVALID;
    for (left = 0; left < count; ++left) {
        uintptr_t a = (uintptr_t)spans[left].pointer;
        for (right = left + 1; right < count; ++right) {
            uintptr_t b = (uintptr_t)spans[right].pointer;
            if (a < b ? b - a < spans[left].length : a - b < spans[right].length)
                return CLOCK_REQUEST_OVERLAP;
        }
    }
    return CLOCK_REQUEST_OK;
}

static uint32_t read32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8)
        | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static uint64_t read64(const uint8_t *bytes) {
    return read32(bytes) | ((uint64_t)read32(bytes + 4) << 32);
}

static void write32(uint8_t *bytes, uint32_t value) {
    size_t index;
    for (index = 0; index < 4; ++index)
        bytes[index] = (uint8_t)(value >> (8 * index));
}

static void write64(uint8_t *bytes, uint64_t value) {
    write32(bytes, (uint32_t)value);
    write32(bytes + 4, (uint32_t)(value >> 32));
}

static enum clock_request_status validate_inputs(
    const struct clock_request_inputs *inputs) {
    size_t index;
    if (inputs->identifier != 0x30 || inputs->requested != RATE
            || inputs->argument3 != 0 || inputs->argument4 != 0
            || (inputs->skip != 0 && inputs->skip != 1 && inputs->skip != UINT32_MAX)
            || inputs->selection != 1)
        return CLOCK_REQUEST_UNSUPPORTED;
    for (index = 0; index < 3; ++index)
        if (inputs->override_heads[index] != 0)
            return CLOCK_REQUEST_UNSUPPORTED;
    return CLOCK_REQUEST_OK;
}

static int matching_misses(const struct clock_request_state *state, int repeated) {
    size_t index;
    if (state->divider_miss != (repeated ? 0x20u : 0u)
            || state->source_miss != (repeated ? 0x80u : 0u))
        return 0;
    for (index = 0; index < CLOCK_REQUEST_MISS_BYTES; ++index)
        if (state->descriptor_miss[index] != (repeated && index == 0x30 ? 1 : 0))
            return 0;
    return 1;
}

static enum clock_request_status validate_state_plan(
    const struct clock_request_inputs *inputs, const struct clock_request_plan *plan,
    int repeated) {
    if (inputs->skip != 0 || inputs->planner_input != 1200)
        return CLOCK_REQUEST_UNSUPPORTED;
    if (plan->acquire == NULL || plan->diagnostic == NULL || plan->release == NULL
            || plan->clock == NULL || (!repeated && (plan->source == NULL || plan->divider == NULL)))
        return CLOCK_REQUEST_INVALID;
    if (plan->clock_reply != 0
            || (!repeated && (plan->source_reply != 0 || plan->divider_replies[0] != 0)))
        return CLOCK_REQUEST_UNSUPPORTED;
    return CLOCK_REQUEST_OK;
}

static enum clock_request_status validate_request(
    const struct clock_request_inputs *inputs, const uint8_t *manager,
    const struct clock_request_state *state, const struct clock_request_plan *plan) {
    uint64_t source = read64(manager + SOURCE);
    uint64_t divider = read64(manager + DIVIDER_RATE);
    uint32_t notification = read32(manager + NOTIFICATIONS + 4);
    uint64_t requested = read64(manager + REQUESTED);
    enum clock_request_status status = validate_inputs(inputs);
    size_t index;
    int base = source == 0 && divider == 0 && inputs->planner_input == 1200;
    if (status != CLOCK_REQUEST_OK)
        return status;
    if (state->initialized != 1
            || read32(manager + TABLE) == 0 || read32(manager + HANDLE) == 0
            || read32(manager + HANDLE) != inputs->comparison_handle)
        return CLOCK_REQUEST_UNSUPPORTED;
    if (requested != UINT64_C(500000000)) {
        uint64_t reference = read64(manager + REFERENCE);
        int repeated = requested == RATE;
        if (repeated) {
            if (source != UINT64_C(1200000000) || divider != RATE
                    || read32(manager + DIVIDER_COUNT) != 2
                    || (reference != 0 && reference != UINT64_C(54000000)))
                return CLOCK_REQUEST_UNSUPPORTED;
        } else if (requested != 0 || source != 0 || divider != 0
                || read32(manager + DIVIDER_COUNT) != 0 || reference != UINT64_C(54000000)) {
            return CLOCK_REQUEST_UNSUPPORTED;
        }
        if (!matching_misses(state, repeated))
            return CLOCK_REQUEST_UNSUPPORTED;
        for (index = 0; index < 4; ++index) {
            const uint8_t *record = manager + NOTIFICATIONS + 8 * index;
            if (record[0] != 0 || read32(record + 4) != 0)
                return CLOCK_REQUEST_UNSUPPORTED;
        }
        return validate_state_plan(inputs, plan, repeated);
    }
    if (read32(manager + DIVIDER_COUNT) != 0 || !matching_misses(state, 0))
        return CLOCK_REQUEST_UNSUPPORTED;
    if (inputs->planner_input == 1200) {
        if (!((source == 0 && divider == 0)
                || (source == UINT64_C(1000000000) && divider == UINT64_C(250000000))
                || (source == UINT64_C(2000000000) && divider == UINT64_C(500000000))
                || (source == UINT64_C(1200000000) && divider == UINT64_C(300000000))))
            return CLOCK_REQUEST_UNSUPPORTED;
    } else if (inputs->planner_input != 1500 || source != 0 || divider != 0) {
        return CLOCK_REQUEST_UNSUPPORTED;
    }
    for (index = 0; index < 4; ++index) {
        const uint8_t *record = manager + NOTIFICATIONS + 8 * index;
        if (index == 0 && notification != 0) {
            if (record[0] != 0x30 || !base)
                return CLOCK_REQUEST_UNSUPPORTED;
        } else if (record[0] != 0 || read32(record + 4) != 0) {
            return CLOCK_REQUEST_UNSUPPORTED;
        }
    }
    if (inputs->skip != 0)
        return base && notification == 0 ? CLOCK_REQUEST_OK : CLOCK_REQUEST_UNSUPPORTED;
    if (plan->acquire == NULL || plan->diagnostic == NULL || plan->release == NULL)
        return CLOCK_REQUEST_INVALID;
    if (notification != 0) {
        if (plan->notify == NULL)
            return CLOCK_REQUEST_INVALID;
        if (plan->notification_replies[0] == 7)
            return CLOCK_REQUEST_OK;
        if (plan->notification_replies[0] != 0 || plan->notification_replies[1] != 7)
            return CLOCK_REQUEST_UNSUPPORTED;
    }
    if (plan->clock == NULL || plan->divider == NULL
            || (source != UINT64_C(1200000000) && plan->source == NULL))
        return CLOCK_REQUEST_INVALID;
    if (base && notification == 0) {
        if (!((plan->source_reply == 0 && plan->clock_reply == 0
                    && plan->divider_replies[0] == 0)
                || (plan->source_reply == UINT32_MAX && plan->clock_reply == UINT32_MAX
                    && plan->divider_replies[0] == UINT32_MAX)))
            return CLOCK_REQUEST_UNSUPPORTED;
    } else if (plan->clock_reply != 0 || plan->divider_replies[0] != 0
            || (source != UINT64_C(1200000000) && plan->source_reply != 0)
            || (source == UINT64_C(1000000000) && plan->divider_replies[1] != 0)) {
        return CLOCK_REQUEST_UNSUPPORTED;
    }
    return CLOCK_REQUEST_OK;
}

static void initialize_manager(uint32_t table, uint8_t *manager,
                               struct clock_request_state *state,
                               const struct clock_request_open_plan *plan) {
    size_t index;
    state->initialized = 1;
    for (index = 0; index < CLOCK_REQUEST_STATE_BYTES; ++index)
        manager[index] = 0;
    write32(manager + TABLE, table);
    plan->open(plan->context, table, 0, manager + HANDLE, plan->reply, plan->handle_write);
    write32(manager + HANDLE, plan->handle_write);
    write64(manager + REFERENCE, UINT64_C(54000000));
}

enum clock_request_status clock_request_initialize(
    uint32_t selection, uint32_t table,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *state,
    const struct clock_request_open_plan *plan, uint32_t *raw_return) {
    struct span spans[4] = {{manager, manager_length}, {state, sizeof(*state)},
        {plan, sizeof(*plan)}, {raw_return, sizeof(*raw_return)}};
    enum clock_request_status status = validate_spans(spans, 4);
    if (status != CLOCK_REQUEST_OK)
        return status;
    if (manager_length < CLOCK_REQUEST_STATE_BYTES)
        return CLOCK_REQUEST_BOUNDS;
    if (selection != 1 || table == 0 || state->initialized != 0
            || !((plan->reply == 0 && plan->handle_write == UINT32_C(0xC10C1234))
                || (plan->reply == 7 && plan->handle_write == 0)))
        return CLOCK_REQUEST_UNSUPPORTED;
    if (plan->open == NULL)
        return CLOCK_REQUEST_INVALID;

    initialize_manager(table, manager, state, plan);
    *raw_return = plan->reply;
    return CLOCK_REQUEST_OK;
}

static void program_source(const struct clock_request_plan *plan,
                           uint32_t handle, uint64_t source) {
    uint32_t arguments[4];
    arguments[0] = handle;
    arguments[1] = 2;
    arguments[2] = (uint32_t)source;
    arguments[3] = (uint32_t)(source >> 32);
    plan->source(plan->context, CLOCK_REQUEST_SOURCE, UINT32_C(0x0EC7D978),
                 arguments, 4, plan->source_reply);
}

static void program_divider(const struct clock_request_plan *plan,
                            uint32_t handle, uint32_t count, size_t reply_index) {
    uint32_t arguments[3];
    arguments[0] = handle;
    arguments[1] = 5;
    arguments[2] = count;
    plan->divider(plan->context, CLOCK_REQUEST_DIVIDER, UINT32_C(0x0EC7D5EA),
                  arguments, 3, plan->divider_replies[reply_index]);
}

static void notify(const struct clock_request_plan *plan,
                   uint32_t identity, uint32_t phase, size_t reply_index) {
    uint32_t arguments[4];
    arguments[0] = 0x30;
    arguments[1] = phase;
    arguments[2] = (uint32_t)RATE;
    arguments[3] = 0;
    plan->notify(plan->context, CLOCK_REQUEST_NOTIFY, identity,
                 arguments, 4, plan->notification_replies[reply_index]);
}

static void execute_request(
    const struct clock_request_inputs *inputs, uint8_t *manager,
    struct clock_request_state *state, uint8_t *output,
    const struct clock_request_plan *plan, uint32_t *raw_return) {
    uint32_t arguments[7], handle, notification, count, result = 0;
    uint64_t old_source, source;
    int lower, repeated = read64(manager + REQUESTED) == RATE;
    if (inputs->skip != 0) {
        *raw_return = inputs->identifier;
        return;
    }

    handle = read32(manager + HANDLE);
    notification = read32(manager + NOTIFICATIONS + 4);
    old_source = read64(manager + SOURCE);
    count = inputs->planner_input == 1200 ? 2 : 3;
    source = inputs->planner_input == 1200 ? UINT64_C(1200000000) : UINT64_C(1800000000);
    lower = old_source != 0 && old_source < source;
    arguments[0] = inputs->mutex_identity;
    plan->acquire(plan->context, CLOCK_REQUEST_ACQUIRE, UINT32_C(0x0ED64D02), arguments, 1, 0);
    arguments[0] = UINT32_C(0x4000);
    arguments[1] = UINT32_C(0x0EC7EF38);
    arguments[2] = inputs->identifier;
    arguments[3] = (uint32_t)inputs->requested;
    arguments[4] = (uint32_t)(inputs->requested >> 32);
    arguments[5] = inputs->argument3;
    arguments[6] = inputs->argument4;
    plan->diagnostic(plan->context, CLOCK_REQUEST_DIAGNOSTIC, UINT32_C(0x0ED17442),
                     arguments, 7, 0);
    state->descriptor_miss[0x30] = 1;
    if (notification != 0) {
        notify(plan, notification, 0, 0);
        if (plan->notification_replies[0] == 7) {
            result = (uint32_t)read64(manager + REQUESTED);
            arguments[0] = inputs->mutex_identity;
            plan->release(plan->context, CLOCK_REQUEST_RELEASE, UINT32_C(0x0ED64D3A),
                          arguments, 1, 0);
            *raw_return = result;
            return;
        }
    }
    state->divider_miss = 0x20;
    state->source_miss = 0x80;
    if (lower)
        program_divider(plan, handle, count, 0);
    write32(manager + DIVIDER_COUNT, count);
    if (old_source != source) {
        if (!lower)
            program_source(plan, handle, source);
        write64(manager + SOURCE, source);
    }
    write64(manager + DIVIDER_RATE, RATE);
    arguments[0] = handle;
    arguments[1] = 0x30;
    arguments[2] = 7;
    arguments[3] = 5;
    arguments[4] = UINT32_C(0x3F800000);
    arguments[5] = 0;
    plan->clock(plan->context, CLOCK_REQUEST_CLOCK, UINT32_C(0x0EC7C7D0),
                arguments, 6, plan->clock_reply);
    if (lower)
        program_source(plan, handle, source);
    if (!repeated)
        program_divider(plan, handle, count, lower ? 1 : 0);
    write64(manager + REQUESTED, RATE);
    if (notification != 0) {
        notify(plan, notification, 2, 1);
        result = UINT32_MAX;
    }
    write64(output, read64(manager + REQUESTED));
    arguments[0] = inputs->mutex_identity;
    plan->release(plan->context, CLOCK_REQUEST_RELEASE, UINT32_C(0x0ED64D3A), arguments, 1, 0);
    *raw_return = result;
}

enum clock_request_status clock_request_execute(
    const struct clock_request_inputs *inputs,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *state,
    uint8_t *output, size_t output_length,
    const struct clock_request_plan *plan, uint32_t *raw_return) {
    struct span spans[6] = {{inputs, sizeof(*inputs)}, {manager, manager_length},
        {state, sizeof(*state)}, {output, output_length},
        {plan, sizeof(*plan)}, {raw_return, sizeof(*raw_return)}};
    enum clock_request_status status = validate_spans(spans, 6);
    if (status != CLOCK_REQUEST_OK)
        return status;
    if (manager_length < CLOCK_REQUEST_STATE_BYTES || output_length < CLOCK_REQUEST_OUTPUT_BYTES)
        return CLOCK_REQUEST_BOUNDS;
    status = validate_request(inputs, manager, state, plan);
    if (status != CLOCK_REQUEST_OK)
        return status;
    execute_request(inputs, manager, state, output, plan, raw_return);
    return CLOCK_REQUEST_OK;
}

enum clock_request_status clock_request_execute_cold(
    const struct clock_request_inputs *inputs, uint32_t table,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *state,
    uint8_t *output, size_t output_length,
    const struct clock_request_open_plan *open_plan,
    const struct clock_request_plan *plan, uint32_t *raw_return) {
    struct span spans[7] = {{inputs, sizeof(*inputs)}, {manager, manager_length},
        {state, sizeof(*state)}, {output, output_length}, {open_plan, sizeof(*open_plan)},
        {plan, sizeof(*plan)}, {raw_return, sizeof(*raw_return)}};
    enum clock_request_status status = validate_spans(spans, 7);
    size_t index;
    if (status != CLOCK_REQUEST_OK)
        return status;
    if (manager_length < CLOCK_REQUEST_STATE_BYTES || output_length < CLOCK_REQUEST_OUTPUT_BYTES)
        return CLOCK_REQUEST_BOUNDS;
    status = validate_inputs(inputs);
    if (status != CLOCK_REQUEST_OK)
        return status;
    if (table == 0 || state->initialized != 0 || !matching_misses(state, 0)
            || open_plan->reply != 0 || open_plan->handle_write != UINT32_C(0xC10C1234)
            || open_plan->handle_write != inputs->comparison_handle)
        return CLOCK_REQUEST_UNSUPPORTED;
    for (index = 0; index < CLOCK_REQUEST_STATE_BYTES; ++index)
        if (manager[index] != 0xA5)
            return CLOCK_REQUEST_UNSUPPORTED;
    if (open_plan->open == NULL)
        return CLOCK_REQUEST_INVALID;
    status = validate_state_plan(inputs, plan, 0);
    if (status != CLOCK_REQUEST_OK)
        return status;
    initialize_manager(table, manager, state, open_plan);
    execute_request(inputs, manager, state, output, plan, raw_return);
    return CLOCK_REQUEST_OK;
}
