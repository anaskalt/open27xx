/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_BOOT_INFO_H
#define OPEN27XX_BOOT_INFO_H

#include <stddef.h>
#include <stdint.h>

#define BOOT_INFO_CACHE_COUNT 15u

/* These results describe host checks, not firmware return values. */
enum boot_info_status {
    BOOT_INFO_OK = 0,
    BOOT_INFO_INVALID = -1,
    BOOT_INFO_BOUNDS = -2,
    BOOT_INFO_OVERFLOW = -3,
    BOOT_INFO_ALLOCATION = -4,
    BOOT_INFO_OVERLAP = -5
};

struct boot_info_buffer {
    uint8_t *data;
    size_t length;
};

/* Slots follow the ascending cache offsets in the format contract. */
struct boot_info_state {
    uint32_t complete;
    struct boot_info_buffer cache[BOOT_INFO_CACHE_COUNT];
};

typedef enum boot_info_status (*boot_info_allocate_fn)(
    void *context, size_t count, size_t item_size,
    struct boot_info_buffer *result);

typedef enum boot_info_status (*boot_info_heap_fn)(
    void *context, size_t length, uint32_t argument1, uint32_t argument2,
    uint32_t caller_word, struct boot_info_buffer *result);

struct boot_info_zero_allocator {
    boot_info_heap_fn allocate;
    void *context;
    uint32_t caller_word;
};

/* State and allocated storage remain caller-owned and must outlive lookup. */
enum boot_info_status boot_info_parse(
    struct boot_info_state *state, const uint8_t *source, size_t length,
    boot_info_allocate_fn allocate, void *context);

enum boot_info_status boot_info_lookup(
    struct boot_info_state *state, const uint8_t *source, size_t length,
    boot_info_allocate_fn allocate, void *context, uint32_t tag,
    struct boot_info_buffer *result);

/* Compatible with boot_info_allocate_fn; context is boot_info_zero_allocator. */
enum boot_info_status boot_info_allocate_zeroed(
    void *context, size_t count, size_t item_size,
    struct boot_info_buffer *result);

enum boot_info_status boot_info_prepare_pointer(uint8_t *section, size_t length);

/* The caller selects the bounded fallback path and supplies the decoded word. */
uint32_t boot_info_fallback_revision(uint32_t present, uint32_t word);

#endif
