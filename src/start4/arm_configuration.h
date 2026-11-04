/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_CONFIGURATION_H
#define OPEN27XX_ARM_CONFIGURATION_H

#include <stddef.h>
#include <stdint.h>

#define ARM_CONFIGURATION_HANDLE UINT32_C(0x61726D11)

enum arm_configuration_status {
    ARM_CONFIGURATION_OK = 0,
    ARM_CONFIGURATION_INVALID = -1,
    ARM_CONFIGURATION_UNSUPPORTED = -2,
    ARM_CONFIGURATION_BOUNDS = -3,
    ARM_CONFIGURATION_OVERLAP = -4
};

struct arm_configuration_inputs {
    uint32_t handle;
    uint32_t control;
};

struct arm_configuration_reply_plan {
    const uint32_t *words;
    size_t count;
};

typedef void (*arm_configuration_observe_fn)(
    void *context, uint32_t entry, const uint32_t *arguments,
    size_t count, uint32_t reply);

/* The destination is an ordinary register index: 2 identifies r2. */
typedef void (*arm_configuration_version_fn)(
    void *context, uint32_t site, uint32_t destination, uint32_t word);

struct arm_configuration_observers {
    arm_configuration_observe_fn acquire;
    arm_configuration_version_fn version;
    arm_configuration_observe_fn service;
    arm_configuration_observe_fn release;
    void *context;
};

enum arm_configuration_status arm_configuration_execute(
    const struct arm_configuration_inputs *inputs, uint32_t *configuration,
    const uint32_t *cpu_word, const uint32_t *service_index,
    const struct arm_configuration_reply_plan *replies,
    const struct arm_configuration_observers *observers, uint32_t *raw_result);

/*
 * Only the two paired profiles in arm-configuration.md apply: handle
 * 0x61726D11, control 1 and initial configuration 0x1230FC1B. CPU word 0
 * requires service index 1, replies [0,7,0] and all four observers. CPU word
 * 0x40 requires replies [0,0], acquire/VERSION/release, and no service index.
 * A supplied unused index retains its full storage span without content
 * access. An available unused service observer is not an extra reply.
 * VERSION is a distinct instruction-result observation, with no reply.
 *
 * Every pointer except service_index is required, including replies->words.
 * All typed objects and the full count-word reply array are disjoint.
 * Preflight checks pointers, address/size wrap, overlap, the exact profile,
 * every reply and all reachable observers before any effect. A short reply
 * count is BOUNDS; an extra count or different word is UNSUPPORTED. INVALID
 * covers missing required storage or observers; OVERLAP covers intersecting
 * declared objects. Every host error preserves all objects and emits nothing.
 * Typed alignment, actual backing, writable configuration/result storage and
 * lifetime are caller requirements. The CPU word and reply plan are immutable.
 *
 * Acquire sees the initial configuration; VERSION, service and release see
 * its bit 6 set. Every observer sees the incoming raw_result, which receives
 * zero only after release. Native identities are opaque tokens, not callable
 * addresses or host pointers. No pointer is retained, allocated or freed.
 * Observers return normally, preserve all API objects and arguments, avoid
 * reentry, concurrent mutation and hardware access, and keep writable
 * bookkeeping separate. Read-only context references may inspect API state.
 */

#endif
