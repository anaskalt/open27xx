/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_SUSPEND_REGISTRAR_INTERNAL_H
#define OPEN27XX_SUSPEND_REGISTRAR_INTERNAL_H

#include "suspend_registrar.h"

#define SUSPEND_REGISTRATION_EXTRA_SPANS 6u

struct suspend_registration_span {
    const void *pointer;
    size_t length;
    size_t alignment;
};

struct suspend_registration_prepared {
    struct suspend_byte_view basename;
    struct suspend_buffer destination;
    uint32_t count;
    uint32_t raw;
    int insert;
};

enum suspend_status suspend_registration_validate_spans(
    const struct suspend_registration_span *spans, size_t count);

/* Enclosing operations supply their complete additional caller storage. */
enum suspend_status suspend_registration_preflight(
    const struct suspend_registration_inputs *inputs,
    const struct suspend_buffer *object, const struct suspend_byte_view *name,
    const uint8_t *logging, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result,
    const struct suspend_registration_span *extra, size_t extra_count,
    struct suspend_registration_prepared *prepared);

/* Inputs and prepared subviews must retain every accepted preflight premise. */
void suspend_registration_execute_validated(
    const struct suspend_registration_inputs *inputs,
    const struct suspend_buffer *object, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result,
    const struct suspend_registration_prepared *prepared);

#endif
