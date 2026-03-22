# ============================================================================
# BSP LOADER (Refactored)
# ============================================================================

# --- 1. Validácia zdroja konfigurácie ---
if {![info exists BOARD_TYPE]} {
    post_message -type error "BSP Loader: BOARD_TYPE not defined! (generated_config.tcl missing?)"
    qexit -error
}

post_message -type info "BSP: Using configuration for board: $BOARD_TYPE"

# --- 2. Load HAL ---
set HAL_SCRIPT "board/bsp/hal_${BOARD_TYPE}.tcl"

if {[file exists $HAL_SCRIPT]} {
    source $HAL_SCRIPT
    post_message -type info "BSP Loader: HAL loaded: $HAL_SCRIPT"
} else {
    post_message -type error "BSP Loader: HAL script not found: $HAL_SCRIPT"
    qexit -error
}