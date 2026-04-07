Tento syntaktický lexikon rozdeľuje kľúčové slová podľa toho, v ktorom type YAML súboru sa nachádzajú. Framework rozlišuje hlavnú konfiguráciu projektu a definíciu IP jadier (registre/pluginy).

---

## 1. Project Configuration (`project_config.yaml`)
Tento súbor definuje inštanciu vášho konkrétneho čipu.

### Sekcia `soc:` (Globálne nastavenia procesora a pamäte)
| Kľúčové slovo | Atribúty / Default | Účel |
| :--- | :--- | :--- |
| `cpu` | `picorv32` (default) | Typ použitého procesora (musí existovať v registri). |
| `clock_freq` | `50000000` (50 MHz) | Frekvencia hlavných systémových hodín v Hz. |
| `ram_size` | **Povinné** (napr. `16384`) | Veľkosť vnútornej RAM v bajtoch (musí byť mocnina 2). |
| `ram_base` | `0x00000000` | Štartovacia adresa RAM v pamäťovom priestore. |
| `ram_latency` | `registered` / `combinational` | Určuje, či má RAM registrovaný výstup (vplyv na časovanie). |
| `reset_vector` | `0x00000000` | Adresa, na ktorej CPU začne vykonávať kód po resete. |
| `stack_percent`| `25` (1-90%) | Koľko % z RAM sa vyhradí pre stack v linker skripte. |

### Sekcia `peripherals:` (Zoznam komponentov)
Každý pod-kľúč je **názov inštancie** (napr. `uart0:`).
| Atribúty | Hodnoty / Default | Účel |
| :--- | :--- | :--- |
| `enabled` | `true` / `false` | Ak je `false`, generátor tento modul úplne ignoruje. |
| `base` | `0xNNNNNNNN` / `auto` | Adresa modulu. `auto` aktivuje automatický alokátor. |
| `type` | Názov z registra | Explicitné určenie typu IP, ak sa líši od názvu inštancie. |
| `params` | Mapa hodnôt | Prepisuje `parameter` hodnoty vo Verilogu (napr. `BAUD: 115200`). |

---

## 2. IP Registry / Plugin Definition (`*.ip.yaml`)
Tento súbor definuje, ako sa má hardvérové jadro správať a ako vyzerá jeho rozhranie.

### Základné meta-dáta
| Kľúčové slovo | Účel |
| :--- | :--- |
| `module` | Názov Verilog modulu (napr. `uart_top`). |
| `bus_type` | Typ zbernice: `simple_bus`, `axi_lite`, `axi_full`, `none`. |
| `address_range`| Veľkosť adresného priestoru, ktorý IP zaberá (napr. `0x100`). |
| `gen_regs` | `true` (default). Ak `false`, framework nevygeneruje register block (použité pri externých IP). |
| `depends_on` | Zoznam iných IP jadier, ktoré musia byť v systéme (napr. `[clk_wiz]`). |

### Sekcia `registers:` (Definícia SW registra)
Zoznam objektov s atribútmi:
* **`name`**: Názov registra (použitý v C hlavičke).
* **`offset`**: Relatívna adresa od `base` (musí byť násobok 4).
* **`access`**: `rw` (čítanie/zápis), `ro` (len čítanie), `wo` (len zápis).
* **`reset`**: Hodnota po resete (default `0`).
* **`width`**: Šírka v bitoch (1-32, default `32`).

### Sekcia `interfaces:` (Prepojenie na vonkajšie piny FPGA)
Definuje, ktoré signály sa vyvedú až do `soc_top` portov.
| Pod-kľúč | Atribúty | Účel |
| :--- | :--- | :--- |
| `type` | `serial`, `gpio`, `spi`... | Kategória rozhrania (ovplyvňuje vizualizáciu v grafe). |
| `signals` | Zoznam signálov | Obsahuje `name`, `dir` (input/output), `width` a `top_name`. |



---

## 3. Timing Configuration (`timing.yaml` alebo sekcia `timing:`)
Definuje fyzické vlastnosti čipu pre Quartus (SDC).

| Kľúčové slovo | Účel |
| :--- | :--- |
| `clocks` | Zoznam hodín: `name`, `port`, `period_ns`. |
| `plls` | Definícia PLL: `inst` (názov v RTL), `source`, `outputs` (násobiče/delitele). |
| `reset` | Pod-sekcia pri hodinách: `port`, `active_low`, `sync_stages`. |
| `clock_groups` | Definuje asynchrónne domény (medzi ktorými TimeQuest nemá počítať slack). |

---

## Príklad hierarchie (Syntaktický strom)
```yaml
project_config.yaml
├── board: { type: string }
├── soc:
│   ├── cpu: string
│   ├── ram_size: int
│   └── clock_freq: int
├── peripherals:
│   └── [instance_name]:
│       ├── enabled: bool
│       ├── base: hex/auto
│       └── params: { KEY: VAL }
└── paths:
    └── ip_plugins: [ string_list ]
```

Tento lexikon je vynucovaný triedami `SchemaValidator` a `RegistryValidator` v súbore `loader.py`. Ak zadáte kľúčové slovo, ktoré tu nie je uvedené, orchestrator vyhlási `ConfigError`.
