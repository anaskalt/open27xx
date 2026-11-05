/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_SERVICE_INITIALIZATION_H
#define OPEN27XX_SERVICE_INITIALIZATION_H

#include <stddef.h>
#include <stdint.h>

#define SERVICE_INITIALIZATION_EVENTS 8u

enum service_initialization_status {
    SERVICE_INITIALIZATION_OK = 0,
    SERVICE_INITIALIZATION_INVALID = -1,
    SERVICE_INITIALIZATION_UNSUPPORTED = -2,
    SERVICE_INITIALIZATION_BOUNDS = -3,
    SERVICE_INITIALIZATION_OVERLAP = -4
};

struct service_initialization_registers {
    uint32_t r[24];
    uint32_t gp;
    uint32_t sp;
    uint32_t lr;
    uint32_t r27;
    uint32_t r28;
    uint32_t r29;
    uint32_t sr;
};

struct service_initialization_input {
    uint32_t version;
    struct service_initialization_registers registers;
};

struct service_initialization_stack {
    uint8_t *bytes;
    size_t length;
    uint32_t address;
};

enum service_initialization_event_kind {
    SERVICE_INITIALIZATION_VERSION = 0,
    SERVICE_INITIALIZATION_MMIO_WRITE = 1,
    SERVICE_INITIALIZATION_TABLE_READ = 2,
    SERVICE_INITIALIZATION_TABLE_WRITE = 3
};

struct service_initialization_event {
    enum service_initialization_event_kind kind;
    uint32_t source;
    uint32_t address;
    uint32_t word;
};

struct service_initialization_result {
    struct service_initialization_registers registers;
    uint32_t pc;
    uint32_t instructions;
    uint32_t event_count;
    struct service_initialization_event events[SERVICE_INITIALIZATION_EVENTS];
};

enum service_initialization_status service_initialization_run(
    const struct service_initialization_input *input,
    const struct service_initialization_stack *stack,
    uint32_t *table_word, struct service_initialization_result *result);

/*
 * The scalar behavior and portable policy are specified separately in
 * docs/bcm2711/service-initialization.md. This function operates only on
 * caller-owned host storage. Address and source fields are numeric tokens;
 * no token, register or VERSION word becomes a host pointer.
 *
 * Input, stack and result are required. VERSION with bits 16 and 3 cleared
 * must be one of 0x04000162, 0x04000161, 0x04000160, 0x04000140, 0x04000104.
 * The same VERSION supplies both recorded observations. Bit 16 clear
 * requires table_word with initial value 0xCEC00DA0; success stores
 * 0xCEC00DA1 there. Bit 16 set permits NULL table_word and never reads or
 * writes table storage, including during preflight. A supplied unused
 * table word still participates in alignment, span and overlap checks.
 *
 * The declared byte span represents VPU addresses beginning at address.
 * Length is at most UINT32_MAX; its exclusive virtual end may equal 2^32.
 * NULL bytes require zero length. SP is four-byte aligned and at least
 * eight. The complete frame [SP-8, SP) must fit in the declared span.
 * LR is even and outside that span. Both LR and the entire virtual stack
 * span exclude all source, table and MMIO regions listed in the document,
 * on both branches. Other incoming register words are unrestricted.
 *
 * Every typed object is naturally aligned. All full host spans are
 * pairwise disjoint, including input, the stack descriptor, every declared
 * stack byte, supplied table storage and result. Byte storage may be
 * unaligned. Each host pointer plus its complete length must fit uintptr_t.
 * Complete read-only preflight precedes all stores. INVALID reports missing
 * objects, invalid NULL byte storage, typed misalignment, misaligned SP,
 * SP below eight or odd LR. UNSUPPORTED reports an unrecognized VERSION or
 * a primary table word other than 0xCEC00DA0. BOUNDS reports span wrap,
 * excess length or an incomplete frame. OVERLAP reports intersecting host
 * spans or a forbidden virtual-address intersection. If several conditions
 * fail, any corresponding error may be returned. Errors preserve every
 * supplied object and byte. This rejection policy does not model the
 * unsupported vendor branch's earlier writes or imply vendor rollback.
 *
 * Success writes only the frame's eight stack bytes, as little-endian zero
 * at SP-8 and incoming LR at SP-4, and the primary table word. Result holds
 * all 31 final scalar register words, final PC, the documented instruction
 * total and three or eight events in source order. Event source is the
 * documented instruction address. VERSION uses address zero as an unused
 * field and carries the complete VERSION word. Other events contain their
 * numeric address and transferred word. Unused event records have all
 * fields zero. Result publication follows stack and table stores. No
 * callback or intermediate-state observation is part of this API.
 *
 * Callers provide actual backing, readability, output/stack/primary-table
 * writability and lifetime. Integer span checks cannot establish allocation
 * validity. Input and descriptors stay immutable, and all supplied storage
 * is free from concurrent access until return. No storage is allocated,
 * freed or retained. Host status is separate from the final r0 word.
 * The function performs no MMIO, VERSION instruction, RTI, SWI or hardware
 * initialization and establishes no live table lifetime or first-open path.
 */

#endif
