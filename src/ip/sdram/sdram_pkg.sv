/**
 * @file sdram_pkg.sv
 * @brief Globálne definície, typy a parametre pre SDRAM Controller.
 * @details Obsahuje výpočty bitových polí pre AXI-to-SDRAM mapping a JEDEC príkazy.
 * Doplnená podpora pre ID tagging a burst tracking.
 */

`ifndef SDRAM_PKG_SV
`define SDRAM_PKG_SV

`default_nettype none

package sdram_pkg;

  // ===========================================================================
  // 1. MEMORY GEOMETRY (Konfigurovateľné)
  // ===========================================================================
  parameter int DATA_WIDTH      = 16;
  parameter int ROW_ADDR_WIDTH  = 13;
  parameter int BANK_ADDR_WIDTH = 2;
  parameter int COL_ADDR_WIDTH  = 9;
  parameter int AXI_ID_WIDTH    = 4;

  // Pomocné konštanty
  localparam int NUM_BANKS = 1 << BANK_ADDR_WIDTH;
  localparam int NUM_ROWS  = 1 << ROW_ADDR_WIDTH;
  localparam int NUM_COLS  = 1 << COL_ADDR_WIDTH;

  // ===========================================================================
  // 2. TIMING PARAMETERS (@100 MHz)
  // ===========================================================================
  parameter int T_RCD_CYCLES  = 2;
  parameter int T_RP_CYCLES   = 2;
  parameter int T_RFC_CYCLES  = 7;
  parameter int T_RAS_CYCLES  = 4;

  // Parametre pre Write/Read Data Path
  parameter int CAS_LATENCY   = 3;
  parameter int T_WR_CYCLES   = 2;
  parameter int T_WTR_CYCLES  = 2;
  parameter int T_RDL_CYCLES  = CAS_LATENCY + 1;

  parameter int T_REFI_CYCLES = 780;

  // ===========================================================================
  // 3. AXI -> SDRAM ADDRESS MAPPING
  // ===========================================================================
  localparam int BYTE_OFFSET_W = $clog2(DATA_WIDTH/8);

  localparam int COL_BIT_LOW   = BYTE_OFFSET_W;
  localparam int COL_BIT_HIGH  = COL_BIT_LOW + COL_ADDR_WIDTH - 1;

  localparam int BANK_BIT_LOW  = COL_BIT_HIGH + 1;
  localparam int BANK_BIT_HIGH = BANK_BIT_LOW + BANK_ADDR_WIDTH - 1;

  localparam int ROW_BIT_LOW   = BANK_BIT_HIGH + 1;
  localparam int ROW_BIT_HIGH  = ROW_BIT_LOW + ROW_ADDR_WIDTH - 1;

  // ===========================================================================
  // 4. SDRAM COMMANDS
  // ===========================================================================
  typedef enum logic [3:0] {
    CMD_MRS  = 4'b0000,
    CMD_REF  = 4'b0001,
    CMD_PRE  = 4'b0010,
    CMD_ACT  = 4'b0011,
    CMD_WR   = 4'b0100,
    CMD_RD   = 4'b0101,
    CMD_TERM = 4'b0110,
    CMD_NOP  = 4'b0111
  } phy_cmd_e;

  // ===========================================================================
  // 5. DATA STRUCTURES
  // ===========================================================================

  /**
   * @struct sdram_addr_t
   * @brief Dekódovaná adresa pre vnútornú logiku kontroléra.
   */
  typedef struct packed {
    logic [ROW_ADDR_WIDTH-1:0]  row;
    logic [BANK_ADDR_WIDTH-1:0] bank;
    logic [COL_ADDR_WIDTH-1:0]  col;
  } sdram_addr_t;

  /**
   * @struct sdram_cmd_t
   * @brief Rozšírený príkaz pre Scheduler a Read Engine.
   * @details Obsahuje meta-dáta potrebné na udržanie AXI kontextu cez pipeline.
   */
  typedef struct packed {
    sdram_addr_t           addr;
    logic                  write_en;
    logic [7:0]            burst_len;
    logic [AXI_ID_WIDTH-1:0] id;        // Pridané: AXI Transaction ID
    logic                  last;      // Pridané: Označenie posledného beatu v burste
  } sdram_cmd_t;

endpackage : sdram_pkg

`endif // SDRAM_PKG_SV
