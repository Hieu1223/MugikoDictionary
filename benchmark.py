#!/usr/bin/env python3
"""
Read and benchmark binary dictionary.
New format:
- Header (24 bytes): magic(4), version(4), trie_start(4), def_start(4), entry_count(4), max_table_size(4)
- Definitions: at def_start
  - Each: null-terminated UTF-8 string "kana1|mean1|kana2|mean2|..."
- Trie nodes: at trie_start
  - Each: table_size(uint32), def_addr(uint32, 0 if not leaf), children...
  - Each child: char_code(uint32), addr(uint32)
  - Open addressing with linear probing, empty slots = (0, 0)
  - All addresses are 32-bit (file < 4GB)
"""

import struct
import time
import sys

class BinaryDictionary:
    def __init__(self, filepath):
        with open(filepath, 'rb') as f:
            self.data = f.read()
        
        # Parse header
        magic, version, trie_start, def_start, entry_count, max_table_size = struct.unpack('<4sIIIII', self.data[:24])
        self.magic = magic
        self.version = version
        self.trie_start = trie_start
        self.def_start = def_start
        self.entry_count = entry_count
        self.max_table_size = max_table_size
        
        print(f"Magic: {magic}")
        print(f"Version: {version}")
        print(f"Trie start: {trie_start}")
        print(f"Def start: {def_start}")
        print(f"Entry count: {entry_count}")
        print(f"Max table size: {max_table_size}")
        print(f"File size: {len(self.data):,} bytes")
    
    def _read_definition(self, offset):
        """Read null-terminated 'kana1|mean1|kana2|mean2|...' string at given offset. 
        Returns list of (kana, mean) tuples."""
        if offset >= len(self.data):
            return None
        end = offset
        while end < len(self.data) and self.data[end] != 0:
            end += 1
        if end >= len(self.data):
            return None
        def_str = self.data[offset:end].decode('utf-8')
        parts = def_str.split('|')
        if len(parts) < 2:
            return None
        # Group into pairs
        result = []
        for i in range(0, len(parts) - 1, 2):
            kana = parts[i]
            mean = parts[i + 1]
            result.append((kana, mean))
        return result
    
    def lookup_fast(self, word):
        """Fast lookup without building dict for children.
        Returns list of (kana, mean) tuples or None."""
        node_offset = self.trie_start
        for char in word:
            # Read node header (8 bytes: table_size uint32 + def_addr uint32)
            if node_offset + 8 > len(self.data):
                return None
            table_size, def_addr = struct.unpack('<II', self.data[node_offset:node_offset+8])
            
            # Search children using linear probing (open addressing)
            char_code = ord(char)
            child_base = node_offset + 8
            hash_val = char_code % table_size
            
            found = False
            for _ in range(table_size):
                child_offset = child_base + hash_val * 8
                if child_offset + 8 > len(self.data):
                    return None
                stored_char, addr = struct.unpack('<II', self.data[child_offset:child_offset+8])
                if stored_char == 0 and addr == 0:
                    # Empty slot - not found
                    return None
                if stored_char == char_code:
                    node_offset = addr
                    found = True
                    break
                hash_val = (hash_val + 1) % table_size
            
            if not found:
                return None
        
        # At final node, check if leaf and get definition
        if node_offset + 8 > len(self.data):
            return None
        table_size, def_addr = struct.unpack('<II', self.data[node_offset:node_offset+8])
        
        if def_addr != 0:
            # Leaf node - def_addr points directly to definition
            return self._read_definition(def_addr)
        
        return None


def benchmark():
    dict_obj = BinaryDictionary('dictionary.bin')
    
    # Test words
    test_words = [
        "おーい",
        "おセンチ",
        "おもしれー",
        "ぎ",
        "魏",
        "伎",
        "ない",
        "する",
        "ある",
        "日本",
        "東京",
        "学生",
        "先生",
        "本",
        "車",
        "電車",
    ]
    
    # Warm up
    for word in test_words:
        dict_obj.lookup_fast(word)
    
    # Benchmark
    iterations = 10000
    start = time.perf_counter()
    for _ in range(iterations):
        for word in test_words:
            dict_obj.lookup_fast(word)
    end = time.perf_counter()
    
    total_lookups = iterations * len(test_words)
    elapsed = end - start
    per_lookup = (elapsed / total_lookups) * 1_000_000  # microseconds
    
    print(f"\nBenchmark Results:")
    print(f"  Total lookups: {total_lookups}")
    print(f"  Total time: {elapsed:.4f} seconds")
    print(f"  Time per lookup: {per_lookup:.2f} µs")
    print(f"  Lookups per second: {total_lookups / elapsed:,.0f}")
    
    # Verify some results
    print("\nVerification:")
    for word in ["おーい", "ぎ", "日本", "学生", "先生", "先", "雅", "額"]:
        result = dict_obj.lookup_fast(word)
        if result:
            if len(result) == 1:
                print(f"  {word}: kana={result[0][0]}, mean={result[0][1][:50]}...")
            else:
                print(f"  {word} ({len(result)} readings):")
                for i, (kana, mean) in enumerate(result):
                    print(f"    {i+1}. kana={kana}, mean={mean[:40]}...")
        else:
            print(f"  {word}: NOT FOUND")


if __name__ == '__main__':
    benchmark()