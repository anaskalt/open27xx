/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "suspend_helpers.h"

struct lookup_alignment { char prefix; struct suspend_lookup_inputs value; };
struct view_alignment { char prefix; struct suspend_byte_view value; };
struct buffer_alignment { char prefix; struct suspend_buffer value; };
struct copy_alignment { char prefix; struct suspend_copy_inputs value; };
struct word_alignment { char prefix; uint32_t value; };

#define ALIGNMENT(name) offsetof(struct name##_alignment, value)

struct span {
    const void *pointer;
    size_t length;
    size_t alignment;
};

static enum suspend_status validate_spans(const struct span *spans,
                                           size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        uintptr_t address = (uintptr_t)spans[left].pointer;
        if ((spans[left].pointer == NULL && spans[left].length != 0)
                || address % spans[left].alignment != 0)
            return SUSPEND_INVALID;
        if (spans[left].length > UINTPTR_MAX - address)
            return SUSPEND_BOUNDS;
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
                return SUSPEND_OVERLAP;
        }
    }
    return SUSPEND_OK;
}

static enum suspend_status bounded_length(const struct suspend_byte_view *source,
                                          uint32_t *length) {
    size_t index;
    if (source->bytes == NULL)
        return SUSPEND_INVALID;
    if (source->length == 0 || source->length > INT32_MAX)
        return SUSPEND_BOUNDS;
    for (index = 0; index < source->length; ++index) {
        if (source->bytes[index] == 0) {
            *length = (uint32_t)index;
            return SUSPEND_OK;
        }
    }
    return SUSPEND_BOUNDS;
}

static uint32_t read_word(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8
        | (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

enum suspend_status suspend_lookup(
    const struct suspend_lookup_inputs *inputs,
    const struct suspend_byte_view *records, uint32_t *raw_result) {
    struct span spans[] = {
        {inputs, sizeof(*inputs), ALIGNMENT(lookup)},
        {records, sizeof(*records), ALIGNMENT(view)},
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)},
        {NULL, 0, 1}};
    enum suspend_status status = validate_spans(spans, 3);
    uint32_t index, raw = UINT32_MAX;
    if (status != SUSPEND_OK)
        return status;
    if (records->length != (uint32_t)records->length)
        return SUSPEND_BOUNDS;
    spans[3].pointer = records->bytes;
    spans[3].length = records->length;
    status = validate_spans(spans, 4);
    if (status != SUSPEND_OK)
        return status;
    if (inputs->count > 0) {
        if ((uint32_t)inputs->count > UINT32_MAX / SUSPEND_RECORD_BYTES
                || (uint32_t)inputs->count > records->length / SUSPEND_RECORD_BYTES)
            return SUSPEND_BOUNDS;
        for (index = 0; index < (uint32_t)inputs->count; ++index) {
            const uint8_t *record = records->bytes + (size_t)index * SUSPEND_RECORD_BYTES;
            if (inputs->first == (uint32_t)record[0]
                    && inputs->second == read_word(record + 4)
                    && inputs->third == read_word(record + 8)) {
                raw = index;
                break;
            }
        }
    }
    *raw_result = raw;
    return SUSPEND_OK;
}

enum suspend_status suspend_length(
    const struct suspend_byte_view *source, uint32_t *length) {
    struct span spans[] = {
        {source, sizeof(*source), ALIGNMENT(view)},
        {length, sizeof(*length), ALIGNMENT(word)}, {NULL, 0, 1}};
    enum suspend_status status = validate_spans(spans, 2);
    uint32_t computed;
    if (status != SUSPEND_OK)
        return status;
    spans[2].pointer = source->bytes;
    spans[2].length = source->length;
    status = validate_spans(spans, 3);
    if (status != SUSPEND_OK)
        return status;
    status = bounded_length(source, &computed);
    if (status != SUSPEND_OK)
        return status;
    *length = computed;
    return SUSPEND_OK;
}

enum suspend_status suspend_copy(
    const struct suspend_copy_inputs *inputs,
    const struct suspend_buffer *destination,
    const struct suspend_byte_view *source, uint32_t *raw_result) {
    struct span spans[] = {
        {inputs, sizeof(*inputs), ALIGNMENT(copy)},
        {destination, sizeof(*destination), ALIGNMENT(buffer)},
        {source, sizeof(*source), ALIGNMENT(view)},
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)},
        {NULL, 0, 1}, {NULL, 0, 1}};
    enum suspend_status status = validate_spans(spans, 4);
    uint32_t length, copied, index;
    if (status != SUSPEND_OK)
        return status;
    if (destination->length != (uint32_t)destination->length
            || destination->length < inputs->capacity)
        return SUSPEND_BOUNDS;
    spans[4].pointer = destination->bytes;
    spans[4].length = destination->length;
    spans[5].pointer = source->bytes;
    spans[5].length = source->length;
    status = validate_spans(spans, 6);
    if (status != SUSPEND_OK)
        return status;
    status = bounded_length(source, &length);
    if (status != SUSPEND_OK)
        return status;
    if (inputs->offset < inputs->capacity) {
        copied = inputs->capacity - inputs->offset - 1;
        if (copied > length)
            copied = length;
        for (index = 0; index < copied; ++index)
            destination->bytes[(size_t)inputs->offset + index] = source->bytes[index];
        destination->bytes[(size_t)inputs->offset + copied] = 0;
    }
    *raw_result = (uint32_t)(length + inputs->offset);
    return SUSPEND_OK;
}
