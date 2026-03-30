// =============================================================================
// MODULE: vexriscv_wrapper
// FILE:   src/cpu/vexriscv/vexriscv_wrapper.sv
// BRIEF:  Adapts VexRiscv Simple bus to our soc_top bus_if
//
// VexRiscv has two separate buses:
//   iBus - instruction fetch (read-only)
//   dBus - data load/store
//
// This wrapper arbitrates: dBus has priority over iBus.
// Reset: VexRiscv active-HIGH, our system active-LOW rst_ni.
// =============================================================================
`default_nettype none

module vexriscv_wrapper (
    input  wire        clk_i,
    input  wire        rst_ni,
    // Unified bus interface to soc_top
    output logic        bus_valid,
    output logic [31:0] bus_addr,
    output logic [31:0] bus_wdata,
    output logic [3:0]  bus_be,
    input  wire  [31:0] bus_rdata,
    input  wire         bus_ready,
    // IRQ
    input  wire         timer_irq,
    input  wire         external_irq
);

    wire reset = ~rst_ni;

    // iBus signals
    wire        iBus_cmd_valid;
    wire        iBus_cmd_ready;
    wire [31:0] iBus_cmd_payload_pc;
    wire        iBus_rsp_valid;
    wire [31:0] iBus_rsp_payload_inst;

    // dBus signals
    wire        dBus_cmd_valid;
    wire        dBus_cmd_ready;
    wire        dBus_cmd_payload_wr;
    wire [3:0]  dBus_cmd_payload_mask;
    wire [31:0] dBus_cmd_payload_address;
    wire [31:0] dBus_cmd_payload_data;
    wire [1:0]  dBus_cmd_payload_size;
    wire        dBus_rsp_ready;
    wire [31:0] dBus_rsp_data;

    VexRiscv u_cpu (
        .clk                        (clk_i),
        .reset                      (reset),
        .iBus_cmd_valid             (iBus_cmd_valid),
        .iBus_cmd_ready             (iBus_cmd_ready),
        .iBus_cmd_payload_pc        (iBus_cmd_payload_pc),
        .iBus_rsp_valid             (iBus_rsp_valid),
        .iBus_rsp_payload_error     (1'b0),
        .iBus_rsp_payload_inst      (iBus_rsp_payload_inst),
        .dBus_cmd_valid             (dBus_cmd_valid),
        .dBus_cmd_ready             (dBus_cmd_ready),
        .dBus_cmd_payload_wr        (dBus_cmd_payload_wr),
        .dBus_cmd_payload_mask      (dBus_cmd_payload_mask),
        .dBus_cmd_payload_address   (dBus_cmd_payload_address),
        .dBus_cmd_payload_data      (dBus_cmd_payload_data),
        .dBus_cmd_payload_size      (dBus_cmd_payload_size),
        .dBus_rsp_ready             (dBus_rsp_ready),
        .dBus_rsp_error             (1'b0),
        .dBus_rsp_data              (dBus_rsp_data),
        .timerInterrupt             (timer_irq),
        .externalInterrupt          (external_irq),
        .softwareInterrupt          (1'b0)
    );

    // -------------------------------------------------------------------------
    // Arbitration state machine: dBus priority over iBus
    // -------------------------------------------------------------------------
    localparam IDLE      = 2'd0;
    localparam IBUS_WAIT = 2'd1;
    localparam DBUS_WAIT = 2'd2;

    reg [1:0]  state;
    reg [31:0] rdata_r;
    reg        ibus_rsp_r;
    reg        dbus_rsp_r;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state     <= IDLE;
            ibus_rsp_r <= 1'b0;
            dbus_rsp_r <= 1'b0;
            rdata_r   <= 32'h0;
        end else begin
            ibus_rsp_r <= 1'b0;
            dbus_rsp_r <= 1'b0;
            case (state)
                IDLE: begin
                    if (dBus_cmd_valid)       state <= DBUS_WAIT;
                    else if (iBus_cmd_valid)  state <= IBUS_WAIT;
                end
                IBUS_WAIT: if (bus_ready) begin
                    rdata_r    <= bus_rdata;
                    ibus_rsp_r <= 1'b1;
                    state      <= IDLE;
                end
                DBUS_WAIT: if (bus_ready) begin
                    rdata_r    <= bus_rdata;
                    dbus_rsp_r <= 1'b1;
                    state      <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // Bus outputs to soc_top
    // -------------------------------------------------------------------------
    always_comb begin
        bus_valid = 1'b0;
        bus_addr  = 32'h0;
        bus_wdata = 32'h0;
        bus_be    = 4'h0;
        case (state)
            IDLE: begin
                if (dBus_cmd_valid) begin
                    bus_valid = 1'b1;
                    bus_addr  = dBus_cmd_payload_address;
                    bus_wdata = dBus_cmd_payload_data;
                    bus_be    = dBus_cmd_payload_wr ? dBus_cmd_payload_mask : 4'h0;
                end else if (iBus_cmd_valid) begin
                    bus_valid = 1'b1;
                    bus_addr  = iBus_cmd_payload_pc;
                    bus_be    = 4'h0;
                    bus_wdata = 32'h0;
                end
            end
            IBUS_WAIT: begin
                bus_valid = 1'b1;
                bus_addr  = iBus_cmd_payload_pc;
                bus_be    = 4'h0;
                bus_wdata = 32'h0;
            end
            DBUS_WAIT: begin
                bus_valid = 1'b1;
                bus_addr  = dBus_cmd_payload_address;
                bus_wdata = dBus_cmd_payload_data;
                bus_be    = dBus_cmd_payload_wr ? dBus_cmd_payload_mask : 4'h0;
            end
            default: ;
        endcase
    end

    // iBus responses
    //assign iBus_cmd_ready        = (state == IBUS_WAIT) && bus_ready;
    assign iBus_cmd_ready = ((state == IDLE && iBus_cmd_valid && !dBus_cmd_valid)
                         || state == IBUS_WAIT) && bus_ready;
    assign iBus_rsp_valid        = ibus_rsp_r;
    assign iBus_rsp_payload_inst = rdata_r;

    // dBus responses
    assign dBus_cmd_ready = (state == DBUS_WAIT) && bus_ready;
    assign dBus_rsp_ready = dbus_rsp_r;
    assign dBus_rsp_data  = rdata_r;

endmodule : vexriscv_wrapper

`default_nettype wire
