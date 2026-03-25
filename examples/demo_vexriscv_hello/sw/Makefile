# ===========================================================
# sw/Makefile - RISC-V firmware build
# ===========================================================
RISCV_PATH   ?= /home/palo/opt/riscv/xpack-riscv-none-elf-gcc-14.2.0-1/bin
CROSS_COMPILE = $(RISCV_PATH)/riscv-none-elf-
CC      = $(CROSS_COMPILE)gcc
OBJCOPY = $(CROSS_COMPILE)objcopy
OBJDUMP = $(CROSS_COMPILE)objdump

BIN2HEX    = ../../../board/generators/bin2hex.py
BIN2MIF    = ../../../board/generators/bin2mif.py
SECTIONS_LD = ../gen/sections.lds
GEN_DIR    = ../gen

# RAM_SIZE auto-synced from generator
-include ../gen/ram_size.mk
RAM_SIZE ?= 4096

TARGET   = software
SRCS     = boot.S main.c
CFLAGS   = -march=rv32i -mabi=ilp32 -ffreestanding -O1
LDFLAGS  = -T $(SECTIONS_LD) -nostdlib -lgcc

.PHONY: all sw clean

all: sw

sw: $(TARGET).hex $(TARGET).mif $(TARGET).lst
	@echo "[OK] SW build done -> $(GEN_DIR)/software.hex + .mif"

$(TARGET).elf: $(SRCS) $(SECTIONS_LD)
	$(CC) $(CFLAGS) $(SRCS) $(LDFLAGS) -o $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(TARGET).hex: $(TARGET).bin
	python3 $(BIN2HEX) $< $@ $(RAM_SIZE)
	cp $@ $(GEN_DIR)/software.hex

$(TARGET).mif: $(TARGET).bin
	python3 $(BIN2MIF) $< $@ $(RAM_SIZE)
	cp $@ $(GEN_DIR)/software.mif

$(TARGET).lst: $(TARGET).elf
	$(OBJDUMP) -d $< > $@

clean:
	rm -f *.o *.elf *.bin *.hex *.mif *.lst
