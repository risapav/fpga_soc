// =============================================================================
// MODULE: led_effects
// FILE:   src/soc/static/led_effects.sv
// BRIEF:  Three independent LED effects, 1-second tick
//
// This is a static RTL module — instantiated by generated soc_top.sv.
// Do not add bus ports here. Port names must match ip_registry.yaml signals.
//
// Effects:
//   ONB_LEDS[5:0]   - rotating shift (onboard LEDs)
//   PMOD_J10_P[7:0] - fill bar (PMOD J10 LED module)
//   PMOD_J11_P[7:0] - Cylon Eye / Larson Scanner (PMOD J11 LED module)
// =============================================================================

`default_nettype none

module led_effects #(
    parameter int CLK_FREQ = 50_000_000
) (
    input  wire        SYS_CLK,
    input  wire        RESET_N,
    output logic [5:0] ONB_LEDS,
    output logic [7:0] PMOD_J10_P,
    output logic [7:0] PMOD_J11_P
);

    // -------------------------------------------------------------------------
    // 1-second tick generator
    // -------------------------------------------------------------------------
    localparam int ONE_SEC = CLK_FREQ - 1;

    logic [$clog2(CLK_FREQ)-1:0] clk_cnt;
    logic                         tick_1s;

    assign tick_1s = (clk_cnt == ONE_SEC[($clog2(CLK_FREQ)-1):0]);

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N)        clk_cnt <= '0;
        else if (tick_1s)   clk_cnt <= '0;
        else                clk_cnt <= clk_cnt + 1;
    end

    // -------------------------------------------------------------------------
    // Effect 1: Rotating shift — onboard LEDs
    // -------------------------------------------------------------------------
    logic [5:0] led_shift;

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N)        led_shift <= 6'b000001;
        else if (tick_1s)   led_shift <= {led_shift[4:0], led_shift[5]};
    end

    assign ONB_LEDS = led_shift;

    // -------------------------------------------------------------------------
    // Effect 2: Fill bar — PMOD J10
    // fill_cnt: 0->8 -> reset, mask: 8'hFF >> (8 - fill_cnt)
    // -------------------------------------------------------------------------
    logic [3:0] fill_cnt;

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N)        fill_cnt <= '0;
        else if (tick_1s)   fill_cnt <= (fill_cnt == 4'd8) ? '0 : fill_cnt + 1;
    end

    assign PMOD_J10_P = (fill_cnt == 0) ? 8'h00 : (8'hFF >> (8 - fill_cnt));

    // -------------------------------------------------------------------------
    // Effect 3: Cylon Eye (Larson Scanner) — PMOD J11
    // -------------------------------------------------------------------------
    typedef enum logic { DIR_RIGHT = 1'b0, DIR_LEFT = 1'b1 } dir_t;

    logic [7:0] cylon_pos;
    dir_t       cylon_dir;

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N) begin
            cylon_pos <= 8'b0000_0001;
            cylon_dir <= DIR_RIGHT;
        end else if (tick_1s) begin
            unique case (cylon_dir)
                DIR_RIGHT: begin
                    if (cylon_pos[7]) begin
                        cylon_dir <= DIR_LEFT;
                        cylon_pos <= cylon_pos >> 1;
                    end else begin
                        cylon_pos <= cylon_pos << 1;
                    end
                end
                DIR_LEFT: begin
                    if (cylon_pos[0]) begin
                        cylon_dir <= DIR_RIGHT;
                        cylon_pos <= cylon_pos << 1;
                    end else begin
                        cylon_pos <= cylon_pos >> 1;
                    end
                end
            endcase
        end
    end

    assign PMOD_J11_P = cylon_pos;

endmodule : led_effects

`default_nettype wire
