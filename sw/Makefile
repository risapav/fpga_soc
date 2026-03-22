# sw/Makefile
# ===========================================================
# RISC-V Toolchain Settings
# ===========================================================
RISCV_PATH   ?= /home/palo/opt/riscv/xpack-riscv-none-elf-gcc-14.2.0-1/bin
CROSS_COMPILE = $(RISCV_PATH)/riscv-none-elf-
CC      = $(CROSS_COMPILE)gcc
OBJCOPY = $(CROSS_COMPILE)objcopy
OBJDUMP = $(CROSS_COMPILE)objdump

# ===========================================================
# Paths
# ===========================================================
GEN_CONFIG  = ../board/generators/gen_config.py
BIN2HEX     = ../board/generators/bin2hex.py
SECTIONS_LD = linker/sections.lds
HEX_OUT     = ../software.hex

# ===========================================================
# Build Settings
# FIX: RAM_SIZE musí zodpovedať ram_size v project_config.yaml
#      Zmeň tu aj v project_config.yaml súčasne.
# ===========================================================
RAM_SIZE = 4096
TARGET   = software

# Explicit source files
SRCS = boot.S main.c

# Compiler flags
CFLAGS  = -march=rv32i -mabi=ilp32 -ffreestanding -O2 -I./include
LDFLAGS = -T $(SECTIONS_LD) -nostdlib

# ===========================================================
# Default Target
# ===========================================================
all: hw $(TARGET).hex $(TARGET).lst

# -----------------------------------------------------------
# Step 1: Generovanie SoC hardvérových súborov (SV + Headers + LDS)
# FIX: Spúšťame cez python3 s explicitnou cestou k skriptu
# -----------------------------------------------------------
hw: $(GEN_CONFIG)
	@echo "🛠️  Spúšťam SoC generátor (Python)..."
	python3 $(GEN_CONFIG)
	@echo "✅  SoC generátor dokončený."

# -----------------------------------------------------------
# Step 2: Kompilácia a linkovanie C/Assembly zdrojov
# FIX: Pridaná závislosť na sections.lds — rebuild pri zmene LDS
# -----------------------------------------------------------
$(TARGET).elf: $(SRCS) $(SECTIONS_LD)
	$(CC) $(CFLAGS) $(SRCS) $(LDFLAGS) -o $@

# -----------------------------------------------------------
# Step 3: Extrahovanie binárky z ELF
# -----------------------------------------------------------
$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

# -----------------------------------------------------------
# Step 4: Konverzia binárky na HEX pre soc_ram.sv
# FIX: Komentár presunutý mimo príkazový riadok
# FIX: cp skopíruje HEX do koreňa projektu pre Quartus
# -----------------------------------------------------------
$(TARGET).hex: $(TARGET).bin
	@echo "💾  Generujem $(TARGET).hex pre soc_ram.sv..."
	python3 $(BIN2HEX) $< $@ $(RAM_SIZE)
	cp $@ $(HEX_OUT)
	@echo "📋  HEX skopírovaný do: $(HEX_OUT)"

# -----------------------------------------------------------
# Step 5: Disassembly listing pre kontrolu
# -----------------------------------------------------------
$(TARGET).lst: $(TARGET).elf
	$(OBJDUMP) -d $< > $@

# ===========================================================
# Pomocné targety
# ===========================================================

# Len SW rebuild bez generovania HW (rýchly iteratívny build)
sw: $(TARGET).hex $(TARGET).lst

# Len HW generátor (bez kompilácie SW)
gen: hw

# ===========================================================
# Cleanup
# ===========================================================
clean:
	rm -f *.o *.elf *.bin *.hex *.lst
	@echo "🧹  Projekt vyčistený."

# ===========================================================
.PHONY: all clean hw sw gen
