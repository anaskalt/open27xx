/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_ARMSTUB_H
#define OPEN27XX_ARMSTUB_H

#include <stddef.h>
#include <stdint.h>

#define ARMSTUB_MIN_SIZE 256u

enum armstub_result {
    ARMSTUB_INVALID = -1,
    ARMSTUB_UNCHANGED = 0,
    ARMSTUB_PREPARED = 1
};

/* Values are caller-selected 32-bit fields, not dereferenced addresses. */
enum armstub_result armstub_prepare(uint8_t *buffer, size_t length,
                                   uint32_t dtb_value, uint32_t dtb_present,
                                   uint32_t kernel_value, uint32_t kernel_result);

#endif
