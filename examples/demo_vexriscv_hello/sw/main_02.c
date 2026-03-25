
#include <stdint.h>
#define LEDS_REG      (*((volatile uint32_t*)(0x80003000UL)))
#define UART_DATA_REG (*((volatile uint32_t*)(0x80002000UL)))
#define UART_STAT_REG (*((volatile uint32_t*)(0x80002004UL)))

static void uart_putc(char c) {
    while (UART_STAT_REG & 1);  /* wait TX_BUSY=0 */
    UART_DATA_REG = c;
}

static void uart_puts(const char *s) {
    while (*s) uart_putc(*s++);
}

static void delay(volatile uint32_t n) {
    while (n--) __asm__ volatile ("nop");
}

int main(void) {
    delay(500000);  /* wait after reset */
    LEDS_REG = 0x01;
    uart_puts("Hello World!\r\n");
    LEDS_REG = 0x3F;
    while(1) {
        uart_puts("ping\r\n");
        delay(3000000);
    }
}
