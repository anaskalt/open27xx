/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_CLOCK_DRIVER_H
#define OPEN27XX_CLOCK_DRIVER_H

#include <stddef.h>
#include <stdint.h>

enum clock_driver_status {
    CLOCK_DRIVER_OK = 0,
    CLOCK_DRIVER_INVALID = -1,
    CLOCK_DRIVER_UNSUPPORTED = -2,
    CLOCK_DRIVER_BOUNDS = -3,
    CLOCK_DRIVER_OVERLAP = -4
};

enum clock_driver_event {
    CLOCK_DRIVER_MMIO_READ,
    CLOCK_DRIVER_MMIO_WRITE,
    CLOCK_DRIVER_NATIVE_READ,
    CLOCK_DRIVER_NATIVE_WRITE
};

/* Observers preserve every API object and cannot access hardware. */
typedef void (*clock_driver_observe_fn)(void *context,
    enum clock_driver_event event, uint32_t address, uint32_t word);

struct clock_driver_observer {
    clock_driver_observe_fn observe;
    void *context;
};

struct clock_driver_read {
    uint32_t address;
    uint32_t word;
};

struct clock_driver_plan {
    const struct clock_driver_read *reads;
    size_t count;
    struct clock_driver_observer observer;
};

struct clock_source_inputs {
    uint32_t handle;
    uint32_t comparison_handle;
    uint32_t source;
    uint64_t requested;
    uint32_t selection;
    uint32_t helper_selection;
    uint32_t helper_gate;
    uint32_t helper_input;
    uint8_t diagnostic;
};

struct clock_source_state {
    uint32_t marker;
    uint64_t requested;
    uint64_t cached;
};

struct clock_word_inputs {
    uint32_t handle;
    uint32_t comparison_handle;
    uint32_t clock;
    uint32_t source;
    uint32_t divider;
    uint32_t factor_bits;
    uint32_t argument5;
    uint8_t diagnostic;
    uint8_t enable;
};

struct clock_divider_inputs {
    uint32_t handle;
    uint32_t comparison_handle;
    uint32_t divider;
    uint32_t count;
    uint32_t selection;
};

struct clock_divider_state {
    uint32_t marker;
    uint32_t count;
};

enum clock_driver_status clock_source_program(
    const struct clock_source_inputs *inputs, struct clock_source_state *state,
    const struct clock_driver_plan *plan, uint32_t *raw_return);

enum clock_driver_status clock_word_program(
    const struct clock_word_inputs *inputs, uint32_t *cell,
    const struct clock_driver_observer *observer, uint32_t *raw_return);

enum clock_driver_status clock_divider_program(
    const struct clock_divider_inputs *inputs, struct clock_divider_state *state,
    const struct clock_driver_plan *plan, uint32_t *raw_return);

/*
 * All declared spans and typed objects must be disjoint and remain valid,
 * backed and correctly aligned throughout the operation. The caller owns
 * their storage. The immutable plan contains literal reads, never writeback.
 * Host errors preserve every state/output byte and emit no observation.
 * Observers run synchronously, return normally and preserve inputs, plans,
 * state, cell and raw output. They may use separate bookkeeping storage.
 * They cannot reenter an operation or mutate the native cell asynchronously.
 * Native-write observations follow the cell store; all observations precede
 * the final raw-return store. Address words identify events, not host pointers.
 * Mismatched profiles need no observer or reads, but retain required API
 * objects. See README.md for the exact finite profiles and scope limits.
 */

#endif
