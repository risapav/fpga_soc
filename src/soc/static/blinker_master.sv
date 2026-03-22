/**
 * @file blinker_master.sv
 * @brief Simple FSM that acts as a Bus Master to toggle LEDs
 */
`default_nettype none

module blinker_master (
  input  wire  clk_sys,
  input  wire  rst_ni,
  bus_if.master bus  // Napojenie na tvoju zbernicu
);

  logic [24:0] counter;
  logic        tick;

  // Generátor pulzu každých ~0.3s pri 50MHz
  always_ff @(posedge clk_sys or negedge rst_ni) begin
    if (!rst_ni) begin
      counter <= '0;
      tick    <= 1'b0;
    end else begin
      if (counter == 25'd15_000_000) begin
        counter <= '0;
        tick    <= 1'b1;
      end else begin
        counter <= counter + 1'b1;
        tick    <= 1'b0;
      end
    end
  end

  // Jednoduchá FSM na zápis do zbernice
  typedef enum logic [1:0] {IDLE, WRITE, WAIT_READY} state_e;
  state_e state;
  logic [7:0] led_data;

  always_ff @(posedge clk_sys or negedge rst_ni) begin
    if (!rst_ni) begin
      state    <= IDLE;
      led_data <= 8'h01;
      bus.valid <= 1'b0;
    end else begin
      case (state)
        IDLE: begin
          if (tick) begin
            bus.addr  <= 32'h0000_4000; // Adresa UART/LED z YAML
            bus.wdata <= {24'h0, led_data};
            bus.we    <= 1'b1;
            bus.be    <= 4'hF;
            bus.valid <= 1'b1;
            state     <= WRITE;
          end
        end

        WRITE: begin
          if (bus.ready) begin
            bus.valid <= 1'b0;
            led_data  <= {led_data[6:0], led_data[7]}; // Rotácia bitov
            state     <= IDLE;
          end
        end
      endcase
    end
  end

endmodule : blinker_master
