# boot.S - Minimal RISC-V startup
# Stack pointer from linker script (_stack_top) - auto-adapts to RAM size
.section .text.start
.globl _start
_start:
    # Stack pointer = top of RAM (4096 = 0x1000)
    lui  sp, %hi(_stack_top)
    addi sp, sp, %lo(_stack_top)

    # Clear BSS
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
    j    halt
