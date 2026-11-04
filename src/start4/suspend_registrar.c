/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "suspend_registrar.h"

struct inputs_alignment { char prefix; struct suspend_registration_inputs value; };
struct buffer_alignment { char prefix; struct suspend_buffer value; };
struct view_alignment { char prefix; struct suspend_byte_view value; };
struct plan_alignment { char prefix; struct suspend_p16_read_plan value; };
struct observers_alignment { char prefix; struct suspend_registration_observers value; };
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

enum suspend_status suspend_register(
    const struct suspend_registration_inputs *inputs,
    const struct suspend_buffer *object, const struct suspend_byte_view *name,
    const uint8_t *logging, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result) {
    struct span spans[] = {
        {inputs, sizeof(*inputs), ALIGNMENT(inputs)},
        {object, sizeof(*object), ALIGNMENT(buffer)},
        {name, name != NULL ? sizeof(*name) : 0, ALIGNMENT(view)},
        {logging, logging != NULL ? sizeof(*logging) : 0, 1},
        {reads, sizeof(*reads), ALIGNMENT(plan)},
        {observers, sizeof(*observers), ALIGNMENT(observers)},
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)},
        {NULL, 0, 1}, {NULL, 0, 1}, {NULL, 0, ALIGNMENT(word)}};
    struct suspend_lookup_inputs lookup;
    struct suspend_byte_view records, basename = {NULL, 0};
    struct suspend_buffer destination = {NULL, 0};
    struct suspend_copy_inputs copy = {22, 0};
    enum suspend_status status = validate_spans(spans, 7);
    uint32_t count, found, length, start, raw = UINT32_MAX, copied;
    size_t index;
    int insert = 0;
    if (status != SUSPEND_OK)
        return status;
    if (object->bytes == NULL || reads->words == NULL)
        return SUSPEND_INVALID;
    if (object->length < SUSPEND_OBJECT_BYTES || object->length > UINT32_MAX
            || (name != NULL && name->length > UINT32_MAX)
            || reads->count == 0 || reads->count > UINT32_MAX / sizeof(*reads->words))
        return SUSPEND_BOUNDS;
    spans[7].pointer = object->bytes;
    spans[7].length = object->length;
    if (name != NULL) {
        spans[8].pointer = name->bytes;
        spans[8].length = name->length;
    }
    spans[9].pointer = reads->words;
    spans[9].length = reads->count * sizeof(*reads->words);
    status = validate_spans(spans, 10);
    if (status != SUSPEND_OK)
        return status;
    if (observers->di == NULL || observers->read == NULL || observers->write == NULL)
        return SUSPEND_INVALID;
    for (index = 0; index < reads->count; ++index)
        if (reads->words[index] != (index + 1 == reads->count ? 0u : 1u))
            return SUSPEND_INVALID;
    count = read_word(object->bytes + 0xB5C);
    if (count > INT32_MAX)
        return SUSPEND_BOUNDS;
    if (count < 40) {
        if (logging == NULL || *logging >= 4)
            return SUSPEND_INVALID;
        lookup.count = (int32_t)count;
        lookup.first = inputs->first;
        lookup.second = inputs->callback;
        lookup.third = inputs->cookie;
        records.bytes = object->bytes + 0x1C;
        records.length = (size_t)count * SUSPEND_RECORD_BYTES;
        status = suspend_lookup(&lookup, &records, &found);
        if (status != SUSPEND_OK)
            return status;
        raw = found != UINT32_MAX ? 0u : 1u;
        insert = found == UINT32_MAX && inputs->callback != 0;
        if (insert) {
            if (name == NULL)
                return SUSPEND_INVALID;
            status = suspend_length(name, &length);
            if (status != SUSPEND_OK)
                return status;
            start = length;
            while (start > 0 && name->bytes[start - 1] != '/'
                    && name->bytes[start - 1] != '\\')
                --start;
            basename.bytes = name->bytes + start;
            basename.length = name->length - start;
            destination.bytes = object->bytes + 0x28 + (size_t)count * SUSPEND_RECORD_BYTES;
            destination.length = 22;
            raw = 0;
        }
    }

    observers->di(observers->context, inputs->sr, inputs->sr & ~UINT32_C(0x40000000));
    for (index = 0; index < reads->count; ++index)
        observers->read(observers->context, reads->words[index]);
    write_word(object->bytes, inputs->sr);
    if (insert) {
        uint8_t *record = object->bytes + 0x1C + (size_t)count * SUSPEND_RECORD_BYTES;
        /* Preflight establishes the complete nested copy domain before DI. */
        (void)suspend_copy(&copy, &destination, &basename, &copied);
        record[0] = (uint8_t)inputs->first;
        write_word(record + 4, inputs->callback);
        write_word(record + 8, inputs->cookie);
        write_word(object->bytes + 0xB5C, count + 1);
        write_word(object->bytes + 0xB74, 0);
    }
    observers->write(observers->context, read_word(object->bytes));
    *raw_result = raw;
    return SUSPEND_OK;
}
