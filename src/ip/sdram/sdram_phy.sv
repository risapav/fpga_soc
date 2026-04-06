/**
 * @file sdram_phy.sv
 * @brief SDR SDRAM PHY s opravenou CAS latency pipeline.
 *
 * OPRAVY:
 *  [FIX-PIPE-DEPTH] valid_pipe_sh mal CAS_LATENCY-1 stupňov (latencia=CL-1).
 *                   Opravené na CAS_LATENCY stupňov.
 *
 *  [FIX-CDC-LATENCY] 2-FF synchronizátor pre read_en_in pridával 2 extra cykly.
 *                    Nahradený 1 registrom — clk a clk_sh majú rovnakú frekvenciu,
 *                    len fázový posun 90°, metastabilita nehrozí.
 *
 *  [FIX-SYNC-LATENCY] Dvojitá spätná synchronizácia (dq_meta→dq_i) pridávala
 *                     2 cykly. Nahradená jedným registrom.
 *
 * VÝSLEDNÁ PIPELINE LATENCIA (od read_en_in po dq_i_valid):
 *
 *   clk:     0  1  2  3  4  5
 *   CMD_RD:  X
 *   read_en_sh: (1 cyklus clk_sh oneskorenie)
 *   pipe[0]: X
 *   pipe[1]:    X
 *   pipe[2]:       X
 *   capture:          X  (valid_pipe[CL-1]=1, sdram_dq vzorkovaný)
 *   dq_i_valid:         X  (synchronizácia do clk domény)
 *
 *   Celková latencia od read_en_in: CAS_LATENCY + 1 clk cyklus
 *   read_engine PIPE_LEN musí byť CAS_LATENCY + 1
 */

`ifndef SDRAM_PHY_SV
`define SDRAM_PHY_SV

`default_nettype none
import sdram_pkg::*;

module sdram_phy #(
  parameter int DATA_WIDTH      = 16,
  parameter int ROW_ADDR_WIDTH  = 13,
  parameter int BANK_ADDR_WIDTH = 2,
  parameter int CAS_LATENCY     = 3
)(
  input  wire clk,
  input  wire clk_sh,
  input  wire rstn,

  input  wire phy_cmd_e                  phy_cmd,
  input  wire [ROW_ADDR_WIDTH-1:0]       addr_in,
  input  wire [BANK_ADDR_WIDTH-1:0]      ba_in,
  input  wire                            read_en_in,

  input  wire [DATA_WIDTH-1:0]           dq_o,
  input  wire                            dq_oe,

  output logic [DATA_WIDTH-1:0]          dq_i,
  output logic                           dq_i_valid,
  output logic                           phy_wready,

  output logic [ROW_ADDR_WIDTH-1:0]      sdram_addr,
  output logic [BANK_ADDR_WIDTH-1:0]     sdram_ba,
  output logic                           sdram_ras_n,
  output logic                           sdram_cas_n,
  output logic                           sdram_we_n,
  output logic                           sdram_cs_n,
  inout  wire  [DATA_WIDTH-1:0]          sdram_dq,
  output logic                           sdram_clk,
  output logic                           sdram_cke
);

  assign sdram_clk = clk_sh;
  assign sdram_cke = 1'b1;

  // --------------------------------------------------------------------------
  // Command register
  // --------------------------------------------------------------------------
  always_ff @(posedge clk or negedge rstn) begin
    if (!rstn) begin
      {sdram_cs_n, sdram_ras_n, sdram_cas_n, sdram_we_n} <= 4'b1111;
      sdram_addr <= '0;
      sdram_ba   <= '0;
    end else begin
      {sdram_cs_n, sdram_ras_n, sdram_cas_n, sdram_we_n} <= phy_cmd;
      sdram_addr <= addr_in;
      sdram_ba   <= ba_in;
    end
  end

  // --------------------------------------------------------------------------
  // DQ tristate
  // --------------------------------------------------------------------------
  assign sdram_dq = dq_oe ? dq_o : 'z;

  // --------------------------------------------------------------------------
  // [FIX-CDC-LATENCY] read_en: clk → clk_sh (1 register, nie 2-FF)
  // clk i clk_sh majú rovnakú frekvenciu — len fázový posun 90°.
  // Metastabilita nehrozí, 1 register je dostatočný.
  // --------------------------------------------------------------------------
  logic read_en_sh;
  always_ff @(posedge clk_sh or negedge rstn) begin
    if (!rstn) read_en_sh <= 1'b0;
    else       read_en_sh <= read_en_in;
  end

  // --------------------------------------------------------------------------
  // [FIX-PIPE-DEPTH] CAS latency pipeline v clk_sh doméne
  //
  // valid_pipe[CAS_LATENCY-1:0] = CAS_LATENCY stupňov
  // Vydanie keď valid_pipe[CAS_LATENCY-1] = 1
  // --------------------------------------------------------------------------
  logic [CAS_LATENCY+1:0] valid_pipe_sh;   // CAS_LATENCY+2 stupňov
  logic [DATA_WIDTH-1:0]  dq_capture_sh;
  logic                   dq_valid_sh;

  always_ff @(posedge clk_sh or negedge rstn) begin
    if (!rstn) begin
      valid_pipe_sh <= '0;
      dq_capture_sh <= '0;
      dq_valid_sh   <= 1'b0;
    end else begin
      // [FIX-PIPE-DEPTH] Posun: read_en_sh vstupuje do LSB
      valid_pipe_sh <= {valid_pipe_sh[CAS_LATENCY:0], read_en_sh};

      // Vydanie po CAS_LATENCY+2 clk_sh cykloch
      dq_valid_sh <= valid_pipe_sh[CAS_LATENCY+1];
      if (valid_pipe_sh[CAS_LATENCY+1])
        dq_capture_sh <= sdram_dq;
    end
  end

  // --------------------------------------------------------------------------
  // [FIX-SYNC-LATENCY] Synchronizácia späť do clk domény (1 register)
  // --------------------------------------------------------------------------
  always_ff @(posedge clk or negedge rstn) begin
    if (!rstn) begin
      dq_i       <= '0;
      dq_i_valid <= 1'b0;
    end else begin
      dq_i       <= dq_capture_sh;
      dq_i_valid <= dq_valid_sh;
    end
  end

  assign phy_wready = 1'b1;

endmodule

`default_nettype wire
`endif
