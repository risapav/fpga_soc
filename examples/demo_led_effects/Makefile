# =============================================================================
# examples/demo_led_effects/Makefile
# Použitie:
#   make gen      → vygeneruje HAL config (generated_config.tcl)
#   make clean    → vymaže vygenerované súbory
# =============================================================================

GEN = ../../board/generators/gen_config.py
CFG = board/project_config.yaml

.PHONY: gen clean

gen:
	@echo "🛠️  Generujem HAL config pre demo..."
	python3 $(GEN) --config $(CFG)
	@echo "✅  Hotovo. Teraz otvor demo_led_effects.qsf v Quartuse."

clean:
	rm -f ../../board/config/generated_config.tcl
	@echo "🧹  Vyčistené."
