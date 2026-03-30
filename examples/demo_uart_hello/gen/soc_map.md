# SoC Memory Map
Generated: 2026-03-30 22:51:21  |  Board: qmtech_ep4ce55  |  Clock: 50 MHz  |  RAM: 4096 B @ 0x00000000  |  latency: registered  |  reset_vector: 0x00000000

## Address Space

| Region | Base | End | Size | Module |
|--------|------|-----|------|--------|
| RAM | 0x00000000 | 0x00000FFF | 4096 B | soc_ram | latency=registered |
| uart0 | 0x80002000 | 0x8000200F | 0x10 | uart_top |
| leds0 | 0x80003000 | 0x80003007 | 0x8 | leds_top |

## Registers

### uart0 (base: 0x80002000)

| Offset | Name | Access | Width | Reset | Description |
|--------|------|--------|-------|-------|-------------|
| 0x00 | DATA `UART0_DATA_REG` | rw | 8 | 0x0 | W: TX byte  R: RX byte |
| 0x04 | STAT `UART0_STAT_REG` | ro | 2 | 0x0 | [0]=TX_BUSY  [1]=RX_VALID |

### leds0 (base: 0x80003000)

| Offset | Name | Access | Width | Reset | Description |
|--------|------|--------|-------|-------|-------------|
| 0x00 | LED `LEDS0_LED_REG` | rw | 6 | 0x0 | LED output register [5:0] |

## Interrupts

| ID | Peripheral | Name | C Macro |
|----|-----------|------|--------|
| 0 | uart0 | rx_done | `UART0_RX_DONE_IRQ` |
