"""Unit-тесты: утилита sanitize_filename."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unpackers.rpa_unpacker import (
    sanitize_filename,
    INVALID_FN_CHARS,
    RESERVED_WIN_NAMES,
)


class TestSanitizeFilename(unittest.TestCase):
    def test_empty_returns_underscore(self):
        self.assertEqual(sanitize_filename(''), '_')

    def test_none_returns_underscore(self):
        self.assertEqual(sanitize_filename(None), '_')

    def test_invalid_chars_replaced(self):
        for ch in INVALID_FN_CHARS:
            result = sanitize_filename(f'a{ch}b')
            self.assertNotIn(ch, result)
            self.assertEqual(result, 'a_b')

    def test_all_invalid_chars(self):
        invalid = '<>:"/\\|?*'
        result = sanitize_filename(invalid)
        for ch in invalid:
            self.assertNotIn(ch, result)

    def test_reserved_names_protected(self):
        for name in RESERVED_WIN_NAMES:
            result = sanitize_filename(name)
            self.assertTrue(
                result.startswith('_'),
                f"Expected '{name}' to be prefixed with '_', got '{result}'"
            )

    def test_reserved_name_with_extension(self):
        result = sanitize_filename('CON.txt')
        self.assertEqual(result, '_CON.txt')

    def test_trailing_dots_and_spaces_stripped(self):
        self.assertEqual(sanitize_filename('hello...'), 'hello')
        self.assertEqual(sanitize_filename('hello   '), 'hello')
        self.assertEqual(sanitize_filename('  hello'), 'hello')

    def test_long_name_truncated(self):
        long_name = 'a' * 300 + '.txt'
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 240)
        self.assertTrue(result.endswith('.txt'))

    def test_long_name_no_extension(self):
        long_name = 'a' * 300
        result = sanitize_filename(long_name)
        self.assertEqual(len(result), 240)

    def test_normal_name_unchanged(self):
        # sanitize_filename работает с одним компонентом имени, а не с путями.
        # Если в имени есть '/', это путь — символ '/' заменяется на '_'.
        # Но 'hello.png' (без '/') не меняется.
        self.assertEqual(sanitize_filename('hello.png'), 'hello.png')
        self.assertEqual(sanitize_filename('my-file_v2.txt'), 'my-file_v2.txt')

    def test_unicode_preserved(self):
        # Юникод не должен портиться
        self.assertEqual(sanitize_filename('привет.txt'), 'привет.txt')
        self.assertEqual(sanitize_filename('日本語.png'), '日本語.png')


if __name__ == '__main__':
    unittest.main()
