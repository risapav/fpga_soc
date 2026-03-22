# =============================================================================
# demo_uart_hello/sw/Makefile
# Compiles C firmware to software.hex
# Called from parent Makefile via: make -C sw
# Usage (from sw/ directly):
#   make        - build software.hex
#   make clean  - remove build artifacts
# NOTE: gen/sections.lds must exist before building (run 'make gen' from demo root)
# =============================================================================

RISCV_PATH   ?= /home/palo/opt/riscv/xpack-riscv-none-elf-gcc-14.2.0-1/bin
CROSS        = $(RISCV_PATH)/riscv-none-elf-
CC           = $(CROSS)gcc
OBJCOPY      = $(CROSS)objcopy
OBJDUMP      = $(CROSS)objdump

BIN2HEX      = ../../../board/generators/bin2hex.py
LDS          = ../gen/sections.lds
GEN_DIR      = ../gen

RAM_SIZE     = 4096
TARGET       = software

SRCS         = boot.S main.c
CFLAGS       = -march=rv32i -mabi=ilp32 -ffreestanding -O2 -Wall
LDFLAGS      = -T $(LDS) -nostdlib

.PHONY: all clean

all: $(TARGET).hex $(TARGET).lst
	@echo "[OK]  SW build done: $(TARGET).hex"

$(TARGET).elf: $(SRCS) $(LDS)
	$(CC) $(CFLAGS) $(SRCS) $(LDFLAGS) -o $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(TARGET).hex: $(TARGET).bin
	python3 $(BIN2HEX) $< $@ $(RAM_SIZE)
	cp $@ $(GEN_DIR)/software.hex

$(TARGET).lst: $(TARGET).elf
	$(OBJDUMP) -d $< > $@

clean:
	rm -f *.o *.elf *.bin *.hex *.lst
	@echo "[OK]  SW clean done."
