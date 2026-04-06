// =============================================================================
// MODULE: soc_ram
// FILE:   src/soc/static/soc_ram.sv
// BRIEF:  On-chip RAM - Quartus altsyncram with MIF initialization
//
// INIT_FILE: path to .mif relative to Quartus project (.qsf) directory
//            -> gen/software.mif
//
// Compatible with PicoRV32 LATCHED_MEM_RDATA=1:
//   rdata is registered (1 clock latency), ready=ram_sel_r in soc_top
// =============================================================================
`default_nettype none

module soc_ram #(
    parameter int SIZE_BYTES = 4096,
    parameter     INIT_FILE  = "gen/software.mif"
) (
    input  wire                            clk,
    input  wire [$clog2(SIZE_BYTES/4)-1:0] addr,
    input  wire [3:0]                      be,
    input  wire                            we,
    input  wire [31:0]                     wdata,
    output wire [31:0]                     rdata
);

    localparam int DEPTH     = SIZE_BYTES / 4;
    localparam int ADDR_BITS = $clog2(DEPTH);

    altsyncram #(
        .operation_mode               ("SINGLE_PORT"),
        .width_a                      (32),
        .widthad_a                    (ADDR_BITS),
        .numwords_a                   (DEPTH),
        .outdata_reg_a                ("UNREGISTERED"),
        .init_file                    (INIT_FILE),
        .init_file_layout             ("PORT_A"),
        .intended_device_family       ("Cyclone IV E"),
        .lpm_type                     ("altsyncram"),
        .ram_block_type               ("M9K"),
        .byte_size                    (8),
        .width_byteena_a              (4),
        .read_during_write_mode_port_a("NEW_DATA_NO_NBE_READ"),
        .power_up_uninitialized       ("FALSE")
    ) u_ram (
        .clock0    (clk),
        .address_a (addr),
        .data_a    (wdata),
        .byteena_a (we ? be : 4'hF),
        .wren_a    (we),
        .q_a       (rdata),
        // Unused ports
        .aclr0(1'b0), .aclr1(1'b0),
        .address_b(1'b1),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_b(1'b1),
        .clock1(1'b1),
        .clocken0(1'b1), .clocken1(1'b1), .clocken2(1'b1), .clocken3(1'b1),
        .data_b(32'hFFFFFFFF), .eccstatus(), .q_b(),
        .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );

endmodule : soc_ram
`default_nettype wire
