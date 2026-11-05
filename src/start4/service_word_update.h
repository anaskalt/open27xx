/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_SERVICE_WORD_UPDATE_H
#define OPEN27XX_SERVICE_WORD_UPDATE_H

#include <stdint.h>

enum service_word_status {
    SERVICE_WORD_OK = 0,
    SERVICE_WORD_INVALID = -1,
    SERVICE_WORD_BOUNDS = -3,
    SERVICE_WORD_OVERLAP = -4
};

struct service_word_request {
    uint32_t opaque;
    uint32_t code;
    uint32_t value;
};

struct service_word_plan {
    uint32_t version;
    uint32_t read_address;
    uint32_t old_word;
    uint32_t write_address;
};

enum service_word_event {
    SERVICE_WORD_VERSION = 0,
    SERVICE_WORD_READ = 1,
    SERVICE_WORD_WRITE = 2
};

typedef void (*service_word_observe_fn)(void *context,
    enum service_word_event event, uint32_t address, uint32_t word);

struct service_word_observer {
    service_word_observe_fn observe;
    void *context;
};

enum service_word_status service_word_update(
    const struct service_word_request *request,
    const struct service_word_plan *plan,
    const struct service_word_observer *observer, uint32_t *raw_result);

/*
 * The general scalar contract is in docs/bcm2711/service-word-update.md.
 * All four API objects and observer->observe are required. Request words,
 * VERSION and old_word accept every uint32_t value; opaque is ignored.
 * Both plan addresses must equal 0x7E002010 + 0x800 * VERSION[19:16]
 * + 4 * code[5:3]. Shift is 4 * code[2:0]. The stored word clears the
 * selected nibble from old_word, then ORs value shifted modulo 2^32.
 * Value is not restricted or masked to a nibble before shifting.
 *
 * Complete read-only preflight precedes all events and result stores.
 * API objects require natural alignment and pairwise disjoint full spans,
 * including immutable objects. INVALID reports missing objects, a missing
 * observer function, typed misalignment or a plan address mismatch. BOUNDS
 * reports pointer-plus-size wrap; OVERLAP reports intersecting object spans.
 * Errors emit nothing and preserve every supplied object and raw_result.
 *
 * Success reports VERSION with address zero and the full VERSION word,
 * READ with the selected address and old_word, then WRITE with that address
 * and the computed word. Address zero on VERSION is an unused event field,
 * not a read address. The observer supplies no value or status. All events
 * see the incoming raw_result; raw zero is published only after WRITE
 * returns. Host status is separate from that raw result. No hardware
 * address or opaque word becomes a host pointer, and no MMIO is performed.
 *
 * Callers provide actual backing, readability, result writability and
 * lifetime. Integer span checks cannot establish allocation validity.
 * Request, plan and observer remain unchanged concurrently and throughout
 * observations. No pointer is retained, allocated or freed. Context is an
 * opaque host reference, never dereferenced here, and may be NULL if the
 * observer accepts it. Read-only context references may inspect the inputs
 * and incoming result. Observers return normally, preserve all API objects,
 * avoid reentry and perform no hardware access. Mutable bookkeeping and
 * all indirectly writable storage remain disjoint from API objects.
 * These indirect-storage and observer-behavior rules are caller premises.
 */

#endif
