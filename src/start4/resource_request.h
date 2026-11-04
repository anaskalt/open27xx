/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_RESOURCE_REQUEST_H
#define OPEN27XX_RESOURCE_REQUEST_H

#include <stddef.h>
#include <stdint.h>

#define RESOURCE_REQUEST_RECORDS 32u
#define RESOURCE_REQUEST_BIT UINT32_C(0x00800000)
#define RESOURCE_REQUEST_DEPENDENCIES UINT32_C(0x180)

enum resource_request_status {
    RESOURCE_REQUEST_OK = 0,
    RESOURCE_REQUEST_INVALID = -1,
    RESOURCE_REQUEST_UNSUPPORTED = -2,
    RESOURCE_REQUEST_BOUNDS = -3,
    RESOURCE_REQUEST_OVERLAP = -4
};

enum resource_request_outcome_kind {
    RESOURCE_REQUEST_RETURNED = 0,
    RESOURCE_REQUEST_STOPPED = 1
};

struct resource_request_outcome {
    enum resource_request_outcome_kind kind;
    union {
        uint32_t raw_return;
        uint32_t stop_flag;
    } value;
};

enum resource_request_boundary {
    RESOURCE_REQUEST_DIAGNOSTIC,
    RESOURCE_REQUEST_ACQUIRE,
    RESOURCE_REQUEST_RELEASE,
    RESOURCE_REQUEST_ENABLE,
    RESOURCE_REQUEST_CONTEXT
};

/* Providers observe a declared literal reply; they do not choose another. */
typedef void (*resource_request_provider_fn)(
    void *context, enum resource_request_boundary boundary,
    const uint32_t *arguments, size_t count, uint32_t reply);

struct resource_request_context {
    uint32_t descriptor;
    uint32_t callback;
    uint32_t opaque;
    uint32_t reply;
    resource_request_provider_fn provider;
    void *context;
};

struct resource_request_record {
    uint32_t self;
    uint32_t requests;
};

struct resource_request_state {
    uint32_t held;
    uint32_t aggregate;
};

struct resource_request_inputs {
    uint32_t object_present;
    uint32_t identity;
    size_t record_index;
    uint32_t logical_index;
    uint32_t argument2;
    uint32_t argument3;
    uint32_t selection;
    uint32_t handle;
    uint32_t mutex_identity;
};

struct resource_request_plan {
    resource_request_provider_fn diagnostic;
    resource_request_provider_fn acquire;
    resource_request_provider_fn release;
    resource_request_provider_fn enable;
    void *context;
    uint32_t enable_replies[2];
    const struct resource_request_context *check_context;
};

enum resource_request_status resource_request_dependency(
    uint32_t logical_index, uint32_t selection, uint32_t *result);

enum resource_request_status resource_request_context_call(
    const struct resource_request_context *context,
    struct resource_request_outcome *outcome);

enum resource_request_status resource_request_check(
    uint32_t condition, const struct resource_request_context *context,
    struct resource_request_outcome *outcome);

enum resource_request_status resource_request_execute(
    const struct resource_request_inputs *inputs,
    struct resource_request_record *records, size_t record_count,
    struct resource_request_state *state,
    const struct resource_request_plan *plan,
    struct resource_request_outcome *outcome);

/*
 * Host errors preserve all state and output and emit no boundary call.
 * Returned and stopped outcomes are successful host operations. A stopped
 * outcome has stop_flag 1 and no raw return word; it preserves prior effects.
 * All typed objects require correct backing, alignment and lifetime. Providers
 * return normally, preserve arguments/state/output, and cannot reenter or use
 * hardware. Their bookkeeping storage must be separate from all API objects.
 * Accessed API objects are disjoint; address extents and overlaps are checked.
 * The caller establishes actual backing, alignment and writable storage.
 * Context is inspected only on a reachable false condition. Identity words
 * are opaque tokens, never pointers. See README.md for routing and limits.
 */

#endif
