# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later

include ./project/rpi4-start4.mk

# The bring-up image only initializes the VPU platform and UART.
MODULES :=
