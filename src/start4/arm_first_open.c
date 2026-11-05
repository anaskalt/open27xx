/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "arm_first_open_internal.h"
#include "arm_object_internal.h"

#include <stddef.h>

struct inputs_alignment { char prefix; struct arm_first_open_inputs value; };
struct state_alignment { char prefix; struct arm_first_open_state value; };
struct replies_alignment { char prefix; struct arm_first_open_reply_plan value; };
struct reads_alignment { char prefix; struct arm_first_open_read_plan value; };
struct observers_alignment { char prefix; struct arm_first_open_observers value; };
struct read_alignment { char prefix; struct arm_first_open_read value; };
struct word_alignment { char prefix; uint32_t value; };

#define ALIGNMENT(name) offsetof(struct name##_alignment, value)

struct span {
    const void *pointer;
    size_t length;
    size_t alignment;
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
    for (left = 0; left < count; ++left)
        if ((uintptr_t)spans[left].pointer % spans[left].alignment != 0)
            return ARM_FIRST_OPEN_INVALID;
    return ARM_FIRST_OPEN_OK;
}

static enum arm_first_open_status callback_preflight(
    uint32_t code, uint32_t new_callback, uint32_t *selected_callback,
    uint32_t *old_callback, uint32_t *raw_result) {
    struct span spans[] = {
        {selected_callback, sizeof(*selected_callback), ALIGNMENT(word)},
        {old_callback, sizeof(*old_callback), ALIGNMENT(word)},
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)}};
    enum arm_first_open_status status = validate_spans(spans, 3);
    if (status != ARM_FIRST_OPEN_OK)
        return status;
    if (code != UINT32_C(0x5E) || new_callback != UINT32_C(0x0EC5716E)
            || *old_callback != UINT32_C(0xA5A5A5A5)
            || (*selected_callback != 0
                && *selected_callback != UINT32_C(0x0EC3EA48)
                && *selected_callback != UINT32_C(0x11223344)))
        return ARM_FIRST_OPEN_UNSUPPORTED;

    return ARM_FIRST_OPEN_OK;
}

static void callback_validated(uint32_t new_callback, uint32_t *selected_callback,
                               uint32_t *old_callback, uint32_t *raw_result) {
    uint32_t selected, raw;
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
}

enum arm_first_open_status arm_callback_register(
    uint32_t code, uint32_t new_callback, uint32_t *selected_callback,
    uint32_t *old_callback, uint32_t *raw_result) {
    enum arm_first_open_status status = callback_preflight(
        code, new_callback, selected_callback, old_callback, raw_result);
    if (status != ARM_FIRST_OPEN_OK)
        return status;
    callback_validated(new_callback, selected_callback, old_callback, raw_result);
    return ARM_FIRST_OPEN_OK;
}

enum arm_first_open_status arm_first_open_prefix_preflight(
    const struct arm_first_open_inputs *inputs,
    struct arm_first_open_state *state, uint8_t *records, size_t records_length,
    const struct arm_first_open_reply_plan *replies,
    const struct arm_first_open_read_plan *reads,
    const struct arm_first_open_observers *observers,
    struct arm_first_open_prepared *prepared) {
    static const uint32_t parameters[4] = {0x80, 0x100, 0x200, 0x400};
    static const uint32_t switches[3] = {0, 0x800, 0xC00};
    const struct arm_first_open_read *read;
    enum arm_first_open_status status;
    enum arm_object_status object_status;
    uint32_t nested_raw;
    size_t index;
    for (index = 0; index < 4; ++index)
        if (inputs->parameter_word == parameters[index])
            break;
    if (index == 4 || inputs->parameter_byte > 2 || state->open_count != 0)
        return ARM_FIRST_OPEN_UNSUPPORTED;
    prepared->selector = (uint32_t)index;
    prepared->switch_bits = switches[inputs->parameter_byte];
    if (replies->count < 4 || reads->count < 1)
        return ARM_FIRST_OPEN_BOUNDS;
    if (reads->count > 1)
        return ARM_FIRST_OPEN_UNSUPPORTED;
    for (index = 0; index < 4; ++index)
        if (replies->words[index] != 0)
            return ARM_FIRST_OPEN_UNSUPPORTED;
    read = reads->entries;
    if (read->pc != UINT32_C(0x0EC59E12) || read->address != UINT32_C(0x7E00B44C)
            || read->size != 4)
        return ARM_FIRST_OPEN_UNSUPPORTED;
    if (observers->acquire == NULL || observers->registrar_acquire == NULL
            || observers->registrar_diagnostic == NULL || observers->registrar_release == NULL
            || observers->version == NULL || observers->read == NULL)
        return ARM_FIRST_OPEN_INVALID;
    prepared->object_plan.acquire = observers->registrar_acquire;
    prepared->object_plan.diagnostic = observers->registrar_diagnostic;
    prepared->object_plan.release = observers->registrar_release;
    prepared->object_plan.context = observers->context;
    object_status = arm_object_register_preflight(1, records, records_length,
        &state->object, &prepared->object_plan, &nested_raw, &prepared->object_profile);
    if (object_status != ARM_OBJECT_OK)
        return (enum arm_first_open_status)object_status;
    status = callback_preflight(UINT32_C(0x5E), UINT32_C(0x0EC5716E),
        &state->selected_callback, &state->old_callback, &nested_raw);
    return status;
}

void arm_first_open_prefix_validated(
    const struct arm_first_open_inputs *inputs,
    struct arm_first_open_state *state, uint8_t *records, uint32_t version,
    const uint32_t *service_index, const struct arm_first_open_reply_plan *replies,
    const struct arm_first_open_read_plan *reads,
    const struct arm_first_open_observers *observers,
    const struct arm_first_open_prepared *prepared, uint32_t *raw_result) {
    const struct arm_first_open_read *read = reads->entries;
    uint32_t arguments[6] = {UINT32_C(0xE403B470), 0, 0, 0, 0, 0};
    observers->acquire(observers->context, UINT32_C(0x0ED64D02), arguments, 1, replies->words[0]);
    state->open_count = 1;
    arm_object_register_validated(1, records, &state->object, &prepared->object_plan, raw_result);
    state->capacity = inputs->parameter_word;
    state->configuration = ((inputs->configuration_source & UINT32_C(0xFFFF0FFF))
        & UINT32_C(0xFFF0001C)) | prepared->selector | UINT32_C(0xF000) | prepared->switch_bits;
    observers->version(observers->context, UINT32_C(0x0EC59DE0), 4, version);
    if (service_index != NULL) {
        arguments[0] = *service_index;
        arguments[1] = (version & UINT32_C(0x40)) == 0 ? state->configuration : UINT32_C(0x200);
        observers->service(observers->context, UINT32_C(0x0ED65284), arguments, 6, replies->words[4]);
    }
    observers->read(observers->context, read->pc, read->address, read->size, read->word);
    callback_validated(UINT32_C(0x0EC5716E), &state->selected_callback,
                       &state->old_callback, raw_result);
}

enum arm_first_open_status arm_first_open_execute(
    const struct arm_first_open_inputs *inputs,
    struct arm_first_open_state *state, uint8_t *records, size_t records_length,
    const uint32_t *cpu_word, const uint32_t *secondary_word,
    const uint32_t *service_index, uint32_t *handle_output,
    const struct arm_first_open_reply_plan *replies,
    const struct arm_first_open_read_plan *reads,
    const struct arm_first_open_observers *observers, uint32_t *raw_result) {
    struct span spans[13] = {
        {inputs, sizeof(*inputs), ALIGNMENT(inputs)},
        {state, sizeof(*state), ALIGNMENT(state)},
        {records, records_length, 1}, {cpu_word, sizeof(*cpu_word), ALIGNMENT(word)},
        {secondary_word, secondary_word != NULL ? sizeof(*secondary_word) : 0, ALIGNMENT(word)},
        {service_index, service_index != NULL ? sizeof(*service_index) : 0, ALIGNMENT(word)},
        {handle_output, sizeof(*handle_output), ALIGNMENT(word)},
        {replies, sizeof(*replies), ALIGNMENT(replies)},
        {reads, sizeof(*reads), ALIGNMENT(reads)},
        {observers, sizeof(*observers), ALIGNMENT(observers)},
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)},
        {NULL, 0, ALIGNMENT(word)}, {NULL, 0, ALIGNMENT(read)}};
    enum arm_first_open_status status = validate_spans(spans, 11);
    struct arm_first_open_prepared prepared;
    uint32_t cpu, nested_raw;
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
    status = arm_first_open_prefix_preflight(inputs, state, records, records_length,
        replies, reads, observers, &prepared);
    if (status != ARM_FIRST_OPEN_OK)
        return status;
    if (inputs->parameter_word != UINT32_C(0x400) || inputs->parameter_byte != 2
            || inputs->configuration_source != UINT32_C(0x12345678)
            || state->capacity != UINT32_C(0xA5A5A5A5)
            || state->configuration != UINT32_C(0xA5A5A5A5)
            || state->selected_callback != 0
            || *handle_output != UINT32_C(0xA5A5A5A5) || prepared.object_profile != 0)
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
    if (reads->entries[0].word != UINT32_C(0x11223344))
        return ARM_FIRST_OPEN_UNSUPPORTED;
    arm_first_open_prefix_validated(inputs, state, records, cpu,
        service ? service_index : NULL, replies, reads, observers, &prepared, &nested_raw);
    *raw_result = nested_raw;
    return ARM_FIRST_OPEN_OK;
}
