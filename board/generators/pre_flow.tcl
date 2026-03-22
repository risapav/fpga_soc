# ============================================================================
# PRE-FLOW ORCHESTRATOR - Robust Version
# ============================================================================

post_message -type info "PRE_FLOW: Starting SoC build pipeline..."

# --- 1. Check Python3 ---
set py [auto_execok python3]
if {![file executable $py]} {
    post_message -type error "Python3 not found in PATH!"
    # Optional fallback:
    set py [auto_execok python]
    if {![file executable $py]} {
        qexit -error
    } else {
        post_message -type warning "Fallback: Using 'python'"
    }
}

# --- 2. Run Python generator ---
post_message -type info "PRE_FLOW: Running Python generator..."
if {[catch { exec $py board/generators/gen_config.py } result]} {
    post_message -type error "Python generator FAILED!"
    post_message -type error $result
    qexit -error
end
post_message -type info "PRE_FLOW: Python generation DONE."

# --- 3. Load generated config ---
set cfg "board/config/generated_config.tcl"
if {[file exists $cfg]} {
    source $cfg
    if {![info exists GENERATED_CONFIG] || ![info exists BOARD_TYPE]} {
        post_message -type error "generated_config.tcl is incomplete (missing BOARD_TYPE or GENERATED_CONFIG)!"
        qexit -error
    }
    post_message -type info "PRE_FLOW: Loaded generated_config.tcl"
} else {
    post_message -type error "Missing generated_config.tcl!"
    qexit -error
}

# --- 4. Run interface generator ---
post_message -type info "PRE_FLOW: Running gen_if.tcl..."
source board/generators/gen_if.tcl
post_message -type info "PRE_FLOW: DONE."
