Transformácia tohto TCL skriptu do YAML formátu je kľúčovým krokom k vytvoreniu **BSP (Board Support Package)** databázy. Namiesto procedurálneho kódu (ako sa čo má urobiť) definujeme v YAML statické fakty o hardvéri (čo na doske je).

Navrhujem štruktúru súboru **`board_definition.yaml`**, ktorý rozdeľuje dáta na globálne parametre, fixné periférie a konfigurovateľné sloty.

---

### Návrh YAML: `board_config/qmtech_ep4ce55.yaml`

```yaml
# =============================================================================
# Board Support Package (BSP) Definition for QMTech Cyclone IV Starter Kit
# =============================================================================

board:
  id: qmtech_ep4ce55
  vendor: QMTech
  family: "Cyclone IV E"
  device: EP4CE55F23C8

# 1. Globálne systémové piny (Fixné)
system:
  clock:
    pin: PIN_T2
    frequency_hz: 50_000_000
    io_standard: "3.3-V LVTTL"
  reset:
    pin: PIN_W13
    active_low: true
    io_standard: "3.3-V LVTTL"
    pull_up: true

# 2. Integrované (On-board) periférie
# Tieto mapy nahrádzajú array set onb_map a onb_io_std
onboard_peripherals:
  uart:
    io_standard: "3.3-V LVTTL"
    pins:
      tx: PIN_J1
      rx: PIN_J2
  
  leds:
    io_standard: "3.3-V LVTTL"
    pins: [PIN_E4, PIN_A8, PIN_B8, PIN_A7, PIN_B7, PIN_A6]
    active: high
  
  buttons:
    io_standard: "3.3-V LVTTL"
    pull_up: true
    pins: [PIN_Y13, PIN_AA13]
    active: low

  vga:
    io_standard: "3.3-V LVTTL"
    pins: [PIN_B11, PIN_A11, PIN_B12, PIN_A12, PIN_B13, PIN_A13, PIN_C11, 
           PIN_D11, PIN_E11, PIN_B14, PIN_A14, PIN_C14, PIN_B10, PIN_A10]

  sdram:
    io_standard: "3.3-V SSTL-2 Class I"
    pins: [PIN_V2, PIN_V1, PIN_U2, PIN_U1, PIN_T1, PIN_R1, PIN_P2, PIN_P1, 
           PIN_N2, PIN_N1, PIN_M2, PIN_M1, PIN_L2, PIN_L1]

# 3. Rozširujúce sloty (PMOD)
# Nahrádza PMOD_PIN_MAP a logiku priraďovania v TCL
expansion_slots:
  pmod_j10:
    type: pmod_dual_6pin
    pins:
      - { pos: 1,  pin: PIN_H1 }
      - { pos: 2,  pin: PIN_F1 }
      - { pos: 3,  pin: PIN_E1 }
      - { pos: 4,  pin: PIN_C1 }
      - { pos: 7,  pin: PIN_H2 }
      - { pos: 8,  pin: PIN_F2 }
      - { pos: 9,  pin: PIN_D2 }
      - { pos: 10, pin: PIN_C2 }
  
  pmod_j11:
    type: pmod_dual_6pin
    capabilities: [lvds, high_speed] # Špeciálna podpora pre HDMI
    pins:
      - { pos: 1,  pin: PIN_R1 }
      - { pos: 2,  pin: PIN_P1 }
      - { pos: 3,  pin: PIN_N1 }
      - { pos: 4,  pin: PIN_M1 }
      - { pos: 7,  pin: PIN_R2 }
      - { pos: 8,  pin: PIN_P2 }
      - { pos: 9,  pin: PIN_N2 }
      - { pos: 10, pin: PIN_M2 }

# 4. Špecifické pravidlá smerovania (Hardware constraints)
constraints:
  - if: module.type == "HDMI"
    requires: expansion_slots.pmod_j11
    error: "HDMI vyzaduje konektor J11 kvoli HW obmedzeniam (LVDS)."
```

---

### Prečo je táto transformácia výhodná pre framework?

1.  **Dátami riadený HAL (Hardware Abstraction Layer):**
    Váš framework môže mať jeden univerzálny Python skript, ktorý prečíta tento YAML a vygeneruje finálny TCL skript pre Quartus pre *akýkoľvek* kit. Stačí mu podhodiť iný YAML súbor.

2.  **Validácia pred syntézou:**
    Framework môže skontrolovať, či sa niekto nepokúša priradiť 8-bitovú zbernicu LED na 6-pinový konektor ešte predtým, než vôbec spustíte Quartus.

3.  **Abstrakcia PMOD slotov:**
    Všimnite si sekciu `expansion_slots`. Framework teraz vie, že PMOD nie je len "kopa pinov", ale slot s pozíciami. Ak zmeníte kit (napr. na Cyclone V), stačí v novom YAML predefinovať piny pre slot `pmod_j10` a zvyšok systému (logika priradenia modulov) ostane nezmenený.



### Ako by framework s týmito dátami pracoval?

Váš `TCLGenerator` v Pythone by robil nasledovné:
1.  **Iterácia:** Prešiel by zoznam periférií aktivovaných v `project_config.yaml`.
2.  **Lookup:** Vyhľadal by ich piny v BSP YAML súbore (tomto novom súbore).
3.  **Mapping:** Ak je aktivovaný `uart0`, Python nájde `onboard_peripherals.uart`, zoberie `PIN_J1` a `PIN_J2` a vygeneruje známy TCL príkaz:
    `set_location_assignment PIN_J1 -to uart0_tx`.

Týmto prístupom sa zbavíte potreby udržiavať zložité TCL skripty s procedurálnou logikou (if/else/foreach) a nahradíte ich čistými dátami.
