/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_STARTUP_INITIALIZATION_H
#define OPEN27XX_STARTUP_INITIALIZATION_H

#include <stddef.h>
#include <stdint.h>

#define STARTUP_INITIALIZATION_DESTINATIONS 3u

enum startup_initialization_status {
    STARTUP_INITIALIZATION_OK = 0,
    STARTUP_INITIALIZATION_INVALID = -1,
    STARTUP_INITIALIZATION_UNSUPPORTED = -2,
    STARTUP_INITIALIZATION_BOUNDS = -3,
    STARTUP_INITIALIZATION_OVERLAP = -4
};

struct startup_initialization_registers {
    uint32_t r[24];
    uint32_t gp;
    uint32_t sp;
    uint32_t lr;
    uint32_t r27;
    uint32_t r28;
    uint32_t r29;
    uint32_t sr;
};

struct startup_initialization_buffer {
    uint8_t *bytes;
    size_t length;
};

struct startup_initialization_destinations {
    struct startup_initialization_buffer
        buffers[STARTUP_INITIALIZATION_DESTINATIONS];
};

struct startup_initialization_stack {
    uint8_t *bytes;
    size_t length;
    uint32_t address;
};

struct startup_initialization_result {
    struct startup_initialization_registers registers;
    uint32_t pc;
};

enum startup_initialization_status startup_initialization_run(
    const struct startup_initialization_registers *input,
    const struct startup_initialization_destinations *destinations,
    const struct startup_initialization_stack *stack,
    struct startup_initialization_result *result);

/*
 * The fixed-table behavior and portable policy are specified in
 * docs/bcm2711/startup-initialization.md. All addresses and register words
 * are numeric values; no VPU address becomes a host pointer.
 *
 * All four objects and all four byte pointers are required. Typed objects
 * are naturally aligned; byte storage may be unaligned. GP is 0x0EE04140.
 * The three destination lengths are exactly 2352, 2048 and 1011288 bytes,
 * in that order. No table, version or alternative destination is accepted.
 * Other scalar inputs follow the documented general conditional domain.
 *
 * Stack describes a byte span beginning at its numeric VPU address. Length
 * is at most UINT32_MAX; its exclusive virtual end may equal 2^32. SP is
 * four-byte aligned and at least 24. The full frame [SP-24, SP) fits within
 * the stack span. The entire span excludes all fixed source, table and
 * destination ranges in the document. LR is even and outside the stack and
 * those fixed ranges. Adjacent half-open ranges are permitted.
 *
 * Every full host pointer-plus-length fits uintptr_t. Input, the complete
 * destinations object, stack descriptor, all destination bytes, the entire
 * declared stack span and result are pairwise disjoint. Complete read-only
 * preflight precedes any store. INVALID reports missing pointers, typed
 * misalignment, invalid SP or odd LR. UNSUPPORTED reports a different GP.
 * BOUNDS reports a wrapping span, excess stack length, wrong destination
 * length or incomplete frame. OVERLAP reports intersecting host spans or
 * forbidden virtual intersections. If several conditions fail, any matching
 * error may be returned. Rejection preserves every supplied byte and object.
 * This policy does not establish rollback for unsupported native paths.
 *
 * Success zeroes all three destination buffers. It writes incoming LR and
 * r6 through r9 at SP-4, SP-8, SP-12, SP-16 and SP-20 in little-endian order.
 * Every other stack byte remains unchanged, including the word at SP-24.
 * Result publication follows these memory effects. Result contains all 31
 * final scalar register words and PC; status is separate from final r0.
 * No event stream, callbacks or intermediate-state observation is exposed.
 *
 * Callers provide actual backing, readability, output/destination/stack
 * writability and lifetime. Integer checks do not establish allocation
 * validity. Input and descriptors stay immutable; all supplied storage is
 * free from concurrent access until return. No storage is allocated, freed
 * or retained. The function performs no hardware access, general INI
 * parsing, address fixups or service transition.
 */

#endif
