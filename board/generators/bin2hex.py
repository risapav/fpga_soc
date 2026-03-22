#!/usr/bin/env python3
"""
@file bin2hex.py
@brief Binary to Verilog Hex converter
@details Converts a raw binary file to a 32-bit word hex format 
         compatible with $readmemh for Intel FPGA RAM initialization.
"""

import sys
import struct

def bin2hex(bin_path, hex_path, size_bytes):
    try:
        with open(bin_path, 'rb') as f:
            bindata = f.read()
    except Exception as e:
        print(f"Error opening binary file: {e}")
        sys.exit(1)

    # Padding binary to match RAM size if necessary
    if len(bindata) > size_bytes:
        print(f"Error: Binary size ({len(bindata)}) exceeds RAM size ({size_bytes})")
        sys.exit(1)
        
    # Process 4 bytes (32-bit word) at a time
    words = []
    for i in range(0, len(bindata), 4):
        word_chunk = bindata[i:i+4]
        # Pad last word with zeros if it's shorter than 4 bytes
        if len(word_chunk) < 4:
            word_chunk = word_chunk.ljust(4, b'\x00')
        
        # Convert to 32-bit Little Endian integer
        word = struct.unpack('<I', word_chunk)[0]
        words.append(f"{word:08x}")

    # Write to HEX file
    try:
        with open(hex_path, 'w') as f:
            for w in words:
                f.write(w + '\n')
        print(f"Successfully converted {bin_path} to {hex_path} ({len(words)} words)")
    except Exception as e:
        print(f"Error writing hex file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 bin2hex.py <input.bin> <output.hex> <size_in_bytes>")
        sys.exit(1)

    bin_path = sys.argv[1]
    hex_path = sys.argv[2]
    size_bytes = int(sys.argv[3])
    
    bin2hex(bin_path, hex_path, size_bytes)
    