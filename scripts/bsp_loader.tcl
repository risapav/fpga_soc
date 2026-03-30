# =============================================================================
# @file: bsp_loader.tcl
# @brief: HAL Loader využívajúci absolútne cesty.
# =============================================================================

# Ak root_dir neexistuje (napr. pri ručnom spustení), vypočítame ho
if {![info exists root_dir]} {
  set root_dir [file normalize [file join [pwd] ".." ".."]]
}

if {![info exists BOARD_TYPE]} {
  post_message -type error "BSP Loader: BOARD_TYPE nie je definovaný!"
  return -code error
}

# Vytvorenie ABSOLÚTNEJ cesty k HAL skriptu
set hal_path [file join $root_dir "board" "bsp" "hal_${BOARD_TYPE}.tcl"]

post_message -type info "BSP: Hľadám HAL skript na: $hal_path"

if {[file exists $hal_path]} {
  if {[catch {source $hal_path} err]} {
    post_message -type error "BSP Loader: Chyba v HAL skripte: $err"
    return -code error
  }
  post_message -type info "BSP Loader: HAL úspešne načítaný."
} else {
  post_message -type error "BSP Loader: Súbor nenájdený: $hal_path"
  # Vypíšeme obsah adresára pre ladenie, ak súbor chýba
  set bsp_dir [file dirname $hal_path]
  post_message -type info "BSP Loader: Obsah adresára $bsp_dir : [glob -nocomplain -directory $bsp_dir *]"
  return -code error
}
