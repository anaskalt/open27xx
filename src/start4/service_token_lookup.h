/* SPDX-FileCopyrightText: 2026 The open27xx Authors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef OPEN27XX_SERVICE_TOKEN_LOOKUP_H
#define OPEN27XX_SERVICE_TOKEN_LOOKUP_H

#include <stdint.h>

enum service_token_lookup_status {
    SERVICE_TOKEN_LOOKUP_OK = 0,
    SERVICE_TOKEN_LOOKUP_INVALID = -1,
    SERVICE_TOKEN_LOOKUP_BOUNDS = -3,
    SERVICE_TOKEN_LOOKUP_OVERLAP = -4
};

struct service_token_lookup_registers {
    uint32_t r[24];
    uint32_t gp;
    uint32_t sp;
    uint32_t lr;
    uint32_t r27;
    uint32_t r28;
    uint32_t r29;
    uint32_t sr;
};

struct service_token_lookup_result {
    struct service_token_lookup_registers registers;
    uint32_t pc;
    uint32_t instructions;
    uint32_t table_reads;
};

enum service_token_lookup_status service_token_lookup(
    const struct service_token_lookup_registers *input,
    struct service_token_lookup_result *result);

/*
 * The scalar behavior is in docs/bcm2711/service-token-lookup.md; the
 * portable policy is in src/start4/README.md. Input holds all 31 incoming
 * scalar register words. Incoming PC is implicit at the documented entry.
 * Input r0 accepts every uint32_t query without masking or translation.
 * LR must be even and outside [0xCEC00D82, 0xCEC00DA0) and
 * [0xCEC01B60, 0xCEC01C08). All other input words, including SP, are
 * unrestricted. Tokens and register values are numeric, never host pointers.
 *
 * Both objects are required, naturally aligned and fully disjoint. Each
 * complete pointer-plus-size must fit uintptr_t. Complete read-only
 * preflight precedes all result stores. INVALID reports NULL objects,
 * typed misalignment or odd LR. BOUNDS reports host span wrap. OVERLAP
 * reports intersecting host spans or LR within either excluded range.
 * If multiple conditions fail, any corresponding error may be returned.
 * Errors preserve every supplied byte. Host status is separate from r0.
 *
 * Success searches the fixed 42-token table in increasing index order.
 * Result holds all 31 final scalar words and PC, the documented native
 * instruction count and table-word read count. These counts describe the
 * scalar contract, not host execution. A match at j produces r0=r3=j,
 * r1=0xCEC01B60+4*(j+1), r2=42 and r4=query, with j+1 reads and 7+3*j
 * instructions. A miss produces r0=r3=0xFFFFFFFF, r1=0xCEC01C08,
 * r2=42 and r4=0xCEC01B20, with 42 reads and 132 instructions. PC equals
 * incoming LR. All other register words remain unchanged, including SR.
 *
 * The scalar body has no memory stores, events or subordinate calls.
 * Observation memory and event arrays are omitted from this API because
 * it never accesses them. Only the host result object is written; no
 * separate raw-index destination exists. No original VPU table address,
 * completion address, query, SP or GP is dereferenced. No hardware,
 * MMIO, SWI, RTI, live table lifetime or connected initialization behavior
 * is established.
 *
 * Callers provide actual backing, readable input, writable result and
 * lifetime. Integer span checks cannot establish allocation validity.
 * Input stays immutable and result is free from concurrent access until
 * return. No storage is allocated, freed or retained.
 */

#endif
