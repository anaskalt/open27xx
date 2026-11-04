/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include <lk/init.h>
#include <stdint.h>
#include <stdio.h>

/* Keep the loader metadata separate from executable text. */
uint32_t bootloader_state[4]
    __attribute__((section(".data.bootloader_state"))) = {0x41545342, 0, 0, 0};
uint32_t firmware_rev[4]
    __attribute__((section(".data.firmware_rev"))) = {3, 0, 0, 0};

static void start4_ready(uint level) {
    puts("open27xx: VPU platform initialized; ARM boot is not implemented");
}

LK_INIT_HOOK(start4, &start4_ready, LK_INIT_LEVEL_APPS);
