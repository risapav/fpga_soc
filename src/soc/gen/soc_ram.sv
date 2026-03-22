/**
 * @file soc_ram.sv
 * @brief Synchronous Single-Port RAM (M9K-optimized) for Cyclone IV
 *
 * ------------------------------------------------------------------------
 * HLAVNÉ VLASTNOSTI:
 * ------------------------------------------------------------------------
 * ✔ Inferencia do M9K blokov (žiadna LUT RAM)
 * ✔ Byte-enable zápis (4×8-bit lanes)
 * ✔ Synchrónne čítanie (READ-FIRST mód)
 * ✔ Parametrická veľkosť pamäte
 * ✔ Bez bypass logiky (žiadne LUT explózie!)
 *
 * ------------------------------------------------------------------------
 * DÔLEŽITÉ PRAVIDLÁ PRE QUARTUS:
 * ------------------------------------------------------------------------
 * 1. NIKDY nepoužívaj: rdata <= wdata (write-first bypass)
 *    → spôsobí obrovský nárast combinational logiky
 *
 * 2. Používaj striktne synchronous read:
 *    → rdata <= mem[addr];
 *
 * 3. Používaj ramstyle + no_rw_check atribút
 *
 * 4. Adresa musí byť word-aligned (addr = bus_addr[14:2])
 *
 * ------------------------------------------------------------------------
 */

`default_nettype none

module soc_ram #(
  // Celková veľkosť pamäte v bajtoch (musí byť násobok 4)
  parameter int SIZE_BYTES = 32768,

  // Inicializačný HEX súbor (Quartus ho načíta do M9K)
  parameter string INIT_FILE = "software.hex"
) (
  // Hodinový signál
  input  logic clk,

  // Adresa slova (nie bajtu!)
  // Pre 32KB RAM: 32768 / 4 = 8192 slov → 13 bitov
  input  logic [$clog2(SIZE_BYTES/4)-1:0] addr,

  // Byte enable (každý bit = 1 bajt)
  input  logic [3:0]  be,

  // Write enable
  input  logic        we,

  // Write data
  input  logic [31:0] wdata,

  // Read data (registrovaný výstup)
  output logic [31:0] rdata
);

  // Počet 32-bit slov
  localparam int DEPTH = SIZE_BYTES / 4;

  // ----------------------------------------------------------------------
  // M9K RAM deklarácia
  // ----------------------------------------------------------------------
  // ramstyle = "M9K" → vynúti block RAM
  // no_rw_check → potlačí warningy pre read-during-write
  //
  // POZNÁMKA:
  // ram_init_file je preferovaný spôsob inicializácie v Quartuse
  // ----------------------------------------------------------------------
  (* ramstyle = "M9K, no_rw_check", ram_init_file = INIT_FILE *)
  logic [31:0] mem [0:DEPTH-1];

  // ----------------------------------------------------------------------
  // Synchrónna RAM logika
  // ----------------------------------------------------------------------
  // Dôležité:
  // ✔ Čítanie je vždy synchronné (posedge clk)
  // ✔ Žiadny bypass (žiadne rdata <= wdata!)
  // ✔ Quartus mapuje priamo na M9K output register
  // ----------------------------------------------------------------------
  always_ff @(posedge clk) begin

    // ---------------------------
    // WRITE PATH (byte-enable)
    // ---------------------------
    if (we) begin
      if (be[0]) mem[addr][7:0]   <= wdata[7:0];
      if (be[1]) mem[addr][15:8]  <= wdata[15:8];
      if (be[2]) mem[addr][23:16] <= wdata[23:16];
      if (be[3]) mem[addr][31:24] <= wdata[31:24];
    end

    // ---------------------------
    // READ PATH (READ-FIRST)
    // ---------------------------
    // Toto je kritické pre správnu inferenciu M9K
    // Quartus použije interný výstupný register RAM
    //
    // Pri súčasnom read+write:
    // → vráti sa STARÁ hodnota (read-first)
    // ---------------------------
    rdata <= mem[addr];
  end

endmodule : soc_ram

`default_nettype wire
