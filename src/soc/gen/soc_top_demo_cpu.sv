/**
 * @file soc_top.sv
 * @brief Auto-generated SoC Top-Level
 */

`default_nettype none

module soc_top (
  input  wire  clk_sys,
  input  wire  rst_ni
);

  // --- Bus Instance ---
  bus_if bus();

  // --- CPU Instance (PicoRV32) ---
  logic [31:0] irq_vector;

blinker_master u_test_master (
  .clk_sys (clk_sys),
  .rst_ni  (rst_ni),
  .bus     (bus.master) // BUM! Blinker teraz ovláda celú tvoju zbernicu
);

  assign bus.we = |bus.be;

  // --- Peripheral Interfaces ---
  uart_if uart0_if();

  // --- Address Decoder ---
  logic uart0_sel, intc_sel, timer0_sel;

  always_comb begin
    uart0_sel  = (bus.addr >= 32'h4000 && bus.addr < 32'h4010);
    intc_sel   = (bus.addr >= 32'h1000 && bus.addr < 32'h1020);
    timer0_sel = (bus.addr >= 32'h5000 && bus.addr < 32'h5010);
  end

  // --- Peripheral Instantiations ---
  uart_top u_uart0 (
    .clk_i  (clk_sys),
    .rst_ni (rst_ni),
    .bus    (bus.slave), // Zjednodušené pre ukážku, v reále cez mux
    .uart   (uart0_if.master)
  );

  // --- IRQ Aggregation ---
  assign irq_vector[0] = u_uart0.irq_rx_done;
  assign irq_vector[1] = u_uart0.irq_tx_ready;
  assign irq_vector[2] = u_timer0.irq_alarm;

endmodule : soc_top
