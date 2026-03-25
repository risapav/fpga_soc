// =============================================================================
// MODULE: seg7_counter
// FILE:   src/soc/static/seg7_counter.sv
// BRIEF:  4-digit hex counter on 7-segment display
//
// Controls:
//   ONB_BUTTONS[0] - manual increment (debounced, active low)
//   ONB_BUTTONS[1] - counter reset   (debounced, active low)
//
// Auto-increment: 1 count per second
// Display: 4 hex digits, multiplexed 3-digit common cathode
//          (QMTech EP4CE55 has 3 digit selects -> shows lower 3 digits)
//
// Port names match ip_registry.yaml signals exactly.
// Ports SYS_CLK/RESET_N match soc_top -- internal aliases clk/rst_n.
// =============================================================================

`default_nettype none

module seg7_counter #(
    parameter int CLK_FREQ = 50_000_000
) (
    input  wire        SYS_CLK,
    input  wire        RESET_N,
    // Display
    output logic [7:0] ONB_SEG,
    output logic [2:0] ONB_DIG,
    // Buttons (active low)
    input  wire  [1:0] ONB_BUTTONS
);

    // -------------------------------------------------------------------------
    // Local aliases
    // -------------------------------------------------------------------------
    wire clk = SYS_CLK;
    wire rst_n = RESET_N;

    // -------------------------------------------------------------------------
    // 1-second tick
    // -------------------------------------------------------------------------
    localparam int ONE_SEC = CLK_FREQ - 1;

    logic [$clog2(CLK_FREQ)-1:0] sec_cnt;
    logic                         tick_1s;

    assign tick_1s = (sec_cnt == ONE_SEC[$clog2(CLK_FREQ)-1:0]);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)       sec_cnt <= '0;
        else if (tick_1s) sec_cnt <= '0;
        else              sec_cnt <= sec_cnt + 1;
    end

    // -------------------------------------------------------------------------
    // Button debounce (20 ms)
    // -------------------------------------------------------------------------
    localparam int DEBOUNCE_CNT = CLK_FREQ / 50;  // 20 ms

    logic [1:0] btn_sync_0, btn_sync_1;  // synchroniser stages
    logic [1:0] btn_db;                  // debounced level (active low)
    logic [1:0] btn_press;               // single-cycle pulse on press

    // Two-stage synchroniser
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            btn_sync_0 <= 2'b11;
            btn_sync_1 <= 2'b11;
        end else begin
            btn_sync_0 <= ONB_BUTTONS;
            btn_sync_1 <= btn_sync_0;
        end
    end

    // Per-button debounce counter
    genvar gi;
    generate
        for (gi = 0; gi < 2; gi++) begin : g_deb
            logic [$clog2(DEBOUNCE_CNT)-1:0] db_cnt;
            logic db_level;

            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    db_cnt   <= '0;
                    db_level <= 1'b1;
                end else begin
                    if (btn_sync_1[gi] != db_level) begin
                        if (db_cnt == DEBOUNCE_CNT[$clog2(DEBOUNCE_CNT)-1:0] - 1) begin
                            db_level <= btn_sync_1[gi];
                            db_cnt   <= '0;
                        end else begin
                            db_cnt <= db_cnt + 1;
                        end
                    end else begin
                        db_cnt <= '0;
                    end
                end
            end

            assign btn_db[gi]    = db_level;
            assign btn_press[gi] = !db_level && btn_sync_1[gi];  // falling edge = press
        end
    endgenerate

    // -------------------------------------------------------------------------
    // 16-bit counter
    // BTN0 = manual increment, BTN1 = reset, tick_1s = auto increment
    // -------------------------------------------------------------------------
    logic [15:0] counter;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            counter <= '0;
        else if (!btn_db[1])        // BTN1 held = reset
            counter <= '0;
        else if (btn_press[0])      // BTN0 press = +1
            counter <= counter + 1;
        else if (tick_1s)           // auto +1 per second
            counter <= counter + 1;
    end

    // -------------------------------------------------------------------------
    // Multiplexed 7-segment display
    // QMTech EP4CE55: 3 digit selects -> digits 0,1,2 (lower 12 bits of counter)
    // Refresh rate: ~1 kHz per digit (CLK_FREQ / 3 / refresh_period)
    // -------------------------------------------------------------------------
    localparam int MUX_PERIOD = CLK_FREQ / 3000;  // ~333 us per digit -> 1 kHz refresh

    logic [$clog2(MUX_PERIOD)-1:0] mux_cnt;
    logic [1:0]                     digit_sel;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mux_cnt   <= '0;
            digit_sel <= '0;
        end else begin
            if (mux_cnt == MUX_PERIOD[$clog2(MUX_PERIOD)-1:0] - 1) begin
                mux_cnt   <= '0;
                digit_sel <= (digit_sel == 2'd2) ? 2'd0 : digit_sel + 1;
            end else begin
                mux_cnt <= mux_cnt + 1;
            end
        end
    end

    // Digit select: active low, one-hot inverted
    always_comb begin
        case (digit_sel)
            2'd0:    ONB_DIG = 3'b110;
            2'd1:    ONB_DIG = 3'b101;
            2'd2:    ONB_DIG = 3'b011;
            default: ONB_DIG = 3'b111;
        endcase
    end

    // Digit value mux
    logic [3:0] digit_val;
    always_comb begin
        case (digit_sel)
            2'd0:    digit_val = counter[3:0];
            2'd1:    digit_val = counter[7:4];
            2'd2:    digit_val = counter[11:8];
            default: digit_val = 4'h0;
        endcase
    end

    // HEX to 7-segment decoder (active low, segment order: gfedcba + dp)
    // Segment bits: [7]=dp [6]=g [5]=f [4]=e [3]=d [2]=c [1]=b [0]=a
    function automatic [7:0] hex_to_seg(input [3:0] val);
        case (val)
            4'h0: return 8'hC0;  // 0: abcdef   dp=1 g=1
            4'h1: return 8'hF9;  // 1: bc
            4'h2: return 8'hA4;  // 2: abdeg
            4'h3: return 8'hB0;  // 3: abcdg
            4'h4: return 8'h99;  // 4: bcfg
            4'h5: return 8'h92;  // 5: acdfg
            4'h6: return 8'h82;  // 6: acdefg
            4'h7: return 8'hF8;  // 7: abc
            4'h8: return 8'h80;  // 8: all
            4'h9: return 8'h90;  // 9: abcdfg
            4'hA: return 8'h88;  // A: abcefg
            4'hB: return 8'h83;  // B: cdefg
            4'hC: return 8'hC6;  // C: adef
            4'hD: return 8'hA1;  // D: bcdeg
            4'hE: return 8'h86;  // E: adefg
            4'hF: return 8'h8E;  // F: aefg
        endcase
    endfunction

    assign ONB_SEG = hex_to_seg(digit_val);

endmodule : seg7_counter

`default_nettype wire
