/* sw/linker/sections.lds */
OUTPUT_FORMAT("elf32-littleriscv")
ENTRY(_start)

MEMORY
{
    RAM (xrw) : ORIGIN = 0x00000000, LENGTH = 32K
}

SECTIONS
{
    .text : {
        KEEP(*(.vectors))   /* boot.S musí byť prvý! */
        *(.text*)
        *(.rodata*)
    } > RAM

    .data : {
        *(.data*)
    } > RAM

    .bss : {
        _sbss = .;
        *(.bss*)
        _ebss = .;
    } > RAM
}
