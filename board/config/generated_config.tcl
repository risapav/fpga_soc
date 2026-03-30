set GENERATED_CONFIG 1
set BOARD_TYPE qmtech_ep4ce55

# On-board peripherals
set ONB_USE_SEG 0
set ONB_USE_DIG 0
set ONB_USE_LEDS 1
set ONB_USE_BUTTONS 0
set ONB_USE_UART 1
set ONB_USE_VGA 0
set ONB_USE_SDRAM 0
set ONB_USE_ETH 0
set ONB_USE_SDC 0
set ONB_USE_CAM 0

# PMOD connectors
set PMOD(J10) "NONE"
set PMOD(J11) "NONE"
# Active peripheral base addresses
set PERIPH_BASE(uart0) 0x80002000
set PERIPH_BASE(leds0) 0x80003000
