/* boot.S - Minimal RISC-V startup for PicoRV32
 * Sets up stack pointer and jumps to main()
 */

.section .text.start
.globl _start

_start:
    /* Set stack pointer to top of RAM */
    la   sp, _stack_top

    /* Clear BSS section */
    la   t0, __bss_start
    la   t1, __bss_end
bss_loop:
    beq  t0, t1, bss_done
    sw   zero, 0(t0)
    addi t0, t0, 4
    j    bss_loop
bss_done:

    /* Jump to C main */
    call main

    /* Halt if main returns */
halt:
    j halt
