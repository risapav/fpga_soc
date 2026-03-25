
#include <stdint.h>
#define LEDS_REG      (*((volatile uint32_t*)(0x80003000UL)))
#define UART_DATA_REG (*((volatile uint32_t*)(0x80002000UL)))
#define UART_STAT_REG (*((volatile uint32_t*)(0x80002004UL)))

static void delay(volatile uint32_t n) {
    while (n--) __asm__ volatile ("nop");
}

int main(void) {
    UART_DATA_REG = 'A';

    /* Wait 100000 cycles - enough for TX to finish */
    delay(100000);

    /* Read STAT_REG after delay */
    uint32_t stat = UART_STAT_REG;

    /* LED0=TX_BUSY still set, LED1=TX_BUSY cleared */
    LEDS_REG = (stat & 1) ? 0x01 : 0x02;

    while(1);
}
