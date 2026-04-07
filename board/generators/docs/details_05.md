Súbor formátu **.dot** je textový popis grafu v jazyku **DOT**, ktorý je súčasťou balíka nástrojov **Graphviz**. Keďže ide o otvorený štandard, existuje niekoľko spôsobov, ako si ho prezerať – od jednoduchých online nástrojov až po profesionálne desktopové aplikácie.

Tu sú najlepšie možnosti:

### 1. Online prehliadače (Najrýchlejšia voľba)
Nemusíte nič inštalovať, stačí vložiť obsah súboru do okna prehliadača.
* **Edotor.net**: Moderný a rýchly editor s okamžitým náhľadom.
* **Graphviz Online**: Klasické rozhranie, ktoré v reálnom čase vykresľuje graf podľa vášho kódu.
* **Viz.js**: Implementácia Graphvizu priamo v JavaScripte, funguje v každom prehliadači.

### 2. Desktopové aplikácie (Lokálne prezeranie)
Ak pracujete s citlivými dátami alebo veľkými grafmi, odporúčam lokálne nástroje:
* **Graphviz (gvedit)**: Oficiálny nástroj, ktorý po inštalácii balíka Graphviz poskytuje jednoduché GUI na editáciu a prezeranie.
* **Gephi**: Profesionálny open-source softvér na vizualizáciu a analýzu obrovských sietí (grafov). Dokáže importovať `.dot` súbory.
* **Zest (Eclipse)**: Ak používate vývojové prostredie Eclipse, existujú pluginy na priame renderovanie týchto grafov.



### 3. Rozšírenia pre IDE (Pre vývojárov)
Ak už máte otvorený kód SoC Orchestratora v editore, môžete si graf pozrieť priamo tam:
* **VS Code (Graphviz Interactive Preview)**: Najpopulárnejšie rozšírenie. Stačí otvoriť `.dot` súbor a stlačiť `Ctrl+Shift+V` (alebo ikonu náhľadu). Zobrazí graf vedľa kódu.
* **IntelliJ IDEA / PyCharm**: Existuje plugin "Graphviz", ktorý umožňuje náhľad priamo v IDE.

### 4. Príkazový riadok (Pre automatizáciu)
Ak máte nainštalovaný Graphviz, môžete súbor previesť na obrázok (PNG, SVG, PDF) jedným príkazom:
```bash
dot -Tpng gen/doc/soc_graph.dot -o soc_graph.png
```
Tento spôsob využíva aj samotný Python skript `export.py` v metóde `render_png`, ak nájde binárku `dot` vo vašom systéme.

### Ktorý si vybrať?
* Ak chcete len **rýchlo vidieť**, ako vyzerá vaše SoC: Použite **VS Code** s pluginom alebo **Edotor.net**.
* Ak je graf **príliš veľký a neprehľadný**: Použite **Gephi**, ktorý umožňuje s uzlami dynamicky hýbať a filtrovať ich.
* Ak chcete graf **vložiť do dokumentácie**: Vyexportujte ho cez príkazový riadok do formátu **SVG** (vektorová grafika, ktorá nestráca kvalitu pri priblížení).
