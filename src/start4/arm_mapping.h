/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_MAPPING_H
#define OPEN27XX_ARM_MAPPING_H

#include <stddef.h>
#include <stdint.h>

#define ARM_MAPPING_HANDLE UINT32_C(0x61726D11)
#define ARM_MAPPING_ENTRIES 64u
#define ARM_MAPPING_TABLE_BYTES 128u

enum arm_mapping_status {
    ARM_MAPPING_OK = 0,
    ARM_MAPPING_INVALID = -1,
    ARM_MAPPING_UNSUPPORTED = -2,
    ARM_MAPPING_BOUNDS = -3,
    ARM_MAPPING_OVERLAP = -4
};

struct arm_mapping_inputs {
    uint32_t handle;
    uint32_t offset;
    uint32_t base;
    uint32_t length;
};

struct arm_mapping_state {
    uint32_t active;
    uint32_t capacity;
    uint32_t marker;
    uint32_t selection;
    uint32_t service_index;
};

typedef void (*arm_mapping_observe_fn)(
    void *context, uint32_t entry, const uint32_t *arguments,
    size_t count, uint32_t reply);

struct arm_mapping_plan {
    arm_mapping_observe_fn acquire;
    arm_mapping_observe_fn release;
    arm_mapping_observe_fn service;
    void *context;
};

enum arm_mapping_status arm_mapping_prepare(
    const struct arm_mapping_inputs *inputs, struct arm_mapping_state *state,
    uint8_t *table, size_t table_length, const struct arm_mapping_plan *plan,
    uint32_t *raw_result);

/*
 * Only the twelve paired complete profiles in arm-mapping.md are admitted.
 * Invalid handle zero needs only inputs and raw_result. Every other profile
 * needs state and acquire/release observers. Active uses only state.active;
 * the six range/zero/alignment profiles also use capacity. The four table
 * profiles require marker, selection and at least 128 table bytes. Only
 * selection zero requires service_index and the service observer. Unused
 * state members are neither read nor validated and remain unchanged.
 *
 * All supplied objects and complete declared table extents participate in
 * wrap and pairwise overlap checks, even on paths that ignore their contents.
 * NULL table requires zero length. Optional state, table and plan pointers
 * may be NULL when unused. All objects are disjoint, including inputs, plan
 * and raw_result. Typed objects require suitable alignment; table bytes may
 * be unaligned. Callers supply actual backing, writable outputs and state,
 * and lifetime. The table tail beyond 128 bytes is always preserved.
 *
 * Preflight validates exact profiles and every reachable observer before
 * any effect. Host errors preserve every object and emit no calls. Successful
 * host execution stores the actual raw word only after release, or directly
 * for the invalid-handle profile. Wrapped-index raw 0xFFFFFFFC retains the
 * initial fill and marker store. The raw-result input value is unconstrained.
 *
 * Observers receive function identities, semantic argument words and fixed
 * replies: zero for mutex calls and 7 for service. They return normally,
 * preserve arguments and all API objects, keep mutable bookkeeping and
 * indirect storage separate, and avoid reentry, concurrent mutation and
 * hardware access. Identities and numeric base/offset words never become
 * host pointers. No pointer is retained, allocated or freed. This operation
 * prepares software state only; runtime acquisition and application remain
 * outside the contract.
 */

#endif
