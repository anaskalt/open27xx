/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "boot_info.h"

struct record_type {
    uint32_t tag;
    size_t capacity;
};

static const struct record_type record_types[BOOT_INFO_CACHE_COUNT] = {
    {UINT32_C(0x4E4F4342), 16},
    {UINT32_C(0x45535047), 16},
    {UINT32_C(0x434D4D42), 16},
    {UINT32_C(0x4D545342), 88},
    {UINT32_C(0x4E545342), 200},
    {UINT32_C(0x36565049), 48},
    {UINT32_C(0x454D564E), 20},
    {UINT32_C(0x52575042), 152},
    {UINT32_C(0x4B534452), 36},
    {UINT32_C(0x43545242), 28},
    {UINT32_C(0x52445342), 24},
    {UINT32_C(0x43455342), 76},
    {UINT32_C(0x53545342), 24},
    {UINT32_C(0x42535542), 80},
    {UINT32_C(0x52455642), 164}
};

static uint32_t read_le32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8)
        | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static size_t record_index(uint32_t tag) {
    size_t index;
    for (index = 0; index < BOOT_INFO_CACHE_COUNT; ++index)
        if (record_types[index].tag == tag)
            break;
    return index;
}

static int span_valid(const void *data, size_t length) {
    return length <= UINTPTR_MAX - (uintptr_t)data;
}

static int overlaps(const void *left, size_t left_length,
                    const void *right, size_t right_length) {
    uintptr_t a = (uintptr_t)left, b = (uintptr_t)right;
    if (left_length == 0 || right_length == 0)
        return 0;
    return a < b ? b - a < left_length : a - b < right_length;
}

static enum boot_info_status validate_allocation(
    const struct boot_info_state *state, const uint8_t *source, size_t length,
    struct boot_info_buffer buffer, size_t capacity) {
    size_t index;
    if (buffer.data == NULL)
        return BOOT_INFO_ALLOCATION;
    if (buffer.length < capacity)
        return BOOT_INFO_BOUNDS;
    if (!span_valid(buffer.data, buffer.length))
        return BOOT_INFO_OVERFLOW;
    if (overlaps(buffer.data, buffer.length, source, length)
            || overlaps(buffer.data, buffer.length, state, sizeof(*state)))
        return BOOT_INFO_OVERLAP;
    for (index = 0; index < BOOT_INFO_CACHE_COUNT; ++index)
        if (state->cache[index].data != NULL
                && overlaps(buffer.data, buffer.length,
                            state->cache[index].data, state->cache[index].length))
            return BOOT_INFO_OVERLAP;
    return BOOT_INFO_OK;
}

enum boot_info_status boot_info_parse(
    struct boot_info_state *state, const uint8_t *source, size_t length,
    boot_info_allocate_fn allocate, void *context) {
    size_t position = 0;
    uint32_t total;
    if (state == NULL)
        return BOOT_INFO_INVALID;
    if (source == NULL || state->complete != 0)
        return BOOT_INFO_OK;
    if (!span_valid(source, length))
        return BOOT_INFO_OVERFLOW;
    if (overlaps(source, length, state, sizeof(*state)))
        return BOOT_INFO_OVERLAP;
    if (length < 4)
        return BOOT_INFO_BOUNDS;
    if (read_le32(source) != UINT32_C(0x45545342)) {
        state->complete = 1;
        return BOOT_INFO_OK;
    }
    if (length < 8)
        return BOOT_INFO_BOUNDS;
    total = read_le32(source + 4);
    if (total > 32768)
        return BOOT_INFO_OK;
    while (position < total) {
        uint32_t next;
        size_t index;
        if (position > length || length - position < 12)
            return BOOT_INFO_BOUNDS;
        next = read_le32(source + position + 8);
        index = record_index(read_le32(source + position));
        if (index < BOOT_INFO_CACHE_COUNT && state->cache[index].data == NULL) {
            struct boot_info_buffer buffer = {NULL, 0};
            size_t copied = read_le32(source + position + 4);
            size_t capacity = record_types[index].capacity;
            size_t byte;
            enum boot_info_status status;
            if (copied > capacity)
                copied = capacity;
            if (copied > length - position)
                return BOOT_INFO_BOUNDS;
            if (allocate == NULL)
                return BOOT_INFO_ALLOCATION;
            status = allocate(context, 1, capacity, &buffer);
            if (status != BOOT_INFO_OK)
                return status;
            status = validate_allocation(state, source, length, buffer, capacity);
            if (status != BOOT_INFO_OK)
                return status;
            for (byte = 0; byte < copied; ++byte)
                buffer.data[byte] = source[position + byte];
            buffer.length = capacity;
            state->cache[index] = buffer;
        }
        if (next == 0)
            break;
        /* Positive offsets and checked addition make every walk finite. */
        if (next > SIZE_MAX - position)
            return BOOT_INFO_OVERFLOW;
        position += next;
    }
    state->complete = 1;
    return BOOT_INFO_OK;
}

enum boot_info_status boot_info_lookup(
    struct boot_info_state *state, const uint8_t *source, size_t length,
    boot_info_allocate_fn allocate, void *context, uint32_t tag,
    struct boot_info_buffer *result) {
    enum boot_info_status status;
    size_t index;
    if (result == NULL)
        return BOOT_INFO_INVALID;
    if (state != NULL && overlaps(result, sizeof(*result), state, sizeof(*state)))
        return BOOT_INFO_OVERLAP;
    result->data = NULL;
    result->length = 0;
    status = boot_info_parse(state, source, length, allocate, context);
    if (status != BOOT_INFO_OK)
        return status;
    index = record_index(tag);
    if (state->complete != 0 && index < BOOT_INFO_CACHE_COUNT)
        *result = state->cache[index];
    return BOOT_INFO_OK;
}

enum boot_info_status boot_info_allocate_zeroed(
    void *context, size_t count, size_t item_size,
    struct boot_info_buffer *result) {
    struct boot_info_zero_allocator *allocator = context;
    struct boot_info_buffer buffer = {NULL, 0};
    enum boot_info_status status;
    size_t length, byte;
    if (result == NULL)
        return BOOT_INFO_INVALID;
    result->data = NULL;
    result->length = 0;
    if (allocator == NULL || allocator->allocate == NULL)
        return BOOT_INFO_INVALID;
    if (count != 0 && item_size > SIZE_MAX / count)
        return BOOT_INFO_OVERFLOW;
    length = count * item_size;
    status = allocator->allocate(allocator->context, length, 32, 1,
                                allocator->caller_word | UINT32_C(0x80000000),
                                &buffer);
    if (status != BOOT_INFO_OK)
        return status;
    if (buffer.data == NULL)
        return BOOT_INFO_OK;
    if (buffer.length < length)
        return BOOT_INFO_BOUNDS;
    if (!span_valid(buffer.data, buffer.length))
        return BOOT_INFO_OVERFLOW;
    for (byte = 0; byte < length; ++byte)
        buffer.data[byte] = 0;
    *result = buffer;
    return BOOT_INFO_OK;
}

enum boot_info_status boot_info_prepare_pointer(uint8_t *section, size_t length) {
    if (section == NULL)
        return BOOT_INFO_OK;
    if (!span_valid(section, length))
        return BOOT_INFO_OVERFLOW;
    if (length < 8)
        return BOOT_INFO_BOUNDS;
    if (read_le32(section) == UINT32_C(0x41545342)) {
        section[4] = 0;
        section[5] = 0;
        section[6] = 4;
        section[7] = 0;
    }
    return BOOT_INFO_OK;
}

uint32_t boot_info_fallback_revision(uint32_t present, uint32_t word) {
    if (present == 0)
        return UINT32_C(0x00A03110);
    switch (word & UINT32_C(0x06)) {
    case 2:
        return UINT32_C(0x00A03114);
    case 4:
        return UINT32_C(0x00C031C0);
    case 6:
        return UINT32_C(0x00A03115);
    default:
        return UINT32_C(0x00A03110);
    }
}
