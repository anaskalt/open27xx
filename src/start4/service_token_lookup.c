/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "service_token_lookup.h"

#include <stddef.h>

struct input_alignment { char prefix; struct service_token_lookup_registers value; };
struct result_alignment { char prefix; struct service_token_lookup_result value; };

#define ALIGNMENT(name) offsetof(struct name##_alignment, value)

static const uint32_t tokens[] = {
    UINT32_C(0xCEC00D82), UINT32_C(0xCEC00432), UINT32_C(0xCEC0043E),
    UINT32_C(0xCEC00460), UINT32_C(0xCEC004AE), UINT32_C(0xCEC0053A),
    UINT32_C(0xCEC005A6), UINT32_C(0xCEC00680), UINT32_C(0xCEC00694),
    UINT32_C(0xCEC006A6), UINT32_C(0xCEC006D0), UINT32_C(0xCEC006DE),
    UINT32_C(0xCEC006F6), UINT32_C(0xCEC00766), UINT32_C(0xCEC0077E),
    UINT32_C(0xCEC0079E), UINT32_C(0xCEC007B4), UINT32_C(0xCEC007B8),
    UINT32_C(0xCEC007C4), UINT32_C(0xCEC00860), UINT32_C(0xCEC0088E),
    UINT32_C(0xCEC0090C), UINT32_C(0xCEC00996), UINT32_C(0xCEC009C2),
    UINT32_C(0xCEC00A4A), UINT32_C(0xCEC00A68), UINT32_C(0xCEC00E16),
    UINT32_C(0xCEC00E40), UINT32_C(0xCEC011A8), UINT32_C(0xCEC011BE),
    UINT32_C(0xCEC011CA), UINT32_C(0xCEC011E0), UINT32_C(0xCEC01444),
    UINT32_C(0xCEC01560), UINT32_C(0xCEC016E4), UINT32_C(0xCEC01700),
    UINT32_C(0xCEC01714), UINT32_C(0xCEC01918), UINT32_C(0xCEC01954),
    UINT32_C(0xCEC019EC), UINT32_C(0xCEC01A74), UINT32_C(0xCEC01B20)
};

static enum service_token_lookup_status validate(
    const struct service_token_lookup_registers *input,
    struct service_token_lookup_result *result) {
    uintptr_t a = (uintptr_t)input, b = (uintptr_t)result;
    if (input == NULL || result == NULL
            || a % ALIGNMENT(input) != 0 || b % ALIGNMENT(result) != 0)
        return SERVICE_TOKEN_LOOKUP_INVALID;
    if (sizeof(*input) > UINTPTR_MAX - a || sizeof(*result) > UINTPTR_MAX - b)
        return SERVICE_TOKEN_LOOKUP_BOUNDS;
    if (a < b ? b - a < sizeof(*input) : a - b < sizeof(*result))
        return SERVICE_TOKEN_LOOKUP_OVERLAP;
    if ((input->lr & UINT32_C(1)) != 0)
        return SERVICE_TOKEN_LOOKUP_INVALID;
    if ((input->lr >= UINT32_C(0xCEC00D82)
            && input->lr < UINT32_C(0xCEC00DA0))
            || (input->lr >= UINT32_C(0xCEC01B60)
                && input->lr < UINT32_C(0xCEC01C08)))
        return SERVICE_TOKEN_LOOKUP_OVERLAP;
    return SERVICE_TOKEN_LOOKUP_OK;
}

enum service_token_lookup_status service_token_lookup(
    const struct service_token_lookup_registers *input,
    struct service_token_lookup_result *result) {
    enum service_token_lookup_status status = validate(input, result);
    uint32_t raw = UINT32_MAX, reads = 42, instructions = 132;
    size_t index;
    if (status != SERVICE_TOKEN_LOOKUP_OK)
        return status;
    for (index = 0; index < sizeof(tokens) / sizeof(tokens[0]); ++index) {
        if (tokens[index] == input->r[0]) {
            raw = (uint32_t)index;
            reads = raw + 1;
            instructions = 7 + 3 * raw;
            break;
        }
    }
    for (index = 5; index < 24; ++index)
        result->registers.r[index] = input->r[index];
    result->registers.r[0] = raw;
    result->registers.r[1] = UINT32_C(0xCEC01B60) + 4 * reads;
    result->registers.r[2] = 42;
    result->registers.r[3] = raw;
    result->registers.r[4] = tokens[reads - 1];
    result->registers.gp = input->gp;
    result->registers.sp = input->sp;
    result->registers.lr = input->lr;
    result->registers.r27 = input->r27;
    result->registers.r28 = input->r28;
    result->registers.r29 = input->r29;
    result->registers.sr = input->sr;
    result->pc = input->lr;
    result->instructions = instructions;
    result->table_reads = reads;
    return SERVICE_TOKEN_LOOKUP_OK;
}
