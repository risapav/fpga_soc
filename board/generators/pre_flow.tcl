# =============================================================================
# pre_flow.tcl — Quartus Pre-Flow Orchestrátor (OPRAVENÁ VERZIA)
#
# OPRAVY:
#   - FIX: `end` nahradené správnym `}` v catch bloku
#   - FIX: Robustnejší fallback pre Python (python3 → python)
#   - FIX: Overenie GENERATED_CONFIG pred source generated_config.tcl
#   - FIX: gen_if.tcl volanie ošetrené catch blokom
# =============================================================================

post_message -type info "PRE_FLOW: Spúšťam SoC build pipeline..."

# --- 1. Nájdenie Python interpretera ---
set py ""
foreach candidate {python3 python} {
    set found [auto_execok $candidate]
    if {$found ne "" && [file executable $found]} {
        set py $found
        post_message -type info "PRE_FLOW: Python interpreter: $py"
        break
    }
}

if {$py eq ""} {
    post_message -type error "PRE_FLOW: Python nenájdený v PATH! Nainštaluj Python 3."
    qexit -error
}

# --- 2. Spustenie Python generátora ---
post_message -type info "PRE_FLOW: Spúšťam gen_config.py..."

# FIX: Opravená syntax catch bloku (pôvodne malo `end` namiesto `}`)
if {[catch {exec $py board/generators/gen_config.py} result]} {
    post_message -type error "PRE_FLOW: gen_config.py ZLYHAL!"
    post_message -type error $result
    qexit -error
}

post_message -type info "PRE_FLOW: gen_config.py dokončený:\n$result"

# --- 3. Načítanie vygenerovanej konfigurácie ---
set cfg "board/config/generated_config.tcl"

if {![file exists $cfg]} {
    post_message -type error "PRE_FLOW: Chýba súbor: $cfg"
    qexit -error
}

# FIX: catch pri source pre lepšiu diagnostiku
if {[catch {source $cfg} src_err]} {
    post_message -type error "PRE_FLOW: Chyba pri načítaní $cfg: $src_err"
    qexit -error
}

# Validácia povinných premenných
foreach required_var {GENERATED_CONFIG BOARD_TYPE} {
    if {![info exists $required_var]} {
        post_message -type error \
            "PRE_FLOW: Premenná '$required_var' chýba v generated_config.tcl!"
        qexit -error
    }
}

post_message -type info "PRE_FLOW: Konfigurácia načítaná. Board: $BOARD_TYPE"

# --- 4. Načítanie HAL (BSP) ---
set HAL_SCRIPT "board/bsp/hal_${BOARD_TYPE}.tcl"

if {![file exists $HAL_SCRIPT]} {
    post_message -type error "PRE_FLOW: HAL skript nenájdený: $HAL_SCRIPT"
    qexit -error
}

if {[catch {source $HAL_SCRIPT} hal_err]} {
    post_message -type error "PRE_FLOW: Chyba v HAL skripte: $hal_err"
    qexit -error
}

post_message -type info "PRE_FLOW: HAL načítaný: $HAL_SCRIPT"

# --- 5. Voliteľný interface generátor ---
set gen_if_script "board/generators/gen_if.tcl"
if {[file exists $gen_if_script]} {
    if {[catch {source $gen_if_script} gif_err]} {
        post_message -type warning "PRE_FLOW: gen_if.tcl zlyhal (nekritické): $gif_err"
    } else {
        post_message -type info "PRE_FLOW: gen_if.tcl dokončený."
    }
} else {
    post_message -type info "PRE_FLOW: gen_if.tcl nenájdený — preskočené."
}

post_message -type info "PRE_FLOW: Build pipeline dokončená. ✅"
