#!/usr/bin/env python3
"""
Example usage of the binary dictionary.
"""

import struct

class BinaryDictionary:
    """Memory-efficient binary dictionary with fast lookup."""
    
    def __init__(self, filepath):
        with open(filepath, 'rb') as f:
            self.data = f.read()
        
        magic, version, trie_start, def_start, entry_count, max_table_size = struct.unpack('<4sIIIII', self.data[:24])
        if magic != b'MUGI':
            raise ValueError(f"Invalid magic: {magic}")
        self.trie_start = trie_start
        self.def_start = def_start
        self.entry_count = entry_count
    
    def _read_definition(self, offset):
        """Read null-terminated 'kana1|mean1|kana2|mean2|...' string. Returns list of (kana, mean)."""
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
            # Read node header: table_size (u32) + def_addr (u32)
            if node_offset + 8 > len(self.data):
                return None
            table_size, def_addr = struct.unpack('<II', self.data[node_offset:node_offset+8])
            
            char_code = ord(char)
            child_base = node_offset + 8
            hash_val = char_code % table_size
            
            # Linear probing search
            found = False
            for _ in range(table_size):
                child_offset = child_base + hash_val * 8
                if child_offset + 8 > len(self.data):
                    return None
                stored_char, addr = struct.unpack('<II', self.data[child_offset:child_offset+8])
                if stored_char == 0 and addr == 0:
                    return None  # Empty slot
                if stored_char == char_code:
                    node_offset = addr
                    found = True
                    break
                hash_val = (hash_val + 1) % table_size
            
            if not found:
                return None
        
        # Check final node for definition
        if node_offset + 8 > len(self.data):
            return None
        table_size, def_addr = struct.unpack('<II', self.data[node_offset:node_offset+8])
        if def_addr != 0:
            return self._read_definition(def_addr)
        return None


# ============================================================
# Example usage
# ============================================================

if __name__ == '__main__':
    # Load dictionary
    dict_obj = BinaryDictionary('dictionary.bin')
    print(f"Loaded dictionary: {dict_obj.entry_count:,} entries")
    
    # Simple lookups
    words = ["日本", "先生", "学生", "東京", "本", "雅", "額"]
    
    print("\nLookups:")
    for word in words:
        result = dict_obj.lookup(word)
        if result:
            if len(result) == 1:
                kana, mean = result[0]
                print(f"  {word} [{kana}]: {mean}")
            else:
                print(f"  {word} ({len(result)} readings):")
                for i, (kana, mean) in enumerate(result):
                    print(f"    {i+1}. [{kana}]: {mean}")
        else:
            print(f"  {word}: Not found")