/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_START_COMPOSITION_H
#define OPEN27XX_ARM_START_COMPOSITION_H

#include "resource_composition.h"

struct arm_start_composition_inputs {
    uint32_t handle;
    uint32_t mutex_identity;
    struct resource_composition_inputs resource;
};

struct arm_start_composition_plan {
    struct resource_composition_plan resource;
    resource_composition_observe_fn acquire;
    resource_composition_observe_fn release;
    void *context;
};

struct arm_start_composition_result {
    struct resource_composition_result resource;
    uint32_t higher_raw;
};

enum clock_driver_status arm_start_composition_execute(
    const struct arm_start_composition_inputs *inputs,
    struct arm_control_start_state *start,
    uint8_t *records, size_t records_length,
    struct resource_composition_state *resource,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *clock_state,
    struct clock_source_state *source, struct clock_divider_state *divider,
    uint32_t *cell, uint8_t *scratch, size_t scratch_length,
    const struct arm_start_composition_plan *plan,
    struct arm_start_composition_result *result);

/*
 * Only the two complete returned profiles in arm-start-composition.md apply.
 * Higher handle/open/mapping/active values are exactly 0x61726D11/1/1/0.
 * The nonzero resource token binds the higher object to request/record 0.
 * Higher and lower mutex tokens are distinct opaque observation identities.
 * Entire-path preflight precedes higher acquisition and every state store.
 * All objects, complete declared buffer spans and read arrays are disjoint.
 * Callers supply actual backing, typed alignment, lifetime and writability.
 * Host errors preserve all objects and emit no observations. Active changes
 * only after the actual lower return; the result is stored only after higher
 * release. Host status, lower/higher raw words and rate scratch are separate.
 * Observers return normally, preserve API objects and arguments, use separate
 * bookkeeping, and avoid reentry, concurrent mutation and hardware access.
 * No stopped outcome, context callback, partial call or recovery is defined.
 * No pointer is retained, allocated or freed; identities are never host pointers.
 */

#endif
