/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_RESOURCE_COMPOSITION_INTERNAL_H
#define OPEN27XX_RESOURCE_COMPOSITION_INTERNAL_H

#include "resource_composition.h"

struct resource_composition_span {
    const void *pointer;
    size_t length;
};

enum clock_driver_status resource_composition_validate_spans(
    const struct resource_composition_span *spans, size_t count);

/* Read-only whole-path validation for enclosing owned operations. */
enum clock_driver_status resource_composition_preflight(
    const struct resource_composition_inputs *inputs,
    const uint8_t *records, size_t records_length,
    const struct resource_composition_state *resource,
    const uint8_t *manager, size_t manager_length,
    const struct clock_request_state *clock_state,
    const struct clock_source_state *source, const struct clock_divider_state *divider,
    const uint32_t *cell, const uint8_t *scratch, size_t scratch_length,
    const struct resource_composition_plan *plan,
    const struct resource_composition_result *result);

#endif
