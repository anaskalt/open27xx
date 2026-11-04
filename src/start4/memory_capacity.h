/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_MEMORY_CAPACITY_H
#define OPEN27XX_MEMORY_CAPACITY_H

#include <stdint.h>

/* Host checks are separate from the raw class written on completion. */
enum memory_capacity_status {
    MEMORY_CAPACITY_OK = 0,
    MEMORY_CAPACITY_INVALID = -1,
    MEMORY_CAPACITY_OVERLAP = -2
};

typedef uint8_t (*memory_capacity_byte_fn)(
    void *context, uint32_t selector, uint32_t first_index,
    uint32_t second_index);

/* The caller selects the supported path with diagnostics disabled. */
enum memory_capacity_status memory_capacity_measure(
    memory_capacity_byte_fn service, void *context,
    uint32_t *size_mib, uint32_t *result_class);

/*
 * Both outputs are required, aligned, writable uint32_t objects that remain
 * valid throughout the call. They must not overlap each other or any mutable
 * callback storage. All storage remains caller-owned. The context may be null
 * if the callback accepts it; otherwise its objects must outlive both passes.
 * The helper checks required null arguments and output/output overlap before
 * any write or callback. The caller enforces lifetime, alignment and context
 * separation, including storage reached indirectly through the context.
 * Callbacks may update their own context and observe the outputs, but must
 * preserve the outputs and configuration, return normally and not reenter the
 * operation. Concurrent output/configuration mutation is unsupported.
 * All sixteen requests execute. size_mib contains 256 during every callback;
 * result_class remains unchanged until completion. Class 7 is a raw result,
 * not a host error. Host validation errors preserve both outputs and emit no
 * callback. See README.md for the bounded capacity contract.
 */

#endif
