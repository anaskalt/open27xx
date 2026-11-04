/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

.text.bootloader_state : ALIGN(4) {
  KEEP(*(.data.bootloader_state))
} >ram
.text.firmware_rev : ALIGN(4) {
  KEEP(*(.data.firmware_rev))
} >ram

ASSERT(_end <= 0xC5FF0000, "firmware overlaps the boot stack reserve")
