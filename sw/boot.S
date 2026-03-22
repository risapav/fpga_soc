# sw/boot.S
# Low-level startup for PicoRV32 SoC

.section .vectors, "ax"
.global _start

_start:
    # 1. Nastavenie Stack Pointera (koniec 32KB RAM)
    li sp, 0x00008000

    # 2. Vynulovanie BSS sekcie (statické neicilizované premenné)
    la a0, _sbss
    la a1, _ebss
    bge a0, a1, end_init_bss
init_bss_loop:
    sw zero, 0(a0)
    addi a0, a0, 4
    blt a0, a1, init_bss_loop
end_init_bss:

    # 3. Skok do hlavnej C funkcie
    call main

    # 4. Nekonečná slučka ak main() skončí
_exit:
    j _exit
    