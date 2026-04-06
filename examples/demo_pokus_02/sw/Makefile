# ===========================================================
# sw/Makefile - RISC-V firmware build (Target: ../gen)
# ===========================================================

RISCV_PATH   ?= /home/palo/opt/riscv/xpack-riscv-none-elf-gcc-14.2.0-1/bin
CROSS_COMPILE = $(RISCV_PATH)/riscv-none-elf-
CC      = $(CROSS_COMPILE)gcc
OBJCOPY = $(CROSS_COMPILE)objcopy
OBJDUMP = $(CROSS_COMPILE)objdump

ROOT        = ../../..
GEN_DIR     = ../gen
BIN2HEX     = $(ROOT)/board/generators/bin2hex.py
BIN2MIF     = $(ROOT)/board/generators/bin2mif.py
SECTIONS_LD = $(GEN_DIR)/sw/sections.lds

# RAM_SIZE auto-synced z generátora
-include $(GEN_DIR)/sw/ram_size.mk
RAM_SIZE ?= 4096

TARGET = software
SRCS   = boot.S main.c
INC    = -I$(GEN_DIR)/sw

CFLAGS  = -march=rv32i -mabi=ilp32 -ffreestanding -O1 $(INC)
LDFLAGS = -T $(SECTIONS_LD) -nostdlib -lgcc

OUTPUTS = \
	$(GEN_DIR)/$(TARGET).elf \
	$(GEN_DIR)/$(TARGET).bin \
	$(GEN_DIR)/$(TARGET).hex \
	$(GEN_DIR)/$(TARGET).mif \
	$(GEN_DIR)/$(TARGET).lst

.PHONY: all sw clean

all: sw

sw: $(OUTPUTS)
	@echo "[OK] SW build done -> $(GEN_DIR)/"

$(GEN_DIR)/$(TARGET).elf: $(SRCS) $(SECTIONS_LD)
	@mkdir -p $(GEN_DIR)
	$(CC) $(CFLAGS) $(SRCS) $(LDFLAGS) -o $@

$(GEN_DIR)/$(TARGET).bin: $(GEN_DIR)/$(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(GEN_DIR)/$(TARGET).hex: $(GEN_DIR)/$(TARGET).bin
	python3 $(BIN2HEX) $< $@ $(RAM_SIZE)

$(GEN_DIR)/$(TARGET).mif: $(GEN_DIR)/$(TARGET).bin
	python3 $(BIN2MIF) $< $@ $(RAM_SIZE)

$(GEN_DIR)/$(TARGET).lst: $(GEN_DIR)/$(TARGET).elf
	$(OBJDUMP) -d $< > $@

clean:
	rm -f $(GEN_DIR)/*.elf $(GEN_DIR)/*.bin \
	      $(GEN_DIR)/*.hex $(GEN_DIR)/*.mif $(GEN_DIR)/*.lst
