#!/usr/bin/env python3
"""
@file bin2hex.py
@brief Binary to Verilog Hex converter (v3)
@details Konvertuje surovú binárku na 32-bitový hex formát kompatibilný s $readmemh.
         Zabezpečuje, že výsledný súbor má presne špecifikovaný počet slov.
"""

import sys
import argparse

def bin2hex(bin_path, hex_path, size_bytes, endian="little"):
    # --- 1. Validácia parametrov ---
    if size_bytes % 4 != 0:
        print(f"[ERROR] size_bytes ({size_bytes}) musí byť násobok 4 (32-bit slovo).")
        sys.exit(1)

    # --- 2. Načítanie binárnych dát ---
    try:
        with open(bin_path, 'rb') as f:
            bindata = f.read()
    except OSError as e:
        print(f"[ERROR] Nepodarilo sa otvoriť binárku: {e}")
        sys.exit(1)

    # --- 3. Kontrola pretečenia ---
    if len(bindata) > size_bytes:
        print(f"[ERROR] Binárka ({len(bindata)} B) je väčšia ako RAM ({size_bytes} B)!")
        sys.exit(1)

    # --- 4. Spracovanie slov a Padding ---
    # Doplníme dáta nulami, aby výsledný HEX mal presne 'size_bytes'
    padded_data = bindata + b'\x00' * (size_bytes - len(bindata))
    words = []

    for i in range(0, len(padded_data), 4):
        chunk = padded_data[i:i+4]
        # Prevod bajtov na 32-bit integer podľa endianity
        word = int.from_bytes(chunk, byteorder=endian)
        words.append(f"{word:08x}")

    # --- 5. Zápis do HEX súboru ---
    try:
        with open(hex_path, 'w') as f:
            for w in words:
                f.write(w + '\n')
        print(f"[OK] {bin_path} -> {hex_path} ({len(words)} slov, endian={endian})")
    except OSError as e:
        print(f"[ERROR] Chyba pri zápise HEX: {e}")
        sys.exit(1)

def _parse_int(s):
    """Pomocná funkcia pre argparse: spracuje 4096 aj 0x1000."""
    return int(s, 0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bin2Hex pre Verilog $readmemh")
    parser.add_argument("input",      help="Vstupný .bin súbor")
    parser.add_argument("output",     help="Výstupný .hex súbor")
    parser.add_argument("size",       type=_parse_int, help="Veľkosť RAM v bajtoch")
    parser.add_argument("--big",      action="store_true", help="Použiť Big-Endian (predvolený je Little)")

    args = parser.parse_args()
    bin2hex(args.input, args.output, args.size, "big" if args.big else "little")
