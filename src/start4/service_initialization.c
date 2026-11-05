/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "service_initialization.h"

struct input_alignment { char prefix; struct service_initialization_input value; };
struct stack_alignment { char prefix; struct service_initialization_stack value; };
struct result_alignment { char prefix; struct service_initialization_result value; };
struct word_alignment { char prefix; uint32_t value; };

#define ALIGNMENT(name) offsetof(struct name##_alignment, value)

struct span {
    const void *pointer;
    size_t length;
    size_t alignment;
};

struct region {
    uint32_t address;
    uint32_t length;
};

static enum service_initialization_status validate_spans(
    const struct span *spans, size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        uintptr_t address = (uintptr_t)spans[left].pointer;
        if ((spans[left].pointer == NULL && spans[left].length != 0)
                || address % spans[left].alignment != 0)
            return SERVICE_INITIALIZATION_INVALID;
        if (spans[left].length > UINTPTR_MAX - address)
            return SERVICE_INITIALIZATION_BOUNDS;
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
                return SERVICE_INITIALIZATION_OVERLAP;
        }
    }
    return SERVICE_INITIALIZATION_OK;
}

static int intersects(uint32_t a, uint32_t a_length,
                      uint32_t b, uint32_t b_length) {
    return a < b ? b - a < a_length : a - b < b_length;
}

static enum service_initialization_status validate_addresses(
    const struct service_initialization_input *input,
    const struct service_initialization_stack *stack) {
    static const struct region excluded[] = {
        {UINT32_C(0xCEC002A0), 96},
        {UINT32_C(0xCEC00DD0), 70},
        {UINT32_C(0xCEC00D76), 12},
        {UINT32_C(0xCEC01E80), 4},
        {UINT32_C(0x7E002030), 4},
        {UINT32_C(0x7E002830), 4},
        {UINT32_C(0x7EE0003C), 4},
        {UINT32_C(0x7EE00040), 4}};
    uint32_t length = (uint32_t)stack->length;
    uint32_t sp = input->registers.sp, lr = input->registers.lr;
    uint32_t frame;
    size_t index;
    if (sp < 8 || (sp & UINT32_C(3)) != 0 || (lr & UINT32_C(1)) != 0)
        return SERVICE_INITIALIZATION_INVALID;
    if (length < 8 || length - 1 > UINT32_MAX - stack->address)
        return SERVICE_INITIALIZATION_BOUNDS;
    frame = sp - 8;
    if (frame < stack->address || frame - stack->address > length - 8)
        return SERVICE_INITIALIZATION_BOUNDS;
    if (intersects(stack->address, length, lr, 1))
        return SERVICE_INITIALIZATION_OVERLAP;
    for (index = 0; index < sizeof(excluded) / sizeof(excluded[0]); ++index) {
        if (intersects(stack->address, length,
                       excluded[index].address, excluded[index].length)
                || intersects(lr, 1,
                              excluded[index].address, excluded[index].length))
            return SERVICE_INITIALIZATION_OVERLAP;
    }
    return SERVICE_INITIALIZATION_OK;
}

static void write_word(uint8_t *bytes, uint32_t word) {
    bytes[0] = (uint8_t)word;
    bytes[1] = (uint8_t)(word >> 8);
    bytes[2] = (uint8_t)(word >> 16);
    bytes[3] = (uint8_t)(word >> 24);
}

static void record(struct service_initialization_result *result, size_t index,
    enum service_initialization_event_kind kind, uint32_t source,
    uint32_t address, uint32_t word) {
    result->events[index].kind = kind;
    result->events[index].source = source;
    result->events[index].address = address;
    result->events[index].word = word;
}

enum service_initialization_status service_initialization_run(
    const struct service_initialization_input *input,
    const struct service_initialization_stack *stack,
    uint32_t *table_word, struct service_initialization_result *result) {
    static const uint32_t versions[] = {
        UINT32_C(0x04000162), UINT32_C(0x04000161), UINT32_C(0x04000160),
        UINT32_C(0x04000140), UINT32_C(0x04000104)};
    struct span spans[] = {
        {input, sizeof(*input), ALIGNMENT(input)},
        {stack, sizeof(*stack), ALIGNMENT(stack)},
        {table_word, table_word == NULL ? 0 : sizeof(*table_word), ALIGNMENT(word)},
        {result, sizeof(*result), ALIGNMENT(result)},
        {NULL, 0, 1}};
    enum service_initialization_status status = validate_spans(spans, 4);
    uint32_t normalized, original = 0, table_address, frame_offset;
    size_t comparison, index;
    int primary;
    if (status != SERVICE_INITIALIZATION_OK)
        return status;
    if (stack->length != (uint32_t)stack->length)
        return SERVICE_INITIALIZATION_BOUNDS;
    spans[4].pointer = stack->bytes;
    spans[4].length = stack->length;
    status = validate_spans(spans, 5);
    if (status != SERVICE_INITIALIZATION_OK)
        return status;
    status = validate_addresses(input, stack);
    if (status != SERVICE_INITIALIZATION_OK)
        return status;
    normalized = input->version & UINT32_C(0xFFFEFFF7);
    for (comparison = 0; comparison < sizeof(versions) / sizeof(versions[0]);
            ++comparison) {
        if (normalized == versions[comparison])
            break;
    }
    if (comparison == sizeof(versions) / sizeof(versions[0]))
        return SERVICE_INITIALIZATION_UNSUPPORTED;
    primary = (input->version & UINT32_C(0x10000)) == 0;
    if (primary) {
        if (table_word == NULL)
            return SERVICE_INITIALIZATION_INVALID;
        original = *table_word;
        if (original != UINT32_C(0xCEC00DA0))
            return SERVICE_INITIALIZATION_UNSUPPORTED;
    }

    table_address = primary ? UINT32_C(0x7E002030) : UINT32_C(0x7E002830);
    frame_offset = input->registers.sp - 8 - stack->address;
    if (primary)
        *table_word = original | UINT32_C(1);
    write_word(stack->bytes + frame_offset, 0);
    write_word(stack->bytes + frame_offset + 4, input->registers.lr);

    for (index = 0; index < 24; ++index)
        result->registers.r[index] = input->registers.r[index];
    result->registers.r[0] = 0;
    result->registers.r[1] = primary ? UINT32_C(0x7EE0003C) : table_address;
    result->registers.r[2] = primary ? UINT32_C(0x7EE00040) : UINT32_C(0xCEC01E00);
    if (primary)
        result->registers.r[5] = input->registers.lr;
    result->registers.gp = input->registers.gp;
    result->registers.sp = input->registers.sp;
    result->registers.lr = input->registers.lr;
    result->registers.r27 = input->registers.r27;
    result->registers.r28 = input->registers.r28;
    result->registers.r29 = input->registers.r29;
    result->registers.sr = 0;
    result->pc = input->registers.lr;
    result->instructions = (primary ? 42u : 18u) + 2u * (uint32_t)comparison;
    result->event_count = primary ? 8u : 3u;
    record(result, 0, SERVICE_INITIALIZATION_VERSION,
           UINT32_C(0xCEC002A0), 0, input->version);
    record(result, 1, SERVICE_INITIALIZATION_MMIO_WRITE,
           UINT32_C(0xCEC002BA), table_address, UINT32_C(0xCEC01E00));
    record(result, 2, SERVICE_INITIALIZATION_VERSION,
           UINT32_C(0xCEC002EA), 0, input->version);
    if (primary) {
        record(result, 3, SERVICE_INITIALIZATION_TABLE_READ,
               UINT32_C(0xCEC00DDC), UINT32_C(0xCEC01E80), original);
        record(result, 4, SERVICE_INITIALIZATION_TABLE_WRITE,
               UINT32_C(0xCEC00DE2), UINT32_C(0xCEC01E80), original | UINT32_C(1));
        record(result, 5, SERVICE_INITIALIZATION_MMIO_WRITE,
               UINT32_C(0xCEC00DF6), UINT32_C(0x7EE0003C), UINT32_C(0x0EC00000));
        record(result, 6, SERVICE_INITIALIZATION_MMIO_WRITE,
               UINT32_C(0xCEC00E02), UINT32_C(0x7EE00040), UINT32_C(0x0EC01FFF));
        record(result, 7, SERVICE_INITIALIZATION_MMIO_WRITE,
               UINT32_C(0xCEC00E0C), UINT32_C(0x7EE0003C), UINT32_C(0x0EC00001));
    } else {
        for (index = 3; index < SERVICE_INITIALIZATION_EVENTS; ++index)
            record(result, index, SERVICE_INITIALIZATION_VERSION, 0, 0, 0);
    }
    return SERVICE_INITIALIZATION_OK;
}
