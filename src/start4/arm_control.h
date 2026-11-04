/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_CONTROL_H
#define OPEN27XX_ARM_CONTROL_H

#include <stddef.h>
#include <stdint.h>

#define ARM_CONTROL_HANDLE UINT32_C(0x61726D11)

/* Host statuses are separate from the function result written on completion. */
enum arm_control_status {
    ARM_CONTROL_OK = 0,
    ARM_CONTROL_INVALID = -1,
    ARM_CONTROL_UNSUPPORTED = -2,
    ARM_CONTROL_OVERLAP = -3
};

/* Driver and cached words are opaque values, never native pointers. */
struct arm_control_configuration {
    uint32_t driver;
    uint32_t selection;
    uint32_t handle;
    uint32_t service_index;
    uint32_t word_a;
    uint32_t word_b;
    uint32_t word_c;
    uint32_t word_d;
};

typedef uint32_t (*arm_control_service_fn)(
    void *context, uint32_t service_index, uint32_t value, uint32_t offset,
    uint32_t argument3, uint32_t argument4, uint32_t argument5);

/* A missing driver preserves incoming_result without calling the service. */
enum arm_control_status arm_control_configure(
    const struct arm_control_configuration *configuration,
    uint32_t incoming_result, arm_control_service_fn service, void *context,
    uint32_t *result);

struct arm_control_start_state {
    uint32_t open_count;
    uint32_t mapping_marker;
    uint32_t active;
    uint32_t resource_object;
};

typedef uint32_t (*arm_control_mutex_fn)(void *context, void *mutex);
typedef uint32_t (*arm_control_resource_fn)(
    void *context, uint32_t resource_object, uint32_t resource,
    uint32_t argument2, uint32_t argument3);

struct arm_control_start_callbacks {
    arm_control_mutex_fn acquire;
    arm_control_mutex_fn release;
    arm_control_resource_fn request;
    void *context;
};

/* Mutex identity is native; resource_object remains an opaque 32-bit value. */
enum arm_control_status arm_control_start(
    struct arm_control_start_state *state, uint32_t handle, void *mutex,
    const struct arm_control_start_callbacks *callbacks, uint32_t *result);

/*
 * All objects remain caller-owned and valid for the call. Callbacks must not
 * modify configuration, state, result or callback tables, reenter the same
 * state or access hardware.
 * Required objects must be aligned and have their declared extents. Result,
 * state, callback table, context storage and mutex storage must not overlap.
 * The helpers check required null arguments and result/state/table overlap;
 * the caller enforces lifetime and the remaining separation requirements.
 * Service and mutex return words are ignored. Resource replies are function
 * results, including nonzero values. Callbacks must return normally; these
 * boundaries provide no transport-error channel or failure recovery. Host
 * validation errors leave result and state untouched and emit no callback.
 * See README.md for routing and callback contracts.
 */

#endif
