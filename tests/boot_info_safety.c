/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "../src/start4/boot_info.h"

#include <assert.h>
#include <stdlib.h>
#include <string.h>

struct allocations {
    void *buffers[BOOT_INFO_CACHE_COUNT];
    size_t count;
    int fail;
};

static enum boot_info_status allocate(void *context, size_t count, size_t size,
                                      struct boot_info_buffer *result) {
    struct allocations *allocations = context;
    assert(count == 1);
    assert(size <= 200);
    if (allocations->fail)
        return BOOT_INFO_OK;
    assert(allocations->count < BOOT_INFO_CACHE_COUNT);
    result->data = malloc(size);
    assert(result->data != NULL);
    result->length = size;
    memset(result->data, 0xA5, size);
    allocations->buffers[allocations->count++] = result->data;
    return BOOT_INFO_OK;
}

static void write_word(uint8_t *bytes, uint32_t word) {
    size_t index;
    for (index = 0; index < 4; ++index)
        bytes[index] = (uint8_t)(word >> (8 * index));
}

static uint32_t random_word(uint32_t *state) {
    *state ^= *state << 13;
    *state ^= *state >> 17;
    *state ^= *state << 5;
    return *state;
}

int main(void) {
    uint32_t random_state = UINT32_C(0x713AC924);
    size_t trial;
    for (trial = 0; trial < 16384; ++trial) {
        struct boot_info_state state = {0};
        struct allocations allocations = {{NULL}, 0, 0};
        size_t length = trial % 301;
        uint8_t *source = malloc(length == 0 ? 1 : length);
        uint8_t *saved = malloc(length == 0 ? 1 : length);
        enum boot_info_status status;
        size_t index;
        assert(source != NULL && saved != NULL);
        for (index = 0; index < length; ++index)
            source[index] = (uint8_t)random_word(&random_state);
        if (length >= 4 && trial % 5 != 0)
            write_word(source, UINT32_C(0x45545342));
        if (length >= 8 && trial % 5 != 0)
            write_word(source + 4, trial % 7 == 0 ? 32768 : (uint32_t)length);
        if (length >= 12 && trial % 3 != 0)
            write_word(source + 8, 12);
        if (length >= 24) {
            write_word(source + 12, UINT32_C(0x52455642));
            write_word(source + 16, (uint32_t)(trial % 201));
            write_word(source + 20, trial % 3 == 0 ? UINT32_MAX : 0);
        }
        memcpy(saved, source, length);
        allocations.fail = trial % 11 == 0;
        status = boot_info_parse(&state, source, length, allocate, &allocations);
        assert(status == BOOT_INFO_OK || status == BOOT_INFO_BOUNDS
               || status == BOOT_INFO_ALLOCATION || status == BOOT_INFO_OVERFLOW);
        assert(state.complete <= 1);
        assert(memcmp(saved, source, length) == 0);
        for (index = 0; index < allocations.count; ++index)
            free(allocations.buffers[index]);
        free(saved);
        free(source);
    }
    return 0;
}
