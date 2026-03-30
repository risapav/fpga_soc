# =============================================================================
# @file: pre_flow.tcl
# @brief: Pre-Flow Orchestrator pre SoC Framework v3
# =============================================================================

load_package flow
load_package project

post_message -type info "PRE_FLOW: Spúšťam build pipeline (Orchestrator Mode)..."

# --- 1. Vyhľadanie Python interpretra ---
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

# --- 2. Absolútne cesty (Kľúčová časť) ---
set qsf_dir  [pwd]
set root_dir [file normalize [file join $qsf_dir ".." ".."]]

set gen_script [file join $root_dir "board" "generators" "gen_config.py"]
set demo_cfg   [file join $qsf_dir  "board" "project_config.yaml"]
set cfg_out    [file join $root_dir "board" "config" "generated_config.tcl"]
set files_gen  [file join $qsf_dir  "gen" "files.tcl"]
set bsp_loader [file join $root_dir "scripts" "bsp_loader.tcl"]

# --- 3. Spustenie generátora ---
if {[catch {exec $py $gen_script --config $demo_cfg} py_output]} {
  post_message -type error "PRE_FLOW: Python zlyhal: $py_output"
  return -code error
}
post_message -type info "PRE_FLOW: Python OK."

# --- 4. Načítanie konfigurácie (BOARD_TYPE) ---
if {[file exists $cfg_out]} {
  source $cfg_out
}

# --- 5. Otvorenie projektu a injekcia ---
if {![is_project_open]} {
  set qpf_files [glob -nocomplain *.qpf]
  if {[llength $qpf_files] > 0} {
    project_open [file rootname [lindex $qpf_files 0]] -current_revision
  }
}

# Injekcia súborov
if {[file exists $files_gen]} {
  post_message -type info "PRE_FLOW: Injektujem zoznam súborov..."
  source $files_gen
}

# Injekcia BSP Loadera (Dôležité: bsp_loader.tcl bude zdieľať premennú root_dir)
if {[file exists $bsp_loader]} {
  post_message -type info "PRE_FLOW: Injektujem BSP Loader z $bsp_loader"
  source $bsp_loader
} else {
  post_message -type error "PRE_FLOW: BSP Loader nenájdený na: $bsp_loader"
  return -code error
}

export_assignments
post_message -type info "PRE_FLOW: Orchestrácia úspešná."
