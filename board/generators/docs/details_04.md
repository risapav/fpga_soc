Áno, `Loader` a hlavný `SoC Orchestrator` majú niekoľko mechanizmov, ako vizualizovať a kontrolovať načítané dáta v rôznych fázach spracovania. Systém rozlišuje medzi **konzolovým výpisom (logovaním)** a **generovaním strojovo čitateľných súborov**.

Tu je prehľad toho, ako môžeš skontrolovať stav objektov:

### 1. Konzola: Logovanie fáz načítania
Priamo v triedach `PluginLoader` a `ConfigLoader` sú zabudované mechanizmy, ktoré do terminálu vypisujú priebeh operácií. Ak spustíš skript s prepínačom `--verbose` (alebo `-v`), získaš podrobnejší výpis.

* **Výpis pred validáciou (Discovery):** `PluginLoader` vypisuje zoznam všetkých nájdených `*.ip.yaml` súborov a poradie, v akom sa načítavajú.
* **Identifikácia pôvodu:** Vďaka kľúčom `_origin_yaml` a `_plugin_path` (ktoré injektuje `ConfigLoader`) systém presne vie, z ktorého súboru pochádza každý načítaný objekt. Ak nastane duplicita, systém vypíše varovanie: `[WARN] IP 'uart' redefined by plugin...`.

### 2. Výpis po validácii: `soc_map.json`
Toto je kľúčový nástroj pre kontrolu. Po tom, čo prebehne kompletná validácia (`SchemaValidator`, `RegistryValidator` a `Cross-validation`), trieda **`JsonExporter`** vyexportuje celý objekt `SoCModel` do súboru.

* **Umiestnenie:** `gen/doc/soc_map.json`
* **Obsah:** Tu nájdeš výsledný stav systému po všetkých transformáciách (napr. po tom, čo sa `auto` adresy zmenili na fixné hexadecimálne hodnoty).
* **Účel:** Slúži na "diff" kontrolu – môžeš porovnať JSON z dvoch rôznych spustení a presne vidieť, čo sa v modeli zmenilo.



### 3. Vizuálna kontrola: `soc_graph.dot`
Ak chceš skontrolovať prepojenia (topológiu) objektov, ktoré úspešne prešli validáciou, `GraphvizExporter` vygeneruje graf.
* V grafe vidíš inštancie, ich bázové adresy, priradené IRQ a typy zberníc.
* Ak v grafe niečo chýba, znamená to, že to neprešlo validáciou alebo nebolo správne povolené (`enabled: true`).

### 4. Interné mechanizmy pre vývojára (Debug)
Ak upravuješ kód a potrebuješ vidieť surový stav objektov v Python pamäti, framework používa metódy `to_dict()` v triedach ako `Peripheral`, `BusFabric` či `SoCModel`.

Môžeš do kódu (napr. do `gen_config.py` po fáze buildu) vložiť:
```python
import json
print(json.dumps(model.to_dict(), indent=4))
```
Toto ti vypíše kompletný stav validovaného modelu priamo do terminálu.

### Zhrnutie kontrolných bodov:

| Fáza | Nástroj kontroly | Čo uvidíš |
| :--- | :--- | :--- |
| **Načítavanie** | Terminálový log | Ktoré súbory boli nájdené a či sa nebijú. |
| **Validácia** | `[OK] Schema: valid` | Potvrdenie, že syntax je v poriadku. |
| **Po validácii** | `gen/doc/soc_map.json` | Definitívny zoznam objektov so všetkými parametrami. |
| **Štruktúra** | `gen/doc/soc_graph.png` | Logické prepojenia medzi načítanými objektmi. |

Ak potrebuješ špecifický formát výpisu (napríklad len zoznam kolízií v adresách), najjednoduchšie je pozrieť sa do súboru `gen/doc/soc_map.json`, ktorý je "zdrojom pravdy" pre celú zostavu.
