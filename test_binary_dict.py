#!/usr/bin/env python3
"""
Test and benchmark the binary dictionary.
"""

import json
import struct
import time
import random
import sys

class BinaryDictionary:
    def __init__(self, filepath):
        with open(filepath, 'rb') as f:
            self.data = f.read()
        
        magic, version, trie_start, def_start, entry_count, max_table_size = struct.unpack('<4sIIIII', self.data[:24])
        if magic != b'MUGI':
            raise ValueError(f"Invalid magic: {magic}")
        self.version = version
        self.trie_start = trie_start
        self.def_start = def_start
        self.entry_count = entry_count
        self.max_table_size = max_table_size
    
    def _read_definition(self, offset):
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
    
    def lookup(self, word: str):
        """
        Look up a word in the dictionary.
        Returns list of (kana, meaning) tuples or None if not found.
        """
        node_offset = self.trie_start
        for char in word:
            if node_offset + 8 > len(self.data):
                return None
            table_size, def_addr = struct.unpack('<II', self.data[node_offset:node_offset+8])
            
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
                    return None
                if stored_char == char_code:
                    node_offset = addr
                    found = True
                    break
                hash_val = (hash_val + 1) % table_size
            
            if not found:
                return None
        
        if node_offset + 8 > len(self.data):
            return None
        table_size, def_addr = struct.unpack('<II', self.data[node_offset:node_offset+8])
        if def_addr != 0:
            return self._read_definition(def_addr)
        return None
    
    def prefix_search(self, prefix, max_results=10):
        """Find all words starting with prefix. Returns list of (word, [(kana, mean), ...])."""
        # Navigate to prefix node
        node_offset = self.trie_start
        for char in prefix:
            if node_offset + 8 > len(self.data):
                return []
            table_size, def_addr = struct.unpack('<II', self.data[node_offset:node_offset+8])
            char_code = ord(char)
            child_base = node_offset + 8
            hash_val = char_code % table_size
            
            found = False
            for _ in range(table_size):
                child_offset = child_base + hash_val * 8
                if child_offset + 8 > len(self.data):
                    return []
                stored_char, addr = struct.unpack('<II', self.data[child_offset:child_offset+8])
                if stored_char == 0 and addr == 0:
                    return []
                if stored_char == char_code:
                    node_offset = addr
                    found = True
                    break
                hash_val = (hash_val + 1) % table_size
            
            if not found:
                return []
        
        # DFS from this node to collect words
        results = []
        stack = [(node_offset, prefix)]
        
        while stack and len(results) < max_results:
            curr_offset, curr_word = stack.pop()
            
            if curr_offset + 8 > len(self.data):
                continue
            table_size, def_addr = struct.unpack('<II', self.data[curr_offset:curr_offset+8])
            
            # Check if this node has a definition
            if def_addr != 0:
                defn = self._read_definition(def_addr)
                if defn:
                    results.append((curr_word, defn))
            
            # Add children to stack
            child_base = curr_offset + 8
            for i in range(table_size):
                child_offset = child_base + i * 8
                if child_offset + 8 > len(self.data):
                    break
                stored_char, addr = struct.unpack('<II', self.data[child_offset:child_offset+8])
                if stored_char != 0 and addr != 0:
                    # Skip definition marker (char_code=0)
                    if stored_char != 0:
                        stack.append((addr, curr_word + chr(stored_char)))
        
        return results


def run_tests():
    print("=" * 60)
    print("Binary Dictionary Test Suite")
    print("=" * 60)
    
    dict_obj = BinaryDictionary('dictionary.bin')
    print(f"Version: {dict_obj.version}")
    print(f"Entries: {dict_obj.entry_count}")
    print(f"Trie start: {dict_obj.trie_start}")
    print(f"Def start: {dict_obj.def_start}")
    print(f"File size: {len(dict_obj.data):,} bytes")
    
    # Test 1: Basic lookups
    print("\n--- Test 1: Basic Lookups ---")
    test_cases = [
        ("おーい", ["おーい"], "ahoy"),
        ("ぎ", ["ぎ"], "việc làm"),
        ("魏", ["ぎ"], "Wei"),
        ("伎", ["ぎ"], "chứng nhượng"),
        ("日本", ["にほん", "にっぽん"], "Nhật Bản"),
        ("東京", ["とうきょう"], "Tokyo"),
        ("学生", ["がくせい"], "sinh viên"),
        ("先生", ["せんせい"], "giáo viên"),
        ("先", ["さき"], "đầu mút"),
        ("先端", ["せんたん"], "mũi nhọn"),
        ("雅", ["が", "みやび"], "elegance"),
        ("額", ["がく", "ひたい"], "trán"),
    ]
    
    passed = 0
    for word, expected_kanas, expected_mean_substr in test_cases:
        result = dict_obj.lookup(word)
        if result:
            kanas = [k for k, _ in result]
            if all(ek in kanas for ek in expected_kanas):
                print(f"  ✓ {word}: {len(result)} reading(s)")
                for kana, mean in result:
                    print(f"    [{kana}]: {mean[:40]}...")
                passed += 1
            else:
                print(f"  ✗ {word}: got kanas={kanas}, expected={expected_kanas}")
        else:
            print(f"  ✗ {word}: NOT FOUND")
    
    print(f"  Passed: {passed}/{len(test_cases)}")
    
    # Test 2: Non-existent words
    print("\n--- Test 2: Non-existent Words ---")
    not_found = 0
    for word in ["存在しない", "abcdef", "zzzz", "xyz"]:
        result = dict_obj.lookup(word)
        if result is None:
            print(f"  ✓ {word}: correctly NOT FOUND")
            not_found += 1
        else:
            print(f"  ✗ {word}: incorrectly FOUND")
    print(f"  Passed: {not_found}/4")
    
    # Test 3: Prefix search
    print("\n--- Test 3: Prefix Search ---")
    prefix_tests = [
        ("先", 5),
        ("先生", 5),
        ("日本", 5),
        ("東", 5),
        ("学", 5),
    ]
    for prefix, max_results in prefix_tests:
        results = dict_obj.prefix_search(prefix, max_results)
        print(f"  Prefix '{prefix}': {len(results)} results")
        for word, defs in results[:3]:
            readings = ', '.join([f"[{k}]" for k, _ in defs])
            print(f"    {word} {readings}: {defs[0][1][:40]}...")
    
    # Test 4: Consistency with JSON
    print("\n--- Test 4: Consistency Check ---")
    with open('data/dictionary.json', 'r', encoding='utf-8') as f:
        jdata = json.load(f)
    
    entries = jdata['api_entries']
    valid_entries = {}
    for e in entries:
        word = e.get('word', '')
        kana = e.get('kana', '')
        mean = e.get('suggest_mean', '')
        if word and mean:
            if word not in valid_entries:
                valid_entries[word] = []
            valid_entries[word].append((kana if kana else word, mean))
    
    # Sample random words
    random.seed(42)
    sample_words = random.sample(list(valid_entries.keys()), min(1000, len(valid_entries)))
    
    mismatches = 0
    for word in sample_words:
        result = dict_obj.lookup(word)
        if result:
            exp_defs = valid_entries[word]
            # Compare sets of (kana, mean) pairs
            exp_set = set(exp_defs)
            got_set = set(result)
            if exp_set != got_set:
                mismatches += 1
                if mismatches <= 5:
                    print(f"  Mismatch: {word}")
                    print(f"    Expected: {exp_set}")
                    print(f"    Got:      {got_set}")
        else:
            mismatches += 1
            if mismatches <= 5:
                print(f"  Missing: {word}")
    
    print(f"  Mismatches: {mismatches}/{len(sample_words)}")
    
    # Test 5: Performance benchmark
    print("\n--- Test 5: Performance Benchmark ---")
    
    # Warm up
    for word in sample_words[:100]:
        dict_obj.lookup(word)
    
    # Random access benchmark
    iterations = 500
    start = time.perf_counter()
    for _ in range(iterations):
        for word in sample_words:
            dict_obj.lookup(word)
    end = time.perf_counter()
    
    total_lookups = iterations * len(sample_words)
    elapsed = end - start
    per_lookup = (elapsed / total_lookups) * 1_000_000
    
    print(f"  Random access: {total_lookups:,} lookups in {elapsed:.3f}s")
    print(f"  Time per lookup: {per_lookup:.2f} µs")
    print(f"  Throughput: {total_lookups / elapsed:,.0f} lookups/sec")
    
    # Sequential access benchmark
    seq_words = list(valid_entries.keys())[:1000]
    for word in seq_words[:100]:
        dict_obj.lookup(word)
    
    start = time.perf_counter()
    for _ in range(iterations):
        for word in seq_words:
            dict_obj.lookup(word)
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
    print(f"  Lookup speed: ~{1_000_000 / per_lookup:,.0f} ops/sec")
    print(f"  All tests: {'PASSED' if passed == len(test_cases) and not_found == 4 and mismatches == 0 else 'SOME FAILED'}")
    print("=" * 60)


if __name__ == '__main__':
    run_tests()