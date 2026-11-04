/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "resource_composition_internal.h"
#include "clock_composition_internal.h"
#include "clock_driver_internal.h"

#define PASSWORD UINT32_C(0x5A000000)
#define A UINT32_C(0x7E1023E0)
#define B UINT32_C(0x7E100110)
#define C UINT32_C(0x7E101170)
#define Q UINT32_C(0x7E101100)
#define UNUSED UINT32_C(0x7E1000FC)

struct cursor {
    const struct clock_driver_plan *plan;
    size_t index;
};

static const struct clock_driver_read control_reads[] = {
    {A, 0x12345678}, {0x7E1021E0, 0xABCDE155}, {UNUSED, 0x13579BDF},
    {B, 0x00123ABC}, {Q, 0}, {C, 0x12345670}, {Q, 0},
    {B, 0x00123000}, {Q, 0}, {C, 0x12345672}, {Q, 0},
    {C, 0x12345670}, {Q, 0}, {B, 0x00123400}, {Q, 0},
    {C, 0x12345672}, {Q, 0}, {C, 0x12345670}, {Q, 0},
    {B, 0x00123C00}, {Q, 0}, {C, 0x12345672}, {Q, 0}, {UNUSED, 0x2468ACE0}
};

static const struct clock_driver_read final_reads[] = {
    {0x7E00B440, 0xFFFFFFFF}, {0x7EC11018, 0x12345679},
    {0x7EC1101C, 0xABCDEF91}, {0x7EC11018, 0x12345678},
    {0x7EC1101C, 0xABCDEF90}
};

enum clock_driver_status resource_composition_validate_spans(
    const struct resource_composition_span *spans, size_t count) {
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

static uint32_t read32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8
        | (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
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

static enum clock_driver_status validate_reads(const struct clock_driver_plan *plan,
    const struct clock_driver_read *expected, size_t count) {
    size_t index;
    if (plan->observer.observe == NULL)
        return CLOCK_DRIVER_INVALID;
    if (plan->count < count)
        return CLOCK_DRIVER_BOUNDS;
    if (plan->count != count)
        return CLOCK_DRIVER_UNSUPPORTED;
    for (index = 0; index < count; ++index)
        if (plan->reads[index].address != expected[index].address
                || plan->reads[index].word != expected[index].word)
            return CLOCK_DRIVER_UNSUPPORTED;
    return CLOCK_DRIVER_OK;
}

static enum clock_driver_status validate_entry(const struct resource_composition_inputs *inputs,
    const uint8_t *records, const struct resource_composition_state *resource) {
    const struct resource_request_inputs *request = &inputs->request;
    const struct arm_control_configuration *configuration = &inputs->configuration;
    uint32_t mutexes[4];
    size_t index, other;
    if (request->object_present != 1 || request->identity == 0 || request->record_index != 0
            || request->logical_index != 23 || request->argument2 != 1 || request->argument3 != 1
            || request->selection != 0 || request->handle != 0 || inputs->table != 0x0EDFD200
            || inputs->selection != 1 || inputs->skip != 0
            || resource->held != 0 || resource->prehook != 0
            || read32(records) != request->identity)
        return CLOCK_DRIVER_UNSUPPORTED;
    for (index = 4; index < RESOURCE_COMPOSITION_RECORD_BYTES; ++index)
        if (records[index] != 0)
            return CLOCK_DRIVER_UNSUPPORTED;
    if (configuration->driver != 0x0EDE54D4 || configuration->selection != 1
            || configuration->handle != ARM_CONTROL_HANDLE || configuration->service_index != 1
            || configuration->word_a != 0 || configuration->word_b != 1
            || configuration->word_c != 0 || configuration->word_d != 0)
        return CLOCK_DRIVER_UNSUPPORTED;
    mutexes[0] = request->mutex_identity;
    mutexes[1] = inputs->outer_mutex;
    mutexes[2] = inputs->resource_mutex;
    mutexes[3] = inputs->clock.request.mutex_identity;
    for (index = 0; index < 4; ++index)
        for (other = index + 1; other < 4; ++other)
            if (mutexes[index] == mutexes[other])
                return CLOCK_DRIVER_UNSUPPORTED;
    return CLOCK_DRIVER_OK;
}

static uint32_t read_mmio(struct cursor *cursor) {
    const struct clock_driver_read *read = &cursor->plan->reads[cursor->index++];
    cursor->plan->observer.observe(cursor->plan->observer.context,
        CLOCK_DRIVER_MMIO_READ, read->address, read->word);
    return read->word;
}

static void write_mmio(struct cursor *cursor, uint32_t address, uint32_t word) {
    cursor->plan->observer.observe(cursor->plan->observer.context,
        CLOCK_DRIVER_MMIO_WRITE, address, word);
}

static void command(struct cursor *cursor, uint32_t word) {
    write_mmio(cursor, Q, PASSWORD | word);
    while (read_mmio(cursor) != 0) { }
}

static void control_phase(const struct clock_driver_plan *plan) {
    struct cursor cursor = {plan, 0};
    uint32_t saved = read_mmio(&cursor), reply;
    unsigned int group;
    reply = read_mmio(&cursor);
    write_mmio(&cursor, A, (saved & UINT32_C(0xFFFFFF00)) | (reply & 0x3FF) | PASSWORD);
    (void)read_mmio(&cursor);
    reply = read_mmio(&cursor);
    write_mmio(&cursor, B, (reply & UINT32_C(0xFFFFF000)) | PASSWORD);
    command(&cursor, 0x10);
    for (group = 0; group < 3; ++group) {
        reply = read_mmio(&cursor);
        write_mmio(&cursor, C, reply | PASSWORD | 2);
        command(&cursor, 8);
        reply = read_mmio(&cursor);
        write_mmio(&cursor, B, reply | PASSWORD | (group == 2 ? 0x3FFu : 0x400u << group));
        command(&cursor, 8);
        reply = read_mmio(&cursor);
        write_mmio(&cursor, C, (reply & UINT32_C(0xFFFFFFFD)) | PASSWORD);
        command(&cursor, 8);
    }
    write_mmio(&cursor, A, saved | PASSWORD);
    (void)read_mmio(&cursor);
}

static void final_clear(const struct clock_driver_plan *plan) {
    struct cursor cursor = {plan, 0};
    uint32_t reply = read_mmio(&cursor);
    write_mmio(&cursor, 0x7E00B440, reply & UINT32_C(0xFFFFFDFF));
    reply = read_mmio(&cursor);
    write_mmio(&cursor, 0x7EC11018, reply & UINT32_C(0xFFFFFFFE));
    reply = read_mmio(&cursor);
    write_mmio(&cursor, 0x7EC1101C, reply & UINT32_C(0xFFFFFFFE));
    while ((read_mmio(&cursor) & 2) != 0) { }
    while ((read_mmio(&cursor) & 2) != 0) { }
}

static void mutex(const struct resource_composition_plan *plan, uint32_t identity, int acquire) {
    resource_composition_observe_fn observer = acquire ? plan->acquire : plan->release;
    observer(plan->context, acquire ? 0x0ED64D02 : 0x0ED64D3A, &identity, 1, 0);
}

static uint32_t service(void *context, uint32_t index, uint32_t value, uint32_t offset,
                        uint32_t argument3, uint32_t argument4, uint32_t argument5) {
    const struct resource_composition_plan *plan = context;
    uint32_t arguments[6] = {index, value, offset, argument3, argument4, argument5};
    plan->service(plan->context, 0x0ED65284, arguments, 6, 0);
    return 0;
}

static uint32_t aggregate(const uint8_t *records, uint32_t held) {
    uint32_t requests = 0;
    size_t index;
    for (index = 0; index < RESOURCE_REQUEST_RECORDS; ++index)
        if (read32(records + index * 28) != 0)
            requests |= read32(records + index * 28 + 8);
    return held | ((requests & RESOURCE_REQUEST_BIT) != 0 ? RESOURCE_REQUEST_DEPENDENCIES : 0);
}

static void repeat_clock(const struct clock_composition_inputs *inputs, uint32_t *cell,
    uint8_t *scratch, const struct clock_composition_plan *plan,
    const struct clock_word_inputs *word_inputs, struct resource_composition_result *actual) {
    uint32_t arguments[7] = {0x4000, 0x0EC7EF38, inputs->request.identifier,
        (uint32_t)inputs->request.requested, (uint32_t)(inputs->request.requested >> 32),
        inputs->request.argument3, inputs->request.argument4};
    uint32_t identity = inputs->request.mutex_identity;
    plan->acquire(plan->context, CLOCK_REQUEST_ACQUIRE, 0x0ED64D02, &identity, 1, 0);
    plan->diagnostic(plan->context, CLOCK_REQUEST_DIAGNOSTIC, 0x0ED17442, arguments, 7, 0);
    (void)clock_word_program(word_inputs, cell, &plan->word, &actual->repeated_word_raw);
    write64(scratch, inputs->request.requested);
    plan->release(plan->context, CLOCK_REQUEST_RELEASE, 0x0ED64D3A, &identity, 1, 0);
    actual->repeated_manager_raw = 0;
}

enum clock_driver_status resource_composition_preflight(
    const struct resource_composition_inputs *inputs,
    const uint8_t *records, size_t records_length,
    const struct resource_composition_state *resource,
    const uint8_t *manager, size_t manager_length,
    const struct clock_request_state *clock_state,
    const struct clock_source_state *source, const struct clock_divider_state *divider,
    const uint32_t *cell, const uint8_t *scratch, size_t scratch_length,
    const struct resource_composition_plan *plan,
    const struct resource_composition_result *result) {
    struct resource_composition_span spans[16] = {{inputs, sizeof(*inputs)}, {records, records_length},
        {resource, sizeof(*resource)}, {manager, manager_length},
        {clock_state, sizeof(*clock_state)}, {source, sizeof(*source)}, {divider, sizeof(*divider)},
        {cell, sizeof(*cell)}, {scratch, scratch_length}, {plan, sizeof(*plan)},
        {result, sizeof(*result)}, {NULL, 0}, {NULL, 0}, {NULL, 0}, {NULL, 0}, {NULL, 0}};
    const struct clock_driver_plan *reads[5];
    struct resource_composition_result actual = {0};
    struct clock_word_inputs repeated_word;
    uint32_t predicted_cell = PASSWORD;
    size_t index;
    enum clock_driver_status status = resource_composition_validate_spans(spans, 11);
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (records_length < RESOURCE_COMPOSITION_RECORD_BYTES
            || manager_length < CLOCK_REQUEST_STATE_BYTES || scratch_length < CLOCK_REQUEST_OUTPUT_BYTES)
        return CLOCK_DRIVER_BOUNDS;
    reads[0] = &plan->clock.source;
    reads[1] = &plan->clock.divider;
    reads[2] = &plan->control[0];
    reads[3] = &plan->control[1];
    reads[4] = &plan->final;
    for (index = 0; index < 5; ++index) {
        if (reads[index]->count > SIZE_MAX / sizeof(*reads[index]->reads))
            return CLOCK_DRIVER_BOUNDS;
        spans[11 + index].pointer = reads[index]->reads;
        spans[11 + index].length = reads[index]->count * sizeof(*reads[index]->reads);
    }
    status = resource_composition_validate_spans(spans, 16);
    if (status != CLOCK_DRIVER_OK)
        return status;
    status = validate_entry(inputs, records, resource);
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (plan->diagnostic == NULL || plan->acquire == NULL || plan->release == NULL || plan->service == NULL)
        return CLOCK_DRIVER_INVALID;
    status = clock_composition_preflight(&inputs->clock, manager, manager_length,
        clock_state, source, divider, cell, scratch, scratch_length, &plan->clock, &actual.first_clock);
    if (status != CLOCK_DRIVER_OK)
        return status;
    for (index = 0; index < 2; ++index) {
        status = validate_reads(&plan->control[index], control_reads,
            sizeof(control_reads) / sizeof(control_reads[0]));
        if (status != CLOCK_DRIVER_OK)
            return status;
    }
    status = validate_reads(&plan->final, final_reads, sizeof(final_reads) / sizeof(final_reads[0]));
    if (status != CLOCK_DRIVER_OK)
        return status;
    repeated_word = (struct clock_word_inputs){UINT32_C(0xC10C1234), UINT32_C(0xC10C1234),
        0x30, 7, 5, UINT32_C(0x3F800000), 0, inputs->clock.diagnostic, 0};
    status = clock_word_preflight(&repeated_word, &predicted_cell,
        &plan->clock.word, &actual.repeated_word_raw);
    if (status != CLOCK_DRIVER_OK)
        return status;

    return CLOCK_DRIVER_OK;
}

enum clock_driver_status resource_composition_execute(
    const struct resource_composition_inputs *inputs,
    uint8_t *records, size_t records_length,
    struct resource_composition_state *resource,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *clock_state,
    struct clock_source_state *source, struct clock_divider_state *divider,
    uint32_t *cell, uint8_t *scratch, size_t scratch_length,
    const struct resource_composition_plan *plan,
    struct resource_composition_result *result) {
    struct resource_composition_result actual;
    struct clock_word_inputs repeated_word;
    uint32_t arguments[6], old, added, mask, configuration_raw;
    enum clock_driver_status status = resource_composition_preflight(inputs, records,
        records_length, resource, manager, manager_length, clock_state, source,
        divider, cell, scratch, scratch_length, plan, result);
    if (status != CLOCK_DRIVER_OK)
        return status;
    repeated_word = (struct clock_word_inputs){UINT32_C(0xC10C1234), UINT32_C(0xC10C1234),
        0x30, 7, 5, UINT32_C(0x3F800000), 0, inputs->clock.diagnostic, 0};

    arguments[0] = 0x4000;
    arguments[1] = 0x0ED7CAB0;
    arguments[2] = inputs->request.identity;
    arguments[3] = inputs->request.logical_index;
    arguments[4] = inputs->request.argument2;
    arguments[5] = inputs->request.argument3;
    plan->diagnostic(plan->context, 0x0ED17442, arguments, 6, 0);
    mutex(plan, inputs->request.mutex_identity, 1);
    old = aggregate(records, resource->held);
    resource->aggregate = old;
    write32(records + 8, read32(records + 8) | RESOURCE_REQUEST_BIT);
    resource->aggregate = aggregate(records, resource->held);
    added = resource->aggregate & ~old;
    for (mask = 1; mask != 0; mask <<= 1) {
        if ((added & mask) == 0)
            continue;
        mutex(plan, inputs->outer_mutex, 1);
        mutex(plan, inputs->resource_mutex, 1);
        resource->prehook |= mask;
        if (mask == 0x100) {
            /* Preflight and preserving observers make all nested calls infallible. */
            (void)arm_control_configure(&inputs->configuration, 0, service, (void *)plan,
                &configuration_raw);
            write64(scratch, 0);
            (void)clock_composition_execute(&inputs->clock, manager, manager_length,
                clock_state, source, divider, cell, scratch, scratch_length,
                &plan->clock, &actual.first_clock);
            control_phase(&plan->control[0]);
            write64(scratch, 0);
            repeat_clock(&inputs->clock, cell, scratch, &plan->clock, &repeated_word, &actual);
            control_phase(&plan->control[1]);
            final_clear(&plan->final);
        }
        mutex(plan, inputs->resource_mutex, 0);
        mutex(plan, inputs->outer_mutex, 0);
    }
    mutex(plan, inputs->request.mutex_identity, 0);
    actual.resource_raw = 0;
    *result = actual;
    return CLOCK_DRIVER_OK;
}
