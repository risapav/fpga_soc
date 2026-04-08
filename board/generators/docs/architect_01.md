Začnem od základov — nové `models.py` s node architektúrou:Mám kompletný obraz. Teraz navrhujem architektúru a implementujem:Teraz navrhujem architektúru pred implementáciou:Architektúra je jasná. Implementujem v 3 fázach:

**Fáza 1** — `models.py`: node dataclassy + `SoCModel` ako kompozícia
**Fáza 2** — `builder.py`: `NodeFactory` aktivuje len prítomné sekcie
**Fáza 3** — `export.py`: `StructureExporter` → `build_report.md` + `plugin_map.json`Fáza 1 a 2 hotové. Výsledky testov:

**Test 1** — port kolízia `ONB_LEDS` medzi `blink_01` a `blink_02` je zachytená s jasnou chybou namiesto tichého "SUCCESSFUL buildu"

**Test 2** — standalone mode: `active_nodes=['StandaloneNode']` — žiadny `CpuNode`, žiadny `MemoryNode`

**Test 3** — JSON obsahuje len `meta, onboard, pmod, standalone` — žiadne `cpu`, `memory`, `irqs`, `bus_fabrics`

**Test 4** — SOC mode aktivuje správne `ClockNode`, `CpuNode`, `MemoryNode`

**Test 5** — `port_overrides` funguje — `blink_01.ONB_LEDS → ONB_LEDS_A`, `blink_02.ONB_LEDS → ONB_LEDS_B`

Zostáva **Fáza 3** — `StructureExporter` pre `build_report.md` a `plugin_map.json`. Pokračujem?