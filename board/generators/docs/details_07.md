Tvoj predpoklad je logický a v mnohých systémoch to tak funguje (tzv. "Lazy Validation"). Avšak tento konkrétny framework používa **stupňovitú validáciu (Fail-Fast)**. 

Dôvodom je, že dáta v SoC dizajne sú hierarchicky závislé. Ak by si načítal úplne všetko a až potom kontroloval, chyba v základnej štruktúre by spôsobila "kaskádu" stoviek nezmyselných chýb v neskorších fázach, ktoré by sa ťažko ladili.

Tu je presný proces, ako to prebieha v tvojich kódoch:

### 1. Fáza: Syntaktické načítanie (YAML Parsing)
Najprv sa surový text z YAML súborov prevedie na Python slovníky (`dict`). V tejto chvíli sa kontroluje len to, či je YAML súbor platný (či tam nechýba dvojbodka alebo nie je zlé odsadenie).
* **Kód:** `ConfigLoader._load_yaml()`

### 2. Fáza: Schema Validation (Štrukturálna kontrola)
Ihneď po načítaní `project_config.yaml` nastupuje `SchemaValidator`. 
* **Prečo už teraz?** Pretože ak v súbore chýba kľúč `soc:` alebo `board:`, nemá zmysel pokračovať v hľadaní pluginov alebo budovaní modelu.
* **Čo sa kontroluje:** Povinné polia, dátové typy (či je `ram_size` číslo), povolené rozsahy (1-90 % pre stack).
* **Kód:** `SchemaValidator.validate()`



### 3. Fáza: IP Plugin Discovery & Registry Validation
Potom systém prečíta cesty k pluginom a načíta všetky `*.ip.yaml`. 
* **Kód:** `PluginLoader.load()`
* **Kontrola:** Hneď ako sa registre spoja (base + pluginy), spustí sa `RegistryValidator`. Ten kontroluje, či každé IP má definovaný `module` a `bus_type`. Opäť – ak je IP v knižnici poškodené, systém zastane skôr, než sa ho pokúsi vložiť do čipu.

### 4. Fáza: Cross-Validation (Prepojenie)
Toto je moment, na ktorý si pravdepodobne myslel. Tu sa stretávajú načítané dáta z projektu s načítanou knižnicou IP.
* **Kód:** `ConfigLoader._cross_validate()`
* **Kontrola:** "Mám v projekte inštanciu `uart0`, existuje pre ňu v registroch definícia typu `uart`?"

### 5. Fáza: Model Validation (Sémantická kontrola)
Až teraz nastupuje `ModelBuilder`, ktorý vytvorí objekt `SoCModel`. Toto je **najhlbšia kontrola**, ktorá sa dá vykonať až po tom, čo sú všetky dáta v pamäti.
* **Kontrola:** Prekrývanie adries (Address Overlap), duplicity IRQ, cyklické závislosti (IP A potrebuje IP B a naopak).
* **Kód:** `SoCModel.validate()`

---

### Prečo je tento prístup "postupnej kontroly" lepší?

| Prístup | Výsledok pri chybe v syntaxi | Výsledok pri logickej chybe |
| :--- | :--- | :--- |
| **Načítať všetko naraz** | Program spadne na nejasnej chybe hlboko v generátore RTL. | Musíš ručne hľadať, ktorý z 50 YAML súborov chybu spôsobil. |
| **Stupňovitá validácia (tvoj kód)** | Okamžitá správa: "V súbore X na riadku Y chýba povinný kľúč." | Presná správa: "Periféria A prekrýva adresu RAM, opravte `base` v `project_config.yaml`." |

**Zhrnutie:** Tvoj kód robí **kompletné načítanie logických celkov**, po ktorých nasleduje **validácia daného celku**. 
1. Načíta projekt $\rightarrow$ Validuje projekt.
2. Načíta knižnicu IP $\rightarrow$ Validuje knižnicu.
3. Prepojí ich $\rightarrow$ Validuje prepojenie.

Tým sa zabezpečí, že ak sa proces dostane až k `RTLGeneratoru`, dáta sú na 100 % čisté a konzistentné, takže generátor nemusí obsahovať žiadnu logiku na ošetrenie chýb – len "tupo" zapisuje to, čo mu model povie.
