/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARM_FIRST_OPEN_MASKED_H
#define OPEN27XX_ARM_FIRST_OPEN_MASKED_H

#include "arm_first_open.h"
#include "suspend_registrar.h"

struct arm_first_open_masked_inputs {
    struct arm_first_open_inputs first_open;
    uint32_t sr;
    uint32_t version;
    uint32_t secondary;
    uint32_t opaque;
};

struct arm_first_open_masked_state {
    struct arm_first_open_state first_open;
    uint32_t driver_table;
    /* Ascending word offsets from the documented software-state base. */
    uint32_t driver_words[4];
};

struct arm_first_open_masked_observers {
    arm_object_observe_fn acquire;
    arm_object_observe_fn registrar_acquire;
    arm_object_observe_fn registrar_diagnostic;
    arm_object_observe_fn registrar_release;
    arm_first_open_version_fn version;
    arm_first_open_read_fn read;
    arm_first_open_read_fn write;
    arm_object_observe_fn release;
    suspend_di_fn di;
    suspend_p16_fn p16_read;
    suspend_p16_fn p16_write;
    void *context;
};

enum arm_first_open_status arm_first_open_masked(
    const struct arm_first_open_masked_inputs *inputs,
    struct arm_first_open_masked_state *state,
    uint8_t *records, size_t records_length,
    const struct suspend_buffer *masks, const struct suspend_buffer *object,
    const struct suspend_byte_view *name, const uint8_t *logging,
    uint32_t *handle_output, const struct arm_first_open_reply_plan *replies,
    const struct arm_first_open_read_plan *reads,
    const struct suspend_p16_read_plan *p16_reads,
    const struct arm_first_open_masked_observers *observers,
    uint32_t *raw_result);

/*
 * The complete bounded contract is in docs/bcm2711/arm-first-open-masked.md.
 * All arguments except name and logging are required. Parameter words are
 * 0x80, 0x100, 0x200 or 0x400; parameter bytes are zero, one or two. Count
 * starts at zero. Object output and old callback start at 0xA5A5A5A5.
 * Records use a successful arm_object_register profile; selected callback
 * is 0x0EC3EA48 or 0x11223344. Other state words and configuration source
 * are arbitrary. VERSION has bit 6 set and secondary is zero. SR and the
 * opaque word are arbitrary immutable inputs. The opaque word never becomes
 * a host pointer or callable token.
 *
 * Records contain 896 through UINT32_MAX bytes. Masks contain 8 through
 * UINT32_MAX bytes and low mask bit 30 is set. Object contains 2936 through
 * UINT32_MAX bytes. The real driver-open computation has no mask source
 * and uses the full suspend registrar domain, including conditional name
 * and logging consumption. For insertion, absent name storage is INVALID;
 * a nonnull name byte pointer with zero length is BOUNDS. Unused views
 * remain subject to storage checks without numerical or string checks.
 *
 * Replies contains exactly five zeros. Reads contains one entry with PC
 * 0x0EC59E12, address 0x7E00B44C, size four and an arbitrary word. The p16
 * plan is nonempty: zero or more ones followed by one zero. Every observer
 * is required. One write observer receives both MMIO writes with size four.
 * Derived registrar SR clears the incoming low four bits and adds six for
 * the default callback, or zero for the prior callback. All observations
 * see the incoming raw result and unchanged handle. Raw one is published
 * only after higher release; all completed registration effects remain.
 *
 * Complete read-only preflight precedes every effect. Every supplied API
 * object and full declared span is pairwise disjoint, including unused
 * views, tails, plan arrays and outputs. Typed objects need natural
 * alignment; byte storage may be unaligned. NULL bytes require zero length
 * and are allowed only for unused views. Products and addresses cannot
 * wrap. Nested validation retains its INVALID, BOUNDS and OVERLAP statuses;
 * unsupported outer domains, clear masks and mismatched replies/reads use
 * UNSUPPORTED. Every host error preserves all storage and emits nothing.
 *
 * Callers provide backing, readability, writability and lifetime without
 * concurrent mutation. Observers return normally, preserve API storage,
 * avoid reentry and hardware access, and keep writable bookkeeping and
 * indirect writable references disjoint. Read-only context references may
 * inspect supplied state. No pointer is retained, allocated or freed. This
 * operation is separate from runtime and establishes no acquired handle.
 */

#endif
