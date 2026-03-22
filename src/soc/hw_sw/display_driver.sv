/**
 * @file display_driver.sv
 * @brief Multiplexed 7-segment display driver (Active Low)
 */

`default_nettype none

module display_driver (
  input  wire        clk,
  input  wire [15:0] hex_val,
  output reg  [7:0]  seg,
  output reg  [3:0]  dig
);

  logic [16:0] prescaler;
  logic [1:0]  digit_sel;

  // Prescaler pre multiplexovanie (~200Hz refresh rate pri 50MHz)
  always_ff @(posedge clk) begin
    prescaler <= prescaler + 1'b1;
    if (prescaler == '0) digit_sel <= digit_sel + 1'b1;
  end

  // Výber číslice a segmentov
  always_comb begin
    // Digits sú Active Low na QMTech (0 = ON, 1 = OFF)
    dig = 4'b1111;
    dig[digit_sel] = 1'b0;

    case (digit_sel)
      2'b00: seg = hex_to_seg(hex_val[3:0]);
      2'b01: seg = hex_to_seg(hex_val[7:4]);
      2'b10: seg = hex_to_seg(hex_val[11:8]);
      2'b11: seg = hex_to_seg(hex_val[15:12]);
      default: seg = 8'hFF;
    endcase
  end

  // Funkcia pre dekódovanie (Active Low: 0=svieti, 1=nesvieti)
  function [7:0] hex_to_seg(input [3:0] hex);
    case (hex)
      4'h0: return 8'hC0; 4'h1: return 8'hF9; 4'h2: return 8'hA4; 4'h3: return 8'hB0;
      4'h4: return 8'h99; 4'h5: return 8'h92; 4'h6: return 8'h82; 4'h7: return 8'hF8;
      4'h8: return 8'h80; 4'h9: return 8'h90; 4'hA: return 8'h88; 4'hB: return 8'h83;
      4'hC: return 8'hC6; 4'hD: return 8'hA1; 4'hE: return 8'h86; 4'hF: return 8'h8E;
      default: return 8'hFF;
    endcase
  endfunction

endmodule : display_driver

`default_nettype wire
