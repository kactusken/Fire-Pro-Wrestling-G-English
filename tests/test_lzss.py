import random
import unittest

from tests import TestCase

import lzss


class LzssTest(TestCase):
    def roundtrip(self, data):
        packed = lzss.compress(data)
        self.assertEqual(lzss.decompress(packed), data)
        return packed

    def test_empty_and_tiny(self):
        for data in (b"", b"A", b"AB", b"ABC"):
            self.roundtrip(data)

    def test_repetitive_data_shrinks(self):
        data = b"Fire Pro Wrestling G " * 400
        self.assertLess(len(self.roundtrip(data)), len(data) // 4)

    def test_random_data(self):
        rng = random.Random(1999)
        data = bytes(rng.randrange(256) for _ in range(5000))
        self.roundtrip(data)

    def test_ring_starts_zero_filled(self):
        # Zeroes at the start can be copied from the zero-filled ring.
        data = bytes(64) + b"text"
        self.assertLess(len(self.roundtrip(data)), len(data))

    def test_matches_across_ring_wrap(self):
        # Longer than the 0x400-byte ring, with repeats at many distances.
        rng = random.Random(7)
        words = [bytes(rng.randrange(65, 91) for _ in range(rng.randrange(3, 12))) for _ in range(40)]
        data = b" ".join(rng.choice(words) for _ in range(2000))
        self.roundtrip(data)

    def test_compression_is_deterministic(self):
        data = b"abcabcabd" * 100
        self.assertEqual(lzss.compress(data), lzss.compress(data))


if __name__ == "__main__":
    unittest.main()
