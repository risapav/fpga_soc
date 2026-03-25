# UART Driver — Pravidlá a poznatky

## Čo funguje
- TX zápis (`UART_DATA_REG = c`) funguje správne
- `TX_BUSY` bit sa správne nastaví na `1` pri zápise
- `TX_BUSY` bit sa správne resetuje na `0` po dokončení TX (~4340 cyklov pri 115200 baud / 50MHz)
- `baud_tick` generátor funguje správne
- `we_pulse` edge detection v `uart_top.sv` funguje správne

## Zistený problém
`uart_putc` s polling slučkou `while (UART_STAT_REG & 1)` nefunguje spoľahlivo
pri `-O1` a `-O2` optimalizácii.

### Príčina
PicoRV32 s `LATCHED_MEM_RDATA=1` drží `bus.valid=1` počas celej transakcie.
Pri read-modify polling loop môže kompilátor generovať kód kde:
1. CPU načíta `STAT_REG` → `bus.valid=1` na perifériu
2. `rdata_o` je kombinačný — vracia okamžite
3. `bus.ready=1` okamžite — transakcia trvá 1 cyklus pre periférie
4. Polling loop beží správne ALE len ak CPU skutočne vykoná load inštrukciu

Problém bol v boot.S kde `sp` ukazoval na nesprávnu adresu (0x1000 pri 4KB RAM
je správne, 0x2000 pri 8KB RAM bolo mimo RAM select v soc_top).

## Pravidlá pre SW development

### 1. boot.S — stack pointer
Vždy používaj `la sp, _stack_top` — nikdy hardcoded `lui sp, 0x1`.
`_stack_top` je definovaný v `sections.lds` a automaticky odráža `RAM_SIZE`.

### 2. RAM_SIZE synchronizácia
`ram_size.mk` sa generuje automaticky z `project_config.yaml`.
`sw/Makefile` ho includuje: `-include ../gen/ram_size.mk`
Nikdy neupravuj `RAM_SIZE` v `sw/Makefile` manuálne.

### 3. Kompilátor flags
- Používaj `-march=rv32i` (nie rv32im) ak CPU nemá `ENABLE_MUL=1` v HW
- Ak `ENABLE_MUL=1` je v `project_config.yaml cpu_params`, môžeš použiť `-march=rv32im`
- Preferuj `-O1` pred `-O2` pre embedded bez OS
- Vždy použi `-lgcc` pre softvérové delenie/modulo pri `-march=rv32i`

### 4. uart_putc — správna implementácia
```c
static void uart_putc(char c) {
    // Čakaj na TX_BUSY=0 — UART je voľný
    while (UART_STAT_REG & UART_TX_BUSY);
    UART_DATA_REG = (uint8_t)c;
}
```
Toto funguje správne ak:
- `UART_STAT_REG` je deklarovaný ako `volatile uint32_t*`
- Stack pointer je správne nastavený (inak stack corruption)
- RAM_SIZE sedí s `soc_top.sv` ram_sel hranicou

### 5. Diagnostika UART
Ak UART mlčí, postupuj takto:
1. Priamy zápis bez busy check: `UART_DATA_REG = 'U'` + delay → overí TX hardware
2. Čítanie STAT po delay: potvrdí že `TX_BUSY` sa resetuje
3. Skontroluj `software.lst` — `sp` inicializácia v `_start`
4. Skontroluj `gen/soc_top.sv` — `ram_sel` hranica musí sedieť s `RAM_SIZE`

## Known issues / TODO

### soc_top — ram_sel hranica
```systemverilog
ram_sel = (bus.addr < 32'h00001000);  // 4KB
```
Toto je generované z `ram_size` v `project_config.yaml`. Pri zmene RAM_SIZE
**musí byť Quartus rekompilovany** — nestačí len reprogram MIF.

### Quartus .qsf — entity warnings
`Warning (20013): Ignored 30 assignments for entity "demo_uart_hello"`
Príčina: HAL zapisuje pin assignments s `-entity demo_uart_hello` ale top
entita sa volá `soc_top`. Assignments sú zdvojené — raz správne (bez entity)
a raz ignorované (s entity). Nefunkčné ale neškodné.

### soc_intc.sv chýba
`Warning (12019): Can't analyze file -- file soc_intc.sv is missing`
`soc_intc` je v `ip_registry.yaml` ale súbor neexistuje.
Riešenie: odstrániť z `files.tcl` alebo vytvoriť stub.
