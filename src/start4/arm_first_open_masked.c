/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "arm_first_open_masked.h"
#include "arm_first_open_internal.h"
#include "driver_open_internal.h"
#include "mask_operations.h"

struct inputs_alignment { char prefix; struct arm_first_open_masked_inputs value; };
struct state_alignment { char prefix; struct arm_first_open_masked_state value; };
struct buffer_alignment { char prefix; struct suspend_buffer value; };
struct view_alignment { char prefix; struct suspend_byte_view value; };
struct replies_alignment { char prefix; struct arm_first_open_reply_plan value; };
struct reads_alignment { char prefix; struct arm_first_open_read_plan value; };
struct p16_alignment { char prefix; struct suspend_p16_read_plan value; };
struct observers_alignment { char prefix; struct arm_first_open_masked_observers value; };
struct read_alignment { char prefix; struct arm_first_open_read value; };
struct word_alignment { char prefix; uint32_t value; };

#define ALIGNMENT(name) offsetof(struct name##_alignment, value)

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
    uint32_t *raw_result) {
    struct suspend_registration_span spans[19] = {
        {inputs, sizeof(*inputs), ALIGNMENT(inputs)},
        {state, sizeof(*state), ALIGNMENT(state)},
        {records, records_length, 1},
        {masks, sizeof(*masks), ALIGNMENT(buffer)},
        {object, sizeof(*object), ALIGNMENT(buffer)},
        {name, name != NULL ? sizeof(*name) : 0, ALIGNMENT(view)},
        {logging, logging != NULL ? sizeof(*logging) : 0, 1},
        {handle_output, sizeof(*handle_output), ALIGNMENT(word)},
        {replies, sizeof(*replies), ALIGNMENT(replies)},
        {reads, sizeof(*reads), ALIGNMENT(reads)},
        {p16_reads, sizeof(*p16_reads), ALIGNMENT(p16)},
        {observers, sizeof(*observers), ALIGNMENT(observers)},
        {raw_result, sizeof(*raw_result), ALIGNMENT(word)},
        {NULL, 0, 1}, {NULL, 0, 1}, {NULL, 0, 1},
        {NULL, 0, ALIGNMENT(word)}, {NULL, 0, ALIGNMENT(read)},
        {NULL, 0, ALIGNMENT(word)}};
    struct arm_first_open_observers prefix_observers;
    struct suspend_registration_observers registrar_observers;
    struct arm_first_open_prepared prefix;
    struct suspend_registration_prepared registrar = {{NULL, 0}, {NULL, 0}, 0, 0, 0};
    struct driver_open_inputs driver;
    struct mask_byte_view mask_view;
    enum arm_first_open_status status;
    enum suspend_status nested_status;
    enum mask_status mask_status;
    uint32_t nested_raw, mutex_identity = UINT32_C(0xE403B470);

    nested_status = suspend_registration_validate_spans(spans, 13);
    if (nested_status != SUSPEND_OK)
        return (enum arm_first_open_status)nested_status;
    if (records == NULL || masks->bytes == NULL || object->bytes == NULL
            || replies->words == NULL || reads->entries == NULL || p16_reads->words == NULL)
        return ARM_FIRST_OPEN_INVALID;
    if (records_length < ARM_OBJECT_RECORD_BYTES || records_length > UINT32_MAX
            || masks->length < 8 || masks->length > UINT32_MAX
            || object->length < SUSPEND_OBJECT_BYTES || object->length > UINT32_MAX
            || (name != NULL && name->length > UINT32_MAX)
            || replies->count > SIZE_MAX / sizeof(*replies->words)
            || reads->count > SIZE_MAX / sizeof(*reads->entries)
            || p16_reads->count == 0 || p16_reads->count > UINT32_MAX / sizeof(*p16_reads->words))
        return ARM_FIRST_OPEN_BOUNDS;
    spans[13].pointer = masks->bytes;
    spans[13].length = masks->length;
    spans[14].pointer = object->bytes;
    spans[14].length = object->length;
    if (name != NULL) {
        spans[15].pointer = name->bytes;
        spans[15].length = name->length;
    }
    spans[16].pointer = replies->words;
    spans[16].length = replies->count * sizeof(*replies->words);
    spans[17].pointer = reads->entries;
    spans[17].length = reads->count * sizeof(*reads->entries);
    spans[18].pointer = p16_reads->words;
    spans[18].length = p16_reads->count * sizeof(*p16_reads->words);
    nested_status = suspend_registration_validate_spans(spans, 19);
    if (nested_status != SUSPEND_OK)
        return (enum arm_first_open_status)nested_status;

    prefix_observers.acquire = observers->acquire;
    prefix_observers.registrar_acquire = observers->registrar_acquire;
    prefix_observers.registrar_diagnostic = observers->registrar_diagnostic;
    prefix_observers.registrar_release = observers->registrar_release;
    prefix_observers.version = observers->version;
    prefix_observers.service = NULL;
    prefix_observers.read = observers->read;
    prefix_observers.context = observers->context;
    status = arm_first_open_prefix_preflight(&inputs->first_open, &state->first_open,
        records, records_length, replies, reads, &prefix_observers, &prefix);
    if (status != ARM_FIRST_OPEN_OK)
        return status;
    if (prefix.object_profile == 2 || state->first_open.selected_callback == 0
            || (inputs->version & UINT32_C(0x40)) == 0 || inputs->secondary != 0)
        return ARM_FIRST_OPEN_UNSUPPORTED;
    if (replies->count < 5)
        return ARM_FIRST_OPEN_BOUNDS;
    if (replies->count > 5 || replies->words[4] != 0)
        return ARM_FIRST_OPEN_UNSUPPORTED;
    if (observers->write == NULL || observers->release == NULL)
        return ARM_FIRST_OPEN_INVALID;

    driver.sr = inputs->sr & UINT32_C(0xFFFFFFF0);
    if (state->first_open.selected_callback == UINT32_C(0x0EC3EA48))
        driver.sr |= 6;
    registrar_observers.di = observers->di;
    registrar_observers.read = observers->p16_read;
    registrar_observers.write = observers->p16_write;
    registrar_observers.context = observers->context;
    nested_status = driver_open_preflight(&driver, masks, NULL, object, name, logging,
        p16_reads, &registrar_observers, &nested_raw, &registrar);
    if (nested_status != SUSPEND_OK)
        return (enum arm_first_open_status)nested_status;
    mask_view.bytes = masks->bytes;
    mask_view.length = masks->length;
    mask_status = mask_predicate(UINT32_C(0x5E), &mask_view, &nested_raw);
    if (mask_status != MASK_OK)
        return (enum arm_first_open_status)mask_status;
    if (nested_raw == 0)
        return ARM_FIRST_OPEN_UNSUPPORTED;

    arm_first_open_prefix_validated(&inputs->first_open, &state->first_open, records,
        inputs->version, NULL, replies, reads, &prefix_observers, &prefix, &nested_raw);
    observers->write(observers->context, UINT32_C(0x0EC59E34), UINT32_C(0x7E00B9BC), 4, 8);
    state->driver_words[0] = 1;
    state->driver_words[2] = 1;
    state->driver_words[1] = 0;
    state->driver_words[3] = 0;
    observers->write(observers->context, UINT32_C(0x0EC59E44), UINT32_C(0x7E00B9BC), 4, 1);
    state->driver_table = UINT32_C(0x0EDFA4DC);
    driver_open_validated(&driver, masks, NULL, object, p16_reads,
                          &registrar_observers, &nested_raw, &registrar);
    /* The accepted mask branch returns before the opaque word is used. */
    (void)mask_predicate(UINT32_C(0x5E), &mask_view, &nested_raw);
    observers->release(observers->context, UINT32_C(0x0ED64D3A),
                       &mutex_identity, 1, replies->words[4]);
    *raw_result = nested_raw;
    return ARM_FIRST_OPEN_OK;
}
