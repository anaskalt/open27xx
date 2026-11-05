/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_OBJECT_INTERNAL_H
#define OPEN27XX_ARM_OBJECT_INTERNAL_H

#include "arm_object.h"

enum arm_object_status arm_object_register_preflight(
    uint32_t output_present, uint8_t *records, size_t records_length,
    uint32_t *object_output, const struct arm_object_plan *plan,
    uint32_t *raw_result, unsigned *profile);

/* Every accepted preflight premise remains true until execution completes. */
void arm_object_register_validated(
    uint32_t output_present, uint8_t *records, uint32_t *object_output,
    const struct arm_object_plan *plan, uint32_t *raw_result);

#endif
