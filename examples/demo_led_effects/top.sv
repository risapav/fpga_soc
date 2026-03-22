// =============================================================================
// DEMO: led_effects/top.sv
// Tri nezávislé LED efekty — standalone RTL, bez CPU a zbernice
//
// Efekty:
//   LED[5:0]   — onboard: bežiace svetlo (rotating shift)
//   LED_J10[7:0] — PMOD J10: plniaci sa stĺpec (fill bar)
//   LED_J11[7:0] — PMOD J11: Cylon Eye (Larson Scanner)
//
// Portové názvy zodpovedajú názvom v hal_qmtech_ep4ce55.tcl:
//   ONB_LEDS, PMOD_J10_P, PMOD_J11_P
// =============================================================================

`timescale 1ns/1ps
`default_nettype none

module top #(
    parameter int CLK_FREQ = 50_000_000
) (
    input  wire        SYS_CLK,
    input  wire        RESET_N,

    // Onboard LED (6x)
    output logic [5:0] ONB_LEDS,

    // PMOD J10 — 8x LED (fill bar)
    output logic [7:0] PMOD_J10_P,

    // PMOD J11 — 8x LED (Cylon Eye)
    output logic [7:0] PMOD_J11_P
);

    // -------------------------------------------------------------------------
    // 1-sekundový tick generátor
    // -------------------------------------------------------------------------
    localparam int ONE_SEC = CLK_FREQ - 1;

    logic [$clog2(CLK_FREQ)-1:0] clk_cnt;
    logic                         tick_1s;

    assign tick_1s = (clk_cnt == ONE_SEC);

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N)   clk_cnt <= '0;
        else if (tick_1s) clk_cnt <= '0;
        else            clk_cnt <= clk_cnt + 1;
    end

    // -------------------------------------------------------------------------
    // Efekt 1: Bežiace svetlo — onboard LED[5:0]
    // -------------------------------------------------------------------------
    logic [5:0] led_shift;

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N)
            led_shift <= 6'b000001;
        else if (tick_1s)
            led_shift <= {led_shift[4:0], led_shift[5]};  // cyklický posun vľavo
    end

    assign ONB_LEDS = led_shift;

    // -------------------------------------------------------------------------
    // Efekt 2: Plniaci sa stĺpec — PMOD J10 [7:0]
    // fill_cnt ide 0→8 → reset na 0
    // -------------------------------------------------------------------------
    logic [3:0] fill_cnt;

    always_ff @(posedge SYS_CLK or negedge RESET_N) begin
        if (!RESET_N)
            fill_cnt <= '0;
        else if (tick_1s) begin
            if (fill_cnt == 4'd8)
                fill_cnt <= '0;
            else
                fill_cnt <= fill_cnt + 1;
        end
    end

    // 8'hFF >> (8 - fill_cnt): 0→00000000, 1→00000001, ..., 8→11111111
    assign PMOD_J10_P = (fill_cnt == 0) ? 8'h00 : (8'hFF >> (8 - fill_cnt));

    // -------------------------------------------------------------------------
    // Efekt 3: Cylon Eye (Larson Scanner) — PMOD J11 [7:0]
    // Jedna LED sa pohybuje tam a späť
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

endmodule : top

`default_nettype wire
