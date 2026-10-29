import unittest
from money import cents


class MoneyTests(unittest.TestCase):
    def test_whole_and_fraction(self):
        self.assertEqual(cents('12.34'), 1234)

    def test_half_cent_rounds_away_from_zero(self):
        self.assertEqual(cents('1.005'), 101)
        self.assertEqual(cents('-1.005'), -101)
