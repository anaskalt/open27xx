/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "resource_request.h"

struct span {
    const void *pointer;
    size_t length;
};

static int valid_extent(const void *pointer, size_t length) {
    return pointer != NULL && length <= UINTPTR_MAX - (uintptr_t)pointer;
}

static int overlaps(struct span left, struct span right) {
    uintptr_t a = (uintptr_t)left.pointer, b = (uintptr_t)right.pointer;
    return a < b ? b - a < left.length : a - b < right.length;
}

static enum resource_request_status validate_spans(const struct span *spans,
                                                  size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left)
        if (!valid_extent(spans[left].pointer, spans[left].length))
            return RESOURCE_REQUEST_INVALID;
    for (left = 0; left < count; ++left)
        for (right = left + 1; right < count; ++right)
            if (overlaps(spans[left], spans[right]))
                return RESOURCE_REQUEST_OVERLAP;
    return RESOURCE_REQUEST_OK;
}

static void returned(struct resource_request_outcome *outcome, uint32_t word) {
    outcome->kind = RESOURCE_REQUEST_RETURNED;
    outcome->value.raw_return = word;
}

static void stopped(struct resource_request_outcome *outcome) {
    outcome->kind = RESOURCE_REQUEST_STOPPED;
    outcome->value.stop_flag = 1;
}

static enum resource_request_status validate_context(
    const struct resource_request_context *context) {
    if (context->provider == NULL)
        return RESOURCE_REQUEST_INVALID;
    if (context->descriptor == 0 || context->callback == 0
            || (context->reply != 0 && context->reply != 7))
        return RESOURCE_REQUEST_UNSUPPORTED;
    return RESOURCE_REQUEST_OK;
}

static void emit_context(const struct resource_request_context *context) {
    uint32_t arguments[3];
    arguments[0] = context->opaque;
    arguments[1] = context->callback;
    arguments[2] = context->descriptor;
    context->provider(context->context, RESOURCE_REQUEST_CONTEXT,
                      arguments, 3, context->reply);
}

enum resource_request_status resource_request_dependency(
    uint32_t logical_index, uint32_t selection, uint32_t *result) {
    if (!valid_extent(result, sizeof(*result)))
        return RESOURCE_REQUEST_INVALID;
    if (logical_index != 23 || selection > 1)
        return RESOURCE_REQUEST_UNSUPPORTED;
    *result = RESOURCE_REQUEST_DEPENDENCIES;
    return RESOURCE_REQUEST_OK;
}

enum resource_request_status resource_request_context_call(
    const struct resource_request_context *context,
    struct resource_request_outcome *outcome) {
    struct span spans[2] = {{context, sizeof(*context)}, {outcome, sizeof(*outcome)}};
    enum resource_request_status status = validate_spans(spans, 2);
    if (status != RESOURCE_REQUEST_OK)
        return status;
    status = validate_context(context);
    if (status != RESOURCE_REQUEST_OK)
        return status;
    emit_context(context);
    returned(outcome, context->reply);
    return RESOURCE_REQUEST_OK;
}

enum resource_request_status resource_request_check(
    uint32_t condition, const struct resource_request_context *context,
    struct resource_request_outcome *outcome) {
    enum resource_request_status status;
    if (!valid_extent(outcome, sizeof(*outcome)))
        return RESOURCE_REQUEST_INVALID;
    if (condition != 0) {
        returned(outcome, condition);
        return RESOURCE_REQUEST_OK;
    }
    status = resource_request_context_call(context, outcome);
    if (status == RESOURCE_REQUEST_OK && outcome->value.raw_return == 7)
        stopped(outcome);
    return status;
}

static uint32_t aggregate(const struct resource_request_record *records,
                          uint32_t held) {
    size_t index;
    for (index = 0; index < RESOURCE_REQUEST_RECORDS; ++index)
        if (records[index].self != 0 && records[index].requests != 0)
            held |= RESOURCE_REQUEST_DEPENDENCIES;
    return held;
}

enum resource_request_status resource_request_execute(
    const struct resource_request_inputs *inputs,
    struct resource_request_record *records, size_t record_count,
    struct resource_request_state *state,
    const struct resource_request_plan *plan,
    struct resource_request_outcome *outcome) {
    struct span spans[6] = {{inputs, sizeof(*inputs)}, {records, 0},
        {state, sizeof(*state)}, {plan, sizeof(*plan)}, {outcome, sizeof(*outcome)},
        {NULL, 0}};
    const struct resource_request_context *context = NULL;
    enum resource_request_status status;
    uint32_t old, arguments[6];
    size_t index;
    int duplicate, enables, needs_context, will_stop;
    if (record_count > SIZE_MAX / sizeof(*records))
        return RESOURCE_REQUEST_INVALID;
    spans[1].length = record_count * sizeof(*records);
    status = validate_spans(spans, 5);
    if (status != RESOURCE_REQUEST_OK)
        return status;
    if (record_count < RESOURCE_REQUEST_RECORDS
            || inputs->record_index >= RESOURCE_REQUEST_RECORDS)
        return RESOURCE_REQUEST_BOUNDS;
    if (inputs->object_present > 1 || inputs->logical_index != 23
            || inputs->argument2 != 1 || inputs->argument3 != 1
            || (inputs->object_present && inputs->identity == 0))
        return RESOURCE_REQUEST_UNSUPPORTED;
    if (!inputs->object_present || records[inputs->record_index].self != inputs->identity) {
        returned(outcome, UINT32_MAX);
        return RESOURCE_REQUEST_OK;
    }
    if (inputs->selection > 1
            || (state->held != 0 && state->held != RESOURCE_REQUEST_DEPENDENCIES))
        return RESOURCE_REQUEST_UNSUPPORTED;
    for (index = 0; index < RESOURCE_REQUEST_RECORDS; ++index)
        if (records[index].requests != 0 && records[index].requests != RESOURCE_REQUEST_BIT)
            return RESOURCE_REQUEST_UNSUPPORTED;
    old = aggregate(records, state->held);
    duplicate = records[inputs->record_index].requests != 0;
    enables = old == 0;
    if (enables && plan->enable_replies[0] != 0 && plan->enable_replies[0] != 7)
        return RESOURCE_REQUEST_UNSUPPORTED;
    needs_context = duplicate || (enables && plan->enable_replies[0] == 7);
    if (needs_context) {
        context = plan->check_context;
        spans[5].pointer = context;
        spans[5].length = sizeof(*context);
        status = validate_spans(spans, 6);
        if (status != RESOURCE_REQUEST_OK)
            return status;
        status = validate_context(context);
        if (status != RESOURCE_REQUEST_OK)
            return status;
    }
    will_stop = needs_context && context->reply == 7;
    if (enables && !will_stop && plan->enable_replies[1] != 0)
        return RESOURCE_REQUEST_UNSUPPORTED;
    if (plan->diagnostic == NULL || plan->acquire == NULL
            || (!will_stop && plan->release == NULL) || (enables && plan->enable == NULL))
        return RESOURCE_REQUEST_INVALID;

    arguments[0] = UINT32_C(0x4000);
    arguments[1] = UINT32_C(0x0ED7CAB0);
    arguments[2] = inputs->identity;
    arguments[3] = 23;
    arguments[4] = arguments[5] = 1;
    plan->diagnostic(plan->context, RESOURCE_REQUEST_DIAGNOSTIC, arguments, 6, 0);
    arguments[0] = inputs->mutex_identity;
    plan->acquire(plan->context, RESOURCE_REQUEST_ACQUIRE, arguments, 1, 0);
    state->aggregate = old;
    if (duplicate) {
        emit_context(context);
        if (will_stop) {
            stopped(outcome);
            return RESOURCE_REQUEST_OK;
        }
    }
    records[inputs->record_index].requests = RESOURCE_REQUEST_BIT;
    state->aggregate = aggregate(records, state->held);
    state->held = 0;
    if (enables) {
        for (index = 0; index < 2; ++index) {
            arguments[0] = inputs->handle;
            arguments[1] = UINT32_C(0x80) << index;
            plan->enable(plan->context, RESOURCE_REQUEST_ENABLE,
                         arguments, 2, plan->enable_replies[index]);
            if (plan->enable_replies[index] != 0) {
                emit_context(context);
                if (will_stop) {
                    stopped(outcome);
                    return RESOURCE_REQUEST_OK;
                }
            }
        }
    }
    arguments[0] = inputs->mutex_identity;
    plan->release(plan->context, RESOURCE_REQUEST_RELEASE, arguments, 1, 0);
    returned(outcome, 0);
    return RESOURCE_REQUEST_OK;
}
