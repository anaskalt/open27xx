/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "memory_capacity.h"

#include <stddef.h>

static uint32_t capacity_pass(memory_capacity_byte_fn service, void *context) {
    static const uint8_t base_counts[] = {4, 6, 8, 12, 16, 24, 32};
    uint8_t replies[8];
    uint32_t first, second, code, count;
    for (second = 0; second < 2; ++second) {
        for (first = 0; first < 2; ++first) {
            uint32_t index = 4 * second + 2 * first;
            replies[index] = service(context, 5, first, second);
            replies[index + 1] = service(context, 8, first, second);
        }
    }
    code = (replies[1] >> 2) & 15u;
    count = code < sizeof(base_counts) ? base_counts[code] : 8;
    if (replies[0] == replies[2] && replies[1] == replies[3])
        count *= 2;
    if ((replies[1] >> 6) == 1)
        count *= 2;
    return count;
}

static uint32_t capacity_class(uint32_t count) {
    switch (count) {
    case 4: return 1;
    case 8: return 2;
    case 16: return 3;
    case 32: return 4;
    case 64: return 5;
    case 128: return 6;
    default: return 7;
    }
}

enum memory_capacity_status memory_capacity_measure(
    memory_capacity_byte_fn service, void *context,
    uint32_t *size_mib, uint32_t *result_class) {
    uintptr_t size_address = (uintptr_t)size_mib;
    uintptr_t class_address = (uintptr_t)result_class;
    uint32_t first_count, second_count;
    if (service == NULL || size_mib == NULL || result_class == NULL)
        return MEMORY_CAPACITY_INVALID;
    if (size_address < class_address
            ? class_address - size_address < sizeof(*size_mib)
            : size_address - class_address < sizeof(*result_class))
        return MEMORY_CAPACITY_OVERLAP;

    *size_mib = 256;
    first_count = capacity_pass(service, context);
    second_count = capacity_pass(service, context);
    *size_mib = first_count * 128;
    *result_class = capacity_class(second_count);
    return MEMORY_CAPACITY_OK;
}
