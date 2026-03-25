// =============================================================================
// MODULE: blink_test
// FILE:   src/soc/static/blink_test.sv
// BRIEF:  Minimal LED blink - verifies clock and LED pins
// =============================================================================
`default_nettype none

module blink_test #(
    parameter int CLK_FREQ = 50_000_000
) (
    input  wire       SYS_CLK,
    input  wire       RESET_N,
    output wire [5:0] ONB_LEDS
);
    // blink ~1.5 Hz
    localparam int CNT_MAX = CLK_FREQ / 3;
    reg [$clog2(CNT_MAX)-1:0] cnt;
    reg blink;

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N) begin
            cnt   <= '0;
            blink <= 1'b0;
        end else if (cnt == CNT_MAX - 1) begin
            cnt   <= '0;
            blink <= ~blink;
        end else begin
            cnt <= cnt + 1'b1;
        end
    end

    assign ONB_LEDS = {6{blink}};

endmodule : blink_test

`default_nettype wire
