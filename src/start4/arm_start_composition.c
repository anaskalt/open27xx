/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "arm_start_composition.h"
#include "resource_composition_internal.h"

enum clock_driver_status arm_start_composition_execute(
    const struct arm_start_composition_inputs *inputs,
    struct arm_control_start_state *start,
    uint8_t *records, size_t records_length,
    struct resource_composition_state *resource,
    uint8_t *manager, size_t manager_length,
    struct clock_request_state *clock_state,
    struct clock_source_state *source, struct clock_divider_state *divider,
    uint32_t *cell, uint8_t *scratch, size_t scratch_length,
    const struct arm_start_composition_plan *plan,
    struct arm_start_composition_result *result) {
    struct resource_composition_span spans[17] = {
        {inputs, sizeof(*inputs)}, {start, sizeof(*start)}, {records, records_length},
        {resource, sizeof(*resource)}, {manager, manager_length},
        {clock_state, sizeof(*clock_state)}, {source, sizeof(*source)},
        {divider, sizeof(*divider)}, {cell, sizeof(*cell)}, {scratch, scratch_length},
        {plan, sizeof(*plan)}, {result, sizeof(*result)},
        {NULL, 0}, {NULL, 0}, {NULL, 0}, {NULL, 0}, {NULL, 0}};
    const struct clock_driver_plan *reads[5];
    struct arm_start_composition_result actual;
    uint32_t mutex_identity;
    size_t index;
    enum clock_driver_status status = resource_composition_validate_spans(spans, 12);
    if (status != CLOCK_DRIVER_OK)
        return status;
    reads[0] = &plan->resource.clock.source;
    reads[1] = &plan->resource.clock.divider;
    reads[2] = &plan->resource.control[0];
    reads[3] = &plan->resource.control[1];
    reads[4] = &plan->resource.final;
    for (index = 0; index < 5; ++index) {
        if (reads[index]->count > SIZE_MAX / sizeof(*reads[index]->reads))
            return CLOCK_DRIVER_BOUNDS;
        spans[12 + index].pointer = reads[index]->reads;
        spans[12 + index].length = reads[index]->count * sizeof(*reads[index]->reads);
    }
    status = resource_composition_validate_spans(spans, 17);
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (inputs->handle != ARM_CONTROL_HANDLE || start->open_count != 1
            || start->mapping_marker != 1 || start->active != 0
            || start->resource_object == 0
            || start->resource_object != inputs->resource.request.identity)
        return CLOCK_DRIVER_UNSUPPORTED;
    mutex_identity = inputs->mutex_identity;
    if (mutex_identity == inputs->resource.request.mutex_identity
            || mutex_identity == inputs->resource.outer_mutex
            || mutex_identity == inputs->resource.resource_mutex
            || mutex_identity == inputs->resource.clock.request.mutex_identity)
        return CLOCK_DRIVER_UNSUPPORTED;
    if (plan->acquire == NULL || plan->release == NULL)
        return CLOCK_DRIVER_INVALID;
    status = resource_composition_preflight(&inputs->resource, records, records_length,
        resource, manager, manager_length, clock_state, source, divider, cell,
        scratch, scratch_length, &plan->resource, &result->resource);
    if (status != CLOCK_DRIVER_OK)
        return status;

    plan->acquire(plan->context, 0x0ED64D02, &mutex_identity, 1, 0);
    /* Whole-path preflight and preserving observers make the dispatch infallible. */
    (void)resource_composition_execute(&inputs->resource, records, records_length,
        resource, manager, manager_length, clock_state, source, divider, cell,
        scratch, scratch_length, &plan->resource, &actual.resource);
    actual.higher_raw = actual.resource.resource_raw;
    if (actual.higher_raw == 0)
        start->active = 1;
    plan->release(plan->context, 0x0ED64D3A, &mutex_identity, 1, 0);
    *result = actual;
    return CLOCK_DRIVER_OK;
}
