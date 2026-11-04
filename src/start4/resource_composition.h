/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_RESOURCE_COMPOSITION_H
#define OPEN27XX_RESOURCE_COMPOSITION_H

#include "arm_control.h"
#include "clock_composition.h"
#include "resource_request.h"

#define RESOURCE_COMPOSITION_RECORD_BYTES 896u

struct resource_composition_inputs {
    struct resource_request_inputs request;
    uint32_t table;
    uint32_t selection;
    uint32_t skip;
    uint32_t outer_mutex;
    uint32_t resource_mutex;
    struct arm_control_configuration configuration;
    struct clock_composition_inputs clock;
};

struct resource_composition_state {
    uint32_t held;
    uint32_t aggregate;
    uint32_t prehook;
};

/* Identity labels the boundary; each observed reply is literal zero. */
typedef void (*resource_composition_observe_fn)(void *context, uint32_t identity,
    const uint32_t *arguments, size_t count, uint32_t reply);

struct resource_composition_plan {
    struct clock_composition_plan clock;
    struct clock_driver_plan control[2];
    struct clock_driver_plan final;
    resource_composition_observe_fn diagnostic;
    resource_composition_observe_fn acquire;
    resource_composition_observe_fn release;
    resource_composition_observe_fn service;
    void *context;
};

struct resource_composition_result {
    struct clock_composition_result first_clock;
    uint32_t repeated_word_raw;
    uint32_t repeated_manager_raw;
    uint32_t resource_raw;
};

enum clock_driver_status resource_composition_execute(
    const struct resource_composition_inputs *inputs,
    uint8_t *records, size_t records_length,
    struct resource_composition_state *resource,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *clock_state,
    struct clock_source_state *source, struct clock_divider_state *divider,
    uint32_t *cell, uint8_t *scratch, size_t scratch_length,
    const struct resource_composition_plan *plan,
    struct resource_composition_result *result);

/*
 * Only the two complete fixed resource-23 profiles in resource-composition.md
 * apply. Records use the documented 28-byte stride and little-endian words.
 * The shared eight-byte scratch is cleared before each nested clock; its
 * declared tail is preserved. All objects and complete declared spans,
 * including every read array, must be disjoint, backed, writable as needed,
 * correctly aligned where typed, and alive throughout the call.
 * Whole-path preflight precedes the first diagnostic and every state store.
 * Host errors preserve all objects and emit no events. The result is stored
 * only after the final manager release. There is no stopped outcome.
 * Observers return normally, preserve all API objects and arguments, use
 * separate bookkeeping, avoid reentry/concurrent mutation, and access no
 * hardware. Context may be null if its observer accepts it. Identity words
 * are opaque labels and never callable or dereferenceable host pointers.
 */

#endif
