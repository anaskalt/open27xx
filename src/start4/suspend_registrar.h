/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_SUSPEND_REGISTRAR_H
#define OPEN27XX_SUSPEND_REGISTRAR_H

#include "suspend_helpers.h"

#define SUSPEND_OBJECT_BYTES 2936u

struct suspend_registration_inputs {
    uint32_t first;
    uint32_t callback;
    uint32_t cookie;
    uint32_t sr;
};

struct suspend_p16_read_plan {
    const uint32_t *words;
    size_t count;
};

typedef void (*suspend_di_fn)(void *context, uint32_t before, uint32_t after);
typedef void (*suspend_p16_fn)(void *context, uint32_t word);

struct suspend_registration_observers {
    suspend_di_fn di;
    suspend_p16_fn read;
    suspend_p16_fn write;
    void *context;
};

enum suspend_status suspend_register(
    const struct suspend_registration_inputs *inputs,
    const struct suspend_buffer *object, const struct suspend_byte_view *name,
    const uint8_t *logging, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result);

/*
 * The general bounded contract is in docs/bcm2711/suspend-registrar.md.
 * Inputs, object, reads, observers and raw_result are required. Object starts
 * at saved SR and contains at least SUSPEND_OBJECT_BYTES bytes. Its signed
 * little-endian count at 0xB5C is from zero through INT32_MAX. Tuple and SR
 * words are arbitrary identities; callback tokens are never called.
 *
 * Count >= 40 returns raw UINT32_MAX without inspecting records, name bytes
 * or logging. Otherwise logging is required and is below four. Lookup runs
 * before the zero-callback check: a match returns zero; absence with callback
 * zero returns one. Absence with nonzero callback inserts the low byte of
 * first, callback, cookie and a basename, increments count and clears 0xB74.
 * Name is required only for insertion: its extent is 1 through INT32_MAX
 * and contains a NUL. The last slash or backslash selects the basename;
 * up to 21 bytes and a NUL are copied. Remaining object bytes are preserved.
 * An unused name descriptor may be NULL, or hold any valid unused byte view.
 *
 * Reads contains zero or more one words and exactly one final zero, with
 * 4 * count <= UINT32_MAX. All three observers are required. DI reports the
 * incoming SR before and with bit 30 cleared after. Every read reports its
 * supplied word. DI and reads see the unchanged object. Write reports the
 * full saved SR after all object stores. Every observation sees the incoming
 * raw_result, which is published only after write returns. These are software
 * observations under a no-interrupt-arrival premise, not physical IRQ access.
 *
 * Complete read-only preflight checks every supplied API object and full
 * declared span, including unused views and tails, before any effect. All
 * extents are at most UINT32_MAX; a NULL byte pointer requires zero extent.
 * All supplied objects/spans are pairwise disjoint. Typed objects and read
 * words require natural alignment; byte views need none. INVALID reports
 * missing required storage/observers, invalid NULL views, typed misalignment,
 * logging >= 4 or an invalid read word/sequence. BOUNDS reports invalid
 * extents, count domain, empty plans, product/address wrap or a missing NUL.
 * OVERLAP reports intersecting spans. Each error preserves all supplied
 * storage and emits nothing. Host status is separate from all raw returns.
 *
 * Callers provide backing, readability, writability and lifetime, with no
 * concurrent changes. No pointer is retained, allocated or freed. Observers
 * return normally, preserve API objects and arguments, avoid reentry and
 * hardware access, and keep mutable bookkeeping disjoint from API storage.
 * Read-only context references may inspect object state and raw_result.
 * Indirect observer storage and behavior are caller premises.
 */

#endif
