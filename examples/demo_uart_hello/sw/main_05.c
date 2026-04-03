#include <stdint.h>
#include "../gen/soc_map.h"

#define UART_TX_BUSY (1u << 0)

static void uart_putc(char c) {
    // Čakaj kým je UART voľný
    while (UART0_STAT_REG & UART_TX_BUSY);
    // Zápis
    UART0_DATA_REG = (uint8_t)c;
    // Počkaj kým sa tx_busy nastaví (1 baud tick ~ 434 cyklov, stačí pár nop)
    __asm__ volatile ("nop\nnop\nnop\nnop\nnop\nnop\nnop\nnop");
    // Teraz čakaj kým TX dokončí
    while (UART0_STAT_REG & UART_TX_BUSY);
}

static void uart_puts(const char *s) {
    while (*s) uart_putc(*s++);
}

int main(void) {
    uart_puts("A\r\n");
    uart_puts("B\r\n");
    uart_puts("C\r\n");
    uart_putc('0');
    uart_putc('\r');
    uart_putc('\n');
    uart_puts("D\r\n");
    while (1);
}
