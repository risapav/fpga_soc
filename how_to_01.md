Tu je podrobný návod, ako integrovať tvoje prvé testovacie príklady do pripravenej architektúry. Tento postup ti umožní otestovať zbernicu a periférie ešte predtým, než do systému vložíš komplexné RISC-V jadro.

---

# 🚀 Návod: Prvé kroky a HW testovanie (bez CPU)

Tento dokument vysvetľuje, kam presne umiestniť nové súbory a ako upraviť framework, aby si rozblikal LED alebo 7-segmentový displej pomocou tvojej novej zbernice.

## 📂 1. Umiestnenie súborov

Dodržiavaj túto štruktúru, aby tvoj `gen_config.py` a Quartus vedeli súbory správne nájsť:

| Súbor | Cieľová cesta | Účel |
| :--- | :--- | :--- |
| **`blinker_master.sv`** | `src/soc/static/blinker_master.sv` | "Fake CPU" (Bus Master), ktorý generuje zápisy. |
| **`seg7_top.sv`** | `src/soc/static/seg7_top.sv` | Periféria (Bus Slave), ktorá prijíma dáta. |
| **`display_driver.sv`** | `src/hw_sw/display_driver.sv` | Čistá logika pre multiplexovanie 7-seg displeja. |
| **`soc_top.sv`** | `src/soc/gen/soc_top.sv` | **(Upraviť)** Tu prepojíš Blinker na zbernicu. |

---

## 🛠 2. Krok za krokom: Implementácia

### Krok A: Pridanie Mastera (Blinker)
Vytvor súbor `src/soc/static/blinker_master.sv`. Tento modul bude cyklicky pristupovať na adresu `0x00004000` (ktorú sme v YAML pridelili UARTu/LEDkám).



### Krok B: Úprava `soc_top.sv` (Manuálny zásah)
V tvojom vygenerovanom `src/soc/gen/soc_top.sv` zakomentuj CPU a vlož tam Blinker Mastera. Týmto dočasne nahradíš procesor tvojím testovacím automatom.

```systemverilog
// --- CPU Instance (PicoRV32) ---
/* picorv32 u_cpu (
  .clk (clk_sys), 
  ... 
);
*/

// --- Test Master (Blinker) ---
blinker_master u_test_master (
  .clk_sys (clk_sys),
  .rst_ni  (rst_ni),
  .bus     (bus.master) // Napojenie na tvoju systémovú zbernicu
);
```

### Krok C: Pripojenie Slave periférie
Ak chceš ovládať reálne piny, musíš v `soc_top.sv` pridať inštanciu tvojho `seg7_top` modulu a priradiť mu `_sel` signál z tvojho adresného dekodéra.

---

## 🏗 3. Example: 7-Segment Driver (Statická logika)

Umiestni tento kód do `src/hw_sw/display_driver.sv`. Toto je klasický driver pre QMTech dosku, ktorý nie je závislý na zbernici, ale dostáva dáta z `seg7_top`.

```systemverilog
/**
 * @file display_driver.sv
 * @brief Low-level 7-segment multiplexer for QMTech boards
 */
module display_driver (
  input  wire        clk,
  input  wire [15:0] hex_val, // 4 číslice v HEX (4x4 bity)
  output reg  [7:0]  seg,     // Segmenty A-G + DP
  output reg  [3:0]  dig      // Spoločné anódy/katódy
);
  logic [1:0]  digit_sel;
  logic [15:0] prescaler;

  // Prepínanie číslic (multiplexing)
  always_ff @(posedge clk) begin
    prescaler <= prescaler + 1'b1;
    if (prescaler == '0) digit_sel <= digit_sel + 1'b1;
  end

  // Dekodér HEX na 7-segment (Active Low pre väčšinu QMTech)
  always_comb begin
    dig = ~(4'b0001 << digit_sel);
    case (digit_sel)
      2'd0: seg = decode_hex(hex_val[3:0]);
      2'd1: seg = decode_hex(hex_val[7:4]);
      2'd2: seg = decode_hex(hex_val[11:8]);
      2'd3: seg = decode_hex(hex_val[15:12]);
    endcase
  end

  function [7:0] decode_hex(input [3:0] val);
    case (val)
      4'h0: return 8'hC0; 4'h1: return 8'hF9; 4'h2: return 8'hA4;
      4'h3: return 8'hB0; 4'h4: return 8'h99; 4'h5: return 8'h92;
      // ... pokračuj pre zvyšok HEX hodnôt ...
      default: return 8'hFF;
    endcase
  endfunction
endmodule
```

---

## ⚡ 4. Spustenie v Quartuse

1.  **Open Project:** Otvor `fpga_prj.qpf`.
2.  **Add Files:** Pridaj všetky nové súbory (`.sv`) cez *Project -> Add/Remove Files*.
3.  **Run Tcl:** Spusti `board/generators/gen_config.py` (ak ho nemáš v Pre-Flow).
4.  **Pin Planner:** Priraď piny podľa schémy tvojej QMTech dosky:
    * `clk_sys` -> Pin `E1` (zvyčajne 50 MHz).
    * `rst_ni` -> Pin tvojho tlačidla (napr. `M15`).
    * `seg[7:0]` a `dig[3:0]` -> Piny prislúchajúce displeju.
5.  **Compile:** Klikni na *Start Compilation*.
6.  **Program:** Použi *Programmer* a nahraj `.sof` súbor.

---

## 🔍 Čo by si mal vidieť?

Ak si nastavil `blinker_master` na adresu `0x00004000` a `seg7_top` má v dekodéri rovnaký rozsah, na displeji uvidíš rotujúce čísla alebo blikajúce LED (podľa toho, čo máš na danom pine).

### Chceš, aby som ti pripravil kompletný `.qsf` (Assignment file) s pinmi pre konkrétny QMTech Cyclone IV model?
Stačí napísať presný model dosky (napr. **EP4CE15** alebo **EP4CE55**). 👍