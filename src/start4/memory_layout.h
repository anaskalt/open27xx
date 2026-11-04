/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_MEMORY_LAYOUT_H
#define OPEN27XX_MEMORY_LAYOUT_H

#include <stddef.h>
#include <stdint.h>

#define MEMORY_LAYOUT_MAX_TOTAL_MIB 16384u

/* Decoded words from offsets 0x80 and 0x88; no raw record is accessed. */
struct memory_layout_record {
    uint32_t flags;
    uint32_t selector;
};

struct memory_layout_inputs {
    uint32_t address_cells;
    uint32_t size_cells;
    uint32_t lower_span_bytes;
    uint32_t total_mib;
    uint32_t control_word;
    const struct memory_layout_record *record;
};

/* Host validation results are separate from the encoded byte count. */
enum memory_layout_status {
    MEMORY_LAYOUT_OK = 0,
    MEMORY_LAYOUT_INVALID = -1,
    MEMORY_LAYOUT_UNSUPPORTED = -2,
    MEMORY_LAYOUT_CAPACITY = -3,
    MEMORY_LAYOUT_OVERLAP = -4
};

enum memory_layout_status memory_layout_serialize(
    const struct memory_layout_inputs *inputs,
    uint8_t *output, size_t capacity, size_t *written);

/*
 * All pointers except inputs->record are required. A null record means absent.
 * Inputs, any record and written are aligned objects of the declared types;
 * output is writable for capacity bytes and needs no additional alignment.
 * All storage is caller-owned and remains valid throughout the call. Output's
 * entire declared capacity and written must not overlap each other, inputs or
 * a present record. The helper checks null pointers, representable extents and
 * these overlaps; the caller enforces actual backing, alignment and lifetime.
 * Inputs and record remain immutable, including during concurrent access.
 * Cells must be 1 or 2; total_mib must not exceed MEMORY_LAYOUT_MAX_TOTAL_MIB.
 * With one address cell, every selected and split base must be below 4096 MiB.
 * Every validation error preserves output and written. Success writes only
 * the encoded extent, stores its byte count in written and preserves the tail.
 * No allocation, physical ownership, placement or tree mutation is provided.
 * See docs/bcm2711/memory-layout.md and README.md for the numeric contract.
 */

#endif
