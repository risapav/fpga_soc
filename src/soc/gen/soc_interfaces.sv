// AUTO-GENERATED - DO NOT EDIT
`default_nettype none

interface bus_if;
  logic [31:0] addr, wdata, rdata;
  logic [3:0]  be;
  logic        we, valid, ready;

  modport master (output addr, wdata, be, we, valid, input rdata, ready);
  modport slave  (input addr, wdata, be, we, valid, output rdata, ready);
endinterface : bus_if
