/**
 * @file        cdc_async_fifo.sv
 * @brief       Asynchrónny FIFO buffer (CDC) s konfigurovateľnými prahmi.
 * @details     Implementuje FIFO pre prenos dát medzi rôznymi hodinovými doménami.
 * Využíva Gray kód pre bezpečný prenos pointerov.
 * Obsahuje synchronizáciu resetov a detekciu pretečenia/podtečenia.
 *
 * @param DATA_WIDTH             Šírka dátového slova.
 * @param DEPTH                  Hĺbka FIFO (musí byť mocnina 2).
 * @param ALMOST_FULL_THRESHOLD  Prah pre signál almost_full.
 * @param ALMOST_EMPTY_THRESHOLD Prah pre signál almost_empty.
 * @param ADDR_WIDTH             Šírka adresy (vypočítaná automaticky).
 *
 * @input  wr_clk_i, wr_rst_ni   Zápisová doména.
 * @input  rd_clk_i, rd_rst_ni   Čítacia doména.
 */

`default_nettype none

`ifndef CDC_ASYNC_FIFO_SV
`define CDC_ASYNC_FIFO_SV

module cdc_async_fifo #(
    parameter int unsigned DATA_WIDTH             = 16,
    parameter int unsigned DEPTH                  = 1024,
    parameter int unsigned ALMOST_FULL_THRESHOLD  = 16,
    parameter int unsigned ALMOST_EMPTY_THRESHOLD = 16,
    // Počet bitov potrebných pre adresovanie hĺbky FIFO
    parameter int unsigned ADDR_WIDTH             = $clog2(DEPTH)
)(
    // Zápisová doména (write clock domain)
    input  wire logic                  wr_clk_i,
    input  wire logic                  wr_rst_ni,
    input  wire logic                  wr_en_i,
    input  wire logic [DATA_WIDTH-1:0] wr_data_i,
    output      logic                  full_o,
    output      logic                  almost_full_o,
    output      logic                  overflow_o,

    // Čítacia doména (read clock domain)
    input  wire logic                  rd_clk_i,
    input  wire logic                  rd_rst_ni,
    input  wire logic                  rd_en_i,
    output      logic [DATA_WIDTH-1:0] rd_data_o,
    output      logic                  empty_o,
    output      logic                  almost_empty_o,
    output      logic                  underflow_o
);

    // -------------------------------------------------------------------------
    // 1. Interné signály a Pamäť
    // -------------------------------------------------------------------------

    // Pamäť FIFO - pole s veľkosťou DEPTH a šírkou DATA_WIDTH
    (* ramstyle = "no_rw_check" *)
    logic [DATA_WIDTH-1:0] mem [0:DEPTH-1];

    // Pointery (Binárne a Gray)
    logic [ADDR_WIDTH:0] wr_ptr_bin, rd_ptr_bin;
    logic [ADDR_WIDTH:0] wr_ptr_gray, rd_ptr_gray;

    // Synchronizované pointery
    logic [ADDR_WIDTH:0] wr_ptr_gray_rdclk_sync;
    logic [ADDR_WIDTH:0] rd_ptr_gray_wrclk_sync;

    // Synchronizované reset signály (Active Low)
    logic wr_rstn_sync;
    logic rd_rstn_sync;

    // -------------------------------------------------------------------------
    // 2. Synchronizácia Resetov
    // -------------------------------------------------------------------------
    // Použitie externého modulu pre bezpečný reset release

    cdc_reset_synchronizer #(
        .STAGES(2),
        .WIDTH(1)
    ) u_wr_rst_sync (
        .clk_i  (wr_clk_i),
        .rst_ni (wr_rst_ni),
        .rst_no (wr_rstn_sync)
    );

    cdc_reset_synchronizer #(
        .STAGES(2),
        .WIDTH(1)
    ) u_rd_rst_sync (
        .clk_i  (rd_clk_i),
        .rst_ni (rd_rst_ni),
        .rst_no (rd_rstn_sync)
    );

    // -------------------------------------------------------------------------
    // 3. Pomocné funkcie (Gray Code)
    // -------------------------------------------------------------------------
    function automatic logic [ADDR_WIDTH:0] bin2gray(input logic [ADDR_WIDTH:0] bin);
        return (bin >> 1) ^ bin;
    endfunction

    function automatic logic [ADDR_WIDTH:0] gray2bin(input logic [ADDR_WIDTH:0] gray);
        logic [ADDR_WIDTH:0] bin;
        bin[ADDR_WIDTH] = gray[ADDR_WIDTH];
        for (int i = ADDR_WIDTH - 1; i >= 0; i--) begin
            bin[i] = bin[i+1] ^ gray[i];
        end
        return bin;
    endfunction

    // -------------------------------------------------------------------------
    // 4. Zápisová doména (Write Domain)
    // -------------------------------------------------------------------------

    // Synchronizácia RD pointera do WR domény
    cdc_two_flop_synchronizer #(.WIDTH(ADDR_WIDTH + 1)) u_rd_ptr_sync (
        .clk_i  (wr_clk_i),
        .rst_ni (wr_rstn_sync),
        .d_i    (rd_ptr_gray),
        .q_o    (rd_ptr_gray_wrclk_sync)
    );

    // Logika zápisu
    always_ff @(posedge wr_clk_i or negedge wr_rstn_sync) begin
        if (!wr_rstn_sync) begin
            wr_ptr_bin  <= '0;
            wr_ptr_gray <= '0;
        end else if (wr_en_i && !full_o) begin
            mem[wr_ptr_bin[ADDR_WIDTH-1:0]] <= wr_data_i;
            wr_ptr_bin  <= wr_ptr_bin + 1'b1;
            wr_ptr_gray <= bin2gray(wr_ptr_bin + 1'b1);
        end
    end

    // Výpočty stavov (Combinatorial)
    logic [ADDR_WIDTH:0] rd_ptr_sync_wr_bin;
    logic [ADDR_WIDTH:0] wr_fill_count;
    localparam int MSB = ADDR_WIDTH;

    assign rd_ptr_sync_wr_bin = gray2bin(rd_ptr_gray_wrclk_sync);
    assign wr_fill_count      = wr_ptr_bin - rd_ptr_sync_wr_bin;

    // Full: MSB !=, MSB-1 !=, zvyšok ==
    assign full_o = (wr_ptr_gray == {
        ~rd_ptr_gray_wrclk_sync[MSB:MSB-1],
        rd_ptr_gray_wrclk_sync[MSB-2:0]
    });

    assign almost_full_o = (wr_fill_count >= (DEPTH - ALMOST_FULL_THRESHOLD));
    assign overflow_o    = wr_en_i && full_o;

    // -------------------------------------------------------------------------
    // 5. Čítacia doména (Read Domain)
    // -------------------------------------------------------------------------

    // Synchronizácia WR pointera do RD domény
    cdc_two_flop_synchronizer #(.WIDTH(ADDR_WIDTH + 1)) u_wr_ptr_sync (
        .clk_i  (rd_clk_i),
        .rst_ni (rd_rstn_sync),
        .d_i    (wr_ptr_gray),
        .q_o    (wr_ptr_gray_rdclk_sync)
    );

    // Logika čítania
    always_ff @(posedge rd_clk_i or negedge rd_rstn_sync) begin
        if (!rd_rstn_sync) begin
            rd_ptr_bin  <= '0;
            rd_ptr_gray <= '0;
            rd_data_o   <= '0;
        end else if (rd_en_i && !empty_o) begin
            rd_data_o   <= mem[rd_ptr_bin[ADDR_WIDTH-1:0]];
            rd_ptr_bin  <= rd_ptr_bin + 1'b1;
            rd_ptr_gray <= bin2gray(rd_ptr_bin + 1'b1);
        end
    end

    // Výpočty stavov (Combinatorial)
    logic [ADDR_WIDTH:0] wr_ptr_sync_rd_bin;
    logic [ADDR_WIDTH:0] rd_fill_count;

    assign wr_ptr_sync_rd_bin = gray2bin(wr_ptr_gray_rdclk_sync);
    assign rd_fill_count      = wr_ptr_sync_rd_bin - rd_ptr_bin;

    assign empty_o        = (rd_ptr_gray == wr_ptr_gray_rdclk_sync);
    assign almost_empty_o = (rd_fill_count <= ALMOST_EMPTY_THRESHOLD);
    assign underflow_o    = rd_en_i && empty_o;

endmodule

`endif // CDC_ASYNC_FIFO_SV

`default_nettype wire
