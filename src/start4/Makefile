# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later

PYTHON ?= python3
JOBS ?= 2
TOOLCHAIN_PREFIX ?= vc4-elf-
ARM64_TOOLCHAIN_PREFIX ?= aarch64-linux-gnu-

.PHONY: all fetch check armstub check-armstub-metadata check-boot-info check-arm-control check-memory-capacity check-memory-layout check-resource-request check-clock-request check-clock-driver check-clock-composition check-resource-composition check-arm-start-composition stage
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

check-boot-info:
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c boot_info.c -o ../../build/start4/boot-info.o

check-arm-control:
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c arm_control.c -o ../../build/start4/arm-control.o

check-memory-capacity:
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c memory_capacity.c -o ../../build/start4/memory-capacity.o

check-memory-layout:
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c memory_layout.c -o ../../build/start4/memory-layout.o

check-resource-request:
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c resource_request.c -o ../../build/start4/resource-request.o

check-clock-request:
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c clock_request.c -o ../../build/start4/clock-request.o

check-clock-driver:
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c clock_driver.c -o ../../build/start4/clock-driver.o

check-clock-composition: check-clock-driver
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c clock_composition.c -o ../../build/start4/clock-composition.o

check-resource-composition: check-clock-composition check-arm-control
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c resource_composition.c -o ../../build/start4/resource-composition.o

check-arm-start-composition: check-resource-composition
	mkdir -p ../../build/start4
	$(TOOLCHAIN_PREFIX)gcc -std=c99 -Os -ffixed-lr -ffreestanding -fno-builtin \
		-Wall -Wextra -Werror -pedantic -c arm_start_composition.c -o ../../build/start4/arm-start-composition.o

stage:
	$(PYTHON) ../../tools/start4.py stage
