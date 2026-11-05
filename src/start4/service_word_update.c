/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "service_word_update.h"

#include <stddef.h>

struct request_alignment { char prefix; struct service_word_request value; };
struct plan_alignment { char prefix; struct service_word_plan value; };
struct observer_alignment { char prefix; struct service_word_observer value; };
struct word_alignment { char prefix; uint32_t value; };

#define ALIGNMENT(name) offsetof(struct name##_alignment, value)

struct span {
    const void *pointer;
    size_t length;
    size_t alignment;
};

static enum service_word_status validate_spans(const struct span *spans,
                                              size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        uintptr_t address = (uintptr_t)spans[left].pointer;
        if (spans[left].pointer == NULL || address % spans[left].alignment != 0)
            return SERVICE_WORD_INVALID;
        if (spans[left].length > UINTPTR_MAX - address)
            return SERVICE_WORD_BOUNDS;
    }
    for (left = 0; left < count; ++left) {
        uintptr_t a = (uintptr_t)spans[left].pointer;
        for (right = left + 1; right < count; ++right) {
            uintptr_t b = (uintptr_t)spans[right].pointer;
            if (a < b ? b - a < spans[left].length
                      : a - b < spans[right].length)
                return SERVICE_WORD_OVERLAP;
        }
    }
    return SERVICE_WORD_OK;
}

enum service_word_status service_word_update(
    const struct service_word_request *request,
    const struct service_word_plan *plan,
    const struct service_word_observer *observer, uint32_t *raw_result) {
    const struct span spans[] = {
        {request, sizeof(*request), ALIGNMENT(request)},
        {plan, sizeof(*plan), ALIGNMENT(plan)},
        {observer, sizeof(*observer), ALIGNMENT(observer)},
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)}};
    enum service_word_status status = validate_spans(spans, 4);
    uint32_t address, shift, mask, stored;
    if (status != SERVICE_WORD_OK)
        return status;
    if (observer->observe == NULL)
        return SERVICE_WORD_INVALID;
    address = UINT32_C(0x7E002010)
        + UINT32_C(0x800) * ((plan->version >> 16) & UINT32_C(0xF))
        + UINT32_C(4) * ((request->code >> 3) & UINT32_C(7));
    if (plan->read_address != address || plan->write_address != address)
        return SERVICE_WORD_INVALID;
    shift = UINT32_C(4) * (request->code & UINT32_C(7));
    mask = UINT32_C(0xF) << shift;
    stored = (plan->old_word & ~mask) | (uint32_t)(request->value << shift);

    observer->observe(observer->context, SERVICE_WORD_VERSION, 0, plan->version);
    observer->observe(observer->context, SERVICE_WORD_READ, address, plan->old_word);
    observer->observe(observer->context, SERVICE_WORD_WRITE, address, stored);
    *raw_result = 0;
    return SERVICE_WORD_OK;
}
