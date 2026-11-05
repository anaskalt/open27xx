/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "mask_operations.h"

struct view_alignment { char prefix; struct mask_byte_view value; };
struct pair_alignment { char prefix; struct mask_word_pair value; };
struct word_alignment { char prefix; uint32_t value; };

#define ALIGNMENT(name) offsetof(struct name##_alignment, value)

struct span {
    const void *pointer;
    size_t length;
    size_t alignment;
};

static enum mask_status validate_spans(const struct span *spans, size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        uintptr_t address = (uintptr_t)spans[left].pointer;
        if ((spans[left].pointer == NULL && spans[left].length != 0)
                || address % spans[left].alignment != 0)
            return MASK_INVALID;
        if (spans[left].length > UINTPTR_MAX - address)
            return MASK_BOUNDS;
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
                return MASK_OVERLAP;
        }
    }
    return MASK_OK;
}

static struct mask_word_pair shifted_pair(uint32_t low, uint32_t high,
                                          uint32_t count) {
    struct mask_word_pair result;
    uint32_t upper_count = (uint32_t)(count - UINT32_C(32));
    if (upper_count < UINT32_C(0x80000000)) {
        result.low = 0;
        result.high = (uint32_t)(low << (upper_count & UINT32_C(31)));
    } else if (count == 0) {
        result.low = low;
        result.high = high;
    } else {
        uint32_t left_count = count & UINT32_C(31);
        uint32_t right_count = (uint32_t)(UINT32_C(32) - count) & UINT32_C(31);
        result.low = (uint32_t)(low << left_count);
        result.high = (uint32_t)(high << left_count) | (low >> right_count);
    }
    return result;
}

/* Volatile byte access preserves reads of the unselected mask half. */
static uint32_t read_word(const volatile uint8_t *bytes) {
    uint32_t word = bytes[0];
    word |= (uint32_t)bytes[1] << 8;
    word |= (uint32_t)bytes[2] << 16;
    word |= (uint32_t)bytes[3] << 24;
    return word;
}

enum mask_status mask_predicate(uint32_t code,
    const struct mask_byte_view *masks, uint32_t *raw_result) {
    struct span spans[] = {
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)},
        {masks, masks == NULL ? 0 : sizeof(*masks), ALIGNMENT(view)},
        {NULL, 0, 1}};
    enum mask_status status = validate_spans(spans, 2);
    int in_range = code >= UINT32_C(0x40) && code < UINT32_C(0x80);
    uint32_t raw = 0;
    if (status != MASK_OK)
        return status;
    if (masks == NULL) {
        if (in_range)
            return MASK_INVALID;
    } else {
        if (masks->length != (uint32_t)masks->length)
            return MASK_BOUNDS;
        spans[2].pointer = masks->bytes;
        spans[2].length = masks->length;
        status = validate_spans(spans, 3);
        if (status != MASK_OK)
            return status;
        if (in_range && masks->length < 8)
            return MASK_BOUNDS;
    }
    if (in_range) {
        struct mask_word_pair selected = shifted_pair(1, 0, code - UINT32_C(0x40));
        uint32_t high = read_word(masks->bytes + 4);
        uint32_t low = read_word(masks->bytes);
        raw = ((high & selected.high) | (low & selected.low)) != 0;
    }
    *raw_result = raw;
    return MASK_OK;
}

enum mask_status mask_shift(uint32_t low, uint32_t high, uint32_t count,
    struct mask_word_pair *result) {
    const struct span span = {result, sizeof(*result), ALIGNMENT(pair)};
    enum mask_status status = validate_spans(&span, 1);
    struct mask_word_pair computed;
    if (status != MASK_OK)
        return status;
    computed = shifted_pair(low, high, count);
    *result = computed;
    return MASK_OK;
}
