/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_SOC_INITIALIZATION_H
#define OPEN27XX_SOC_INITIALIZATION_H

#include <stddef.h>
#include <stdint.h>

#define SOC_INITIALIZATION_REGIONS 7u

enum soc_initialization_status {
    SOC_INITIALIZATION_OK = 0,
    SOC_INITIALIZATION_INVALID = -1,
    SOC_INITIALIZATION_UNSUPPORTED = -2,
    SOC_INITIALIZATION_BOUNDS = -3,
    SOC_INITIALIZATION_OVERLAP = -4
};

enum soc_initialization_followup {
    SOC_INITIALIZATION_VERSION2 = 0,
    SOC_INITIALIZATION_MMIO = 1
};

enum soc_initialization_region {
    SOC_INITIALIZATION_FLAGS_A = 0,
    SOC_INITIALIZATION_FLAGS_B = 1,
    SOC_INITIALIZATION_COMPLETION = 2,
    SOC_INITIALIZATION_CLASSIFICATION = 3,
    SOC_INITIALIZATION_CONTROL_MODE = 4,
    SOC_INITIALIZATION_DIAGNOSTIC = 5,
    SOC_INITIALIZATION_WATCHED = 6
};

struct soc_initialization_registers {
    uint32_t r[24];
    uint32_t gp;
    uint32_t sp;
    uint32_t lr;
    uint32_t r27;
    uint32_t r28;
    uint32_t r29;
    uint32_t sr;
};

struct soc_initialization_observations {
    uint32_t version1;
    enum soc_initialization_followup kind;
    uint32_t word;
};

struct soc_initialization_buffer {
    uint8_t *bytes;
    size_t length;
};

struct soc_initialization_memory {
    struct soc_initialization_buffer buffers[SOC_INITIALIZATION_REGIONS];
};

struct soc_initialization_stack {
    uint8_t *bytes;
    size_t length;
    uint32_t address;
};

struct soc_initialization_result {
    struct soc_initialization_registers registers;
    uint32_t pc;
};

enum soc_initialization_status soc_initialization_run(
    const struct soc_initialization_registers *input,
    const struct soc_initialization_observations *observations,
    const struct soc_initialization_memory *memory,
    const struct soc_initialization_stack *stack,
    struct soc_initialization_result *result);

/*
 * docs/bcm2711/soc-initialization.md defines the conditional state relation
 * and portable policy. All register words and VPU addresses are numeric;
 * no VPU address becomes a host pointer. Observations supplies VERSION1 and
 * exactly one tagged word: MMIO for a recognized selector, VERSION2 for
 * every other selector. No hardware access or callback occurs.
 *
 * All five objects and eight byte pointers are required. Typed objects are
 * naturally aligned; byte storage may be unaligned. The seven buffers have
 * exact lengths 16, 16, 12, 8, 20, 12 and 12 bytes in enum order. Their
 * numeric starts are GP plus the offsets in the document. The diagnostic
 * byte is at offset 4 in its buffer and must be at most 3. GP and SP are
 * four-byte aligned; SP is at least 24. The complete frame [SP-24, SP) fits
 * inside the declared stack span, whose length is at most UINT32_MAX.
 *
 * Every full host pointer-plus-length fits uintptr_t. The five objects,
 * seven buffers and entire stack byte span are pairwise disjoint, including
 * object padding and read-only storage. Every virtual span fits without
 * wrapping, with its exclusive end permitted to equal 2^32. Ordinary and
 * stack spans are pairwise disjoint and exclude the fixed code/table and
 * peripheral intervals. LR is even and outside all these virtual spans.
 * Adjacent half-open spans are permitted. Complete read-only preflight
 * precedes all stores. Rejection preserves every supplied byte and object.
 *
 * Success updates only the selected ordinary fields and 24 frame bytes,
 * then publishes all 31 final scalar words and PC. The frame retains LR
 * and r6 through r10 at SP-4 through SP-24 in little-endian order. Unselected
 * flags, guards and the entire diagnostic and watched buffers are preserved.
 * Status is separate from final r0. No intermediate-state observer, event
 * stream, instruction count or physical store timing is exposed.
 *
 * Callers provide backing, readability, writable result/frame and selected
 * ordinary fields, and lifetime through return without concurrent access.
 * Integer checks do not establish allocation validity. Inputs and
 * descriptors remain immutable. No storage is allocated, freed or retained.
 * The operation establishes no physical initialization or startup lifetime.
 */

#endif
