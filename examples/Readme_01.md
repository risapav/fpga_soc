# QMTech Cyclone IV RISC-V SoC Framework

Metadata-driven framework for automated SoC generation on QMTech EP4CE55F23C8.
A single YAML file drives RTL generation, C headers, linker scripts and pin assignments.

---

## Core principle

`soc_top.sv` is ALWAYS the Quartus TOP entity -- never written by hand.
`gen_config.py` assembles it from `project_config.yaml` + `ip_registry.yaml`.

```
project_config.yaml  ──>  gen_config.py  ──>  src/soc/gen/soc_top.sv   (Quartus TOP)
ip_registry.yaml     ──/                 ──>  sw/include/soc_map.h
                                         ──>  sw/include/soc_irq.h
                                         ──>  sw/linker/sections.lds
                                         ──>  board/config/generated_config.tcl  ──>  HAL pins
```

---

## Directory structure

```
fpga_soc/
|-- board/
|   |-- bsp/
|   |   +-- hal_qmtech_ep4ce55.tcl     Static.  Pin assignments for EP4CE55F23C8.
|   |-- config/
|   |   |-- project_config.yaml        Edit.    Main SoC configuration.
|   |   |-- ip_registry.yaml           Edit.    Peripheral catalogue.
|   |   +-- generated_config.tcl       GENERATED. Do not edit.
|   +-- generators/
|       +-- gen_config.py              Framework orchestrator.
|-- examples/
|   +-- demo_led_effects/              Demo 1: three LED effects, standalone RTL.
|-- scripts/
|   |-- pre_flow.tcl                   Quartus pre-flow for main SoC project.
|   +-- pre_flow_demo.tcl              Quartus pre-flow for demo projects.
|-- src/
|   |-- cpu/
|   |   +-- picorv32.v                 Static.  RISC-V core (not generated).
|   +-- soc/
|       |-- gen/                       GENERATED. Do not edit contents.
|       |   |-- soc_top.sv
|       |   +-- soc_interfaces.sv
|       +-- static/                    Static RTL modules instantiated by soc_top.
|           +-- led_effects.sv
+-- sw/
    |-- include/                       GENERATED.
    |   |-- soc_map.h
    |   +-- soc_irq.h
    |-- linker/                        GENERATED.
    |   +-- sections.lds
    +-- Makefile
```

---

## Two generation modes

### SoC mode (default)

Full RISC-V SoC with CPU, bus fabric and peripherals.

```bash
# From project root
python3 board/generators/gen_config.py
```

Generates: `soc_top.sv`, `soc_interfaces.sv`, `soc_map.h`, `soc_irq.h`,
`sections.lds`, `generated_config.tcl`.

### Standalone mode (demos)

Pure RTL, no CPU, no bus. Used for hardware demos and testing.
Set `demo.mode: standalone` in `project_config.yaml`.

```bash
# From demo project directory
python3 ../../board/generators/gen_config.py --config board/project_config.yaml
# or simply:
make gen
```

Generates: `soc_top.sv` (wraps static module), `generated_config.tcl`.

---

## Quickstart: run a demo

```bash
cd examples/demo_led_effects
make gen                            # generate soc_top.sv + HAL config
# Open demo_led_effects.qsf in Quartus Prime 25.1
# Processing -> Start Compilation
# Tools -> Programmer -> load .sof
```

---

## Quickstart: main SoC project

1. Edit `board/config/project_config.yaml` -- enable peripherals, set addresses.
2. Run `python3 board/generators/gen_config.py`.
3. Compile SW: `cd sw && make`.
4. Open your `.qsf` in Quartus. Compilation calls `scripts/pre_flow.tcl` automatically.

---

## project_config.yaml reference

```yaml
board:
  type: qmtech_ep4ce55          # selects HAL file: board/bsp/hal_<type>.tcl

soc:
  cpu: picorv32
  ram_size: 4096                # bytes, must match sw/Makefile RAM_SIZE
  clock_freq: 50_000_000

onboard:                        # enables HAL pin assignments
  leds:    true
  seg:     false
  dig:     false
  buttons: true
  uart:    false

pmod:
  J10: LED                      # NONE | LED | SEG | GPIO | HDMI (J11 only)
  J11: NONE

peripherals:                    # SoC mode: bus-mapped peripherals
  intc:
    enabled: true
    base: 0x80001000
  uart0:
    type: uart
    enabled: true
    base: 0x80006000

# Standalone mode only:
standalone_modules:
  led_fx:
    module: led_effects
    enabled: true
    params:
      CLK_FREQ: 50_000_000
```

---

## ip_registry.yaml reference

Each entry defines a peripheral type. `gen_config.py` looks up the type
when instantiating a peripheral from `project_config.yaml`.

Key fields per peripheral:

| Field | Description |
|---|---|
| `module` | SystemVerilog module name in `src/soc/static/` |
| `bus_type` | `simple_bus` / `axi_lite` / `axi_full` / `none` |
| `needs_bus` | `true` generates bus port connections |
| `address_range` | hex size, used for address decoder |
| `interrupts` | list of `{name, id}` -- id maps to `irq_lines[id]` |
| `interfaces` | external port definitions (dir, width, name) |
| `params` | parameter list forwarded to module instantiation |

---

## Adding a new peripheral

1. Write `src/soc/static/my_periph.sv` -- use `clk_sys`/`rst_ni` internally.
2. Add entry to `board/config/ip_registry.yaml` under `peripherals:`.
3. Enable in `board/config/project_config.yaml` with a `base:` address.
4. Run `python3 board/generators/gen_config.py` -- `soc_top.sv` and `soc_map.h` update automatically.

---

## Adding a new demo

1. Copy `examples/demo_led_effects/` to `examples/demo_<name>/`.
2. Write `src/soc/static/<name>.sv`.
3. Register in `ip_registry.yaml` with `bus_type: none`.
4. Update `examples/demo_<name>/board/project_config.yaml`:
   - set `demo.mode: standalone`
   - add entry under `standalone_modules:`
5. Fix `demo_<name>.qsf`: `TOP_LEVEL_ENTITY soc_top`, add both `.sv` files.

---

## Critical rules

- All files read by Quartus must be ASCII-only. No diacritics, no Unicode, no emoji in comments.
- `src/soc/gen/` is fully generated -- never edit files there manually.
- `soc_top` port names `SYS_CLK` and `RESET_N` must match exactly what HAL assigns.
- `RAM_SIZE` in `sw/Makefile` must equal `ram_size` in `project_config.yaml`.
- PMOD pin assignments use `PIN_Xxx` format -- bare `E4` is rejected by the Fitter.

---

## Hardware: QMTech EP4CE55F23C8

| Signal | Pin | Notes |
|---|---|---|
| `SYS_CLK` | PIN_T2 | 50 MHz onboard oscillator |
| `RESET_N` | PIN_W13 | Active low, weak pull-up |
| `ONB_LEDS[5:0]` | E4,A8,B8,A7,B7,A6 | Active high |
| `ONB_SEG[7:0]` | A4,B1,B4,A5,C3,A3,B2,C4 | Active low |
| `ONB_DIG[2:0]` | B6,B3,B5 | Active low |
| `ONB_BUTTONS[1:0]` | Y13,AA13 | Active low, weak pull-up |
| PMOD J10 | H1,F1,E1,C1,H2,F2,D2,C2 | P[0..7] |
| PMOD J11 | R1,P1,N1,M1,R2,P2,N2,M2 | P[0..7] |

---

## Demos

| Demo | Mode | Peripherals | Status |
|---|---|---|---|
| `demo_led_effects` | standalone | ONB_LEDS, PMOD J10/J11 | Working |
| `demo_seg7_counter` | standalone | ONB_SEG, ONB_DIG, ONB_BUTTONS | Planned |
| `demo_uart_hello` | SoC | UART, INTC | Planned |
| `demo_timer_irq` | SoC | Timer, INTC, ONB_LEDS | Planned |