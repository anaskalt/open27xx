/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "memory_layout.h"

struct memory_tuple {
    uint32_t base_mib;
    uint32_t size_mib;
};

static int valid_extent(const void *pointer, size_t length) {
    return length == 0 || length - 1 <= UINTPTR_MAX - (uintptr_t)pointer;
}

static int overlaps(const void *left, size_t left_length,
                    const void *right, size_t right_length) {
    uintptr_t a = (uintptr_t)left, b = (uintptr_t)right;
    if (left_length == 0 || right_length == 0)
        return 0;
    return a < b ? b - a < left_length : a - b < right_length;
}

static uint32_t minimum(uint32_t left, uint32_t right) {
    return left < right ? left : right;
}

static size_t select_tuples(const struct memory_layout_inputs *inputs,
                            struct memory_tuple tuples[3]) {
    uint32_t total = inputs->total_mib;
    uint32_t first_limit = inputs->control_word == 0 ? 4032 : 4096;
    uint32_t second_threshold = 4096, second_base = 4096;
    uint32_t second_limit = total;
    size_t count = 1;
    if (inputs->record != NULL && (inputs->record->flags & 16u) != 0) {
        if (inputs->record->selector == 24) {
            first_limit = 1536;
            second_threshold = 1536;
            second_base = 2048;
            second_limit = 3072;
        } else if (inputs->record->selector == 48) {
            first_limit = 3072;
            second_threshold = 3072;
            second_limit = 6144;
        }
    }
    tuples[0].base_mib = 0;
    tuples[0].size_mib = inputs->lower_span_bytes >> 20;
    if (total > 1024) {
        tuples[count].base_mib = 1024;
        tuples[count++].size_mib = minimum(total, first_limit) - 1024;
    }
    if (total > second_threshold) {
        tuples[count].base_mib = second_base;
        tuples[count++].size_mib = minimum(total, second_limit) - second_threshold;
    }
    return count;
}

static uint8_t *write_cell(uint8_t *output, uint32_t value) {
    output[0] = (uint8_t)(value >> 24);
    output[1] = (uint8_t)(value >> 16);
    output[2] = (uint8_t)(value >> 8);
    output[3] = (uint8_t)value;
    return output + 4;
}

static uint8_t *write_field(uint8_t *output, uint32_t mib, uint32_t cells) {
    if (cells == 2)
        output = write_cell(output, mib >> 12);
    return write_cell(output, (mib & 4095u) << 20);
}

enum memory_layout_status memory_layout_serialize(
    const struct memory_layout_inputs *inputs,
    uint8_t *output, size_t capacity, size_t *written) {
    struct memory_tuple tuples[3];
    const struct memory_layout_record *record;
    size_t index, count, stride, required = 0;
    uint8_t *cursor = output;
    if (inputs == NULL || output == NULL || written == NULL)
        return MEMORY_LAYOUT_INVALID;
    if (!valid_extent(inputs, sizeof(*inputs)) || !valid_extent(output, capacity)
            || !valid_extent(written, sizeof(*written)))
        return MEMORY_LAYOUT_INVALID;
    if (overlaps(output, capacity, inputs, sizeof(*inputs))
            || overlaps(written, sizeof(*written), inputs, sizeof(*inputs))
            || overlaps(output, capacity, written, sizeof(*written)))
        return MEMORY_LAYOUT_OVERLAP;
    record = inputs->record;
    if (record != NULL) {
        if (!valid_extent(record, sizeof(*record)))
            return MEMORY_LAYOUT_INVALID;
        if (overlaps(output, capacity, record, sizeof(*record))
                || overlaps(written, sizeof(*written), record, sizeof(*record)))
            return MEMORY_LAYOUT_OVERLAP;
    }
    if ((inputs->address_cells != 1 && inputs->address_cells != 2)
            || (inputs->size_cells != 1 && inputs->size_cells != 2)
            || inputs->total_mib > MEMORY_LAYOUT_MAX_TOTAL_MIB)
        return MEMORY_LAYOUT_UNSUPPORTED;

    count = select_tuples(inputs, tuples);
    stride = 4 * (inputs->address_cells + inputs->size_cells);
    for (index = 0; index < count; ++index) {
        uint32_t base = tuples[index].base_mib;
        uint32_t size = tuples[index].size_mib;
        for (;;) {
            if (inputs->address_cells == 1 && base >= 4096)
                return MEMORY_LAYOUT_UNSUPPORTED;
            if (required > SIZE_MAX - stride)
                return MEMORY_LAYOUT_INVALID;
            required += stride;
            if (inputs->size_cells != 1 || size < 4096)
                break;
            if (base > UINT32_MAX - 2048)
                return MEMORY_LAYOUT_INVALID;
            base += 2048;
            size -= 2048;
        }
    }
    if (capacity < required)
        return MEMORY_LAYOUT_CAPACITY;

    for (index = 0; index < count; ++index) {
        uint32_t base = tuples[index].base_mib;
        uint32_t size = tuples[index].size_mib;
        while (inputs->size_cells == 1 && size >= 4096) {
            cursor = write_field(cursor, base, inputs->address_cells);
            cursor = write_field(cursor, 2048, inputs->size_cells);
            base += 2048;
            size -= 2048;
        }
        cursor = write_field(cursor, base, inputs->address_cells);
        cursor = write_field(cursor, size, inputs->size_cells);
    }
    *written = required;
    return MEMORY_LAYOUT_OK;
}
