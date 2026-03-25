# =============================================================================
# SCRIPT:  hal_qmtech_ep4ce55.tcl (Refactor 4.1 -- OPRAVEN? VERZIA)
# VERSION: 4.1
#
# OPRAVY:
#   - FIX: onb_map prerobeny na `array set` (povodny `set` nefungoval s `array names`)
#   - FIX: PMOD loop osetreny voci neexistujucemu poli PMOD (catch pred foreach)
#   - FIX: Pridane osetrenie pre pripad, ze projekt nie je otvoreny pri volani export_assignments
#   - FIX: VGA, SDRAM, ETH, SDC, CAM pridane do onb_map s realnymi pinmi
# =============================================================================

# -----------------------------------------------------------------------------
# 0. Helper Functions & Sync File Initialization
# -----------------------------------------------------------------------------

# Bezpecne priradenie -- v audit m?de (read-only) preskoci zapisy
proc safe_assign {cmd args} {
    if {[info exists ::IS_POST_FLOW_AUDIT] && $::IS_POST_FLOW_AUDIT} {
        return
    }
    if {[catch {eval $cmd $args} err]} {
        post_message -type warning "safe_assign failed: $cmd $args\n  Error: $err"
    }
}

# Vytvorenie out adresara a sync suboru
set SYNC_DIR  "out"
set SYNC_FILE "${SYNC_DIR}/macros_sync.tcl"
if {![file exists $SYNC_DIR]} { file mkdir $SYNC_DIR }

set m_fp [open $SYNC_FILE "w"]
puts $m_fp "# ============================================================================="
puts $m_fp "# GENERATED DOCUMENT: macros_sync.tcl"
puts $m_fp "# DATE: [clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}]"
puts $m_fp "# SOURCE: hal_qmtech_ep4ce55.tcl v4.1"
puts $m_fp "# ============================================================================="
puts $m_fp "set ::ACTIVE_MACROS_LIST {}"

# -----------------------------------------------------------------------------
# 1. Global Device & System Constraints
# -----------------------------------------------------------------------------
safe_assign set_global_assignment -name FAMILY "Cyclone IV E"
safe_assign set_global_assignment -name DEVICE  EP4CE55F23C8

# Systemovy clock (50 MHz)
safe_assign set_location_assignment  PIN_T2  -to SYS_CLK
safe_assign set_instance_assignment  -name IO_STANDARD "3.3-V LVTTL" -to SYS_CLK

# Reset (aktivne nizky)
safe_assign set_location_assignment  PIN_W13 -to RESET_N
safe_assign set_instance_assignment  -name IO_STANDARD       "3.3-V LVTTL" -to RESET_N
safe_assign set_instance_assignment  -name WEAK_PULL_UP_RESISTOR ON         -to RESET_N

# -----------------------------------------------------------------------------
# 2. On-board Peripherals Mapping
# FIX: Pouzity `array set` namiesto `set` -- umoznuje `array names onb_map`
# -----------------------------------------------------------------------------

# Format: PERIPH {pin0 pin1 pin2 ...}
array set onb_map {
    SEG     {PIN_C4 PIN_B2 PIN_A3 PIN_C3 PIN_A5 PIN_B4 PIN_B1 PIN_A4}
    DIG     {PIN_B5 PIN_B3 PIN_B6}
    LEDS    {PIN_E4 PIN_A8 PIN_B8 PIN_A7 PIN_B7 PIN_A6}
    BUTTONS {PIN_Y13 PIN_AA13}
    UART    {PIN_J1 PIN_J2}
    VGA     {PIN_B11 PIN_A11 PIN_B12 PIN_A12 PIN_B13 PIN_A13 PIN_C11 PIN_D11 PIN_E11 PIN_B14 PIN_A14 PIN_C14 PIN_B10 PIN_A10}
    SDRAM   {PIN_V2 PIN_V1 PIN_U2 PIN_U1 PIN_T1 PIN_R1 PIN_P2 PIN_P1 PIN_N2 PIN_N1 PIN_M2 PIN_M1 PIN_L2 PIN_L1}
    ETH     {PIN_D3 PIN_E3 PIN_F4 PIN_G4 PIN_H4}
    SDC     {PIN_K1 PIN_K2 PIN_L3 PIN_L4}
    CAM     {PIN_R14 PIN_T14 PIN_T13 PIN_R13 PIN_T12 PIN_R12 PIN_T11 PIN_R11 PIN_T10 PIN_R10}
}

# Mapa IO standardov pre kazdu periferiu
array set onb_io_std {
    SEG     "3.3-V LVTTL"
    DIG     "3.3-V LVTTL"
    LEDS    "3.3-V LVTTL"
    BUTTONS "3.3-V LVTTL"
    UART    "3.3-V LVTTL"
    VGA     "3.3-V LVTTL"
    SDRAM   "3.3-V SSTL-2 Class I"
    ETH     "3.3-V LVTTL"
    SDC     "3.3-V LVTTL"
    CAM     "3.3-V LVTTL"
}

# UART special case: TX and RX are logically distinct signals, not a bus array.
# Assign to UART_TX / UART_RX directly instead of ONB_UART[0]/ONB_UART[1].
# UART pin order in onb_map: index 0 = TX (PIN_J1), index 1 = RX (PIN_J2)
if {[info exists ONB_USE_UART] && $ONB_USE_UART} {
    set uart_pins $onb_map(UART)
    # PIN_J1=TX, PIN_J2=RX
    safe_assign set_location_assignment [lindex $uart_pins 0] -to UART_TX
    safe_assign set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to UART_TX
    safe_assign set_location_assignment [lindex $uart_pins 1] -to UART_RX
    safe_assign set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to UART_RX
    post_message -type info "HAL: UART_TX -> [lindex $uart_pins 0], UART_RX -> [lindex $uart_pins 1]"
}

foreach peripheral [array names onb_map] {
    # UART handled separately above
    if {$peripheral eq "UART"} { continue }

    set var "ONB_USE_${peripheral}"
    if {[info exists $var] && [set $var]} {
        set pins   $onb_map($peripheral)
        set io_std $onb_io_std($peripheral)

        safe_assign set_instance_assignment \
            -name IO_STANDARD $io_std -to ONB_${peripheral}\[*\]

        # Pull-up pre tlacidla
        if {$peripheral eq "BUTTONS"} {
            safe_assign set_instance_assignment \
                -name WEAK_PULL_UP_RESISTOR ON -to ONB_${peripheral}\[*\]
        }

        set idx 0
        foreach pin $pins {
            safe_assign set_location_assignment $pin -to ONB_${peripheral}\[$idx\]
            incr idx
        }

        post_message -type info "HAL: ONB_${peripheral} -> ${idx} pinov priradenych."
    }
}

# -----------------------------------------------------------------------------
# 3. Dynamic PMOD Router & Macro Registration
# FIX: Overenie existencie pola PMOD pred iteraciou
# -----------------------------------------------------------------------------

array set PMOD_PIN_MAP {
    J10,1  "PIN_H1"  J10,2  "PIN_F1"  J10,3  "PIN_E1"  J10,4  "PIN_C1"
    J10,7  "PIN_H2"  J10,8  "PIN_F2"  J10,9  "PIN_D2"  J10,10 "PIN_C2"
    J11,1  "PIN_R1"  J11,2  "PIN_P1"  J11,3  "PIN_N1"  J11,4  "PIN_M1"
    J11,7  "PIN_R2"  J11,8  "PIN_P2"  J11,9  "PIN_N2"  J11,10 "PIN_M2"
}

proc assign_pmod_module {port module} {
    global PMOD_PIN_MAP
    set base "PMOD_${port}_P"

    # Hardverova obmedzenie: HDMI len na J11
    if {[string match "HDMI*" $module] && $port ne "J11"} {
        post_message -type error "HW ERROR: HDMI vyzaduje konektor J11, pouzity: $port"
        return -code error "HDMI requires J11"
    }

    set io_std "3.3-V LVTTL"
    if {[string match "HDMI*" $module]} { set io_std "LVDS" }

    safe_assign set_instance_assignment -name IO_STANDARD $io_std -to ${base}\[*\]

    # Poradie pinov podla modulu
    set pin_order {10 4 9 3 8 2 7 1}
    if {$module eq "SEG"} { set pin_order {10 9 3 4 8 2 1 7} }

    set idx 0
    foreach p_idx $pin_order {
        set key "${port},${p_idx}"
        if {[info exists PMOD_PIN_MAP($key)]} {
            safe_assign set_location_assignment $PMOD_PIN_MAP($key) -to ${base}\[$idx\]
        } else {
            post_message -type warning "HAL: Chyba PMOD pin mapa pre ${key}"
        }
        incr idx
    }
    post_message -type info "HAL: PMOD ${port} -> ${module} priradeny."
}

# FIX: Overenie, ze pole PMOD existuje pred iteraciou
if {[array exists PMOD]} {
    foreach port [array names PMOD] {
        if {$PMOD($port) ne "NONE"} {
            if {[catch {assign_pmod_module $port $PMOD($port)} err]} {
                post_message -type error "PMOD router zlyhal pre ${port}: $err"
            } else {
                set m_name1 "PMOD_${port}_IS_$PMOD($port)"
                set m_name2 "PMOD_${port}_ENABLED"

                safe_assign set_global_assignment -name VERILOG_MACRO "${m_name1}=1"
                safe_assign set_global_assignment -name VERILOG_MACRO "${m_name2}=1"

                puts $m_fp "lappend ::ACTIVE_MACROS_LIST {$m_name1}"
                puts $m_fp "lappend ::ACTIVE_MACROS_LIST {$m_name2}"
            }
        }
    }
} else {
    post_message -type warning "HAL: Pole PMOD nie je definovane -- PMOD konfiguracia preskocena."
}

# -----------------------------------------------------------------------------
# 3b. Explicit port name assignments from generated_config.tcl PORT_MAP
# These match soc_top port names exactly (uart0_tx, uart0_rx, leds0_led, etc.)
# -----------------------------------------------------------------------------

# UART explicit pin mapping
if {[info exists ONB_USE_UART] && $ONB_USE_UART} {
    # TX = first UART pin (J2), RX = second UART pin (J1)
    if {[array exists PORT_MAP]} {
        foreach port_name [array names PORT_MAP] {
            if {[string match "uart*_tx" $port_name]} {
                safe_assign set_location_assignment PIN_J1 -to $port_name
                safe_assign set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to $port_name
            }
            if {[string match "uart*_rx" $port_name]} {
                safe_assign set_location_assignment PIN_J2 -to $port_name
                safe_assign set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to $port_name
                safe_assign set_instance_assignment -name WEAK_PULL_UP_RESISTOR ON -to $port_name
            }
        }
    }
}

# LEDs explicit pin mapping
if {[info exists ONB_USE_LEDS] && $ONB_USE_LEDS} {
    set led_pins {PIN_E4 PIN_A8 PIN_B8 PIN_A7 PIN_B7 PIN_A6}
    if {[array exists PORT_MAP]} {
        foreach port_name [array names PORT_MAP] {
            if {[string match "*led*" [string tolower $port_name]]} {
                safe_assign set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to ${port_name}\[*\]
                set idx 0
                foreach pin $led_pins {
                    safe_assign set_location_assignment $pin -to ${port_name}\[$idx\]
                    incr idx
                }
                post_message -type info "HAL: $port_name -> $idx LED pins assigned."
            }
        }
    }
}

# -----------------------------------------------------------------------------
# 4. On-board Macro Registration & Database Sync
# -----------------------------------------------------------------------------

set onb_list {LEDS SEG DIG BUTTONS UART VGA SDRAM ETH SDC CAM}
foreach p $onb_list {
    set var "ONB_USE_${p}"
    if {[info exists $var] && [set $var]} {
        set m_name "ONB_${p}_ENABLED"
        safe_assign set_global_assignment -name VERILOG_MACRO "${m_name}=1"
        puts $m_fp "lappend ::ACTIVE_MACROS_LIST {$m_name}"
        post_message -type info "BSP: Periferia ONB_${p} aktivna. Macro: ${m_name}"
    }
}

# -----------------------------------------------------------------------------
# 5. Zatvorenie sync suboru & export priradeni
# -----------------------------------------------------------------------------

close $m_fp

# FIX: Dvojita podmienka -- projekt musi by? otvoreny A nesmieme by? v audit m?de
if {[catch {is_project_open} proj_open_err] == 0 && [is_project_open]} {
    if {![info exists ::IS_POST_FLOW_AUDIT] || !$::IS_POST_FLOW_AUDIT} {
        export_assignments
        post_message -type info "HAL: Priradenia exportovane. Sync subor: $SYNC_FILE"
    }
} else {
    post_message -type warning "HAL: Projekt nie je otvoreny -- export_assignments preskoceny."
}
