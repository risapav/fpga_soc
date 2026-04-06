---

## Directory structure

set qsf_dir  [pwd]
set root_dir [file normalize [file join $qsf_dir ".." ".."]]

set gen_script [file join $root_dir "board" "generators" "gen_config.py"]
set demo_cfg   [file join $qsf_dir  "board" "project_config.yaml"]
set cfg_out    [file join $root_dir "board" "config" "generated_config.tcl"]
set files_gen  [file join $qsf_dir  "gen" "files.tcl"]
set bsp_loader [file join $root_dir "scripts" "bsp_loader.tcl"]


```
fpga_soc/                              $root_dir
|-- board/
|   |-- bsp/
|   |   +-- hal_qmtech_ep4ce55.tcl     Static.  Pin assignments for EP4CE55F23C8.
|   |-- config/
|   |   |-- project_config.yaml        Edit.    Main SoC configuration.
|   |   |-- ip_registry.yaml           Edit.    Peripheral catalogue.
|   |   +-- generated_config.tcl       GENERATED. Do not edit.
|   +-- generators/
|       +-- gen_config.py              Framework orchestrator.
|
|-- examples/
|   +-- demo_led_effects/              Demo 1: three LED effects, standalone RTL.
|   +-- demo_project/                  Demo Project main template. $qsf_dir  [pwd]
|       |-- Makefile                   local Makefile
|       |-- soc_top.qpf                Quartus file
|       |-- soc_top.qsf                Quartus file
|       |-- soc_top.sdc                Quartus file
|       |-- config/                    Project configuration.
|       |   |-- project_config.yaml    Project configuration YAML file.
|       |-- sw/                        Project sw
|       |
|       +-- gen/                       GENERATED. Do not edit contents.
|           |-- files.tcl              GENERATED. Do not edit contents.
|           |-- ram_size.mk            GENERATED. Do not edit contents.
|           |-- soc_top.sv             GENERATED. Do not edit contents.
|           |-- software.mif           GENERATED. Do not edit contents.
|           |-- software.hex           GENERATED. Do not edit contents.
|           +-- hal/                   GENERATED. Do not edit contents.
|               +-- board.tcl          GENERATED. HW pin assigments.
|-- scripts/
|   |-- bsp_loader.tcl
|   +-- pre_flow.tcl                   Quartus pre-flow for main SoC project.
|
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