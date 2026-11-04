/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "arm_control.h"

struct configuration_request {
    uint32_t offset;
    uint32_t value;
};

static int overlaps(const void *left, size_t left_length,
                    const void *right, size_t right_length) {
    uintptr_t a = (uintptr_t)left, b = (uintptr_t)right;
    return a < b ? b - a < left_length : a - b < right_length;
}

enum arm_control_status arm_control_configure(
    const struct arm_control_configuration *configuration,
    uint32_t incoming_result, arm_control_service_fn service, void *context,
    uint32_t *result) {
    struct configuration_request requests[7];
    size_t index, count;
    if (configuration == NULL || result == NULL)
        return ARM_CONTROL_INVALID;
    if (overlaps(configuration, sizeof(*configuration), result, sizeof(*result)))
        return ARM_CONTROL_OVERLAP;
    if (configuration->driver == 0) {
        *result = incoming_result;
        return ARM_CONTROL_OK;
    }
    if (configuration->selection != 1 || configuration->handle != ARM_CONTROL_HANDLE)
        return ARM_CONTROL_UNSUPPORTED;
    if (service == NULL)
        return ARM_CONTROL_INVALID;

    requests[0].offset = UINT32_C(0x41C);
    requests[0].value = UINT32_C(0xA);
    requests[1].offset = UINT32_C(0x08);
    requests[1].value = UINT32_C(0x3030);
    requests[2].offset = 0;
    requests[2].value = (configuration->word_a == 0 ? UINT32_C(0x1000) : 0)
        | (configuration->word_c != 0 ? UINT32_C(0x400) : 0);
    requests[3].offset = UINT32_C(0x4F5200);
    requests[3].value = UINT32_C(0x30);
    requests[4].offset = UINT32_C(0x4F5204);
    requests[4].value = (configuration->word_b != 0 ? UINT32_C(0xF) : 0)
        | (configuration->word_c != 0 ? UINT32_C(0xFFFF0) : 0);
    requests[5].offset = UINT32_C(0x4F5220);
    requests[5].value = UINT32_C(0x200)
        | (configuration->word_a == 0 ? UINT32_C(0x10) : 0);
    requests[6].offset = UINT32_C(0x4F520C);
    requests[6].value = UINT32_C(0xF);
    count = configuration->word_d != 0 ? 7 : 6;
    for (index = 0; index < count; ++index)
        (void)service(context, configuration->service_index, requests[index].value,
                      requests[index].offset, 0, 0, 0);
    *result = 0;
    return ARM_CONTROL_OK;
}

enum arm_control_status arm_control_start(
    struct arm_control_start_state *state, uint32_t handle, void *mutex,
    const struct arm_control_start_callbacks *callbacks, uint32_t *result) {
    uint32_t selected = UINT32_MAX;
    if (state == NULL || mutex == NULL || callbacks == NULL || result == NULL)
        return ARM_CONTROL_INVALID;
    if (overlaps(state, sizeof(*state), result, sizeof(*result))
            || overlaps(callbacks, sizeof(*callbacks), result, sizeof(*result))
            || overlaps(state, sizeof(*state), callbacks, sizeof(*callbacks)))
        return ARM_CONTROL_OVERLAP;
    if (callbacks->acquire == NULL || callbacks->release == NULL || callbacks->request == NULL)
        return ARM_CONTROL_INVALID;
    (void)callbacks->acquire(callbacks->context, mutex);

    if (handle == ARM_CONTROL_HANDLE && state->open_count != 0
            && state->mapping_marker != 0 && state->active == 0) {
        selected = callbacks->request(callbacks->context, state->resource_object, 23, 1, 1);
        if (selected == 0)
            state->active = 1;
    }
    (void)callbacks->release(callbacks->context, mutex);
    *result = selected;
    return ARM_CONTROL_OK;
}
