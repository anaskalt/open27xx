/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "driver_open_internal.h"

struct inputs_alignment { char prefix; struct driver_open_inputs value; };
struct buffer_alignment { char prefix; struct suspend_buffer value; };
struct view_alignment { char prefix; struct suspend_byte_view value; };
struct word_alignment { char prefix; uint32_t value; };

#define ALIGNMENT(name) offsetof(struct name##_alignment, value)

static uint32_t read_word(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8
        | (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static void write_word(uint8_t *bytes, uint32_t value) {
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
    bytes[2] = (uint8_t)(value >> 16);
    bytes[3] = (uint8_t)(value >> 24);
}

enum suspend_status driver_open_preflight(
    const struct driver_open_inputs *inputs,
    const struct suspend_buffer *masks, const struct suspend_byte_view *source,
    const struct suspend_buffer *object, const struct suspend_byte_view *name,
    const uint8_t *logging, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result,
    struct suspend_registration_prepared *prepared) {
    struct suspend_registration_span spans[] = {
        {inputs, sizeof(*inputs), ALIGNMENT(inputs)},
        {masks, sizeof(*masks), ALIGNMENT(buffer)},
        {source, source != NULL ? sizeof(*source) : 0, ALIGNMENT(view)},
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)},
        {NULL, 0, 1}, {NULL, 0, 1}};
    struct suspend_registration_inputs registration = {1, UINT32_C(0x0ED004C6), 0, 0};
    uint32_t registrar_raw;
    enum suspend_status status = suspend_registration_validate_spans(spans, 4);
    if (status != SUSPEND_OK)
        return status;
    if (masks->bytes == NULL
            || (source != NULL && source->bytes == NULL && source->length != 0))
        return SUSPEND_INVALID;
    if (masks->length < 8 || masks->length > UINT32_MAX
            || (source != NULL && (source->length > UINT32_MAX
                || (source->bytes != NULL && source->length < 8))))
        return SUSPEND_BOUNDS;
    spans[4].pointer = masks->bytes;
    spans[4].length = masks->length;
    if (source != NULL) {
        spans[5].pointer = source->bytes;
        spans[5].length = source->length;
    }
    status = suspend_registration_preflight(&registration, object, name, logging,
        reads, observers, &registrar_raw, spans, sizeof(spans) / sizeof(spans[0]), prepared);
    return status;
}

void driver_open_validated(
    const struct driver_open_inputs *inputs,
    const struct suspend_buffer *masks, const struct suspend_byte_view *source,
    const struct suspend_buffer *object, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result,
    const struct suspend_registration_prepared *prepared) {
    struct suspend_registration_inputs registration = {1, UINT32_C(0x0ED004C6), 0, inputs->sr};
    uint32_t registrar_raw;
    if (source != NULL && source->bytes != NULL) {
        uint32_t high = read_word(source->bytes + 4);
        uint32_t low = read_word(source->bytes);
        write_word(masks->bytes, low);
        write_word(masks->bytes + 4, high);
    }
    suspend_registration_execute_validated(&registration, object, reads, observers,
                                           &registrar_raw, prepared);
    *raw_result = 0;
}

enum suspend_status driver_open_register(
    const struct driver_open_inputs *inputs,
    const struct suspend_buffer *masks, const struct suspend_byte_view *source,
    const struct suspend_buffer *object, const struct suspend_byte_view *name,
    const uint8_t *logging, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result) {
    struct suspend_registration_prepared prepared = {{NULL, 0}, {NULL, 0}, 0, 0, 0};
    enum suspend_status status = driver_open_preflight(inputs, masks, source, object,
        name, logging, reads, observers, raw_result, &prepared);
    if (status != SUSPEND_OK)
        return status;
    driver_open_validated(inputs, masks, source, object, reads, observers, raw_result, &prepared);
    return SUSPEND_OK;
}
