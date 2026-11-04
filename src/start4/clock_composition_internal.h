/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_CLOCK_COMPOSITION_INTERNAL_H
#define OPEN27XX_CLOCK_COMPOSITION_INTERNAL_H

#include "clock_composition.h"

/* Read-only whole-path validation for enclosing owned operations. */
enum clock_driver_status clock_composition_preflight(
    const struct clock_composition_inputs *inputs,
    const uint8_t *manager, size_t manager_length,
    const struct clock_request_state *state,
    const struct clock_source_state *source, const struct clock_divider_state *divider,
    const uint32_t *cell, const uint8_t *output, size_t output_length,
    const struct clock_composition_plan *plan,
    const struct clock_composition_result *result);

#endif
