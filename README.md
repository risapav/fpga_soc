Tu je aktualizované a doplnené **README.md**, ktoré obsahuje všetky nové závislosti, skripty a generované súbory, aby odrážalo kompletnú transformáciu projektu na plnohodnotný SoC orchestrátor:

---

# 🌀 QMTech Cyclone IV RISC-V SoC Framework

Tento projekt je pokročilý, metadátami riadený framework pre automatizovanú generáciu System-on-Chip (SoC) architektúr na FPGA **QMTech Cyclone IV**. Framework transformuje vysokoúrovňovú špecifikáciu (YAML) na kompletný hardvérový stack (SystemVerilog) a softvérový stack (C Headers, Linker Scripts).

## 🚀 Kľúčové vlastnosti

* **Single Source of Truth:** Celá konfigurácia SoC (periférie, adresy, prerušenia) je definovaná v `project_config.yaml`.
* **RISC-V Core:** Integrácia jadra **PicoRV32** s natívnou podporou prerušení.
* **Vectored Interrupt Controller (VIC):** Deterministická obsluha prerušení s prioritným enkodérom (O(1) latency).
* **Lite Bus Fabric:** Efektívna memory-mapped zbernica s automatickým adresným dekodérom a multiplexerom.
* **Auto-Register Generation:** Automatická tvorba RTL registrových blokov a synchronizovaných C hlavičiek.
* **Hardware Audit:** Post-flow kontrola pinov a IO štandardov pre ochranu QMTech hardvéru.
* **Automatizovaný Pre-Flow:** Python orchestrátor (`gen_config.py`) generuje `soc_top.sv`, `soc_interfaces.sv`, `generated_config.tcl` pred Quartus flow.
* **Refaktorovaný BSP & PMOD Router:** `hal_qmtech_ep4ce55.tcl` spravuje pinout, onboard periférie a dynamické PMOD porty s audit logovaním.

---

## 📂 Architektúra adresárov

Framework striktne oddeľuje generované artefakty od statického zdrojového kódu:

```text
.
├── board/
│   ├── bsp/               # Board Support Package (Pinouty pre QMTech)
│   │   └── hal_qmtech_ep4ce55.tcl  # BSP + PMOD router + macro sync
│   ├── config/
│   │   ├── project_config.yaml     # Hlavná definícia SoC (adresy, RAM, periférie)
│   │   ├── ip_registry.yaml        # Pravidlá pre IP bloky (adresy, IRQ)
│   │   └── generated_config.tcl   # Auto-generated pre Quartus
│   └── generators/
│       └── gen_config.py           # Python Orchestrátor (YAML → SV + TCL)
├── src/
│   ├── cpu/
│   │   └── picorv32.v              # RISC-V Jadro
│   ├── soc/
│   │   ├── gen/                     # <--- AUTO-GENEROVANÉ RTL
│   │   │   ├── soc_interfaces.sv
│   │   │   ├── soc_top.sv
│   │   │   ├── soc_intc.sv
│   │   │   └── soc_ram.sv
│   │   └── static/                  # Ručne písané SoC moduly
│   └── top/                         # Top-level obal pre FPGA piny
├── sw/
│   ├── include/
│   │   ├── soc_map.h                # Auto-generated C Register Map
│   │   └── soc_irq.h                # Auto-generated IRQ IDs
│   └── linker/
│       └── sections.lds             # Auto-generated Linker Script
├── out/                              # Bitstreamy a reporty (RBF, SOF)
└── scripts/
    └── pre_flow.tcl                  # Quartus pre-flow orchestrator
```

---

## 🛠 Konfiguračný Flow

Proces zostavenia SoC prebieha v štyroch automatizovaných krokoch:

1. **Definícia:** Užívateľ upraví `project_config.yaml` (pridá UART, zmení RAM, pridelí adresu).
2. **Meta-Analýza:** `gen_config.py` validuje adresné kolízie a závislosti (napr. UART potrebuje CLK).
3. **RTL/SW Syntéza:** Generátor vytvorí SystemVerilog kód, C hlavičky a Linker script.
4. **FPGA Build:** Quartus Prime spracuje vygenerované súbory a vytvorí bitstream.

---

## 🧱 Príklad konfigurácie (`project_config.yaml`)

```yaml
soc:
  cpu: picorv32
  clock_freq: 50_000_000
  ram_size: 32768

peripherals:
  uart0:
    enabled: true
    base: 0x4000
  timer0:
    enabled: true
    base: 0x5000
```

---

## 📝 Coding Guidelines (RTL & Gen)

* **Resety:** Vždy asynchrónne, aktívne v nule (`rst_ni`).
* **Šírky:** Všetky signály musia mať explicitne definovanú šírku (napr. `[31:0]`).
* **Naming:** Moduly `snake_case`, inštancie `u_name`, rozhrania `name_if`.
* **Syntéza:** Všetok kód musí byť kompatibilný s **Intel Quartus Prime 25.1 Lite**.
* **Python Orchestrátor:** Generuje všetky adresy, IRQ, bus muxy a `generated_config.tcl`.

---

## 🦾 AI Collaboration Mode

Tento framework je navrhnutý pre spoluprácu s AI agentmi. AI musí pri generovaní nových modulov rešpektovať `ip_registry.yaml` a nikdy nezasahovať do súborov v adresároch `*/gen/` manuálne.

---

## 📂 Súbory a skripty

| Súbor / Skript                      | Účel                                               |
| :---------------------------------- | :------------------------------------------------- |
| `board/config/project_config.yaml`  | Hlavná SoC konfigurácia                            |
| `board/config/ip_registry.yaml`     | Definuje typy periférií, adresy, IRQ a moduly      |
| `board/config/generated_config.tcl` | Výstup z Python generátora pre Quartus             |
| `board/generators/gen_config.py`    | Python orchestrátor (YAML → SV + TCL)              |
| `board/bsp/hal_qmtech_ep4ce55.tcl`  | BSP + PMOD Router + Macro Sync                     |
| `scripts/pre_flow.tcl`              | Quartus pre-flow skript spúšťajúci `gen_config.py` |
| `src/soc/gen/soc_top.sv`            | Auto-generated top-level SoC modul                 |
| `src/soc/gen/soc_interfaces.sv`     | Bus interfaces                                     |
| `src/soc/gen/soc_intc.sv`           | IRQ Prioritizer / VIC                              |
| `src/soc/gen/soc_ram.sv`            | M9K On-chip RAM s bootovacím HEX súborom           |
| `sw/include/soc_map.h`              | C definície registrov                              |
| `sw/include/soc_irq.h`              | C definície IRQ linek                              |
| `sw/linker/sections.lds`            | Linker mapovanie RAM                               |
| `out/`                              | Bitstreamy a reporty (RBF, SOF)                    |

---

## 🧭 Posledná rada pred kompiláciou

1. Skontroluj, že `software.hex` je v rovnakom adresári ako `soc_ram.sv` (alebo uprav `INIT_FILE`).
2. Pridaj všetky vygenerované `.sv` súbory do projektu (`Project -> Add/Remove Files in Project`).
3. Clock pin (zvyčajne 50 MHz na pine `E1`) musí byť pripojený na `clk_sys` v `soc_top`.

---

Týmto README poskytuje kompletný prehľad **nových závislostí, skriptov a adresárovej štruktúry** pre nový orchestrátor SoC.

---

Ak chceš, môžem pripraviť ešte **diagram flow** od YAML → Python → Generated RTL → Quartus → Bitstream, aby bolo README vizuálne kompletne hotové.

Chceš, aby som ho urobil?
