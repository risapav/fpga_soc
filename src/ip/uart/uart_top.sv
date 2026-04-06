// =============================================================================
// MODULE: uart_top
// FILE:   src/soc/static/uart_top.sv
// BRIEF:  Simple UART peripheral - bus-mapped TX/RX
//
// Register map (base + offset):
//   0x00  DATA_REG  [7:0]  W: write byte to TX FIFO  R: read byte from RX FIFO
//   0x04  STAT_REG  [0]    TX_BUSY  1=transmitting
//                  [1]    RX_VALID 1=data available in RX
//
// Baud rate: CLK_FREQ / (BAUD_DIV+1)
// Default: 50 MHz / 434 = ~115200 baud
// =============================================================================

`default_nettype none

module uart_top #(
    parameter int CLK_FREQ = 50_000_000,
    parameter int BAUD_DIV = 433        // 50MHz/115200 - 1
) (
    input  wire        clk_i,
    input  wire        rst_ni,
    // Simple bus interface
    input  wire [5:0]  addr_i,
    input  wire [31:0] wdata_i,
    input  wire        we_i,
    output logic [31:0] rdata_o,
    // External UART pins
    output logic       tx_o,
    input  wire        rx_i,
    // IRQ
    output logic       irq_o
);

    // -------------------------------------------------------------------------
    // Baud rate generator
    // -------------------------------------------------------------------------
    logic [$clog2(BAUD_DIV+1)-1:0] baud_cnt;
    logic                           baud_tick;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            baud_cnt  <= '0;
            baud_tick <= 1'b0;
        end else begin
            if (baud_cnt == BAUD_DIV[$clog2(BAUD_DIV+1)-1:0]) begin
                baud_cnt  <= '0;
                baud_tick <= 1'b1;
            end else begin
                baud_cnt  <= baud_cnt + 1;
                baud_tick <= 1'b0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // TX shift register
    // -------------------------------------------------------------------------
    // Frame: start(0) + 8 data bits + stop(1)
    logic [9:0] tx_shift;   // {stop, data[7:0], start}
    logic [3:0] tx_bit_cnt;
    logic       tx_busy;

    // Edge detect on we_i - prevents re-triggering when bus.valid holds high
    logic we_prev;
    always_ff @(posedge clk_i or negedge rst_ni)
        if (!rst_ni) we_prev <= 1'b0;
        else          we_prev <= we_i;
    wire we_pulse = we_i & ~we_prev;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            tx_shift   <= 10'h3FF;  // idle = all 1s
            tx_bit_cnt <= '0;
            tx_busy    <= 1'b0;
            tx_o       <= 1'b1;
        end else begin
            if (!tx_busy && we_pulse && addr_i[2:0] == 3'h0) begin
                // Load TX: start=0, data, stop=1
                tx_shift   <= {1'b1, wdata_i[7:0], 1'b0};
                tx_bit_cnt <= 4'd10;
                tx_busy    <= 1'b1;
            end else if (tx_busy && baud_tick) begin
                tx_o       <= tx_shift[0];
                tx_shift   <= {1'b1, tx_shift[9:1]};
                tx_bit_cnt <= tx_bit_cnt - 1;
                if (tx_bit_cnt == 4'd1)
                    tx_busy <= 1'b0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // RX shift register (sample at mid-bit)
    // -------------------------------------------------------------------------
    logic [1:0]  rx_sync;
    logic [9:0]  rx_shift;
    logic [3:0]  rx_bit_cnt;
    logic [$clog2(BAUD_DIV+1)-1:0] rx_sample_cnt;
    logic        rx_active;
    logic        rx_valid;
    logic [7:0]  rx_data;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            rx_sync       <= 2'b11;
            rx_active     <= 1'b0;
            rx_bit_cnt    <= '0;
            rx_sample_cnt <= '0;
            rx_valid      <= 1'b0;
            rx_data       <= '0;
        end else begin
            rx_sync <= {rx_sync[0], rx_i};

            if (rx_valid && we_i && addr_i[2:0] == 3'h0)
                rx_valid <= 1'b0;  // clear on read of DATA reg

            if (!rx_active) begin
                // Detect start bit (falling edge)
                if (rx_sync[1] && !rx_sync[0]) begin
                    rx_active     <= 1'b1;
                    rx_bit_cnt    <= 4'd9;   // 1 start + 8 data
                    rx_sample_cnt <= (BAUD_DIV[$clog2(BAUD_DIV+1)-1:0] >> 1); // half period
                end
            end else begin
                if (rx_sample_cnt == '0) begin
                    rx_sample_cnt <= BAUD_DIV[$clog2(BAUD_DIV+1)-1:0];
                    rx_shift      <= {rx_sync[1], rx_shift[9:1]};
                    rx_bit_cnt    <= rx_bit_cnt - 1;
                    if (rx_bit_cnt == 4'd1) begin
                        rx_active <= 1'b0;
                        rx_valid  <= 1'b1;
                        rx_data   <= rx_shift[9:2];
                    end
                end else begin
                    rx_sample_cnt <= rx_sample_cnt - 1;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // Bus read
    // -------------------------------------------------------------------------
    always_comb begin
        rdata_o = 32'h0;
        case (addr_i[2:0])
            3'h0: rdata_o = {24'h0, rx_data};
            3'h1: rdata_o = {30'h0, rx_valid, tx_busy};
            default: rdata_o = 32'h0;
        endcase
    end

    // -------------------------------------------------------------------------
    // IRQ: RX data available
    // -------------------------------------------------------------------------
    assign irq_o = rx_valid;

endmodule : uart_top

`default_nettype wire
