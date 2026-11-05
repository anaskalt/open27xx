/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "soc_initialization.h"

struct input_alignment { char prefix; struct soc_initialization_registers value; };
struct observations_alignment { char prefix; struct soc_initialization_observations value; };
struct memory_alignment { char prefix; struct soc_initialization_memory value; };
struct stack_alignment { char prefix; struct soc_initialization_stack value; };
struct result_alignment { char prefix; struct soc_initialization_result value; };

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

static const struct region ordinary[SOC_INITIALIZATION_REGIONS] = {
    {UINT32_C(0x1560), 16},
    {UINT32_C(0x16E0), 16},
    {UINT32_C(0x3B890), 12},
    {UINT32_C(0x3B8AC), 8},
    {UINT32_C(0x3B920), 20},
    {UINT32_C(0xCCDB4), 12},
    {UINT32_C(0x3B480), 12}};

static enum soc_initialization_status validate_spans(
    const struct span *spans, size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        uintptr_t address = (uintptr_t)spans[left].pointer;
        if (spans[left].pointer == NULL || address % spans[left].alignment != 0)
            return SOC_INITIALIZATION_INVALID;
        if (spans[left].length > UINTPTR_MAX - address)
            return SOC_INITIALIZATION_BOUNDS;
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
                return SOC_INITIALIZATION_OVERLAP;
        }
    }
    return SOC_INITIALIZATION_OK;
}

static int intersects(uint32_t a, uint32_t a_length,
                      uint32_t b, uint32_t b_length) {
    return a < b ? b - a < a_length : a - b < b_length;
}

static enum soc_initialization_status validate_addresses(
    const struct soc_initialization_registers *input,
    const struct soc_initialization_stack *stack) {
    static const struct region excluded[] = {
        {UINT32_C(0x0EC6221C), 342},
        {UINT32_C(0x7E0000B4), 4}};
    struct region regions[SOC_INITIALIZATION_REGIONS + 1];
    uint32_t length = (uint32_t)stack->length;
    uint32_t frame;
    size_t left, right;
    if ((input->gp & UINT32_C(3)) != 0
            || input->sp < 24 || (input->sp & UINT32_C(3)) != 0
            || (input->lr & UINT32_C(1)) != 0)
        return SOC_INITIALIZATION_INVALID;
    if (length < 24 || length - 1 > UINT32_MAX - stack->address)
        return SOC_INITIALIZATION_BOUNDS;
    frame = input->sp - 24;
    if (frame < stack->address || frame - stack->address > length - 24)
        return SOC_INITIALIZATION_BOUNDS;
    for (left = 0; left < SOC_INITIALIZATION_REGIONS; ++left) {
        if (ordinary[left].address > UINT32_MAX - input->gp)
            return SOC_INITIALIZATION_BOUNDS;
        regions[left].address = input->gp + ordinary[left].address;
        regions[left].length = ordinary[left].length;
        if (regions[left].length - 1 > UINT32_MAX - regions[left].address)
            return SOC_INITIALIZATION_BOUNDS;
    }
    regions[SOC_INITIALIZATION_REGIONS].address = stack->address;
    regions[SOC_INITIALIZATION_REGIONS].length = length;
    for (left = 0; left < SOC_INITIALIZATION_REGIONS + 1; ++left) {
        if (intersects(regions[left].address, regions[left].length, input->lr, 1))
            return SOC_INITIALIZATION_OVERLAP;
        for (right = left + 1; right < SOC_INITIALIZATION_REGIONS + 1; ++right) {
            if (intersects(regions[left].address, regions[left].length,
                           regions[right].address, regions[right].length))
                return SOC_INITIALIZATION_OVERLAP;
        }
        for (right = 0; right < sizeof(excluded) / sizeof(excluded[0]); ++right) {
            if (intersects(regions[left].address, regions[left].length,
                           excluded[right].address, excluded[right].length))
                return SOC_INITIALIZATION_OVERLAP;
        }
    }
    for (right = 0; right < sizeof(excluded) / sizeof(excluded[0]); ++right) {
        if (intersects(input->lr, 1, excluded[right].address, excluded[right].length))
            return SOC_INITIALIZATION_OVERLAP;
    }
    return SOC_INITIALIZATION_OK;
}

static unsigned selected_flags(uint32_t version) {
    switch (version) {
    case UINT32_C(0x04000160):
    case UINT32_C(0x04000161):
        return 1;
    case UINT32_C(0x04000162):
        return 2;
    case UINT32_C(0x04000170):
    case UINT32_C(0x04000180):
    case UINT32_C(0x04000181):
    case UINT32_C(0x04000182):
    case UINT32_C(0x04000183):
        return 3;
    case UINT32_C(0x04000184):
        return 4;
    default:
        return 0;
    }
}

static uint32_t read_word(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8)
        | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static void write_word(uint8_t *bytes, uint32_t word) {
    bytes[0] = (uint8_t)word;
    bytes[1] = (uint8_t)(word >> 8);
    bytes[2] = (uint8_t)(word >> 16);
    bytes[3] = (uint8_t)(word >> 24);
}

enum soc_initialization_status soc_initialization_run(
    const struct soc_initialization_registers *input,
    const struct soc_initialization_observations *observations,
    const struct soc_initialization_memory *memory,
    const struct soc_initialization_stack *stack,
    struct soc_initialization_result *result) {
    struct span spans[] = {
        {input, sizeof(*input), ALIGNMENT(input)},
        {observations, sizeof(*observations), ALIGNMENT(observations)},
        {memory, sizeof(*memory), ALIGNMENT(memory)},
        {stack, sizeof(*stack), ALIGNMENT(stack)},
        {result, sizeof(*result), ALIGNMENT(result)},
        {NULL, 0, 1}, {NULL, 0, 1}, {NULL, 0, 1}, {NULL, 0, 1},
        {NULL, 0, 1}, {NULL, 0, 1}, {NULL, 0, 1}, {NULL, 0, 1}};
    enum soc_initialization_status status = validate_spans(spans, 5);
    unsigned flags;
    uint32_t diagnostic, tested_bit, control = 0, frame_offset;
    size_t index;
    if (status != SOC_INITIALIZATION_OK)
        return status;
    if (stack->length != (uint32_t)stack->length)
        return SOC_INITIALIZATION_BOUNDS;
    for (index = 0; index < SOC_INITIALIZATION_REGIONS; ++index) {
        if (memory->buffers[index].length != ordinary[index].length)
            return SOC_INITIALIZATION_BOUNDS;
        spans[5 + index].pointer = memory->buffers[index].bytes;
        spans[5 + index].length = memory->buffers[index].length;
    }
    spans[12].pointer = stack->bytes;
    spans[12].length = stack->length;
    status = validate_spans(spans, 13);
    if (status != SOC_INITIALIZATION_OK)
        return status;
    status = validate_addresses(input, stack);
    if (status != SOC_INITIALIZATION_OK)
        return status;
    flags = selected_flags(observations->version1);
    if (observations->kind != (flags != 0 ? SOC_INITIALIZATION_MMIO
                                         : SOC_INITIALIZATION_VERSION2))
        return SOC_INITIALIZATION_INVALID;
    diagnostic = memory->buffers[SOC_INITIALIZATION_DIAGNOSTIC].bytes[4];
    if (diagnostic > 3)
        return SOC_INITIALIZATION_UNSUPPORTED;

    frame_offset = input->sp - 24 - stack->address;
    write_word(stack->bytes + frame_offset + 20, input->lr);
    for (index = 0; index < 5; ++index)
        write_word(stack->bytes + frame_offset + 16 - 4 * index, input->r[6 + index]);
    if (flags != 0) {
        for (index = flags; index > 0; --index) {
            size_t flag = index - 1;
            write_word(memory->buffers[flag / 2].bytes + 4 + 4 * (flag % 2), 1);
        }
        tested_bit = observations->word & UINT32_C(1);
        memory->buffers[SOC_INITIALIZATION_CLASSIFICATION].bytes[2] = 3;
        control = read_word(memory->buffers[SOC_INITIALIZATION_CONTROL_MODE].bytes + 4)
            | (tested_bit != 0 ? UINT32_C(0x07000000) : UINT32_C(0x05000000));
        write_word(memory->buffers[SOC_INITIALIZATION_CONTROL_MODE].bytes + 4, control);
        write_word(memory->buffers[SOC_INITIALIZATION_CONTROL_MODE].bytes + 12,
                   UINT32_C(0x37F5));
    } else {
        tested_bit = (observations->word >> 6) & UINT32_C(1);
        memory->buffers[SOC_INITIALIZATION_CLASSIFICATION].bytes[2] = (uint8_t)tested_bit;
        write_word(memory->buffers[SOC_INITIALIZATION_CONTROL_MODE].bytes + 12,
                   UINT32_C(0x7FF5));
    }
    write_word(memory->buffers[SOC_INITIALIZATION_COMPLETION].bytes + 4, 1);

    for (index = 0; index < 24; ++index)
        result->registers.r[index] = input->r[index];
    result->registers.r[4] = observations->version1 - UINT32_C(0x04000160);
    if (flags != 0) {
        result->registers.r[1] = observations->word;
        result->registers.r[2] = diagnostic;
        result->registers.r[3] = UINT32_C(0x7E000080);
        if (tested_bit != 0) {
            result->registers.r[0] = control;
            result->registers.r[4] = diagnostic;
        }
    } else {
        result->registers.r[1] = tested_bit;
        result->registers.r[2] = observations->word;
        result->registers.r[5] = diagnostic;
    }
    result->registers.gp = input->gp;
    result->registers.sp = input->sp;
    result->registers.lr = input->lr;
    result->registers.r27 = input->r27;
    result->registers.r28 = input->r28;
    result->registers.r29 = input->r29;
    result->registers.sr = (input->sr & UINT32_C(0xFFFFFFF0))
        | (tested_bit == 0 ? UINT32_C(0xA) : 0);
    result->pc = input->lr;
    return SOC_INITIALIZATION_OK;
}
