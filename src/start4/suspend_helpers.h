/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_SUSPEND_HELPERS_H
#define OPEN27XX_SUSPEND_HELPERS_H

#include <stddef.h>
#include <stdint.h>

#define SUSPEND_RECORD_BYTES 36u

enum suspend_status {
    SUSPEND_OK = 0,
    SUSPEND_INVALID = -1,
    SUSPEND_BOUNDS = -3,
    SUSPEND_OVERLAP = -4
};

struct suspend_byte_view {
    const uint8_t *bytes;
    size_t length;
};

struct suspend_buffer {
    uint8_t *bytes;
    size_t length;
};

struct suspend_lookup_inputs {
    int32_t count;
    uint32_t first;
    uint32_t second;
    uint32_t third;
};

struct suspend_copy_inputs {
    uint32_t capacity;
    uint32_t offset;
};

enum suspend_status suspend_lookup(
    const struct suspend_lookup_inputs *inputs,
    const struct suspend_byte_view *records, uint32_t *raw_result);

enum suspend_status suspend_length(
    const struct suspend_byte_view *source, uint32_t *length);

enum suspend_status suspend_copy(
    const struct suspend_copy_inputs *inputs,
    const struct suspend_buffer *destination,
    const struct suspend_byte_view *source, uint32_t *raw_result);

/*
 * The general bounded contract is in docs/bcm2711/suspend-helpers.md.
 * Every descriptor, inputs structure and result is required, naturally
 * aligned and disjoint from all other objects and full declared byte views.
 * Byte storage may be unaligned. Callers provide actual backing, lifetime,
 * readability and writable destination/result storage without concurrent
 * mutation. No storage is allocated and no pointer is retained.
 *
 * Lookup's view starts at the first record's byte key, with a 36-byte stride
 * and little-endian word keys at offsets 4 and 8. Positive count requires
 * 36 * count bytes, with that product at most UINT32_MAX. Nonpositive count
 * reads no record bytes and permits a NULL, zero-length record view.
 * All byte views have lengths at most UINT32_MAX; NULL requires length zero.
 *
 * Source length is from 1 through INT32_MAX, including a required NUL.
 * Length and copy share the bounded first-NUL computation. Copy requires
 * destination.length >= capacity, even when offset >= capacity. A NULL
 * destination is valid only with length and capacity zero. Offset accepts
 * every uint32_t value. Offset >= capacity performs no destination access.
 * Otherwise copy writes min(length, capacity - offset - 1) bytes then NUL.
 * Its raw result is (full source length + offset) modulo 2^32.
 *
 * Preflight is read-only and completes before destination/result stores.
 * Missing objects, invalid NULL views and typed misalignment return
 * SUSPEND_INVALID; invalid lengths, count products, address wrap and missing
 * source NUL return SUSPEND_BOUNDS; pairwise overlap returns SUSPEND_OVERLAP.
 * Errors preserve all supplied storage. Success publishes the separate
 * result only after computation and copy writes. Host status is distinct
 * from every raw word, including zero, UINT32_MAX and wrapped copy results.
 */

#endif
