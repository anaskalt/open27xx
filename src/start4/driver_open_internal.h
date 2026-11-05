/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_DRIVER_OPEN_INTERNAL_H
#define OPEN27XX_DRIVER_OPEN_INTERNAL_H

#include "driver_open.h"
#include "suspend_registrar_internal.h"

enum suspend_status driver_open_preflight(
    const struct driver_open_inputs *inputs,
    const struct suspend_buffer *masks, const struct suspend_byte_view *source,
    const struct suspend_buffer *object, const struct suspend_byte_view *name,
    const uint8_t *logging, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result,
    struct suspend_registration_prepared *prepared);

/* Every accepted preflight premise remains true until execution completes. */
void driver_open_validated(
    const struct driver_open_inputs *inputs,
    const struct suspend_buffer *masks, const struct suspend_byte_view *source,
    const struct suspend_buffer *object, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result,
    const struct suspend_registration_prepared *prepared);

#endif
