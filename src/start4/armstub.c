/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "armstub.h"

static uint32_t read_le32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8)
        | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static void write_le32(uint8_t *bytes, uint32_t value) {
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
    bytes[2] = (uint8_t)(value >> 16);
    bytes[3] = (uint8_t)(value >> 24);
}

enum armstub_result armstub_prepare(uint8_t *buffer, size_t length,
                                   uint32_t dtb_value, uint32_t dtb_present,
                                   uint32_t kernel_value, uint32_t kernel_result) {
    if (buffer == NULL || length < ARMSTUB_MIN_SIZE)
        return ARMSTUB_INVALID;
    if (read_le32(buffer + 0xF0) != UINT32_C(0x5AFE570B))
        return ARMSTUB_UNCHANGED;

    write_le32(buffer + 0xF0, 0);
    write_le32(buffer + 0xF4, 0);
    write_le32(buffer + 0xF8, dtb_present != 0 ? dtb_value : 0);
    write_le32(buffer + 0xFC, kernel_result == 0 ? kernel_value : 0);
    return ARMSTUB_PREPARED;
}
