/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "arm_first_open.h"

struct span {
    const void *pointer;
    size_t length;
};

static enum arm_first_open_status validate_spans(const struct span *spans,
                                                size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        if (spans[left].pointer == NULL && spans[left].length != 0)
            return ARM_FIRST_OPEN_INVALID;
        if (spans[left].length > UINTPTR_MAX - (uintptr_t)spans[left].pointer)
            return ARM_FIRST_OPEN_BOUNDS;
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
                return ARM_FIRST_OPEN_OVERLAP;
        }
    }
    return ARM_FIRST_OPEN_OK;
}

enum arm_first_open_status arm_callback_register(
    uint32_t code, uint32_t new_callback, uint32_t *selected_callback,
    uint32_t *old_callback, uint32_t *raw_result) {
    struct span spans[] = {{selected_callback, sizeof(*selected_callback)},
        {old_callback, sizeof(*old_callback)}, {raw_result, sizeof(*raw_result)}};
    enum arm_first_open_status status = validate_spans(spans, 3);
    uint32_t selected, raw;
    if (status != ARM_FIRST_OPEN_OK)
        return status;
    if (code != UINT32_C(0x5E) || new_callback != UINT32_C(0x0EC5716E)
            || *old_callback != UINT32_C(0xA5A5A5A5)
            || (*selected_callback != 0
                && *selected_callback != UINT32_C(0x0EC3EA48)
                && *selected_callback != UINT32_C(0x11223344)))
        return ARM_FIRST_OPEN_UNSUPPORTED;

    *old_callback = 0;
    selected = *selected_callback;
    if (selected == 0) {
        raw = UINT32_MAX;
    } else {
        if (selected != UINT32_C(0x0EC3EA48))
            *old_callback = selected;
        *selected_callback = new_callback;
        raw = 0;
    }
    *raw_result = raw;
    return ARM_FIRST_OPEN_OK;
}

enum arm_first_open_status arm_first_open_execute(
    const struct arm_first_open_inputs *inputs,
    struct arm_first_open_state *state, uint8_t *records, size_t records_length,
    const uint32_t *cpu_word, const uint32_t *secondary_word,
    const uint32_t *service_index, uint32_t *handle_output,
    const struct arm_first_open_reply_plan *replies,
    const struct arm_first_open_read_plan *reads,
    const struct arm_first_open_observers *observers, uint32_t *raw_result) {
    struct span spans[13] = {{inputs, sizeof(*inputs)}, {state, sizeof(*state)},
        {records, records_length}, {cpu_word, sizeof(*cpu_word)},
        {secondary_word, secondary_word != NULL ? sizeof(*secondary_word) : 0},
        {service_index, service_index != NULL ? sizeof(*service_index) : 0},
        {handle_output, sizeof(*handle_output)}, {replies, sizeof(*replies)},
        {reads, sizeof(*reads)}, {observers, sizeof(*observers)},
        {raw_result, sizeof(*raw_result)}, {NULL, 0}, {NULL, 0}};
    enum arm_first_open_status status = validate_spans(spans, 11);
    struct arm_object_plan registrar;
    const struct arm_first_open_read *read;
    uint32_t cpu, nested_raw, arguments[6] = {UINT32_C(0xE403B470), 0, 0, 0, 0, 0};
    size_t index, required;
    int service;
    if (status != ARM_FIRST_OPEN_OK)
        return status;
    if (records == NULL || replies->words == NULL || reads->entries == NULL)
        return ARM_FIRST_OPEN_INVALID;
    if (replies->count > SIZE_MAX / sizeof(*replies->words)
            || reads->count > SIZE_MAX / sizeof(*reads->entries))
        return ARM_FIRST_OPEN_BOUNDS;
    spans[11].pointer = replies->words;
    spans[11].length = replies->count * sizeof(*replies->words);
    spans[12].pointer = reads->entries;
    spans[12].length = reads->count * sizeof(*reads->entries);
    status = validate_spans(spans, 13);
    if (status != ARM_FIRST_OPEN_OK)
        return status;
    if (records_length < ARM_OBJECT_RECORD_BYTES || reads->count < 1)
        return ARM_FIRST_OPEN_BOUNDS;
    if (reads->count > 1)
        return ARM_FIRST_OPEN_UNSUPPORTED;
    if (inputs->parameter_word != UINT32_C(0x400) || inputs->parameter_byte != 2
            || inputs->configuration_source != UINT32_C(0x12345678)
            || state->open_count != 0 || state->object != UINT32_C(0xA5A5A5A5)
            || state->capacity != UINT32_C(0xA5A5A5A5)
            || state->configuration != UINT32_C(0xA5A5A5A5)
            || state->selected_callback != 0
            || state->old_callback != UINT32_C(0xA5A5A5A5)
            || *handle_output != UINT32_C(0xA5A5A5A5))
        return ARM_FIRST_OPEN_UNSUPPORTED;
    for (index = 0; index < ARM_OBJECT_RECORD_BYTES; ++index)
        if (records[index] != 0)
            return ARM_FIRST_OPEN_UNSUPPORTED;
    cpu = *cpu_word;
    if (cpu != 0 && cpu != UINT32_C(0x40))
        return ARM_FIRST_OPEN_UNSUPPORTED;
    service = cpu == 0;
    if (cpu != 0) {
        if (secondary_word == NULL)
            return ARM_FIRST_OPEN_INVALID;
        if (*secondary_word > 1)
            return ARM_FIRST_OPEN_UNSUPPORTED;
        service = *secondary_word != 0;
    }
    if (service) {
        if (service_index == NULL || observers->service == NULL)
            return ARM_FIRST_OPEN_INVALID;
        if (*service_index != 1)
            return ARM_FIRST_OPEN_UNSUPPORTED;
    }
    required = service ? 5 : 4;
    if (replies->count < required)
        return ARM_FIRST_OPEN_BOUNDS;
    if (replies->count > required)
        return ARM_FIRST_OPEN_UNSUPPORTED;
    for (index = 0; index < required; ++index)
        if (replies->words[index] != 0)
            return ARM_FIRST_OPEN_UNSUPPORTED;
    read = reads->entries;
    if (read->pc != UINT32_C(0x0EC59E12) || read->address != UINT32_C(0x7E00B44C)
            || read->size != 4 || read->word != UINT32_C(0x11223344))
        return ARM_FIRST_OPEN_UNSUPPORTED;
    if (observers->acquire == NULL || observers->registrar_acquire == NULL
            || observers->registrar_diagnostic == NULL || observers->registrar_release == NULL
            || observers->version == NULL || observers->read == NULL)
        return ARM_FIRST_OPEN_INVALID;

    registrar.acquire = observers->registrar_acquire;
    registrar.diagnostic = observers->registrar_diagnostic;
    registrar.release = observers->registrar_release;
    registrar.context = observers->context;
    observers->acquire(observers->context, UINT32_C(0x0ED64D02), arguments, 1, replies->words[0]);
    state->open_count = 1;
    /* Whole-call preflight establishes both nested domains before acquire. */
    (void)arm_object_register(1, records, records_length, &state->object, &registrar, &nested_raw);
    state->capacity = inputs->parameter_word;
    state->configuration = ((inputs->configuration_source & UINT32_C(0xFFFF0FFF))
        & UINT32_C(0xFFF0001C)) | 3u | UINT32_C(0xF000) | UINT32_C(0xC00);
    observers->version(observers->context, UINT32_C(0x0EC59DE0), 4, cpu);
    if (service) {
        arguments[0] = *service_index;
        arguments[1] = (cpu & UINT32_C(0x40)) == 0 ? state->configuration : UINT32_C(0x200);
        observers->service(observers->context, UINT32_C(0x0ED65284), arguments, 6, replies->words[4]);
    }
    observers->read(observers->context, read->pc, read->address, read->size, read->word);
    (void)arm_callback_register(UINT32_C(0x5E), UINT32_C(0x0EC5716E),
        &state->selected_callback, &state->old_callback, &nested_raw);
    *raw_result = nested_raw;
    return ARM_FIRST_OPEN_OK;
}
