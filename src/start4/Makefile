# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later

PYTHON ?= python3
JOBS ?= 2
TOOLCHAIN_PREFIX ?= vc4-elf-
ARM64_TOOLCHAIN_PREFIX ?= aarch64-linux-gnu-

.PHONY: all fetch check armstub check-armstub-metadata stage
all:
	$(PYTHON) ../../tools/start4.py build --jobs $(JOBS) --toolchain-prefix $(TOOLCHAIN_PREFIX)

fetch:
	$(PYTHON) ../../tools/start4.py fetch

check:
	$(PYTHON) ../../tools/start4.py check ../../build/start4/start4.elf

armstub:
	$(PYTHON) ../../tools/start4.py armstub --toolchain-prefix $(ARM64_TOOLCHAIN_PREFIX)

check-armstub-metadata:
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c armstub.c -o ../../build/start4/armstub-metadata.o

stage:
	$(PYTHON) ../../tools/start4.py stage
