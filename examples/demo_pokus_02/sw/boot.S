# boot.S - VexRiscv startup
# resetVector = 0x80000000 -> code starts here
.section .text.start
.globl _start
_start:
    la   sp, _stack_top  # stack pointer
    la   t0, __bss_start
    la   t1, __bss_end
bss_loop:
    beq  t0, t1, bss_done
    sw   zero, 0(t0)
    addi t0, t0, 4
    j    bss_loop
bss_done:
    call main
halt:
    j halt
