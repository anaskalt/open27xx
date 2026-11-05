/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_FIRST_OPEN_INTERNAL_H
#define OPEN27XX_ARM_FIRST_OPEN_INTERNAL_H

#include "arm_first_open.h"

struct arm_first_open_prepared {
    struct arm_object_plan object_plan;
    unsigned object_profile;
    uint32_t selector;
    uint32_t switch_bits;
};

/* Enclosing operations validate their complete caller storage first. */
enum arm_first_open_status arm_first_open_prefix_preflight(
    const struct arm_first_open_inputs *inputs,
    struct arm_first_open_state *state, uint8_t *records, size_t records_length,
    const struct arm_first_open_reply_plan *replies,
    const struct arm_first_open_read_plan *reads,
    const struct arm_first_open_observers *observers,
    struct arm_first_open_prepared *prepared);

/* Service inputs, when used, retain their enclosing preflight premises. */
void arm_first_open_prefix_validated(
    const struct arm_first_open_inputs *inputs,
    struct arm_first_open_state *state, uint8_t *records, uint32_t version,
    const uint32_t *service_index, const struct arm_first_open_reply_plan *replies,
    const struct arm_first_open_read_plan *reads,
    const struct arm_first_open_observers *observers,
    const struct arm_first_open_prepared *prepared, uint32_t *raw_result);

#endif
