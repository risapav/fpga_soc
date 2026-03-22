# =============================================================================
# demo_uart_hello/Makefile
# Usage:
#   make gen      - generate SoC RTL + SW headers
#   make sw       - compile C firmware -> gen/software.hex
#   make all      - gen + sw (default)
#   make clean    - remove all generated artifacts
# =============================================================================

GEN = ../../board/generators/gen_config.py
CFG = board/project_config.yaml

.PHONY: all gen sw clean

all: sw

# gen produces gen/sections.lds -- use it as sentinel
gen/sections.lds: $(CFG) ../../board/config/ip_registry.yaml
	@echo "[GEN] Running SoC generator..."
	python3 $(GEN) --config $(CFG)
	@echo "[OK]  RTL generated."

gen: gen/sections.lds

# sw depends on sentinel so gen runs automatically if needed
sw: gen/sections.lds
	@echo "[SW]  Building firmware..."
	$(MAKE) -C sw
	@echo "[OK]  Firmware built: gen/software.hex"

clean:
	@echo "[CLEAN] Removing generated files..."
	rm -rf gen/
	rm -rf db/
	rm -rf incremental_db/
	rm -rf out/
	rm -f  *.rpt *.summary *.smsg *.pin *.done *.flow.rpt
	rm -f  *.jdi *.sld *.asm.rpt *.fit.rpt *.map.rpt *.sta.rpt
	rm -f  *.qpf.bak
	$(MAKE) -C sw clean
	@echo "[OK]  Clean done."
