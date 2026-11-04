/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "clock_driver_internal.h"

#define PASSWORD UINT32_C(0x5A000000)
#define HANDLE UINT32_C(0xC10C1234)
#define RATE UINT64_C(1200000000)
#define REFERENCE UINT32_C(54000000)
#define CM UINT32_C(0x7E101170)
#define COMMAND UINT32_C(0x7E101100)
#define LOCK UINT32_C(0x7E101114)
#define ANA0 UINT32_C(0x7E1020F0)
#define ANA1 UINT32_C(0x7E1020F4)
#define ANA2 UINT32_C(0x7E1020F8)
#define ANA3 UINT32_C(0x7E1020FC)
#define CTRL UINT32_C(0x7E1021E0)
#define FRAC UINT32_C(0x7E1022E0)
#define ARM UINT32_C(0x7E1023E0)
#define CELL UINT32_C(0x0EE056B0)

struct span {
    const void *pointer;
    size_t length;
};

struct cursor {
    const struct clock_driver_plan *plan;
    size_t index;
    enum clock_driver_status status;
};

static enum clock_driver_status validate_spans(const struct span *spans,
                                              size_t count) {
    size_t left, right;
    for (left = 0; left < count; ++left) {
        if (spans[left].length == 0)
            continue;
        if (spans[left].pointer == NULL)
            return CLOCK_DRIVER_INVALID;
        if (spans[left].length > UINTPTR_MAX - (uintptr_t)spans[left].pointer)
            return CLOCK_DRIVER_BOUNDS;
    }
    for (left = 0; left < count; ++left) {
        uintptr_t a = (uintptr_t)spans[left].pointer;
        if (spans[left].length == 0)
            continue;
        for (right = left + 1; right < count; ++right) {
            uintptr_t b = (uintptr_t)spans[right].pointer;
            if (spans[right].length != 0
                    && (a < b ? b - a < spans[left].length
                              : a - b < spans[right].length))
                return CLOCK_DRIVER_OVERLAP;
        }
    }
    return CLOCK_DRIVER_OK;
}

static enum clock_driver_status validate_plan(struct span *spans,
                                              const struct clock_driver_plan *plan) {
    enum clock_driver_status status = validate_spans(spans, 4);
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (plan->count > SIZE_MAX / sizeof(*plan->reads))
        return CLOCK_DRIVER_BOUNDS;
    spans[4].pointer = plan->reads;
    spans[4].length = plan->count * sizeof(*plan->reads);
    return validate_spans(spans, 5);
}

static void expect_read(struct cursor *cursor, uint32_t address, uint32_t word) {
    if (cursor->status != CLOCK_DRIVER_OK)
        return;
    if (cursor->index == cursor->plan->count) {
        cursor->status = CLOCK_DRIVER_BOUNDS;
        return;
    }
    if (cursor->plan->reads[cursor->index].address != address
            || cursor->plan->reads[cursor->index].word != word)
        cursor->status = CLOCK_DRIVER_UNSUPPORTED;
    ++cursor->index;
}

static enum clock_driver_status finish_plan(const struct cursor *cursor) {
    if (cursor->status != CLOCK_DRIVER_OK)
        return cursor->status;
    return cursor->index == cursor->plan->count
        ? CLOCK_DRIVER_OK : CLOCK_DRIVER_UNSUPPORTED;
}

static void observe(const struct clock_driver_observer *observer,
                    enum clock_driver_event event, uint32_t address, uint32_t word) {
    observer->observe(observer->context, event, address, word);
}

static uint32_t read_mmio(struct cursor *cursor) {
    const struct clock_driver_read *read = &cursor->plan->reads[cursor->index++];
    observe(&cursor->plan->observer, CLOCK_DRIVER_MMIO_READ, read->address, read->word);
    return read->word;
}

static void write_mmio(struct cursor *cursor, uint32_t address, uint32_t word) {
    observe(&cursor->plan->observer, CLOCK_DRIVER_MMIO_WRITE, address, word);
}

static enum clock_driver_status validate_source_reads(const struct clock_driver_plan *plan) {
    struct cursor cursor = {plan, 0, CLOCK_DRIVER_OK};
    uint32_t control, analog, integer, index;
    int disabled, reconfigure, delayed, exhausted;
    if (plan->count < 2)
        return CLOCK_DRIVER_BOUNDS;
    if (plan->count > 2006)
        return CLOCK_DRIVER_UNSUPPORTED;
    analog = plan->reads[0].word;
    control = plan->reads[1].word;
    if (!((analog == 0 && (control == 0 || control == 0x20014
                                      || control == 0x20016 || control == 0x20018))
            || (analog == 0x4000 && control == 0x20016)))
        return CLOCK_DRIVER_UNSUPPORTED;
    disabled = control == 0;
    reconfigure = disabled || analog != 0;
    delayed = disabled && plan->count == 22;
    exhausted = !reconfigure && control == 0x20016 && plan->count == 2006;
    expect_read(&cursor, ANA2, analog);
    expect_read(&cursor, CTRL, control);
    if (disabled) {
        expect_read(&cursor, 0x7E102070, 0x00123456);
        expect_read(&cursor, 0x7E102074, 0x00234567);
        expect_read(&cursor, 0x7E102078, 0x00345678);
        expect_read(&cursor, 0x7E10207C, 0x00456789);
    }
    expect_read(&cursor, CM, 0x00345678);
    if (reconfigure) {
        expect_read(&cursor, ANA3, 0x00111111);
        expect_read(&cursor, ANA2, analog);
        expect_read(&cursor, ANA1, 0x00222222);
        expect_read(&cursor, ANA0, 0x00333333);
        expect_read(&cursor, CM, 0x00345678);
        if (delayed)
            expect_read(&cursor, COMMAND, 0x1234);
        expect_read(&cursor, COMMAND, 0);
        expect_read(&cursor, CM, 0x0034567A);
    }
    expect_read(&cursor, CTRL, control);
    integer = control & 0x3FF;
    while (!disabled && integer != 22) {
        expect_read(&cursor, CTRL, (control & ~UINT32_C(0x3FF)) | integer);
        integer = integer < 22 ? integer + 1 : integer - 1;
    }
    expect_read(&cursor, CM, reconfigure ? 0x0034577A : 0x00345678);
    for (index = 0; index < (exhausted ? 2000u : delayed ? 2u : 0u); ++index)
        expect_read(&cursor, LOCK, 0);
    if (!exhausted)
        expect_read(&cursor, LOCK, 0x200);
    expect_read(&cursor, CM, reconfigure ? 0x0034567A : 0x00345678);
    if (disabled)
        expect_read(&cursor, CTRL, 0x1016);
    return finish_plan(&cursor);
}

enum clock_driver_status clock_source_preflight(
    const struct clock_source_inputs *inputs, const struct clock_source_state *state,
    const struct clock_driver_plan *plan, const uint32_t *raw_return) {
    struct span spans[5] = {{inputs, sizeof(*inputs)}, {state, sizeof(*state)},
        {plan, sizeof(*plan)}, {raw_return, sizeof(*raw_return)}, {NULL, 0}};
    enum clock_driver_status status = validate_plan(spans, plan);
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (inputs->comparison_handle != HANDLE
            || (inputs->handle != HANDLE && inputs->handle != HANDLE + 1)
            || inputs->source != 2 || inputs->requested != RATE
            || inputs->selection != 1 || inputs->helper_selection != 0
            || inputs->helper_gate != 0 || inputs->helper_input != 1200
            || inputs->diagnostic != 0 || state->marker != 0x55667788
            || state->requested != UINT64_C(0x99AABBCC11223344)
            || state->cached != UINT64_C(1000000000))
        return CLOCK_DRIVER_UNSUPPORTED;
    if (inputs->handle != inputs->comparison_handle) {
        if (plan->count != 0)
            return CLOCK_DRIVER_UNSUPPORTED;
        return CLOCK_DRIVER_OK;
    }
    if (plan->observer.observe == NULL)
        return CLOCK_DRIVER_INVALID;
    return validate_source_reads(plan);
}

enum clock_driver_status clock_source_program(
    const struct clock_source_inputs *inputs, struct clock_source_state *state,
    const struct clock_driver_plan *plan, uint32_t *raw_return) {
    enum clock_driver_status status = clock_source_preflight(inputs, state, plan, raw_return);
    struct cursor cursor = {plan, 0, CLOCK_DRIVER_OK};
    uint32_t analog, control, initial_cm, word, ana0, integer, target, fraction;
    uint32_t count, locked = 0;
    uint64_t quotient;
    int enabled, reconfigure;
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (inputs->handle != inputs->comparison_handle) {
        *raw_return = UINT32_MAX;
        return CLOCK_DRIVER_OK;
    }
    state->marker = 1;
    state->requested = inputs->requested;
    state->cached = inputs->requested;
    quotient = (inputs->requested * (UINT64_C(1) << 20) + REFERENCE / 2) / REFERENCE;
    target = (uint32_t)(quotient >> 20);
    fraction = (uint32_t)quotient & 0xFFFFF;
    analog = read_mmio(&cursor);
    control = read_mmio(&cursor);
    enabled = (control & 0x20000) != 0;
    reconfigure = !enabled || (analog & 0x4000) != 0;
    if (!enabled) {
        word = read_mmio(&cursor);
        (void)read_mmio(&cursor);
        (void)read_mmio(&cursor);
        (void)read_mmio(&cursor);
        /* These fixed words belong only to the supplied selector-1 profile. */
        write_mmio(&cursor, 0x7E10207C, PASSWORD);
        write_mmio(&cursor, 0x7E102078, PASSWORD | 0x2C);
        write_mmio(&cursor, 0x7E102074, PASSWORD | 0x2C00);
        write_mmio(&cursor, 0x7E102070, PASSWORD | word);
    }
    initial_cm = read_mmio(&cursor);
    if (reconfigure) {
        (void)read_mmio(&cursor);
        (void)read_mmio(&cursor);
        (void)read_mmio(&cursor);
        ana0 = read_mmio(&cursor);
        word = read_mmio(&cursor);
        write_mmio(&cursor, CM, word | PASSWORD | 2);
        write_mmio(&cursor, COMMAND, PASSWORD | (REFERENCE / 1000000));
        while (read_mmio(&cursor) != 0) { }
        word = read_mmio(&cursor);
        write_mmio(&cursor, CM, word | PASSWORD | 0x100);
        write_mmio(&cursor, ANA3, PASSWORD);
        write_mmio(&cursor, ANA2, PASSWORD);
        write_mmio(&cursor, ANA1, PASSWORD | 0x128000);
        write_mmio(&cursor, ANA0, PASSWORD | ana0);
    }
    if (enabled) {
        word = read_mmio(&cursor);
        integer = word & 0x3FF;
        write_mmio(&cursor, FRAC, PASSWORD | fraction);
        while (integer != target) {
            integer = integer < target ? integer + 1 : integer - 1;
            word = read_mmio(&cursor);
            write_mmio(&cursor, CTRL, (word & UINT32_C(0xFFFF8C00))
                       | PASSWORD | 0x1000 | integer);
        }
    } else {
        write_mmio(&cursor, FRAC, PASSWORD | fraction);
        word = read_mmio(&cursor);
        write_mmio(&cursor, CTRL, (word & UINT32_C(0xFFFF8C00))
                   | PASSWORD | 0x1000 | target);
    }
    word = read_mmio(&cursor);
    write_mmio(&cursor, CM, (word & UINT32_C(0xFFFFFEFF)) | PASSWORD);
    for (count = 0; count < 2000; ++count) {
        locked = read_mmio(&cursor) & 0x200;
        if (locked != 0)
            break;
    }
    word = read_mmio(&cursor);
    write_mmio(&cursor, CM, (initial_cm & word) | PASSWORD);
    if (!enabled && locked != 0) {
        word = read_mmio(&cursor);
        write_mmio(&cursor, CTRL, word | PASSWORD | 0x20000);
    }
    *raw_return = locked != 0 ? 0 : 4;
    return CLOCK_DRIVER_OK;
}

static uint32_t read_cell(const uint32_t *cell,
                          const struct clock_driver_observer *observer) {
    uint32_t word = *cell;
    observe(observer, CLOCK_DRIVER_NATIVE_READ, CELL, word);
    return word;
}

static void write_cell(uint32_t *cell, const struct clock_driver_observer *observer,
                       uint32_t word) {
    *cell = word;
    observe(observer, CLOCK_DRIVER_NATIVE_WRITE, CELL, word);
}

enum clock_driver_status clock_word_preflight(
    const struct clock_word_inputs *inputs, const uint32_t *cell,
    const struct clock_driver_observer *observer, const uint32_t *raw_return) {
    struct span spans[4] = {{inputs, sizeof(*inputs)}, {cell, sizeof(*cell)},
        {observer, sizeof(*observer)}, {raw_return, sizeof(*raw_return)}};
    enum clock_driver_status status = validate_spans(spans, 4);
    int matching, mismatch, zero;
    if (status != CLOCK_DRIVER_OK)
        return status;
    matching = inputs->handle == HANDLE && inputs->comparison_handle == HANDLE;
    mismatch = inputs->handle == HANDLE + 1 && inputs->comparison_handle == HANDLE;
    zero = inputs->handle == 0 && inputs->comparison_handle == 0;
    if (inputs->clock != 0x30 || inputs->source != 7 || inputs->divider != 5
            || inputs->factor_bits != 0x3F800000 || inputs->argument5 != 0
            || inputs->diagnostic != 0 || inputs->enable != 0
            || !((matching && (*cell == 0 || *cell == 0x10 || *cell == 0x12345678
                                                         || *cell == 0x80 || *cell == PASSWORD))
                || (mismatch && *cell == 0x12345678) || (zero && *cell == 0)))
        return CLOCK_DRIVER_UNSUPPORTED;
    if (mismatch) {
        return CLOCK_DRIVER_OK;
    }
    if (observer->observe == NULL)
        return CLOCK_DRIVER_INVALID;
    return CLOCK_DRIVER_OK;
}

enum clock_driver_status clock_word_program(
    const struct clock_word_inputs *inputs, uint32_t *cell,
    const struct clock_driver_observer *observer, uint32_t *raw_return) {
    enum clock_driver_status status = clock_word_preflight(inputs, cell, observer, raw_return);
    uint32_t word, count;
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (inputs->handle != inputs->comparison_handle) {
        *raw_return = UINT32_MAX;
        return CLOCK_DRIVER_OK;
    }
    (void)read_cell(cell, observer);
    word = read_cell(cell, observer);
    write_cell(cell, observer, (word & UINT32_C(0xFFFFFFEF)) | PASSWORD);
    for (count = 2000; count != 0; --count)
        if ((read_cell(cell, observer) & 0x80) == 0)
            break;
    if (count == 0) {
        word = read_cell(cell, observer);
        write_cell(cell, observer, word | PASSWORD | 0x20);
    }
    *raw_return = 0;
    return CLOCK_DRIVER_OK;
}

static enum clock_driver_status validate_divider_reads(const struct clock_driver_plan *plan) {
    struct cursor cursor = {plan, 0, CLOCK_DRIVER_OK};
    uint32_t first, count;
    int delayed, joined;
    if (plan->count < 2)
        return CLOCK_DRIVER_BOUNDS;
    if (plan->count > 255)
        return CLOCK_DRIVER_UNSUPPORTED;
    first = plan->reads[0].word;
    if (first != 0 && first != 1 && first != 2 && first != 5
            && first != 255 && first != 0x12340102)
        return CLOCK_DRIVER_UNSUPPORTED;
    delayed = first == 5 && plan->count == 8;
    joined = first == 5 && plan->count == 5 && plan->reads[4].word == 0x00345678;
    expect_read(&cursor, ARM, first);
    for (count = first & 0xFF; count > 2; --count) {
        if (delayed)
            expect_read(&cursor, COMMAND, 0x321);
        expect_read(&cursor, COMMAND, 0);
    }
    expect_read(&cursor, CM, first == 0x12340102 || joined ? 0x00345678 : 0x0034567A);
    return finish_plan(&cursor);
}

enum clock_driver_status clock_divider_preflight(
    const struct clock_divider_inputs *inputs, const struct clock_divider_state *state,
    const struct clock_driver_plan *plan, const uint32_t *raw_return) {
    struct span spans[5] = {{inputs, sizeof(*inputs)}, {state, sizeof(*state)},
        {plan, sizeof(*plan)}, {raw_return, sizeof(*raw_return)}, {NULL, 0}};
    enum clock_driver_status status = validate_plan(spans, plan);
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (inputs->comparison_handle != HANDLE
            || (inputs->handle != HANDLE && inputs->handle != HANDLE + 1)
            || inputs->divider != 5 || inputs->count != 2 || inputs->selection != 1
            || state->marker != 0x12345678 || state->count != 0x87654321)
        return CLOCK_DRIVER_UNSUPPORTED;
    if (inputs->handle != inputs->comparison_handle) {
        if (plan->count != 0)
            return CLOCK_DRIVER_UNSUPPORTED;
        return CLOCK_DRIVER_OK;
    }
    if (plan->observer.observe == NULL)
        return CLOCK_DRIVER_INVALID;
    return validate_divider_reads(plan);
}

enum clock_driver_status clock_divider_program(
    const struct clock_divider_inputs *inputs, struct clock_divider_state *state,
    const struct clock_driver_plan *plan, uint32_t *raw_return) {
    enum clock_driver_status status = clock_divider_preflight(inputs, state, plan, raw_return);
    struct cursor cursor = {plan, 0, CLOCK_DRIVER_OK};
    uint32_t count, word, target;
    if (status != CLOCK_DRIVER_OK)
        return status;
    if (inputs->handle != inputs->comparison_handle) {
        *raw_return = UINT32_MAX;
        return CLOCK_DRIVER_OK;
    }
    state->marker = 1;
    state->count = inputs->count;
    target = inputs->count / 1;
    count = read_mmio(&cursor) & 0xFF;
    while (count > target) {
        --count;
        write_mmio(&cursor, ARM, PASSWORD | count);
        write_mmio(&cursor, COMMAND, PASSWORD | ((REFERENCE / 1000000) * 10));
        while (read_mmio(&cursor) != 0) { }
    }
    write_mmio(&cursor, ARM, PASSWORD | target);
    word = read_mmio(&cursor);
    write_mmio(&cursor, CM, (word & UINT32_C(0xFFFFFFFD)) | PASSWORD);
    *raw_return = 0;
    return CLOCK_DRIVER_OK;
}
