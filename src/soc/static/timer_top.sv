/**
 * @file timer_top.sv
 * @brief Simple 32-bit Timer with Interrupt Support for RISC-V SoC
 * @details Compatible with bus_if. Follows 2-space indentation and 100 char limit.
 */

`default_nettype none

module timer_top (
  input  wire        clk_i,
  input  wire        rst_ni,
  bus_if.slave       bus,
  output wire        irq_o    // Interrupt request to soc_intc
);

  // --- Register Map (Offsets) ---
  // 0x00: CTRL  [0] - Enable, [1] - IE (Interrupt Enable), [2] - Auto-Reload
  // 0x04: COUNT (Current counter value)
  // 0x08: MATCH (Target value for interrupt/reset)
  // 0x0C: STATUS [0] - Match Flag (Write 1 to clear)

  logic [31:0] ctrl_reg;
  logic [31:0] count_reg;
  logic [31:0] match_reg;
  logic        match_flag;

  // Aliases for clarity
  wire timer_en    = ctrl_reg[0];
  wire irq_en      = ctrl_reg[1];
  wire auto_reload = ctrl_reg[2];

  // --- Timer Core Logic ---
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      count_reg  <= '0;
      match_flag <= 1'b0;
    end else begin
      if (timer_en) begin
        if (count_reg >= match_reg && match_reg != '0) begin
          match_flag <= 1'b1;
          count_reg  <= auto_reload ? '0 : count_reg;
        end else begin
          count_reg <= count_reg + 1'b1;
        end
      end

      // Clear interrupt flag on write to Status register
      if (bus.valid && bus.we && (bus.addr[3:0] == 4'hC) && bus.wdata[0]) begin
        match_flag <= 1'b0;
      end
    end
  end

  // --- Bus Interface Logic ---
  assign bus.ready = bus.valid; // Single cycle access

  // Read Path
  always_comb begin
    case (bus.addr[3:0])
      4'h0:    bus.rdata = ctrl_reg;
      4'h4:    bus.rdata = count_reg;
      4'h8:    bus.rdata = match_reg;
      4'hC:    bus.rdata = {31'b0, match_flag};
      default: bus.rdata = 32'h0;
    endcase
  end

  // Write Path
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      ctrl_reg  <= '0;
      match_reg <= '0;
    end else if (bus.valid && bus.we) begin
      case (bus.addr[3:0])
        4'h0: ctrl_reg  <= bus.wdata;
        4'h8: match_reg <= bus.wdata;
        default: ; // Other registers are read-only or handled above
      endcase
    end
  end

  // Interrupt Output
  assign irq_o = match_flag && irq_en;

endmodule : timer_top

`default_nettype wire
