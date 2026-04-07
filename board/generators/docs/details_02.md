Tu je podrobný prehľad kľúčových tried (objektov) a ich metód vo frameworku **SoC Orchestrator v6**. Systém je navrhnutý ako modulárna pipeline, kde dáta pretekajú od surového YAML vstupu až po finálny HW/SW kód.

---

## 1. Fáza LOAD (Načítanie a validácia)

### **Trieda: `ConfigLoader` (v `loader.py`)**
Zodpovedá za prvotný kontakt s diskami a kontrolu správnosti vstupov.
* **`_load()`**: Načíta projektový YAML a spojí ho so základným registrom IP jadier.
* **`_cross_validate()`**: Kľúčová metóda, ktorá overuje, či periférie definované v projekte skutočne existujú v registroch (IP knižnici).

### **Trieda: `PluginLoader` (v `loader.py`)**
Umožňuje dynamické rozširovanie knižnice IP jadier bez úpravy hlavného kódu.
* **`_discover()`**: Prehľadáva adresáre a hľadá súbory `*.ip.yaml`.
* **`_detect_layout()`**: Heuristika, ktorá rozpozná, v akom formáte je IP zapísané (Layout A, B alebo C), čo umožňuje flexibilitu pri písaní nových ovládačov.

---

## 2. Fáza BUILD (Transformácia na objektový model)

### **Trieda: `ModelBuilder` (v `builder.py`)**
Srdce logiky, ktoré mení textové dáta na prepojený graf objektov.
* **`build()`**: Hlavná pipeline, ktorá spúšťa inštanciáciu periférií, zberníc a závislostí.
* **`_allocate_address(size)`**: **Address Allocator.** Vypočíta bázovú adresu pre perifériu (ak je nastavená na `auto`), pričom dodržiava zarovnanie (alignment) a kontroluje kolízie.
* **`_resolve_files()`**: Centralizovaná metóda na prevod relatívnych ciest (z pluginov) na absolútne cesty potrebné pre kompiláciu.
* **`_build_dependencies()`**: Vytvára graf prepojení (hodiny, resety, zbernice), ktorý neskôr určí poradie generovania kódu.

---

## 3. Dátový Model (Reprezentácia systému)

### **Trieda: `SoCModel` (v `models.py`)**
Objekt, ktorý drží kompletný "obraz" celého čipu.
* **`validate()`**: Finálna kontrola celého SoC (prekrývanie adries, IRQ konflikty, kompatibilita zberníc).
* **`topological_sort()`**: Implementácia **Kahnovho algoritmu**. Zoradí periférie tak, aby tie, od ktorých iné závisia, boli v kóde prvé.
* **`to_dict()`**: Serializuje celý model do JSON formátu pre externé nástroje.

### **Trieda: `Peripheral` (v `models.py`)**
Reprezentuje jedno konkrétne IP jadro v systéme.
* **`is_aligned`**: Property, ktorá overuje, či je adresa správne zarovnaná podľa veľkosti bloku.
* **`addr_width`**: Vypočíta potrebný počet bitov adresného dekodéra.

---

## 4. Fáza GENERATE & EXPORT (Výstupy)

### **Trieda: `SoCOrchestrator` (v `gen_config.py`)**
Najvyššia úroveň riadenia (Manager), ktorá spája všetky fázy.
* **`_generate_rtl()`**: Volá `RTLGenerator` na vytvorenie SystemVerilog súborov.
* **`_generate_sw()`**: Volá `SWGenerator` na vytvorenie hlavičiek (`.h`) a linker skriptov (`.lds`).
* **`_generate_timing()`**: Načíta `TimingLoader` a vygeneruje SDC súbory pre časovú analýzu.

### **Trieda: `GraphvizExporter` (v `export.py`)**
* **`generate()`**: Vytvorí súbor `.dot`, ktorý vizualizuje architektúru SoC (CPU -> Fabric -> Peripherals).

---

## Vzájomné prepojenie a tok dát

Prepojenie objektov funguje na princípe **Dependency Injection** (vkladania závislostí):

1.  **Vstup:** Používateľ spustí `gen_config.py`.
2.  **Loader -> Builder:** `ConfigLoader` odovzdá "surové" slovníky (raw dicts) do `ModelBuilder`.
3.  **Builder -> Model:** `ModelBuilder` vytvorí inštancie `Peripheral`, `BusFabric` a `RamConfig`, ktoré vloží do jedného objektu `SoCModel`.
4.  **Model -> Generators:** Objekt `SoCModel` je odovzdaný ako argument všetkým generátorom (RTL, SW, TCL, SDC). Tie z neho čítajú atribúty a generujú textové súbory.



**Diagram prepojenia v skratke:**
`YAML` $\rightarrow$ `ConfigLoader` $\rightarrow$ `ModelBuilder` $\rightarrow$ `SoCModel` $\rightarrow$ `Generators` $\rightarrow$ `Final Files (.sv, .h, .sdc)`

Tento prístup zabezpečuje, že ak zmeníte adresu periférie v YAML súbore, zmena sa automaticky a konzistentne premietne do Verilog kódu, C-hlavičiek aj dokumentácie naraz.

Máš nejakú konkrétnu classu, ktorej vnútorné fungovanie by ťa zaujímalo detailnejšie?
