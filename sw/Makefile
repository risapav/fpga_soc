# sw/Makefile

# ===========================================================
# RISC-V Toolchain Settings
# ===========================================================
RISCV_PATH ?= /home/palo/opt/riscv/xpack-riscv-none-elf-gcc-14.2.0-1/bin
CROSS_COMPILE = $(RISCV_PATH)/riscv-none-elf-

CC      = $(CROSS_COMPILE)gcc
OBJCOPY = $(CROSS_COMPILE)objcopy
OBJDUMP = $(CROSS_COMPILE)objdump

# ===========================================================
# Paths to SoC generators and scripts
# ===========================================================
GEN_CONFIG = ../board/generators/gen_config.py
BIN2HEX    = ../board/generators/bin2hex.py

# ===========================================================
# Build Settings
# ===========================================================
RAM_SIZE = 32768
TARGET   = software

# Explicit source files
SRCS = boot.S main.c

# Compiler flags
CFLAGS  = -march=rv32i -mabi=ilp32 -ffreestanding -O2 -I./include
LDFLAGS = -T linker/sections.lds -nostdlib

# ===========================================================
# Default Target: Build Hardware + Software
# ===========================================================
all: hw $(TARGET).hex $(TARGET).lst

# -----------------------------------------------------------
# Step 1: Generate SoC hardware files (SystemVerilog + Config)
# -----------------------------------------------------------
hw: $(GEN_CONFIG)
	@echo "🛠️ Spúšťam SoC generátor (Python)..."
	python3 $(GEN_CONFIG)
	@echo "✅ SoC generátor dokončený."

# -----------------------------------------------------------
# Step 2: Convert binary to HEX for soc_ram.sv
# -----------------------------------------------------------
$(TARGET).hex: $(TARGET).bin
	@echo "💾 Generujem $(TARGET).hex pre soc_ram.sv..."
	python3 $(BIN2HEX) $< $@ $(RAM_SIZE)
	cp $@ ../software.hex  # Skopíruje HEX do koreňa projektu pre Quartus

# -----------------------------------------------------------
# Step 3: Extract binary from ELF
# -----------------------------------------------------------
$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

# -----------------------------------------------------------
# Step 4: Compile and link C/Assembly sources
# -----------------------------------------------------------
$(TARGET).elf: $(SRCS)
	$(CC) $(CFLAGS) $(SRCS) $(LDFLAGS) -o $@

# -----------------------------------------------------------
# Step 5: Generate disassembly listing for inspection
# -----------------------------------------------------------
$(TARGET).lst: $(TARGET).elf
	$(OBJDUMP) -d $< > $@

# ===========================================================
# Cleanup
# ===========================================================
clean:
	rm -f *.o *.elf *.bin *.hex *.lst
	@echo "🧹 Projekt vyčistený."

# ===========================================================
# Phony targets
# ===========================================================
.PHONY: all clean hw
