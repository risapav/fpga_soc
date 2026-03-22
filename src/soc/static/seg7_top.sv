/**
 * @file seg7_top.sv
 * @brief Bus-to-7Segment Bridge for QMTech SoC
 */

`default_nettype none

module seg7_top (
  input  wire        clk_i,
  input  wire        rst_ni,
  bus_if.slave       bus,
  output wire [7:0]  seg,
  output wire [3:0]  dig
);

  logic [15:0] display_data;

  // --- Bus Interface (Write Only for Display) ---
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      display_data <= 16'hCAFE; // Default message after reset
    end else if (bus.valid && bus.we) begin
      // Zapíšeme spodných 16 bitov zo zbernice do displeja
      display_data <= bus.wdata[15:0];
    end
  end

  // Bus handshake
  assign bus.ready = bus.valid;
  assign bus.rdata = {16'h0, display_data};

  // --- Physical Driver Instance ---
  display_driver u_driver (
    .clk     (clk_i),
    .hex_val (display_data),
    .seg     (seg),
    .dig     (dig)
  );

endmodule : seg7_top

`default_nettype wire
