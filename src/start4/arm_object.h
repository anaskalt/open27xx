/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_OBJECT_H
#define OPEN27XX_ARM_OBJECT_H

#include <stddef.h>
#include <stdint.h>

#define ARM_OBJECT_RECORDS 32u
#define ARM_OBJECT_RECORD_SIZE 28u
#define ARM_OBJECT_RECORD_BYTES 896u
#define ARM_OBJECT_RECORD_BASE UINT32_C(0xE40DA4C4)
#define ARM_OBJECT_METADATA0 UINT32_C(0x0EC59E8C)
#define ARM_OBJECT_METADATA1 UINT32_C(0x158)
#define ARM_OBJECT_HANDLE UINT32_C(0x61726D11)

enum arm_object_status {
    ARM_OBJECT_OK = 0,
    ARM_OBJECT_INVALID = -1,
    ARM_OBJECT_UNSUPPORTED = -2,
    ARM_OBJECT_BOUNDS = -3,
    ARM_OBJECT_OVERLAP = -4
};

typedef void (*arm_object_observe_fn)(
    void *context, uint32_t entry, const uint32_t *arguments,
    size_t count, uint32_t reply);

struct arm_object_plan {
    arm_object_observe_fn acquire;
    arm_object_observe_fn diagnostic;
    arm_object_observe_fn release;
    void *context;
};

struct arm_object_open_state {
    uint32_t count;
    uint32_t object;
};

enum arm_object_status arm_object_register(
    uint32_t output_present, uint8_t *records, size_t records_length,
    uint32_t *object_output, const struct arm_object_plan *plan,
    uint32_t *raw_result);

enum arm_object_status arm_object_reopen(
    uint32_t parameter_word, uint8_t parameter_byte,
    struct arm_object_open_state *state, uint32_t *handle_output,
    const struct arm_object_plan *plan, uint32_t *raw_result);

/*
 * Only the complete finite profiles in arm-object.md apply. Registration
 * accepts the four documented present-output record profiles, fixed incoming
 * output 0xA5A5A5A5, fixed token base and fixed metadata. output_present is 0
 * or 1. Zero represents the vendor-null argument; records, object_output and
 * plan may then be NULL and records_length may be zero. Any supplied objects
 * and the complete declared records extent still participate in preflight;
 * their contents are not accessed on this path. NULL records require length
 * zero. Present output requires at least 896 record bytes and all pointers.
 *
 * Reopen requires parameter_word 0x400, parameter_byte 2, count 1, object
 * 0x11223344 and incoming handle output 0xA5A5A5A5. The object is an opaque
 * word, preserved without following it. No first-open operation is defined.
 *
 * Host errors preserve every object, including raw_result, and emit no calls.
 * raw_result is always required and receives the actual 0 or 0xFFFFFFFF only
 * after release, or directly for vendor-null registration. All declared
 * objects and full extents are disjoint. Preflight checks null pointers,
 * extent wrap, overlap, exact profiles and every reachable observer. Full
 * registration needs no diagnostic; vendor-null registration needs no calls.
 *
 * Record bytes need no alignment. Typed objects require suitable alignment;
 * callers establish actual backing, writability and lifetime for all storage.
 * Observers receive entry identities and only semantic arguments, with a
 * prescribed zero reply. They return normally, preserve API objects and
 * arguments, use separate bookkeeping and indirectly referenced storage, and
 * avoid reentry, concurrent mutation and hardware access. No pointer is
 * retained, allocated or freed. Tokens never become host pointers.
 */

#endif
