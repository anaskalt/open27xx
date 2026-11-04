/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "arm_configuration.h"

struct span {
    const void *pointer;
    size_t length;
};

static enum arm_configuration_status validate_spans(const struct span *spans,
                                                     size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        if (spans[left].pointer == NULL && spans[left].length != 0)
            return ARM_CONFIGURATION_INVALID;
        if (spans[left].length > UINTPTR_MAX - (uintptr_t)spans[left].pointer)
            return ARM_CONFIGURATION_BOUNDS;
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
                return ARM_CONFIGURATION_OVERLAP;
        }
    }
    return ARM_CONFIGURATION_OK;
}

enum arm_configuration_status arm_configuration_execute(
    const struct arm_configuration_inputs *inputs, uint32_t *configuration,
    const uint32_t *cpu_word, const uint32_t *service_index,
    const struct arm_configuration_reply_plan *replies,
    const struct arm_configuration_observers *observers, uint32_t *raw_result) {
    struct span spans[8] = {{inputs, sizeof(*inputs)}, {configuration, sizeof(*configuration)},
        {cpu_word, sizeof(*cpu_word)}, {service_index, service_index != NULL ? sizeof(*service_index) : 0},
        {replies, sizeof(*replies)}, {observers, sizeof(*observers)},
        {raw_result, sizeof(*raw_result)}, {NULL, 0}};
    enum arm_configuration_status status = validate_spans(spans, 7);
    uint32_t cpu, arguments[6] = {UINT32_C(0xE403B470), 0, 0, 0, 0, 0};
    size_t index, required;
    if (status != ARM_CONFIGURATION_OK)
        return status;
    if (replies->count > SIZE_MAX / sizeof(*replies->words))
        return ARM_CONFIGURATION_BOUNDS;
    if (replies->words == NULL)
        return ARM_CONFIGURATION_INVALID;
    spans[7].pointer = replies->words;
    spans[7].length = replies->count * sizeof(*replies->words);
    status = validate_spans(spans, 8);
    if (status != ARM_CONFIGURATION_OK)
        return status;
    cpu = *cpu_word;
    if (inputs->handle != ARM_CONFIGURATION_HANDLE || inputs->control != 1
            || *configuration != UINT32_C(0x1230FC1B)
            || (cpu != 0 && cpu != UINT32_C(0x40)))
        return ARM_CONFIGURATION_UNSUPPORTED;
    required = cpu == 0 ? 3 : 2;
    if (replies->count < required)
        return ARM_CONFIGURATION_BOUNDS;
    if (replies->count > required)
        return ARM_CONFIGURATION_UNSUPPORTED;
    for (index = 0; index < required; ++index)
        if (replies->words[index] != (cpu == 0 && index == 1 ? 7u : 0u))
            return ARM_CONFIGURATION_UNSUPPORTED;
    if (cpu == 0) {
        if (service_index == NULL)
            return ARM_CONFIGURATION_INVALID;
        if (*service_index != 1)
            return ARM_CONFIGURATION_UNSUPPORTED;
        if (observers->service == NULL)
            return ARM_CONFIGURATION_INVALID;
    }
    if (observers->acquire == NULL || observers->version == NULL || observers->release == NULL)
        return ARM_CONFIGURATION_INVALID;

    observers->acquire(observers->context, UINT32_C(0x0ED64D02), arguments, 1, replies->words[0]);
    *configuration |= UINT32_C(0x40);
    observers->version(observers->context, UINT32_C(0x0EC59EEE), 2, cpu);
    if ((cpu & UINT32_C(0x40)) == 0) {
        arguments[0] = *service_index;
        arguments[1] = *configuration;
        observers->service(observers->context, UINT32_C(0x0ED65284), arguments, 6, replies->words[1]);
    }
    arguments[0] = UINT32_C(0xE403B470);
    observers->release(observers->context, UINT32_C(0x0ED64D3A), arguments, 1, replies->words[required - 1]);
    *raw_result = 0;
    return ARM_CONFIGURATION_OK;
}
