/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_CLOCK_DRIVER_INTERNAL_H
#define OPEN27XX_CLOCK_DRIVER_INTERNAL_H

#include "clock_driver.h"

/* Read-only preflight shared by the standalone and owned operations. */
enum clock_driver_status clock_source_preflight(
    const struct clock_source_inputs *inputs, const struct clock_source_state *state,
    const struct clock_driver_plan *plan, const uint32_t *raw_return);
enum clock_driver_status clock_word_preflight(
    const struct clock_word_inputs *inputs, const uint32_t *cell,
    const struct clock_driver_observer *observer, const uint32_t *raw_return);
enum clock_driver_status clock_divider_preflight(
    const struct clock_divider_inputs *inputs, const struct clock_divider_state *state,
    const struct clock_driver_plan *plan, const uint32_t *raw_return);

#endif
