#!/usr/bin/env python3
"""
Build combined kanji binary dictionary from kanji_bank_1.json and kanji_bank_2.json.
Binary format:
- Header (32 bytes):
  - magic: 4 bytes "KANJ"
  - version: 4 bytes (uint32)
  - table_size: 4 bytes (uint32) - hash table size (power of 2)
  - entry_count: 4 bytes (uint32)
  - entries_offset: 4 bytes (uint32) - offset to entries array
  - def_start: 4 bytes (uint32) - offset to definitions
  - reserved: 4 bytes
- Hash table (at entries_offset):
  - Each entry: kanji_code (uint32), def_offset (uint32, 0 if empty)
  - Open addressing with linear probing
  - Empty slots: kanji_code=0, def_offset=0
- Definitions (at def_start):
  - Each entry: null-terminated UTF-8 string with all details
  - Format: "kanji|reading|meanings|strokes|radical|penstrokes|shape|unicode\0"
  - For kanji appearing in both banks, combine all data
"""

import json
import struct
import sys

def load_kanji_bank(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

# Load both banks
print("Loading kanji banks...")
bank1 = load_kanji_bank('data/kanji_bank_1.json')
bank2 = load_kanji_bank('data/kanji_bank_2.json')

print(f"Bank 1: {len(bank1)} entries")
print(f"Bank 2: {len(bank2)} entries")

# Combine and deduplicate by kanji
# We'll store all data per kanji, merging readings and meanings
kanji_data = {}

def extract_entry(entry):
    """Extract all fields from an entry."""
    kanji = entry[0]
    reading = entry[1] if len(entry) > 1 else ''
    meanings = entry[4] if len(entry) > 4 else []
    details = entry[5] if len(entry) > 5 else {}
    
    strokes = details.get('Strokes', '')
    radical = details.get('Radical', '')
    penstrokes = details.get('PenStrokes', '')
    shape = details.get('Shape', '')
    unicode_val = details.get('Unicode', '')
    
    return {
        'kanji': kanji,
        'reading': reading,
        'meanings': meanings,
        'strokes': strokes,
        'radical': radical,
        'penstrokes': penstrokes,
        'shape': shape,
        'unicode': unicode_val,
    }

# Process bank 1 first (priority)
for entry in bank1:
    if not entry[0]:
        continue
    extracted = extract_entry(entry)
    kanji = extracted['kanji']
    if kanji not in kanji_data:
        kanji_data[kanji] = extracted
    else:
        # Merge: append reading if different, merge meanings
        existing = kanji_data[kanji]
        if extracted['reading'] and extracted['reading'] not in existing['reading']:
            existing['reading'] += ' ' + extracted['reading']
        for m in extracted['meanings']:
            if m and m not in existing['meanings']:
                existing['meanings'].append(m)

# Process bank 2
for entry in bank2:
    if not entry[0]:
        continue
    extracted = extract_entry(entry)
    kanji = extracted['kanji']
    if kanji not in kanji_data:
        kanji_data[kanji] = extracted
    else:
        # Merge
        existing = kanji_data[kanji]
        if extracted['reading'] and extracted['reading'] not in existing['reading']:
            existing['reading'] += ' ' + extracted['reading']
        for m in extracted['meanings']:
            if m and m not in existing['meanings']:
                existing['meanings'].append(m)
        # Update details if missing
        for field in ['strokes', 'radical', 'penstrokes', 'shape', 'unicode']:
            if not existing[field] and extracted[field]:
                existing[field] = extracted[field]

print(f"Total unique kanji: {len(kanji_data)}")

# ============================================================
# STEP 1: Build definitions and get their addresses
# ============================================================
print("Building definitions...")

header_size = 32

# Hash table size: power of 2 >= entry_count * 2 (load factor <= 0.5)
entry_count = len(kanji_data)
table_size = 1
while table_size < entry_count * 2:
    table_size *= 2

print(f"Hash table size: {table_size} (load factor: {entry_count/table_size:.3f})")

# Hash table size in bytes: table_size * 8 bytes (4 + 4)
hash_table_bytes = table_size * 8
entries_offset = header_size
def_start = entries_offset + hash_table_bytes

print(f"Definitions start at: {def_start}")

# Build definitions
def_data = bytearray()
def_addresses = {}  # kanji -> absolute address

# Sort for consistent ordering
for kanji in sorted(kanji_data.keys()):
    data = kanji_data[kanji]
    addr = def_start + len(def_data)
    def_addresses[kanji] = addr
    
    # Join meanings with semicolon
    meanings_str = ';'.join(data['meanings'])
    
    # Format: "kanji|reading|meanings|strokes|radical|penstrokes|shape|unicode\0"
    def_str = f"{data['kanji']}|{data['reading']}|{meanings_str}|{data['strokes']}|{data['radical']}|{data['penstrokes']}|{data['shape']}|{data['unicode']}"
    def_bytes = def_str.encode('utf-8') + b'\x00'
    def_data.extend(def_bytes)

def_end = def_start + len(def_data)
total_size = def_end

print(f"Definitions: {len(def_data)} bytes ({def_start} to {def_end})")
print(f"Total file size: {total_size} bytes ({total_size/1024/1024:.1f} MB)")

# ============================================================
# STEP 2: Build hash table
# ============================================================
print("Building hash table...")

# Initialize hash table
hash_table = [(0, 0)] * table_size  # (kanji_code, def_addr)

for kanji, def_addr in def_addresses.items():
    kanji_code = ord(kanji)
    hash_val = kanji_code % table_size
    
    # Linear probing
    while hash_table[hash_val] != (0, 0):
        hash_val = (hash_val + 1) % table_size
    
    hash_table[hash_val] = (kanji_code, def_addr)

# Verify all entries placed
placed = sum(1 for k, v in hash_table if k != 0)
print(f"Placed entries: {placed}/{entry_count}")

# ============================================================
# STEP 3: Write final file
# ============================================================
print("Writing binary file...")

header = struct.pack('<4sIIIIII',
    b'KANJ',
    1,
    table_size,
    entry_count,
    entries_offset,
    def_start,
    0  # reserved
)

# Write hash table
hash_table_data = bytearray()
for kanji_code, def_addr in hash_table:
    hash_table_data.extend(struct.pack('<II', kanji_code, def_addr))

assert len(hash_table_data) == hash_table_bytes

output_file = 'kanji_dictionary.bin'
with open(output_file, 'wb') as f:
    f.write(header)
    f.write(hash_table_data)
    f.write(def_data)

print(f"Written to {output_file}")
print(f"Header: {len(header)} bytes")
print(f"Hash table: {len(hash_table_data)} bytes ({entries_offset} to {entries_offset + len(hash_table_data)})")
print(f"Definitions: {len(def_data)} bytes ({def_start} to {def_end})")
print(f"Total: {len(header) + len(hash_table_data) + len(def_data)} bytes")