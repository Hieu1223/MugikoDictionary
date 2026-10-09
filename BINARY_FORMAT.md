# Binary Dictionary Format Specification

## Overview

The binary dictionary format is designed for fast, memory-efficient lookups of Japanese words. It uses a trie data structure with open-addressing hash tables for child nodes, and stores definitions as null-terminated "kana1|mean1|kana2|mean2|..." strings. All addresses use 32-bit unsigned integers (file size < 4GB). For words with multiple readings/meanings, all variants are appended to the same definition string.

## File Structure

```
+------------------+
| Header (24 bytes)|
+------------------+
| Definitions      |  <- def_start (typically 24)
+------------------+
| Trie Nodes       |  <- trie_start
+------------------+
```

### Header (24 bytes)

| Offset | Size | Type    | Description |
|--------|------|---------|-------------|
| 0      | 4    | char[4] | Magic: "MUGI" |
| 4      | 4    | uint32  | Version (1) |
| 8      | 4    | uint32  | trie_start - byte offset to trie data |
| 12     | 4    | uint32  | def_start - byte offset to definitions (usually 24) |
| 16     | 4    | uint32  | entry_count - number of unique dictionary words |
| 20     | 4    | uint32  | max_table_size - maximum hash table size (reference) |

All integers are little-endian.

### Definitions (variable length)

Stored sequentially starting at `def_start`. Each entry is a **null-terminated UTF-8 string**:

```
"kana1|mean1|kana2|mean2|...\0"
```

Example for "日本" (two readings):
```
"にほん|Nhật Bản;...|にっぽん|Nhật Bản;...\0"
```

Example for "雅" (two readings):
```
"が|elegance, grace;...|みやび|refinement, elegance...\0"
```

The word itself is NOT stored - it's reconstructed from trie traversal.

### Trie Nodes (variable length)

Stored sequentially starting at `trie_start`. Each node:

| Field       | Size     | Type    | Description |
|-------------|----------|---------|-------------|
| table_size  | 4        | uint32  | Hash table size (power of 2) |
| def_addr    | 4        | uint32  | Address of definition (0 if not a leaf) |
| children    | table_size × 8 | - | Hash table entries |

#### Child Entry (8 bytes each)

| Field       | Size | Type    | Description |
|-------------|------|---------|-------------|
| char_code   | 4    | uint32  | Unicode code point (0 = empty slot or definition marker) |
| address     | 4    | uint32  | Child node address or definition address |

**Open Addressing Hash Table:**
- Uses linear probing for collision resolution
- Load factor ≤ 0.5 (table_size ≥ 2 × num_children)
- Empty slots marked with `char_code = 0, address = 0`
- For leaf nodes, an extra entry with `char_code = 0, address = def_addr` marks the definition pointer in the hash table
- The `def_addr` in the node header also points to the definition (dual storage for fast leaf check)

## Lookup Algorithm

```python
def lookup(word):
    node_offset = trie_start
    for char in word:
        # Read node header (8 bytes: table_size u32 + def_addr u32)
        table_size, def_addr = read_u32(node_offset), read_u32(node_offset + 4)
        char_code = ord(char)
        child_base = node_offset + 8
        hash_val = char_code % table_size
        
        for _ in range(table_size):
            child_offset = child_base + hash_val * 8
            stored_char = read_u32(child_offset)
            addr = read_u32(child_offset + 4)
            if stored_char == 0 and addr == 0:
                return None  # Not found
            if stored_char == char_code:
                node_offset = addr
                break
            hash_val = (hash_val + 1) % table_size
        else:
            return None
    
    # Check final node for definition
    table_size, def_addr = read_u32(node_offset), read_u32(node_offset + 4)
    if def_addr != 0:
        return read_definition(def_addr)
    return None

def read_definition(offset):
    # Read null-terminated "kana1|mean1|kana2|mean2|..." string
    end = offset
    while data[end] != 0:
        end += 1
    def_str = data[offset:end].decode('utf-8')
    parts = def_str.split('|')
    result = []
    for i in range(0, len(parts) - 1, 2):
        kana = parts[i]
        mean = parts[i + 1]
        result.append((kana, mean))
    return result
```

## Building the Dictionary

Run `python3 build_binary.py` to convert `data/dictionary.json` to `dictionary.bin`.

The build process:
1. Loads and filters valid entries (word + meaning required)
2. **Groups duplicate words** by collecting all (kana, mean) pairs
3. Sorts unique words by word
4. Writes definitions first (to get absolute addresses) - format: `"kana1|mean1|kana2|mean2|...\0"`
5. Builds trie with open-addressing hash tables
6. Writes trie nodes with absolute addresses (32-bit)
7. Writes header with correct offsets

## Performance Characteristics

- **File size**: ~24 MB for 185,368 unique words (vs 51 MB JSON)
- **Lookup time**: ~3-6 µs per lookup (~170,000-250,000 lookups/sec)
- **Memory**: Can be memory-mapped for zero-copy reads
- **Prefix search**: Supported by DFS from prefix node
- **All addresses**: 32-bit (file < 4GB)
- **Duplicate handling**: Multiple readings/meanings stored in single definition

## Kanji Dictionary

A separate `kanji_dictionary.bin` exists for single-kanji lookups:
- Format: Open-addressing hash map (not trie)
- Magic: "KANJ"
- 10,350 unique kanji from two banks
- Definition: `"kanji|reading|meanings|strokes|radical|penstrokes|shape|unicode\0"`