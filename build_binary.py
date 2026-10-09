#!/usr/bin/env python3
"""
Build binary dictionary from JSON.
Binary format:
- Header (24 bytes):
  - magic: 4 bytes "MUGI"
  - version: 4 bytes (uint32)
  - trie_start: 4 bytes (uint32) - offset from file start
  - def_start: 4 bytes (uint32) - offset from file start
  - entry_count: 4 bytes (uint32)
  - max_table_size: 4 bytes (uint32) - hash table size for trie nodes
- Definitions (at def_start):
  - Each entry: null-terminated UTF-8 string "kana1|mean1|kana2|mean2|..."
  - For duplicate words, all readings/meanings are appended
- Trie nodes (at trie_start):
  - Each node: table_size (uint32), def_addr (uint32, 0 if not leaf), children...
  - Each child: char (uint32 - Unicode code point), address (uint32)
  - Uses open addressing hash for children lookup (linear probing)
  - Empty slots: char=0, addr=0
  - All addresses are 32-bit (file < 4GB)
"""

import json
import struct
import sys

# Load dictionary
print("Loading dictionary...")
with open('data/dictionary.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

entries = data['api_entries']
print(f"Total entries: {len(entries)}")

# Group by word, collecting all (kana, mean) pairs
word_to_defs = {}
for e in entries:
    word = e.get('word', '')
    kana = e.get('kana', '')
    mean = e.get('suggest_mean', '')
    if word and mean:
        if word not in word_to_defs:
            word_to_defs[word] = []
        word_to_defs[word].append((kana if kana else word, mean))

print(f"Unique words: {len(word_to_defs)}")

# Convert to list of (word, [(kana, mean), ...]) and sort
valid_entries = []
for word, defs in word_to_defs.items():
    valid_entries.append({
        'word': word,
        'definitions': defs  # List of (kana, mean) tuples
    })

valid_entries.sort(key=lambda x: x['word'])

print(f"Words with duplicates: {sum(1 for e in valid_entries if len(e['definitions']) > 1)}")

# ============================================================
# STEP 1: Build definitions and get their addresses
# ============================================================
print("Building definitions...")

header_size = 24
def_start = header_size  # Definitions start right after header
def_data = bytearray()
def_addresses = []  # Absolute file address for each entry

for entry in valid_entries:
    addr = def_start + len(def_data)
    def_addresses.append(addr)
    
    # Format: "kana1|mean1|kana2|mean2|..." + null terminator
    def_parts = []
    for kana, mean in entry['definitions']:
        def_parts.append(kana)
        def_parts.append(mean)
    def_str = '|'.join(def_parts)
    def_bytes = def_str.encode('utf-8') + b'\x00'
    def_data.extend(def_bytes)

def_end = def_start + len(def_data)
trie_start = def_end  # Trie starts after definitions
print(f"Definitions: {len(def_data)} bytes, {def_start} to {def_end}")

# ============================================================
# STEP 2: Build trie structure
# ============================================================
print("Building trie...")

class TrieNode:
    __slots__ = ('children', 'def_index')
    def __init__(self):
        self.children = {}  # char -> TrieNode
        self.def_index = -1  # Index into valid_entries, -1 if not leaf

root = TrieNode()

for idx, entry in enumerate(valid_entries):
    node = root
    for char in entry['word']:
        if char not in node.children:
            node.children[char] = TrieNode()
        node = node.children[char]
    node.def_index = idx

print("Trie built.")

# Collect all nodes in breadth-first order for stable indexing
all_nodes = []
node_to_index = {}

def collect_nodes(node):
    if id(node) in node_to_index:
        return node_to_index[id(node)]
    index = len(all_nodes)
    node_to_index[id(node)] = index
    all_nodes.append(node)
    for child in node.children.values():
        collect_nodes(child)
    return index

collect_nodes(root)
print(f"Total trie nodes: {len(all_nodes)}")

# ============================================================
# STEP 3: Serialize trie nodes with open addressing
# ============================================================
print("Serializing trie...")

# For each node, build its hash table
node_sizes = []
for node in all_nodes:
    num_children = len(node.children)
    # For leaf nodes, we add a special entry for definition (char_code=0)
    if node.def_index >= 0:
        num_children += 1
    # Hash table size: power of 2 >= num_children * 2 (load factor <= 0.5)
    table_size = 1
    while table_size < num_children * 2:
        table_size *= 2
    # Node size: 8 bytes header + table_size * 8 bytes
    node_size = 8 + table_size * 8
    node_sizes.append(node_size)

# Compute absolute address for each node
node_addresses = []
current_offset = trie_start
for size in node_sizes:
    node_addresses.append(current_offset)
    current_offset += size

trie_end = current_offset
total_size = trie_end
print(f"Trie: {len(node_sizes)} nodes, {total_size - trie_start} bytes, {trie_start} to {trie_end}")

# ============================================================
# STEP 4: Write trie data
# ============================================================
trie_data = bytearray()

for node_idx, node in enumerate(all_nodes):
    num_children = len(node.children)
    is_leaf = node.def_index >= 0
    if is_leaf:
        num_children += 1  # For definition pointer
    
    table_size = 1
    while table_size < num_children * 2:
        table_size *= 2
    
    # Node header: table_size (uint32), def_addr (uint32)
    def_addr = def_addresses[node.def_index] if is_leaf else 0
    trie_data.extend(struct.pack('<II', table_size, def_addr))
    
    # Initialize hash table
    hash_table = [(0, 0)] * table_size
    
    # Insert children
    for char, child_node in node.children.items():
        char_code = ord(char)
        child_addr = node_addresses[node_to_index[id(child_node)]]
        # Linear probing
        hash_val = char_code % table_size
        while hash_table[hash_val] != (0, 0):
            hash_val = (hash_val + 1) % table_size
        hash_table[hash_val] = (char_code, child_addr)
    
    # Insert definition pointer for leaf nodes
    if is_leaf:
        # Use char_code=0 as marker for definition
        hash_val = 0 % table_size
        while hash_table[hash_val] != (0, 0):
            hash_val = (hash_val + 1) % table_size
        hash_table[hash_val] = (0, def_addresses[node.def_index])
    
    # Write hash table
    for char_code, addr in hash_table:
        trie_data.extend(struct.pack('<II', char_code, addr))

# Verify size matches
assert len(trie_data) == trie_end - trie_start, f"Size mismatch: {len(trie_data)} vs {trie_end - trie_start}"

# ============================================================
# STEP 5: Write final file
# ============================================================
max_table_size = 1
while max_table_size < max(len(node.children) for node in all_nodes) * 2:
    max_table_size *= 2

header = struct.pack('<4sIIIII',
    b'MUGI',
    1,
    trie_start,
    def_start,
    len(valid_entries),
    max_table_size
)

output_file = 'dictionary.bin'
with open(output_file, 'wb') as f:
    f.write(header)
    f.write(def_data)
    f.write(trie_data)

print(f"Written to {output_file}")
print(f"Header: {len(header)} bytes")
print(f"Definitions: {len(def_data)} bytes ({def_start} to {def_start + len(def_data)})")
print(f"Trie: {len(trie_data)} bytes ({trie_start} to {trie_start + len(trie_data)})")
print(f"Total: {len(header) + len(def_data) + len(trie_data)} bytes")