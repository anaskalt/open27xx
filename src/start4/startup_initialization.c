/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "startup_initialization.h"

struct input_alignment { char prefix; struct startup_initialization_registers value; };
struct destinations_alignment { char prefix; struct startup_initialization_destinations value; };
struct stack_alignment { char prefix; struct startup_initialization_stack value; };
struct result_alignment { char prefix; struct startup_initialization_result value; };

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

static enum startup_initialization_status validate_spans(
    const struct span *spans, size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        uintptr_t address = (uintptr_t)spans[left].pointer;
        if (spans[left].pointer == NULL || address % spans[left].alignment != 0)
            return STARTUP_INITIALIZATION_INVALID;
        if (spans[left].length > UINTPTR_MAX - address)
            return STARTUP_INITIALIZATION_BOUNDS;
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
                return STARTUP_INITIALIZATION_OVERLAP;
        }
    }
    return STARTUP_INITIALIZATION_OK;
}

static int intersects(uint32_t a, uint32_t a_length,
                      uint32_t b, uint32_t b_length) {
    return a < b ? b - a < a_length : a - b < b_length;
}

static enum startup_initialization_status validate_addresses(
    const struct startup_initialization_registers *input,
    const struct startup_initialization_stack *stack) {
    static const struct region excluded[] = {
        {UINT32_C(0x0EC3D740), 182},
        {UINT32_C(0x0EC3D7F6), 2},
        {UINT32_C(0x0ED1FDF0), 4},
        {UINT32_C(0x0ED1FE14), 56},
        {UINT32_C(0x0EDD7870), 36},
        {UINT32_C(0x0EE056A0), 2352},
        {UINT32_C(0x0EE33200), 2048},
        {UINT32_C(0x0EE33A00), 1011288}};
    uint32_t length = (uint32_t)stack->length;
    uint32_t frame;
    size_t index;
    if (input->sp < 24 || (input->sp & UINT32_C(3)) != 0
            || (input->lr & UINT32_C(1)) != 0)
        return STARTUP_INITIALIZATION_INVALID;
    if (length < 24 || length - 1 > UINT32_MAX - stack->address)
        return STARTUP_INITIALIZATION_BOUNDS;
    frame = input->sp - 24;
    if (frame < stack->address || frame - stack->address > length - 24)
        return STARTUP_INITIALIZATION_BOUNDS;
    if (intersects(stack->address, length, input->lr, 1))
        return STARTUP_INITIALIZATION_OVERLAP;
    for (index = 0; index < sizeof(excluded) / sizeof(excluded[0]); ++index) {
        if (intersects(stack->address, length,
                       excluded[index].address, excluded[index].length)
                || intersects(input->lr, 1,
                              excluded[index].address, excluded[index].length))
            return STARTUP_INITIALIZATION_OVERLAP;
    }
    return STARTUP_INITIALIZATION_OK;
}

static void write_word(uint8_t *bytes, uint32_t word) {
    bytes[0] = (uint8_t)word;
    bytes[1] = (uint8_t)(word >> 8);
    bytes[2] = (uint8_t)(word >> 16);
    bytes[3] = (uint8_t)(word >> 24);
}

enum startup_initialization_status startup_initialization_run(
    const struct startup_initialization_registers *input,
    const struct startup_initialization_destinations *destinations,
    const struct startup_initialization_stack *stack,
    struct startup_initialization_result *result) {
    static const size_t lengths[STARTUP_INITIALIZATION_DESTINATIONS] = {
        2352, 2048, 1011288};
    struct span spans[] = {
        {input, sizeof(*input), ALIGNMENT(input)},
        {destinations, sizeof(*destinations), ALIGNMENT(destinations)},
        {stack, sizeof(*stack), ALIGNMENT(stack)},
        {result, sizeof(*result), ALIGNMENT(result)},
        {NULL, 0, 1}, {NULL, 0, 1}, {NULL, 0, 1}, {NULL, 0, 1}};
    enum startup_initialization_status status = validate_spans(spans, 4);
    uint32_t frame_offset;
    size_t index, offset;
    if (status != STARTUP_INITIALIZATION_OK)
        return status;
    if (stack->length != (uint32_t)stack->length)
        return STARTUP_INITIALIZATION_BOUNDS;
    for (index = 0; index < STARTUP_INITIALIZATION_DESTINATIONS; ++index) {
        if (destinations->buffers[index].length != lengths[index])
            return STARTUP_INITIALIZATION_BOUNDS;
        spans[4 + index].pointer = destinations->buffers[index].bytes;
        spans[4 + index].length = lengths[index];
    }
    spans[7].pointer = stack->bytes;
    spans[7].length = stack->length;
    status = validate_spans(spans, 8);
    if (status != STARTUP_INITIALIZATION_OK)
        return status;
    if (input->gp != UINT32_C(0x0EE04140))
        return STARTUP_INITIALIZATION_UNSUPPORTED;
    status = validate_addresses(input, stack);
    if (status != STARTUP_INITIALIZATION_OK)
        return status;

    frame_offset = input->sp - 24 - stack->address;
    write_word(stack->bytes + frame_offset + 20, input->lr);
    for (index = 0; index < 4; ++index)
        write_word(stack->bytes + frame_offset + 16 - 4 * index,
                   input->r[6 + index]);
    for (index = 0; index < STARTUP_INITIALIZATION_DESTINATIONS; ++index) {
        for (offset = 0; offset < lengths[index]; ++offset)
            destinations->buffers[index].bytes[offset] = 0;
    }

    for (index = 0; index < 24; ++index)
        result->registers.r[index] = input->r[index];
    result->registers.r[0] = 0;
    result->registers.r[1] = 0;
    result->registers.r[2] = 0;
    result->registers.r[3] = UINT32_C(0x0EF2A858);
    result->registers.r[4] = 0;
    result->registers.r[5] = UINT32_C(0x0EDD7870);
    result->registers.gp = input->gp;
    result->registers.sp = input->sp;
    result->registers.lr = UINT32_C(0x0EC3D77A);
    result->registers.r27 = input->r27;
    result->registers.r28 = input->r28;
    result->registers.r29 = input->r29;
    result->registers.sr = (input->sr & UINT32_C(0xFFFFFFF0)) | UINT32_C(6);
    result->pc = input->lr;
    return STARTUP_INITIALIZATION_OK;
}
