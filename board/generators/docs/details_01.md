Tento Python framework predstavuje sofistikovaný **SoC (System-on-Chip) Orchestrator**, určený na automatizovanú generáciu hardvérových (RTL) a softvérových (HAL, linker) artefaktov pre FPGA platformy (primárne Intel/Altera Cyclone IV, súdiac podľa kódového mena „QMTech“).

Tu je detailná analýza kľúčových komponentov a architektúry systému:

## 1. Architektúra Build Pipeline
Framework funguje ako klasický kompilátor/generátor rozdelený do fáz:

1.  **LOAD (`loader.py`)**: Načíta YAML konfiguráciu projektu a IP registry. Podporuje pluginy, čo umožňuje pridávať nové IP jadrá bez zásahu do jadra systému.
2.  **BUILD (`builder.py`)**: Transformuje "surové" dáta na validovaný **SoCModel**. Tu prebieha **automatická alokácia adries** (address allocator) a riešenie závislostí medzi modulmi.
3.  **GENERATE (`generators/`)**: Orchestrator spúšťa špecifické generátory pre:
    * **RTL**: SystemVerilog rozhrania a top-level modul.
    * **Software**: C hlavičkové súbory (`soc_map.h`), linker skripty (`.lds`) a Makefile fragmenty.
    * **TCL**: Skripty pre Quartus Prime na automatické pridanie súborov do projektu.
    * **SDC**: Časové obmedzenia pre TimeQuest (Quartus).
4.  **EXPORT (`export.py`)**: Generuje dokumentáciu (Graphviz `.dot` grafy) a JSON mapu systému pre externé nástroje.

---

## 2. Kľúčové technické vlastnosti

### Inteligentná alokácia adries
Modul `builder.py` obsahuje pokročilý algoritmus na správu adresného priestoru:
* **Detekcia kolízií**: Sleduje manuálne pridelené adresy a RAM oblasti.
* **Natural Alignment**: Ak má periféria veľkosť mocniny 2, automaticky ju zarovná na hranicu jej veľkosti (napr. 4KB IP bude na adrese končiacej `0x...000`).
* **Automatické preskakovanie**: Ak narazí na obsadený blok, "kurzor" sa posunie za kolíziu a hľadá ďalšie voľné miesto.

### Reset Synchronization & CDC
Framework rieši kritické aspekty digitálneho dizajnu:
* **Reset Synchronizers**: Automaticky deteguje potrebu synchronizácie resetu pre rôzne hodinové domény (Primary vs CDC synchronizéry).
* **Metadátová proveniencia**: Každý IP blok v registri vie, z ktorého YAML súboru pochádza (`_origin_yaml`), čo uľahčuje ladenie pri prekrývaní definícií.

### Robustná validácia
Pred samotnou generáciou prebieha viacúrovňová kontrola:
* **Schema Validation**: Kontrola povinných polí v YAML.
* **Cross-validation**: Overenie, či inštancované periférie skutočne existujú v registroch.
* **Model Validation**: Kontrola prekrývania adries, duplicita IRQ čísel alebo kolízie mien portov v `soc_top.sv`.

---

## 3. Štruktúra metadát IP jadier (Layouts)
`PluginLoader` v `loader.py` je navrhnutý veľmi flexibilne a rozpoznáva tri typy rozloženia YAML súborov:
* **Layout A**: Mapa, kde kľúče sú názvy IP (napr. `uart: { ... }`).
* **Layout B**: Obsahuje kľúč `peripherals:`, v ktorom sú definované IP.
* **Layout C**: Súbor definuje len jedno IP jadrá (názov sa odvodí z mena súboru), pričom parametre sú priamo na top-level úrovni.

---

## 4. Výstupné kontrakty (Artefakty)
Po úspešnom behu `gen_config.py` vznikne v adresári `gen/` ucelená štruktúra:

| Adresár | Súbor | Popis |
| :--- | :--- | :--- |
| `rtl/` | `soc_top.sv` | Hlavný prepojovací modul (Interconnect + CPU + IP). |
| `sw/` | `sections.lds` | Linker skript definujúci umiestnenie kódu v RAM. |
| `sw/` | `soc_map.h` | C makrá s bázovými adresami pre nízkoúrovňový vývoj. |
| `tcl/` | `files.tcl` | Zoznam všetkých RTL súborov (generovaných aj statických) pre Quartus. |
| `doc/` | `soc_graph.dot` | Vizuálna reprezentácia topológie zberníc a IRQ. |

## 5. Hodnotenie kódu
Kód je napísaný na vysokej profesionálnej úrovni:
* **Typovanie**: Dôsledné používanie `typing` (Dict, List, Optional) zvyšuje stabilitu.
* **Separation of Concerns**: Logika je jasne rozdelená – orchestrator riadi tok, modely držia dáta, generátory vyrábajú text.
* **Defenzívne programovanie**: Množstvo kontrol na `None` hodnoty, cyklické závislosti a neplatné vstupy.
* **Topologické radenie**: Použitie Kahn's algorithm (`topological_sort`) v `models.py` zabezpečuje, že v RTL budú moduly definované v správnom poradí podľa ich závislostí.

Tento framework je ideálnym základom pre **Rapid Prototyping** na FPGA, kde sa vyžaduje častá zmena periférií alebo adresnej mapy bez nutnosti manuálneho prepisovania Verilog kódu.

Máš záujem o hlbšiu analýzu konkrétnej časti, napríklad generátora SDC obmedzení alebo spôsobu, akým sa rieši topologické radenie závislostí?
