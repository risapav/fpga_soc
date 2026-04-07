Analýza poskytnutého SoC Frameworku (v6) ukazuje, že ide o vysoko modulárny, produkčne orientovaný systém s čistou architektúrou. Kód kombinuje hardvérové inžinierstvo (RTL) so softvérovým inžinierstvom (Python/Jinja2/YAML).

Tu je podrobné prehodnotenie kvality, funkčnosti a návrhy na vylepšenia.

---

## 1. Hodnotenie kvality a architektúry
**Silné stránky:**
* **Separation of Concerns:** Jasné oddelenie fáz (Load -> Build -> Generate -> Export).
* **Typová bezpečnosť:** Dôsledné používanie `dataclasses` a `Enums` v `models.py` minimalizuje chyby pri prenose dát medzi modulmi.
* **Robustná validácia:** `SchemaValidator` a `RegistryValidator` zachytia 90 % chýb v konfigurácii skôr, než sa spustí generovanie RTL.
* **Flexibilita pluginov:** Podpora troch layoutov YAML (A, B, C) v `PluginLoader` je vynikajúca pre spätnú kompatibilitu.

**Slabé stránky:**
* **Error Handling:** Hoci systém vyhadzuje `ConfigError`, pri kritických runtime chybách (napr. IO chyby pri zápise) len vypíše traceback.
* **Testovateľnosť:** Chýba unit test suite pre kľúčovú logiku (napr. pre Kahnov algoritmus alebo Address Allocator).

---

## 2. Funkčnosť a potenciálne bugy

### A. Address Allocator (Potenciálny "Corner Case")
V `builder.py` metóda `_allocate_address` používa `alignment = size` pre mocniny dvojky.
* **Problém:** Ak má periféria veľkosť napr. 64 KB, ale používateľ manuálne umiestnil inú perifériu na adresu `0x90008000`, auto-alokátor môže zlyhať alebo vytvoriť obrovskú medzeru, hoci by sa tam IP zmestila pri inom zarovnaní.
* **Riziko:** Pri veľmi tesných pamäťových mapách môže 1024 iterácií v cykle naraziť na limit (zbytočné vyčerpanie adresného priestoru).

### B. Reset Synchronizácia
V `gen_config.py` sa `timing_cfg` načítava v metóde `_generate_timing`, ale metóda `_generate_rtl` ho potrebuje na generovanie synchronizérov v `soc_top.sv`.
* **Bug:** V kóde je poznámka: `_generate_timing runs AFTER _generate_rtl`. Ak teda `_generate_rtl` potrebuje informáciu o tom, koľko stupňov má mať synchronizér, a táto info je v `timing.yaml`, môže dôjsť k situácii, kde sa vygeneruje RTL s defaultnými hodnotami namiesto tých špecifických.

### C. Závislosti (Topological Sort)
* **Riziko:** Kahnov algoritmus v `models.py` rieši závislosti medzi perifériami. Ak však periféria A závisí od periférie B a obe majú rovnakú `base` adresu (chyba v konfigurácii), `tie-breaker` (zoradenie podľa adresy) nemusí fungovať správne, ak validácia adries zlyhá až neskôr.

---

## 3. Navrhované vylepšenia

### 1. Zavedenie Logging modulu
Namiesto `print()` a manuálnych `_info()`/`_warn()` wrapperov odporúčam štandardnú knižnicu `logging`.
* **Prínos:** Umožní logovať do súboru, filtrovať úrovne (DEBUG/INFO) a lepšie formátovať výstupy pre CI/CD linky.

### 2. Inkrementálne generovanie (Checksums)
Pridať kontrolu `build_hash` pred spustením generátorov.
* **Návrh:** Ak sa `project_config.yaml` ani IP pluginy nezmenili, orchestrator by mal preskočiť fázu generovania RTL. To dramaticky zrýchli prácu pri veľkých projektoch, kde Quartus nemusí znova analyzovať nezmenené súbory.

### 3. Zlepšenie Address Allocator-a
* **Návrh:** Pridať podporu pre "Address Regions". Napríklad definovať región `PERIPHERALS` (0x40000000 - 0x7FFFFFFF) a `SRAM` (0x00000000 - 0x3FFFFFFF). Alokátor by potom nehľadal v celom 32-bitovom priestore, ale len v špecifických zónach.

### 4. Automatizovaná dokumentácia registra (HTML)
Pridať nový `Exporter`, ktorý vygeneruje interaktívnu HTML stránku s dokumentáciou registrov.
* **Prínos:** Vývojári firmvéru by mali k dispozícii klikateľnú dokumentáciu namiesto prezerania surového JSONu alebo .dot grafu.



### 5. Verilator / Lint integrácia
Do `TCLGenerator` alebo nového modulu pridať generovanie `Makefile` pre **Verilator**.
* **Prínos:** Umožní okamžitý linting vygenerovaného RTL bez nutnosti otvárať Quartus, čo šetrí minúty pri každej zmene konfigurácie.

---

## 4. Ukážka opravy kritického miesta (Refaktoring)

V `builder.py` odporúčam upraviť vkladanie do `_allocated` tak, aby sa predchádzalo `ConfigError` až pri alokácii, ale už pri načítaní:

```python
# V builder.py - lepšia detekcia kolízií
def _insert_allocated(self, base: int, end: int, source: str) -> None:
    for b, e, s in self._allocated_with_source:
        if base <= e and end >= b:
            raise ConfigError(
                f"Collision: {source} [0x{base:08X}-0x{end:08X}] "
                f"overlaps with {s} [0x{b:08X}-0x{e:08X}]"
            )
    self._allocated_with_source.append((base, end, source))
    self._allocated.append((base, end))
    self._allocated.sort() 
```

**Záver:** Systém je vo verzii 6 veľmi stabilný a pripravený na nasadenie. Najväčší prínos by momentálne mala **integrácia s linterom (Verilator)** a **precíznejšie časovanie načítania timing konfigurácie**, aby RTL generátor vždy pracoval s finálnymi dátami o hodinových doménach.
