#!/usr/bin/env python3
"""
@file bin2mif.py
@brief Binary to Quartus MIF converter (v3)
@details Generuje Memory Initialization File (MIF) pre Intel FPGA.
         Podporuje byte-offsety (base_addr) a voliteľnú endianitu.
"""

import sys
import argparse

def bin2mif(in_path, out_path, size_bytes=4096, base_addr=0, endian="little"):
    # --- 1. Validácia ---
    if size_bytes % 4 != 0 or base_addr % 4 != 0:
        print(f"[ERROR] Veľkosť a báza musia byť zarovnané na 4 bajty.")
        sys.exit(1)

    try:
        with open(in_path, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"[ERROR] Načítanie zlyhalo: {e}")
        sys.exit(1)

    if len(data) > size_bytes:
        print(f"[ERROR] Binárka presahuje alokovanú RAM!")
        sys.exit(1)

    depth = size_bytes // 4
    word_base = base_addr // 4

    # --- 2. Generovanie MIF obsahu ---
    try:
        with open(out_path, "w") as f:
            f.write(f"-- Auto-generated MIF\n-- Source: {in_path}\n")
            f.write(f"DEPTH = {depth};\nWIDTH = 32;\n")
            f.write(f"ADDRESS_RADIX = HEX;\nDATA_RADIX = HEX;\nCONTENT BEGIN\n")

            for i in range(0, size_bytes, 4):
                word_addr = word_base + (i // 4)

                if i < len(data):
                    chunk = data[i : i + 4]
                    if len(chunk) < 4:
                        chunk = chunk.ljust(4, b'\x00') # Padding posledného neúplného slova
                    val = int.from_bytes(chunk, byteorder=endian)
                else:
                    val = 0 # Padding zvyšku pamäte nulami

                f.write(f"  {word_addr:04X} : {val:08X};\n")

            f.write("END;\n")
        print(f"[OK] {in_path} -> {out_path} (Depth: {depth}, Base: 0x{base_addr:X})")
    except OSError as e:
        print(f"[ERROR] Zápis MIF zlyhal: {e}")
        sys.exit(1)

def _parse_int(s):
    return int(s, 0)

def main():
    parser = argparse.ArgumentParser(description="Bin2Mif pre Intel Quartus")
    parser.add_argument("input",  help="Vstupný .bin")
    parser.add_argument("output", help="Výstupný .mif")
    parser.add_argument("size",   nargs="?", type=_parse_int, default=4096, help="RAM v bajtoch")
    parser.add_argument("--base", type=_parse_int, default=0, help="Bázová adresa (byte offset)")
    parser.add_argument("--big",  action="store_true", help="Big-Endian mód")

    args = parser.parse_args()
    bin2mif(args.input, args.output, args.size, args.base, "big" if args.big else "little")

if __name__ == "__main__":
    main()
