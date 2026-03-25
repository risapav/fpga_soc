#!/usr/bin/env python3
"""
bin2mif.py - Convert binary to Quartus MIF format
Usage: python3 bin2mif.py input.bin output.mif [size_bytes]
"""
import sys

def bin2mif(in_path, out_path, size_bytes=4096):
    data = open(in_path, 'rb').read()
    if len(data) > size_bytes:
        print(f"ERROR: Binary ({len(data)} bytes) exceeds RAM ({size_bytes} bytes)")
        sys.exit(1)
    data = data + b'\x00' * (size_bytes - len(data))
    depth = size_bytes // 4

    with open(out_path, 'w') as f:
        f.write(f"DEPTH = {depth};\n")
        f.write(f"WIDTH = 32;\n")
        f.write("ADDRESS_RADIX = HEX;\n")
        f.write("DATA_RADIX = HEX;\n")
        f.write("CONTENT BEGIN\n")
        for i in range(0, len(data), 4):
            word = data[i:i+4]
            val  = word[0] | (word[1]<<8) | (word[2]<<16) | (word[3]<<24)
            f.write(f"  {i//4:04X} : {val:08X};\n")
        f.write("END;\n")
    print(f"[OK] {in_path} -> {out_path}  ({depth} words)")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: bin2mif.py input.bin output.mif [size_bytes]")
        sys.exit(1)
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 4096
    bin2mif(sys.argv[1], sys.argv[2], size)
