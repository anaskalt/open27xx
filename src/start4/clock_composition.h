/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_CLOCK_COMPOSITION_H
#define OPEN27XX_CLOCK_COMPOSITION_H

#include "clock_driver.h"
#include "clock_request.h"

struct clock_composition_inputs {
    struct clock_request_inputs request;
    uint32_t helper_selection;
    uint32_t helper_gate;
    uint32_t helper_input;
    uint8_t diagnostic;
};

struct clock_composition_plan {
    struct clock_driver_plan source;
    struct clock_driver_observer word;
    struct clock_driver_plan divider;
    clock_request_provider_fn acquire;
    clock_request_provider_fn diagnostic;
    clock_request_provider_fn release;
    void *context;
};

struct clock_composition_result {
    uint32_t source_raw;
    uint32_t word_raw;
    uint32_t divider_raw;
    uint32_t manager_raw;
};

enum clock_driver_status clock_composition_execute(
    const struct clock_composition_inputs *inputs,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *state,
    struct clock_source_state *source, struct clock_divider_state *divider,
    uint32_t *cell, uint8_t *output, size_t output_length,
    const struct clock_composition_plan *plan,
    struct clock_composition_result *result);

/*
 * Only the two complete first-request profiles in clock-composition.md apply.
 * The operation owns nested source, native-word and divider effects; no
 * programming reply is supplied by the caller. Acquire, diagnostic and
 * release observe literal zero replies through the existing boundary type.
 * Every API object and both complete declared byte spans must be disjoint,
 * backed, correctly aligned where typed, and valid throughout the call.
 * The whole path is checked before effects. Host errors preserve all bytes
 * and emit no observations. The result is stored only after release.
 * Observers preserve every API object and use separate bookkeeping storage;
 * they return normally, cannot reenter or access hardware, and cannot change
 * the cell asynchronously. Context pointers may be null if observers accept
 * them. Identity words label events and never become executable pointers.
 * Source-return prefixes are evidence only; there is no partial operation.
 */

#endif
