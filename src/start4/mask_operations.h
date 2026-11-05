/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_MASK_OPERATIONS_H
#define OPEN27XX_MASK_OPERATIONS_H

#include <stddef.h>
#include <stdint.h>

enum mask_status {
    MASK_OK = 0,
    MASK_INVALID = -1,
    MASK_BOUNDS = -3,
    MASK_OVERLAP = -4
};

struct mask_byte_view {
    const uint8_t *bytes;
    size_t length;
};

struct mask_word_pair {
    uint32_t low;
    uint32_t high;
};

enum mask_status mask_predicate(uint32_t code,
    const struct mask_byte_view *masks, uint32_t *raw_result);

enum mask_status mask_shift(uint32_t low, uint32_t high, uint32_t count,
    struct mask_word_pair *result);

/*
 * The general scalar contract is in docs/bcm2711/mask-predicate.md.
 * Predicate codes from 0x40 through 0x7F select bit code - 0x40 from
 * little-endian low/high words at masks->bytes offsets zero and four.
 * Both words are read, high before low, using byte access. The result is
 * raw zero or one. Every other code returns raw zero without reading bytes
 * or computing a shift; masks may be NULL on that route.
 *
 * In-range codes require a view of at least eight bytes. Supplied views
 * always have length at most UINT32_MAX; NULL bytes require zero length.
 * A nonnull byte pointer with zero length has no span. Unused views and
 * unused tail bytes still participate in all storage validation.
 *
 * Shift accepts every low/high word and count. Counts zero through 63
 * perform a logical 64-bit left shift. For other counts the documented
 * wrapped subtraction and five-bit subshift counts define pinned scalar
 * behavior, not a C shift by count or a physical ISA claim. The predicate
 * shares this computation with inputs (1, 0, code - 0x40).
 *
 * Results are required. Result objects and supplied view descriptors need
 * natural alignment, nonwrapping spans and pairwise disjoint storage,
 * including the complete declared byte view. Byte storage may be unaligned.
 * Complete read-only preflight precedes mask reads and result publication.
 * MASK_INVALID reports missing required objects, typed misalignment and
 * NULL bytes with nonzero length. MASK_BOUNDS reports span wrap, lengths
 * above UINT32_MAX and an in-range view shorter than eight bytes.
 * MASK_OVERLAP reports intersecting spans. All errors preserve every
 * supplied byte and result. Success preserves the descriptor and full byte
 * view and publishes its result only after computation finishes.
 *
 * Callers provide actual backing, readability, result writability and
 * lifetime. Span checks cannot establish allocation validity. Descriptors
 * and bytes remain immutable without concurrent modification. No original
 * firmware address becomes a host pointer. No pointer is retained,
 * allocated or freed. Host status is separate from all result words.
 */

#endif
