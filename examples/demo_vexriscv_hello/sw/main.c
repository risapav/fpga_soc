#include <stdint.h>
#include "../gen/soc_map.h"

#define UART_TX_BUSY (1u << 0)

static void uart_putc(char c) {
    while (UART0_STAT_REG & UART_TX_BUSY);
    UART0_DATA_REG = (uint8_t)c;
}

static void uart_puts(const char *s) {
    while (*s) uart_putc(*s++);
}

static void uart_putu(uint32_t n) {
    static char buf[10];
    int i = 0;
    if (n == 0) { uart_putc('0'); return; }
    while (n > 0) { buf[i++] = '0' + (n % 10); n /= 10; }
    while (i--) uart_putc(buf[i]);
}

static void delay(volatile uint32_t n) {
    while (n--) __asm__ volatile ("nop");
}

int main(void) {
    delay(500000);
    uart_puts("\r\n================================\r\n");
    uart_puts(" PicoRV32 SoC - Hello World!    \r\n");
    uart_puts(" QMTech EP4CE55 @ 50 MHz        \r\n");
    uart_puts("================================\r\n\r\n");

    uint32_t count = 0;
    while (1) {
        LEDS0_LED_REG = count & 0x3F;
        uart_puts("Hello! count=");
        uart_putu(count);
        uart_puts("\r\n");
        count++;
        delay(5000000);
    }
}
