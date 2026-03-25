// =============================================================================
// MODULE: leds_top
// FILE:   src/soc/static/leds_top.sv
// BRIEF:  Bus-mapped LED output register
//
// NOTE: QMTech EP4CE55 LEDs are active-low (output inverted).
//       Write 1 to a bit to turn LED ON, 0 to turn OFF.
//
// Register map:
//   0x00  LED  [5:0]  W: set LED state (1=ON)  R: read current state
// =============================================================================
`default_nettype none

module leds_top (
    input  wire        SYS_CLK,
    input  wire        RESET_N,
    input  wire [5:0]  addr_i,
    input  wire [31:0] wdata_i,
    input  wire        we_i,
    output logic [31:0] rdata_o,
    output logic [5:0] led          // active-low: inverted before output
);

    logic [5:0] led_reg;

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N)
            led_reg <= '0;
        else if (we_i && addr_i[2:0] == 3'h0)
            led_reg <= wdata_i[5:0];
    end

    // Active-high LEDs: reg=1 -> pin=1 -> LED ON
    assign led     = led_reg;
    assign rdata_o = {26'h0, led_reg};

endmodule : leds_top

`default_nettype wire
