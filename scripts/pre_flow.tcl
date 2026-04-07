# =============================================================================
# @file: pre_flow.tcl
# @brief: Pre-Flow Orchestrator pre SoC Framework v3 (opravený)
# =============================================================================
load_package flow
load_package project

post_message -type info "PRE_FLOW: Spúšťam build pipeline..."

# --- 1. Python ---
set py ""
foreach candidate {python3 python} {
    set found [auto_execok $candidate]
    if {$found ne "" && [file executable $found]} {
        set py $found
        break
    }
}
if {$py eq ""} {
    return -code error "PRE_FLOW: Python nebol nájdený!"
}

# --- 2. Absolútne cesty ---
set qsf_dir    [pwd]
set root_dir   [file normalize [file join $qsf_dir ".." ".."]]
set gen_script [file join $root_dir "board" "generators" "gen_config.py"]
set demo_cfg   [file join $qsf_dir  "board" "project_config.yaml"]
set gen_dir    [file join $qsf_dir  "gen"]

# OPRAVA 1: správna cesta k generated_config.tcl (gen/tcl/, nie board/config/)
set cfg_out    [file join $gen_dir "tcl" "generated_config.tcl"]
set files_gen  [file join $gen_dir "tcl" "files.tcl"]
set hal_gen    [file join $gen_dir "hal" "board.tcl"]
set sdc_gen    [file join $gen_dir "tcl" "soc_timing.sdc"]

# --- 3. Spustenie generátora s explicitným --out ---
# OPRAVA 4: pridané --out pre deterministický výstupný adresár
post_message -type info "PRE_FLOW: Spúšťam gen_config.py..."
if {[catch {exec $py $gen_script --config $demo_cfg --out $gen_dir} py_out]} {
    post_message -type error "PRE_FLOW: Python zlyhal:\n$py_out"
    return -code error
}
# OPRAVA 5: zobrazenie výstupu generátora
foreach line [split $py_out "\n"] {
    if {$line ne ""} { post_message -type info "  GEN: $line" }
}

# --- 4. Načítanie generated_config.tcl (BOARD_TYPE a ostatné premenné) ---
# OPRAVA 1: správna cesta
if {[file exists $cfg_out]} {
    source $cfg_out
    post_message -type info "PRE_FLOW: generated_config.tcl načítaný (BOARD_TYPE=$BOARD_TYPE)"
} else {
    post_message -type error "PRE_FLOW: generated_config.tcl nenájdený: $cfg_out"
    return -code error
}

# --- 5. Otvorenie projektu ---
if {![is_project_open]} {
    set qpf_files [glob -nocomplain *.qpf]
    if {[llength $qpf_files] > 0} {
        project_open [file rootname [lindex $qpf_files 0]] -current_revision
    }
}

# --- 6. Injekcia RTL súborov ---
if {[file exists $files_gen]} {
    post_message -type info "PRE_FLOW: Načítavam $files_gen"
    source $files_gen
} else {
    post_message -type error "PRE_FLOW: files.tcl nenájdený: $files_gen"
    return -code error
}

# --- 7. OPRAVA 2+3: Načítanie gen/hal/board.tcl (pin assignments) ---
# Nahradza starý bsp_loader -> hal_BOARD_TYPE.tcl reťazec.
# gen/hal/board.tcl je self-contained, žiadne ďalšie source volania.
if {[file exists $hal_gen]} {
    post_message -type info "PRE_FLOW: Načítavam pin assignments z $hal_gen"
    source $hal_gen
} else {
    post_message -type error "PRE_FLOW: board.tcl nenájdený: $hal_gen"
    return -code error
}

# --- 8. SDC timing constraints (ak existuje) ---
if {[file exists $sdc_gen]} {
    post_message -type info "PRE_FLOW: Registrujem SDC: $sdc_gen"
    set_global_assignment -name SDC_FILE $sdc_gen
}

export_assignments
post_message -type info "PRE_FLOW: Orchestrácia úspešná."
