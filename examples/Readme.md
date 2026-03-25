# Príklady a Demo projekty

Každý demo projekt je **samostatný** — má vlastný `project_config.yaml`,
vlastný `top.sv` a vlastný `.qsf`. Zdieľajú len HAL a generátor z rootu frameworku.

## Štruktúra každého dema

```
examples/<demo_name>/
├── top.sv                    ← RTL dizajn
├── <demo_name>.qsf           ← Quartus projekt
├── <demo_name>.sdc           ← Timing constraints
├── README.md                 ← Popis a návod
└── board/
    └── project_config.yaml   ← Konfigurácia periférií
```

## Dostupné demá

### ✅ demo_led_effects — Tri LED efekty (standalone RTL)

Bez CPU, bez zbernice. Čisté RTL.

| | |
|---|---|
| Úroveň | Začiatočník |
| Periférie | Onboard LED, PMOD J10 LED, PMOD J11 LED |
| Efekty | Bežiace svetlo, Fill bar, Cylon Eye |

---

## Plánované demá

### 🔲 demo_seg7_counter — Počítadlo na 7-seg displeji

Binárne počítadlo zobrazené na 7-segmentovom displeji. Stále bez CPU.

| | |
|---|---|
| Úroveň | Začiatočník |
| Periférie | Onboard 7-seg (SEG + DIG), Buttons |
| Nové koncepty | Multiplexovanie displeja, debounce tlačidiel |

---

### 🔲 demo_uart_hello — Hello World cez UART (s CPU)

Prvý demo s PicoRV32 jadrom. Program v C posiela `Hello World` cez UART.

| | |
|---|---|
| Úroveň | Stredný |
| Periférie | UART |
| Nové koncepty | RISC-V toolchain, linker script, boot.S |

---

### 🔲 demo_timer_irq — Blikanie LED cez timer prerušenie

CPU obsluhuje timer IRQ a prepína LED v handleri.

| | |
|---|---|
| Úroveň | Stredný |
| Periférie | Onboard LED, Timer0, INTC |
| Nové koncepty | VIC, IRQ handler v C, `soc_irq.h` |

---

### 🔲 demo_vga_pattern — VGA testovací vzor

Generátor farebných pruhov na VGA výstupe. Standalone RTL.

| | |
|---|---|
| Úroveň | Pokročilý |
| Periférie | VGA |
| Nové koncepty | Pixel clock, hsync/vsync timing |

---

## Ako pridať nové demo

1. Skopíruj adresár `demo_led_effects/` ako základ
2. Premenuj podľa nového dema
3. Uprav `board/project_config.yaml` — zapni potrebné periférie
4. Prepíš `top.sv` svojou logikou
5. Pridaj záznam do tohto README
