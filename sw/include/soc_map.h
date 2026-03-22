/**
 * @file soc_map.h
 * @brief Auto-generated Register Map
 */

#ifndef SOC_MAP_H
#define SOC_MAP_H

#include <stdint.h>

// Base Addresses
#define INTC_BASE   0x00001000
#define UART0_BASE  0x00004000
#define TIMER0_BASE 0x00005000

// UART0 Registers
#define UART0_CTRL    (*(volatile uint32_t*)(UART0_BASE + 0x00))
#define UART0_STATUS  (*(volatile uint32_t*)(UART0_BASE + 0x04))
#define UART0_DATA    (*(volatile uint32_t*)(UART0_BASE + 0x08))

// Interrupt IDs
#define IRQ_ID_UART0_RX 0
#define IRQ_ID_UART0_TX 1
#define IRQ_ID_TIMER0   2

#endif // SOC_MAP_H
