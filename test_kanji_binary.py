#!/usr/bin/env python3
"""
Test and benchmark the kanji binary dictionary.
"""

import struct
import time
import sys

class KanjiDictionary:
    def __init__(self, filepath):
        with open(filepath, 'rb') as f:
            self.data = f.read()
        
        magic, version, entries_offset, entry_count, table_size = struct.unpack('<4sIQQQ', self.data[:32])
        if magic != b'KANJ':
            raise ValueError(f"Invalid magic: {magic}")
        self.version = version
        self.entries_offset = entries_offset
        self.entry_count = entry_count
        self.table_size = table_size
        
        print(f"Magic: {magic}")
        print(f"Version: {version}")
        print(f"Entries offset: {entries_offset}")
        print(f"Entry count: {entry_count}")
        print(f"Table size: {table_size}")
        print(f"File size: {len(self.data):,} bytes")
    
    def _read_definition(self, offset):
        """Read null-terminated definition string. Returns dict of fields."""
        end = offset
        while end < len(self.data) and self.data[end] != 0:
            end += 1
        if end >= len(self.data):
            return None
        def_str = self.data[offset:end].decode('utf-8')
        parts = def_str.split('|', 7)
        if len(parts) < 8:
            return None
        return {
            'kanji': parts[0],
            'reading': parts[1],
            'meanings': parts[2].split(';') if parts[2] else [],
            'strokes': parts[3],
            'radical': parts[4],
            'penstrokes': parts[5],
            'shape': parts[6],
            'unicode': parts[7],
        }
    
    def lookup(self, kanji):
        """Look up a single kanji character. Returns dict or None."""
        if len(kanji) != 1:
            return None
        
        kanji_code = ord(kanji)
        hash_val = kanji_code % self.table_size
        entries_base = self.entries_offset
        
        for _ in range(self.table_size):
            entry_offset = entries_base + hash_val * 12
            if entry_offset + 12 > len(self.data):
                return None
            stored_code, def_addr = struct.unpack('<IQ', self.data[entry_offset:entry_offset+12])
            if stored_code == 0 and def_addr == 0:
                return None  # Empty slot
            if stored_code == kanji_code:
                return self._read_definition(def_addr)
            hash_val = (hash_val + 1) % self.table_size
        
        return None
    
    def lookup_batch(self, kanji_list):
        """Look up multiple kanji at once."""
        return {k: self.lookup(k) for k in kanji_list}


def run_tests():
    print("=" * 60)
    print("Kanji Binary Dictionary Test Suite")
    print("=" * 60)
    
    dict_obj = KanjiDictionary('kanji_dictionary.bin')
    
    # Test 1: Basic lookups
    print("\n--- Test 1: Basic Lookups ---")
    test_kanji = ['亜', '愛', '阿', '唖', '娃', '哀', '㝡', '㝢', '㝫', '㝵']
    
    for kanji in test_kanji:
        result = dict_obj.lookup(kanji)
        if result:
            print(f"  {kanji} ({result['unicode']}): {result['reading']}")
            print(f"    Meanings: {result['meanings'][:3]}")
            print(f"    Strokes: {result['strokes']}, Radical: {result['radical']}")
        else:
            print(f"  {kanji}: NOT FOUND")
    
    # Test 2: Non-existent
    print("\n--- Test 2: Non-existent Kanji ---")
    for kanji in ['A', 'Z', 'あ', 'ア', '🀄']:
        result = dict_obj.lookup(kanji)
        if result is None:
            print(f"  {kanji}: correctly NOT FOUND")
        else:
            print(f"  {kanji}: incorrectly FOUND")
    
    # Test 3: Verify specific entries
    print("\n--- Test 3: Verify Details ---")
    # Check 亜 from bank 1
    result = dict_obj.lookup('亜')
    if result:
        print(f"  亜: reading={result['reading']}, strokes={result['strokes']}, radical={result['radical']}")
        print(f"    unicode={result['unicode']}, shape={result['shape']}")
        print(f"    penstrokes={result['penstrokes']}")
    
    # Check 㝡 from bank 2
    result = dict_obj.lookup('㝡')
    if result:
        print(f"  㝡: reading={result['reading']}, strokes={result['strokes']}, radical={result['radical']}")
        print(f"    unicode={result['unicode']}, shape={result['shape']}")
    
    # Test 4: Consistency with JSON
    print("\n--- Test 4: Consistency Check ---")
    import json
    
    with open('data/kanji_bank_1.json', 'r', encoding='utf-8') as f:
        bank1 = json.load(f)
    with open('data/kanji_bank_2.json', 'r', encoding='utf-8') as f:
        bank2 = json.load(f)
    
    all_entries = bank1 + bank2
    mismatches = 0
    
    for entry in all_entries:
        kanji = entry[0]
        if not kanji:
            continue
        result = dict_obj.lookup(kanji)
        if result:
            expected_reading = entry[1]
            if result['reading'] != expected_reading:
                mismatches += 1
                if mismatches <= 5:
                    print(f"  Mismatch {kanji}: expected reading={expected_reading}, got={result['reading']}")
        else:
            mismatches += 1
            if mismatches <= 5:
                print(f"  Missing: {kanji}")
    
    print(f"  Mismatches: {mismatches}/{len(all_entries)}")
    
    # Test 5: Performance benchmark
    print("\n--- Test 5: Performance Benchmark ---")
    
    # Sample kanji for benchmark
    all_kanji = [e[0] for e in all_entries if e[0]]
    
    # Warm up
    for kanji in all_kanji[:100]:
        dict_obj.lookup(kanji)
    
    # Random access benchmark
    import random
    random.seed(42)
    sample = random.sample(all_kanji, min(1000, len(all_kanji)))
    
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        for kanji in sample:
            dict_obj.lookup(kanji)
    end = time.perf_counter()
    
    total_lookups = iterations * len(sample)
    elapsed = end - start
    per_lookup = (elapsed / total_lookups) * 1_000_000
    
    print(f"  Random access: {total_lookups:,} lookups in {elapsed:.3f}s")
    print(f"  Time per lookup: {per_lookup:.2f} µs")
    print(f"  Throughput: {total_lookups / elapsed:,.0f} lookups/sec")
    
    # Sequential access
    seq_sample = all_kanji[:1000]
    for kanji in seq_sample[:100]:
        dict_obj.lookup(kanji)
    
    start = time.perf_counter()
    for _ in range(iterations):
        for kanji in seq_sample:
            dict_obj.lookup(kanji)
    end = time.perf_counter()
    
    elapsed = end - start
    per_lookup = (elapsed / total_lookups) * 1_000_000
    print(f"  Sequential access: {total_lookups:,} lookups in {elapsed:.3f}s")
    print(f"  Time per lookup: {per_lookup:.2f} µs")
    print(f"  Throughput: {total_lookups / elapsed:,.0f} lookups/sec")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Dictionary size: {len(dict_obj.data) / 1024 / 1024:.1f} MB")
    print(f"  Entries: {dict_obj.entry_count:,}")
    print(f"  Hash table size: {dict_obj.table_size:,} slots")
    print(f"  Load factor: {dict_obj.entry_count / dict_obj.table_size:.3f}")
    print(f"  Lookup speed: ~{1_000_000 / per_lookup:,.0f} ops/sec")
    print("=" * 60)


if __name__ == '__main__':
    run_tests()