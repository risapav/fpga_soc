# =============================================================================
# pre_flow_demo.tcl -- Pre-Flow Orchestrator for Demo projects
# =============================================================================

post_message -type info "PRE_FLOW_DEMO: Starting demo build pipeline..."

# --- Find Python interpreter ---
set py ""
foreach candidate {python3 python} {
    set found [auto_execok $candidate]
    if {$found ne "" && [file executable $found]} {
        set py $found
        break
    }
}
if {$py eq ""} {
    post_message -type error "PRE_FLOW_DEMO: Python not found in PATH!"
    qexit -error
}

# --- Resolve paths ---
# Quartus sets working dir to the QSF project directory
set qsf_dir  [pwd]
set root_dir [file normalize [file join $qsf_dir ".." ".."]]

set gen_script [file join $root_dir "board" "generators" "gen_config.py"]
set demo_cfg   [file join $qsf_dir  "board" "project_config.yaml"]
set cfg_out    [file join $root_dir "board" "config" "generated_config.tcl"]
set hal_dir    [file join $root_dir "board" "bsp"]

post_message -type info "PRE_FLOW_DEMO: QSF dir : $qsf_dir"
post_message -type info "PRE_FLOW_DEMO: Root dir: $root_dir"

# --- Validate paths ---
if {![file exists $gen_script]} {
    post_message -type error "PRE_FLOW_DEMO: gen_config.py not found: $gen_script"
    qexit -error
}
if {![file exists $demo_cfg]} {
    post_message -type error "PRE_FLOW_DEMO: project_config.yaml not found: $demo_cfg"
    qexit -error
}

# --- Run generator ---
post_message -type info "PRE_FLOW_DEMO: Running gen_config.py..."
if {[catch {exec $py $gen_script --config $demo_cfg} result]} {
    post_message -type error "PRE_FLOW_DEMO: gen_config.py FAILED:\n$result"
    qexit -error
}
post_message -type info "PRE_FLOW_DEMO: Generator output:\n$result"

# --- Load generated config ---
if {![file exists $cfg_out]} {
    post_message -type error "PRE_FLOW_DEMO: Missing generated_config.tcl: $cfg_out"
    qexit -error
}
if {[catch {source $cfg_out} err]} {
    post_message -type error "PRE_FLOW_DEMO: Error sourcing generated_config.tcl: $err"
    qexit -error
}
foreach required {GENERATED_CONFIG BOARD_TYPE} {
    if {![info exists $required]} {
        post_message -type error "PRE_FLOW_DEMO: Missing variable '$required' in generated_config.tcl"
        qexit -error
    }
}
post_message -type info "PRE_FLOW_DEMO: Config loaded. Board: $BOARD_TYPE"

# --- Open project so HAL assignments work ---
# project_open is required before set_location_assignment / set_global_assignment

#set project_name [file rootname [lindex [glob -directory $qsf_dir *.qsf] 0]]
#if {[catch {project_open $project_name} perr]} {
#    post_message -type warning "PRE_FLOW_DEMO: project_open failed (may already be open): $perr"
#}

# --- Load HAL ---
set hal [file join $hal_dir "hal_${BOARD_TYPE}.tcl"]
if {![file exists $hal]} {
    post_message -type error "PRE_FLOW_DEMO: HAL not found: $hal"
    qexit -error
}
if {[catch {source $hal} err]} {
    post_message -type error "PRE_FLOW_DEMO: HAL error: $err"
    qexit -error
}
post_message -type info "PRE_FLOW_DEMO: HAL loaded: $hal"

# --- Close project ---
catch {project_close}

post_message -type info "PRE_FLOW_DEMO: Done."
