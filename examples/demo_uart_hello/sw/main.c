/*
 * main.c - UART Hello World demo
 * Prints "Hello from PicoRV32!" repeatedly and blinks LED on each message.
 *
 * Hardware: QMTech EP4CE55F23C8
 * CPU: PicoRV32 @ 50 MHz, 4 KB RAM
 */

#include <stdint.h>

/* ---- Register map (from generated soc_map.h) ---- */
#define UART0_BASE   (0x80002000UL)
#define LEDS0_BASE   (0x80003000UL)

/* UART registers */
#define UART_DATA    (*((volatile uint32_t*)(UART0_BASE + 0x00)))
#define UART_STAT    (*((volatile uint32_t*)(UART0_BASE + 0x04)))
#define UART_TX_BUSY (1u << 0)
#define UART_RX_RDY  (1u << 1)

/* LED register */
#define LEDS_REG     (*((volatile uint32_t*)(LEDS0_BASE + 0x00)))

/* ---- Helpers ---- */

static void uart_putc(char c)
{
    while (UART_STAT & UART_TX_BUSY)
        ;
    UART_DATA = (uint8_t)c;
}

static void uart_puts(const char *s)
{
    while (*s)
        uart_putc(*s++);
}

static void delay(volatile uint32_t n)
{
    while (n--)
        __asm__ volatile ("nop");
}

/* ---- Main ---- */

int main(void)
{
    uint32_t count = 0;

    uart_puts("\r\n");
    uart_puts("================================\r\n");
    uart_puts(" PicoRV32 SoC Framework Demo    \r\n");
    uart_puts(" QMTech EP4CE55F23C8 @ 50 MHz   \r\n");
    uart_puts("================================\r\n");

    while (1) {
        /* Toggle LED pattern */
        LEDS_REG = (count & 0x3F);

        /* Print message */
        uart_puts("Hello from PicoRV32!  count=0x");

        /* Print count as 4-digit hex */
        for (int i = 12; i >= 0; i -= 4) {
            uint8_t nibble = (count >> i) & 0xF;
            uart_putc(nibble < 10 ? '0' + nibble : 'A' + nibble - 10);
        }
        uart_puts("\r\n");

        count++;

        /* ~1 second delay at 50 MHz (approx) */
        delay(5000000);
    }

    return 0;
}
