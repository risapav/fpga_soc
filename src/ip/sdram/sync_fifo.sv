/**
 * @file sync_fifo.sv
 * @brief Generický synchronný FIFO modul.
 *
 * Parametrizovaný FIFO s AXI-S rozhraním (valid/ready handshake).
 * Nahrádza cmd_fifo, data_fifo v write_engine a meta pipeline v read_engine.
 *
 * @param WIDTH  Šírka dátového slova v bitoch
 * @param DEPTH  Počet slov (musí byť mocnina 2)
 */

`ifndef SYNC_FIFO_SV
`define SYNC_FIFO_SV

`default_nettype none

module sync_fifo #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 16
)(
  input  wire              clk,
  input  wire              rstn,

  // Vstupná strana (producer)
  input  wire [WIDTH-1:0]  s_data,
  input  wire              s_valid,
  output logic             s_ready,

  // Výstupná strana (consumer)
  output logic [WIDTH-1:0] m_data,
  output logic             m_valid,
  input  wire              m_ready,

  // Stavové výstupy
  output logic [$clog2(DEPTH):0] count,
  output logic                   almost_full,
  output logic                   almost_empty
);

  localparam int PTR_W  = $clog2(DEPTH);
  localparam int CNT_W  = PTR_W + 1;

  logic [WIDTH-1:0]  mem [0:DEPTH-1];
  logic [PTR_W-1:0]  wr_ptr, rd_ptr;
  logic [CNT_W-1:0]  cnt;

  wire push = s_valid && s_ready;
  wire pop  = m_valid && m_ready;

  assign s_ready     = (cnt < CNT_W'(DEPTH));
  assign m_valid     = (cnt > 0);
  assign m_data      = mem[rd_ptr];
  assign count       = cnt;
  assign almost_full  = (cnt >= CNT_W'(DEPTH - 2));
  assign almost_empty = (cnt <= CNT_W'(2));

  always_ff @(posedge clk or negedge rstn) begin
    if (!rstn) begin
      wr_ptr <= '0;
      rd_ptr <= '0;
      cnt    <= '0;
    end else begin
      if (push) begin
        mem[wr_ptr] <= s_data;
        wr_ptr      <= wr_ptr + 1;
      end
      if (pop)
        rd_ptr <= rd_ptr + 1;
      case ({push, pop})
        2'b10:   cnt <= cnt + 1;
        2'b01:   cnt <= cnt - 1;
        default: cnt <= cnt;
      endcase
    end
  end

  // Assertion: overflow/underflow check
  // synthesis translate_off
  always_ff @(posedge clk) begin
    if (rstn) begin
      if (push && cnt == CNT_W'(DEPTH))
        $error("[SYNC_FIFO] Overflow! WIDTH=%0d DEPTH=%0d", WIDTH, DEPTH);
      if (pop && cnt == '0)
        $error("[SYNC_FIFO] Underflow! WIDTH=%0d DEPTH=%0d", WIDTH, DEPTH);
    end
  end
  // synthesis translate_on

endmodule

`endif
