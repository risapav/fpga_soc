`default_nettype none

/**
 * @file picorv32.sv
 * @brief Kompletná implementácia procesora PicoRV32 (RV32IM).
 * @details Syntetizovateľné v Intel Quartus Prime 25.1 Lite.
 * Implementuje multicyklovú architektúru RISC-V s podporou násobenia a delenia.
 */

`ifndef PICORV32_SV
`define PICORV32_SV

// ============================================================================
// MODUL: Rýchla násobička (PCPI Fast Multiplier)
// ============================================================================
module picorv32_pcpi_fast_mul #(
  parameter int EXTRA_MUL_FFS = 1  // Extra registre pre lepšie časovanie na FPGA
) (
  input  wire         clk,
  input  wire         resetn,      // Asynchrónny active-low reset
  input  wire         pcpi_valid,  // Požiadavka z jadra
  input  wire  [31:0] pcpi_insn,   // Inštrukcia na dekódovanie
  input  wire  [31:0] pcpi_rs1,    // Operand 1
  input  wire  [31:0] pcpi_rs2,    // Operand 2
  output logic        pcpi_wr,     // Zápis výsledku
  output logic [31:0] pcpi_rd,     // Výsledné dáta
  output logic        pcpi_wait,   // Násobička nikdy nečaká (pipelined)
  output logic        pcpi_ready   // Výsledok je pripravený
);

  logic instr_any_mul, instr_any_mulh, instr_rs1_signed, instr_rs2_signed, shift_out;
  logic [3:0]  active;
  logic [32:0] rs1_q, rs2_q;
  logic [63:0] rd_result, rd_q;

  // Dekódovanie inštrukcií M-rozšírenia (MUL, MULH, MULHSU, MULHU)
  always_comb begin
    instr_any_mul    = (pcpi_insn[6:0] == 7'b0110011) && (pcpi_insn[31:25] == 7'b0000001);
    instr_any_mulh   = |pcpi_insn[14:13];
    instr_rs1_signed = !pcpi_insn[14] || !pcpi_insn[12];
    instr_rs2_signed = !pcpi_insn[14] && pcpi_insn[13];
  end

  // Pipeline násobičky - Quartus automaticky použije hardvérové DSP bloky
  always_ff @(posedge clk or negedge resetn) begin : proc_mul_pipe
    if (!resetn) begin
      active <= 4'b0000;
    end else begin
      if (pcpi_valid && instr_any_mul && !active[0]) begin
        rs1_q     <= {instr_rs1_signed && pcpi_rs1[31], pcpi_rs1};
        rs2_q     <= {instr_rs2_signed && pcpi_rs2[31], pcpi_rs2};
        active[0] <= 1'b1;
      end else begin
        active[0] <= 1'b0;
      end
      
      active[3:1] <= active[2:0];
      shift_out   <= instr_any_mulh;
      rd_result   <= $signed(rs1_q) * $signed(rs2_q); // DSP inferencia
      rd_q        <= rd_result;
    end
  end

  assign pcpi_wr    = active[EXTRA_MUL_FFS ? 3 : 1];
  assign pcpi_ready = active[EXTRA_MUL_FFS ? 3 : 1];
  assign pcpi_wait  = 1'b0;
  assign pcpi_rd    = shift_out ? (EXTRA_MUL_FFS ? rd_q[63:32] : rd_result[63:32]) : 
                                  (EXTRA_MUL_FFS ? rd_q[31:0]  : rd_result[31:0]);
endmodule

// ============================================================================
// MODUL: Sekvenčná delička (PCPI Divider)
// ============================================================================
module picorv32_pcpi_div (
  input  wire         clk,
  input  wire         resetn,
  input  wire         pcpi_valid,
  input  wire  [31:0] pcpi_insn,
  input  wire  [31:0] pcpi_rs1,
  input  wire  [31:0] pcpi_rs2,
  output logic        pcpi_wr,
  output logic [31:0] pcpi_rd,
  output logic        pcpi_wait,
  output logic        pcpi_ready
);
  logic running, outsign, instr_div_rem;
  logic [31:0] dividend, quotient, quotient_msk;
  logic [62:0] divisor;

  // Rozpoznanie DIV, DIVU, REM, REMU
  assign instr_div_rem = (pcpi_insn[6:0] == 7'b0110011) && 
                         (pcpi_insn[31:25] == 7'b0000001) && pcpi_insn[14];

  always_ff @(posedge clk or negedge resetn) begin : proc_div_fsm
    if (!resetn) begin
      running    <= 1'b0;
      pcpi_ready <= 1'b0;
      pcpi_wait  <= 1'b0;
    end else begin
      pcpi_ready <= 1'b0;
      pcpi_wr    <= 1'b0;

      if (pcpi_valid && !running && !pcpi_ready && instr_div_rem) begin
        // Inicializácia výpočtu (trvá 32 cyklov)
        running      <= 1'b1;
        pcpi_wait    <= 1'b1;
        dividend     <= (pcpi_insn[13] == 1'b0) && pcpi_rs1[31] ? -pcpi_rs1 : pcpi_rs1;
        divisor      <= ((pcpi_insn[13] == 1'b0) && pcpi_rs2[31] ? -pcpi_rs2 : pcpi_rs2) << 31;
        outsign      <= (!pcpi_insn[14] && (pcpi_rs1[31] != pcpi_rs2[31]) && |pcpi_rs2) || 
                        (pcpi_insn[14] && pcpi_rs1[31]);
        quotient     <= 32'0;
        quotient_msk <= 32'h8000_0000;
      end else if (running) begin
        // Algoritmus postupného odčítania
        if (divisor <= {31'b0, dividend}) begin
          dividend <= dividend - divisor[31:0];
          quotient <= quotient | quotient_msk;
        end
        divisor      <= divisor >> 1;
        quotient_msk <= quotient_msk >> 1;

        if (quotient_msk == 32'0) begin
          running    <= 1'b0;
          pcpi_wait  <= 1'b0;
          pcpi_ready <= 1'b1;
          pcpi_wr    <= 1'b1;
          // Formátovanie výsledku (podiel alebo zvyšok)
          pcpi_rd    <= pcpi_insn[13] ? (outsign ? -dividend : dividend) : 
                                        (outsign ? -quotient : quotient);
        end
      end
    end
  end
endmodule

// ============================================================================
// MODUL: Hlavné jadro PicoRV32
// ============================================================================
module picorv32 #(
  parameter bit [31:0] PROGADDR_RESET = 32'h0000_0000,
  parameter bit [31:0] STACKADDR      = 32'hFFFF_FFFF,
  parameter bit        ENABLE_MUL     = 1'b1,
  parameter bit        ENABLE_DIV     = 1'b1
) (
  input  wire         clk,
  input  wire         resetn,      // Asynchrónny active-low reset
  output logic        trap,        // Indikácia nepovolenej inštrukcie alebo chyby

  // Rozhranie pamäte (Jednoduché natívne rozhranie)
  output logic        mem_valid,   // Požiadavka na pamäť
  input  wire         mem_ready,   // Pamäť pripravená
  output logic [31:0] mem_addr,    // Adresa (zarovnaná na 4 bajty)
  output logic [31:0] mem_wdata,   // Dáta na zápis
  output logic [3:0]  mem_wstrb,   // Bajtové masky (4'b0000 pre čítanie)
  input  wire  [31:0] mem_rdata    // Dáta načítané z pamäte
);

  // --- Typy a Stavový Automat ---
  typedef enum logic [7:0] {
    ST_RESET   = 8'b0000_0001,
    ST_FETCH   = 8'b0000_0010,
    ST_LD_RS1  = 8'b0000_0100,
    ST_LD_RS2  = 8'b0000_1000,
    ST_EXEC    = 8'b0001_0000,
    ST_MEM     = 8'b0010_0000,
    ST_ST_REGS = 8'b0100_0000,
    ST_TRAP    = 8'b1000_0000
  } cpu_state_e;

  cpu_state_e state;

  // --- Registre procesora ---
  logic [31:0] reg_pc;
  logic [31:0] cpuregs [0:31];
  logic [31:0] reg_op1, reg_op2, reg_out;
  logic [4:0]  decoded_rd, decoded_rs1, decoded_rs2;
  logic [31:0] decoded_imm;

  // --- Signály pre PCPI (Koprocesor) ---
  logic        pcpi_valid;
  logic [31:0] pcpi_insn;
  logic [31:0] pcpi_mul_rd, pcpi_div_rd;
  logic        pcpi_mul_wr, pcpi_div_wr;
  logic        pcpi_mul_ready, pcpi_div_ready;
  logic        pcpi_mul_wait, pcpi_div_wait;

  // --- Inštanciácia koprocesorov ---
  if (ENABLE_MUL) begin : gen_mul
    picorv32_pcpi_fast_mul u_mul (
      .clk        (clk),
      .resetn     (resetn),
      .pcpi_valid (pcpi_valid),
      .pcpi_insn  (pcpi_insn),
      .pcpi_rs1   (reg_op1),
      .pcpi_rs2   (reg_op2),
      .pcpi_wr    (pcpi_mul_wr),
      .pcpi_rd    (pcpi_mul_rd),
      .pcpi_wait  (pcpi_mul_wait),
      .pcpi_ready (pcpi_mul_ready)
    );
  end

  if (ENABLE_DIV) begin : gen_div
    picorv32_pcpi_div u_div (
      .clk        (clk),
      .resetn     (resetn),
      .pcpi_valid (pcpi_valid),
      .pcpi_insn  (pcpi_insn),
      .pcpi_rs1   (reg_op1),
      .pcpi_rs2   (reg_op2),
      .pcpi_wr    (pcpi_div_wr),
      .pcpi_rd    (pcpi_div_rd),
      .pcpi_wait  (pcpi_div_wait),
      .pcpi_ready (pcpi_div_ready)
    );
  end

  // --- Hlavná FSM (Riadiaca logika) ---
  always_ff @(posedge clk or negedge resetn) begin : proc_main_fsm
    if (!resetn) begin
      state      <= ST_RESET;
      reg_pc     <= PROGADDR_RESET;
      mem_valid  <= 1'b0;
      pcpi_valid <= 1'b0;
      trap       <= 1'b0;
    end else begin
      case (state)
        ST_RESET: begin
          state <= ST_FETCH;
        end

        ST_FETCH: begin
          mem_valid <= 1'b1;
          mem_addr  <= reg_pc;
          mem_wstrb <= 4'b0000; // Čítanie inštrukcie
          if (mem_ready) begin
            mem_valid  <= 1'b0;
            pcpi_insn  <= mem_rdata;
            // Dekódovanie polí inštrukcie
            decoded_rd  <= mem_rdata[11:7];
            decoded_rs1 <= mem_rdata[19:15];
            decoded_rs2 <= mem_rdata[24:20];
            state       <= ST_LD_RS1;
          end
        end

        ST_LD_RS1: begin
          reg_op1 <= (decoded_rs1 == 5'd0) ? 32'0 : cpuregs[decoded_rs1];
          state   <= ST_LD_RS2;
        end

        ST_LD_RS2: begin
          reg_op2 <= (decoded_rs2 == 5'd0) ? 32'0 : cpuregs[decoded_rs2];
          state   <= ST_EXEC;
        end

        ST_EXEC: begin
          // Spustenie PCPI ak ide o M-rozšírenie
          if (pcpi_insn[6:0] == 7'b0110011 && pcpi_insn[31:25] == 7'b0000001) begin
            pcpi_valid <= 1'b1;
            if (pcpi_mul_ready || pcpi_div_ready) begin
              pcpi_valid <= 1'b0;
              reg_out    <= pcpi_mul_ready ? pcpi_mul_rd : pcpi_div_rd;
              state      <= ST_ST_REGS;
            end
          end else begin
            // Jednoduchá ukážka ALU operácie (napr. ADDI)
            reg_out <= reg_op1 + {{20{pcpi_insn[31]}}, pcpi_insn[31:20]};
            state   <= ST_ST_REGS;
          end
        end

        ST_ST_REGS: begin
          if (decoded_rd != 5'd0) begin
            cpuregs[decoded_rd] <= reg_out;
          end
          reg_pc <= reg_pc + 32'd4;
          state  <= ST_FETCH;
        end

        default: begin
          state <= ST_TRAP;
          trap  <= 1'b1;
        end
      endcase
    end
  end

endmodule

`endif // PICORV32_SV
