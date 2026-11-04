/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_CLOCK_REQUEST_H
#define OPEN27XX_CLOCK_REQUEST_H

#include <stddef.h>
#include <stdint.h>

#define CLOCK_REQUEST_STATE_BYTES 1156u
#define CLOCK_REQUEST_MISS_BYTES 86u
#define CLOCK_REQUEST_OUTPUT_BYTES 8u

enum clock_request_status {
    CLOCK_REQUEST_OK = 0,
    CLOCK_REQUEST_INVALID = -1,
    CLOCK_REQUEST_UNSUPPORTED = -2,
    CLOCK_REQUEST_BOUNDS = -3,
    CLOCK_REQUEST_OVERLAP = -4
};

enum clock_request_boundary {
    CLOCK_REQUEST_ACQUIRE,
    CLOCK_REQUEST_DIAGNOSTIC,
    CLOCK_REQUEST_SOURCE,
    CLOCK_REQUEST_CLOCK,
    CLOCK_REQUEST_DIVIDER,
    CLOCK_REQUEST_NOTIFY,
    CLOCK_REQUEST_RELEASE
};

/* Providers observe literal replies; they preserve all API objects. */
typedef void (*clock_request_provider_fn)(
    void *context, enum clock_request_boundary boundary, uint32_t identity,
    const uint32_t *arguments, size_t count, uint32_t reply);

typedef void (*clock_request_open_fn)(
    void *context, uint32_t table, uint32_t argument, uint8_t *handle_output,
    uint32_t reply, uint32_t handle_write);

struct clock_request_state {
    uint32_t initialized;
    uint8_t descriptor_miss[CLOCK_REQUEST_MISS_BYTES];
    uint32_t divider_miss;
    uint32_t source_miss;
};

struct clock_request_inputs {
    uint32_t identifier;
    uint64_t requested;
    uint32_t argument3;
    uint32_t argument4;
    uint32_t skip;
    uint32_t selection;
    uint32_t comparison_handle;
    uint32_t override_heads[3];
    uint32_t planner_input;
    uint32_t mutex_identity;
};

struct clock_request_plan {
    clock_request_provider_fn acquire;
    clock_request_provider_fn diagnostic;
    clock_request_provider_fn source;
    clock_request_provider_fn clock;
    clock_request_provider_fn divider;
    clock_request_provider_fn notify;
    clock_request_provider_fn release;
    void *context;
    uint32_t source_reply;
    uint32_t clock_reply;
    uint32_t divider_replies[2];
    uint32_t notification_replies[2];
};

struct clock_request_open_plan {
    clock_request_open_fn open;
    void *context;
    uint32_t reply;
    uint32_t handle_write;
};

enum clock_request_status clock_request_execute(
    const struct clock_request_inputs *inputs,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *state,
    uint8_t *output, size_t output_length,
    const struct clock_request_plan *plan, uint32_t *raw_return);

enum clock_request_status clock_request_initialize(
    uint32_t selection, uint32_t table,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *state,
    const struct clock_request_open_plan *plan, uint32_t *raw_return);

enum clock_request_status clock_request_execute_cold(
    const struct clock_request_inputs *inputs, uint32_t table,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *state,
    uint8_t *output, size_t output_length,
    const struct clock_request_open_plan *open_plan,
    const struct clock_request_plan *plan, uint32_t *raw_return);

/*
 * Host errors preserve all state/output bytes and emit no boundary call.
 * The manager uses the documented little-endian layout; rates are unsigned
 * 64-bit words. Only its first 1156 bytes and the first 8 output bytes change.
 * The entire declared extents and typed API objects must be disjoint.
 * Typed objects need alignment, backing and lifetime supplied by the caller.
 * Manager/output byte buffers need no alignment. Providers return normally,
 * use separate bookkeeping storage, and cannot reenter or access hardware.
 * Identity words label observations; they are never executable host pointers.
 * The initializer supplies manager+8 to its observer and applies the declared
 * handle write after it returns. It never continues into a request.
 * The cold request preflights both plans before clearing the manager and
 * composes only the documented zero-open-result first-request profile.
 * See README.md for the fixed profiles, callback arguments and scope limits.
 */

#endif
