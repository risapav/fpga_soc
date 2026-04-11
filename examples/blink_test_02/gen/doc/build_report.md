# SoC Build Report

Generated: 2026-04-11 21:07:57  
Board: `qmtech_ep4ce55`  
Mode: `standalone`  
Clock: 50 MHz  
Build hash: `26d6a48bab49`  

## Active feature nodes

Only sections present in `project_config.yaml` are activated.

| Node | Status | Activated by |
|----------------------|------------|------------------------------------------|
| `ClockTreeNode` | [active] | timing_config.yaml present |
| `CpuNode` | [absent] | `soc.cpu` field |
| `MemoryNode` | [absent] | `soc.ram_size` + `soc.cpu` |
| `PeripheralNode` | [absent] | `peripherals:` section |
| `StandaloneNode` | [active] | `standalone_modules:` section |


## Plugin registry

10 IP(s) loaded.

| IP name | Type | Module | Origin file |
|----------------------|--------------|----------------------|----------------------------------------------------|
| `blink_test` | standalone | `blink_test` | `blink_test.ip.yaml` |
| `cdc_async_fifo` | utility | `cdc_async_fifo` | `cdc_lib.ip.yaml` |
| `cdc_reset_synchronizer` | utility | `cdc_reset_synchronizer` | `cdc_lib.ip.yaml` |
| `cdc_two_flop_synchronizer` | utility | `cdc_two_flop_synchronizer` | `cdc_lib.ip.yaml` |
| `clkpll` | standalone | `ClkPll` | `clkpll.ip.yaml` |
| `leds` | peripheral | `leds_top` | `leds.ip.yaml` |
| `sdram_system_top` | peripheral | `sdram_system_top` | `sdram_system_top.ip.yaml` |
| `soc_ram` | memory | `soc_ram` | `soc_ram.ip.yaml` |
| `uart` | peripheral | `uart_top` | `uart.ip.yaml` |
| `vexriscv` | cpu | `—` | `vexriscv.ip.yaml` |


## Clock domains

| Logical domain | Physical signal |
|------------------------|------------------------|
| `clk_100mhz` | `clk_100mhz` |
| `reset` | `RESET_N` |
| `sys_clk` | `SYS_CLK` |


## Reset synchronisers

| Instance | Domain | Clock signal | Stages | Type | Sync from |
|--------------------------|----------------|------------------|----------|------------|----------------|
| `u_rst_sync_sys_clk` | SYS_CLK | `SYS_CLK` | 2 | primary | — |
| `u_rst_sync_clk_100mhz` | clk_100mhz | `clk_100mhz` | 2 | cdc | SYS_CLK |


## Standalone modules

| Instance | Module | Clock port | Reset port | Params | Files |
|----------------|------------------|--------------|--------------|--------------------------------|--------------------------------|
| `blink_01` | `blink_test` | `SYS_CLK` | `RESET_N` | CLK_FREQ=100000000 | `blink_test.sv` |
| `blink_02` | `blink_test` | `SYS_CLK` | `RESET_N` | CLK_FREQ=100000000 | `blink_test.sv` |
| `blink_03` | `blink_test` | `SYS_CLK` | `RESET_N` | CLK_FREQ=50000000 | `blink_test.sv` |
| `pll` | `ClkPll` | `inclk0` | `areset` | — | `ClkPll.qip` |


### External ports (from standalone modules)

| Instance | Signal | Top port | Direction | Width |
|----------------|------------------|----------------------|--------------|----------|
| `blink_01` | `ONB_LEDS` | `ONB_LEDS` | output | 6 |
| `blink_02` | `ONB_LEDS` | `PMOD_J10_P` | output | 6 |
| `blink_03` | `ONB_LEDS` | `PMOD_J11_P` | output | 6 |


## soc_top port summary

All ports that appear in the generated `soc_top` module:

| Port | Direction | Width | Driven by |
|------------------------|--------------|----------|----------------------|
| `SYS_CLK` | input | 1 | board |
| `RESET_N` | input | 1 | board |
| `ONB_LEDS` | output | 6 | `blink_01` |
| `PMOD_J10_P` | output | 6 | `blink_02` |
| `PMOD_J11_P` | output | 6 | `blink_03` |


## Files included in build

Files that will appear in `gen/tcl/files.tcl`:

- `blink_test.sv` — SystemVerilog
- `blink_test.sv` — SystemVerilog
- `blink_test.sv` — SystemVerilog
- `ClkPll.qip` — Quartus IP
- `cdc_reset_synchronizer.sv` — SystemVerilog

