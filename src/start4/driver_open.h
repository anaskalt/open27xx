/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_DRIVER_OPEN_H
#define OPEN27XX_DRIVER_OPEN_H

#include "suspend_registrar.h"

struct driver_open_inputs {
    uint32_t sr;
};

enum suspend_status driver_open_register(
    const struct driver_open_inputs *inputs,
    const struct suspend_buffer *masks, const struct suspend_byte_view *source,
    const struct suspend_buffer *object, const struct suspend_byte_view *name,
    const uint8_t *logging, const struct suspend_p16_read_plan *reads,
    const struct suspend_registration_observers *observers, uint32_t *raw_result);

/*
 * The bounded contract is in docs/bcm2711/driver-open-masks.md. Inputs, masks,
 * object, reads, observers and raw_result are required. Masks contains from
 * 8 through UINT32_MAX bytes. Source is optional: a NULL descriptor or NULL
 * bytes with zero length skips the copy. Present source bytes require from
 * 8 through UINT32_MAX bytes. Both little-endian words are read, high then
 * low, before writing low then high to masks. Remaining mask bytes and all
 * source bytes are preserved. Neither byte view needs alignment.
 *
 * Registration uses the actual suspend registrar with fixed first key 1,
 * callback token 0x0ED004C6, cookie zero and incoming inputs->sr. Callback
 * tokens are opaque identities and are never invoked. Object, name, logging,
 * reads and observers retain the complete suspend_register contract. Name
 * bytes are caller supplied; no literal basename is embedded. Capacity and
 * match paths preserve optional mask writes. The registrar's raw result
 * stays private; raw_result becomes zero only after registration completes
 * and the final p16 write observer returns normally.
 *
 * Complete shared read-only preflight precedes every mask/object store,
 * observation and result publication. Every caller-supplied object and full
 * declared span is pairwise disjoint, including unused descriptors, views,
 * tails and raw_result. Typed objects and read words need natural alignment.
 * All byte extents are at most UINT32_MAX and must not wrap host addresses.
 * A NULL byte pointer with nonzero length is invalid. Missing storage,
 * invalid source presence and typed misalignment return SUSPEND_INVALID;
 * invalid lengths or address arithmetic return SUSPEND_BOUNDS; intersecting
 * spans return SUSPEND_OVERLAP. Registrar validation retains its categories.
 * Host errors preserve every supplied byte and emit no observations.
 *
 * DI and p16 reads observe completed masks and the original object; the final
 * write observes completed masks and object. Every observer sees the incoming
 * raw_result. All software observations require the registrar's explicit
 * no-interrupt-arrival premise and do not establish physical IRQ access.
 * Callers provide live readable/writable backing with no concurrent mutation.
 * Observers return normally, preserve inputs/API objects, avoid reentry and
 * hardware access, and keep mutable bookkeeping disjoint from API storage.
 * Read-only context references may inspect masks, object and raw_result.
 * Indirect observer storage and behavior remain caller premises. No pointer
 * is retained, allocated or freed.
 */

#endif
