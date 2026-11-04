/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_FIRST_OPEN_H
#define OPEN27XX_ARM_FIRST_OPEN_H

#include "arm_object.h"

enum arm_first_open_status {
    ARM_FIRST_OPEN_OK = 0,
    ARM_FIRST_OPEN_INVALID = -1,
    ARM_FIRST_OPEN_UNSUPPORTED = -2,
    ARM_FIRST_OPEN_BOUNDS = -3,
    ARM_FIRST_OPEN_OVERLAP = -4
};

struct arm_first_open_inputs {
    uint32_t parameter_word;
    uint32_t parameter_byte;
    uint32_t configuration_source;
};

struct arm_first_open_state {
    uint32_t open_count;
    uint32_t object;
    uint32_t capacity;
    uint32_t configuration;
    uint32_t selected_callback;
    uint32_t old_callback;
};

struct arm_first_open_reply_plan {
    const uint32_t *words;
    size_t count;
};

struct arm_first_open_read {
    uint32_t pc;
    uint32_t address;
    uint32_t size;
    uint32_t word;
};

struct arm_first_open_read_plan {
    const struct arm_first_open_read *entries;
    size_t count;
};

/* The destination is an ordinary register index: 4 identifies r4. */
typedef void (*arm_first_open_version_fn)(
    void *context, uint32_t site, uint32_t destination, uint32_t word);

typedef void (*arm_first_open_read_fn)(
    void *context, uint32_t pc, uint32_t address, uint32_t size, uint32_t word);

struct arm_first_open_observers {
    arm_object_observe_fn acquire;
    arm_object_observe_fn registrar_acquire;
    arm_object_observe_fn registrar_diagnostic;
    arm_object_observe_fn registrar_release;
    arm_first_open_version_fn version;
    arm_object_observe_fn service;
    arm_first_open_read_fn read;
    void *context;
};

enum arm_first_open_status arm_callback_register(
    uint32_t code, uint32_t new_callback, uint32_t *selected_callback,
    uint32_t *old_callback, uint32_t *raw_result);

enum arm_first_open_status arm_first_open_execute(
    const struct arm_first_open_inputs *inputs,
    struct arm_first_open_state *state, uint8_t *records, size_t records_length,
    const uint32_t *cpu_word, const uint32_t *secondary_word,
    const uint32_t *service_index, uint32_t *handle_output,
    const struct arm_first_open_reply_plan *replies,
    const struct arm_first_open_read_plan *reads,
    const struct arm_first_open_observers *observers, uint32_t *raw_result);

/*
 * Only the finite profiles in arm-first-open.md apply. Callback registration
 * accepts code 0x5E, new token 0x0EC5716E, old output 0xA5A5A5A5 and selected
 * word 0, 0x0EC3EA48 or 0x11223344. All three word pointers are required and
 * disjoint. It clears the old output, computes the selected-word replacement
 * and publishes the actual raw result after those state writes, with no calls.
 *
 * First open accepts parameter word 0x400, byte 2 and source 0x12345678;
 * count and selected callback zero; object, capacity, configuration, old
 * callback and handle output 0xA5A5A5A5; and 896 zero record bytes. The full
 * records_length span is checked, including its untouched tail. CPU word 0
 * requires index 1 and ignores secondary_word. CPU word 0x40 requires secondary
 * 0 or 1; only secondary 1 requires index 1 and a service observer. Supplied
 * unused words contribute their spans without content access. All other
 * pointers are required, including reply words and read entries.
 *
 * Function replies are exactly four zeros without service or five with it.
 * The single read entry is (0x0EC59E12,0x7E00B44C,4,0x11223344). VERSION and
 * read observations use explicit inputs, not function replies. All observers
 * except an unused service are required. The operation composes the actual
 * arm_object_register and arm_callback_register computations. No higher
 * release occurs. Every observer sees the incoming raw result and handle;
 * raw publication follows the read observation and callback state writes.
 *
 * Preflight checks all required pointers, complete spans, address/size wrap,
 * pairwise overlap, exact initial domains and every reachable observer and
 * reply/read before any effect. INVALID covers missing storage or observers,
 * BOUNDS covers short records/plans and wrap, UNSUPPORTED covers other domains
 * or extra plan entries, and OVERLAP covers intersecting declared objects.
 * Every host error preserves all objects and emits nothing. A completed raw
 * 0xFFFFFFFF is OK with retained effects, not a host error or rollback.
 *
 * All supplied API objects and full declared arrays are disjoint, including
 * immutable inputs, plans, observers and outputs. Record bytes may be
 * unaligned; typed objects require natural alignment. Actual backing,
 * writability and lifetime are caller requirements. Native identities are
 * opaque tokens, not callable addresses or host pointers. No pointer is
 * retained, allocated or freed. Observers return normally, preserve API
 * objects and arguments, avoid reentry, concurrent mutation and hardware
 * access, and keep writable bookkeeping separate. Read-only context
 * references may inspect API state. The helper is separate from runtime.
 */

#endif
