# =============================================================================
# demo_led_effects/Makefile
# Usage:
#   make gen      - generate soc_top.sv + files.tcl + generated_config.tcl
#   make clean    - remove all generated artifacts
# =============================================================================

GEN = ../../board/generators/gen_config.py
CFG = board/project_config.yaml

.PHONY: gen clean

gen:
	@echo "[GEN] Running generator..."
	python3 $(GEN) --config $(CFG)
	@echo "[OK]  Done. Open demo_led_effects.qsf in Quartus."

clean:
	@echo "[CLEAN] Removing generated files..."
	rm -rf gen/
	rm -rf db/
	rm -rf incremental_db/
	rm -rf out/
	rm -f  *.rpt *.summary *.smsg *.pin *.done *.flow.rpt
	rm -f  *.jdi *.sld *.asm.rpt *.fit.rpt *.map.rpt *.sta.rpt
	rm -f  *.qpf.bak
	@echo "[OK]  Clean done."
