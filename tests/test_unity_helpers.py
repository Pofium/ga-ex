"""Тесты для вспомогательных функций unity_unpacker (scene-based организация)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unpackers.unity_unpacker import (
    UnityUnpacker,
    _is_sane_filename,
    UNREFERENCED_DIR,
    COMMON_DIR,
)


class TestIsSaneFilename(unittest.TestCase):
    """Тесты для _is_sane_filename."""

    def test_normal_name_is_sane(self):
        """Обычное имя файла проходит."""
        self.assertTrue(_is_sane_filename('background'))
        self.assertTrue(_is_sane_filename('ava_nic_001'))
        self.assertTrue(_is_sane_filename('button_pressed'))

    def test_md5_hash_is_not_sane(self):
        """MD5-хеш (32 hex chars) не подходит как имя файла."""
        self.assertFalse(_is_sane_filename('08db278ffa10df88aa80d130d1ffa85d'))
        self.assertFalse(_is_sane_filename('AABBCCDDEEFF00112233445566778899'))

    def test_empty_is_not_sane(self):
        """Пустая строка не подходит."""
        self.assertFalse(_is_sane_filename(''))
        self.assertFalse(_is_sane_filename(None))

    def test_too_long_is_not_sane(self):
        """Слишком длинные имена не подходят."""
        self.assertFalse(_is_sane_filename('a' * 200))


class TestTypeSubdirName(unittest.TestCase):
    """Тесты для _type_subdir_name."""

    def test_sprite_to_sprites(self):
        """Sprite -> Sprites (множественное число)."""
        self.assertEqual(UnityUnpacker._type_subdir_name('Sprite'), 'Sprites')

    def test_texture_to_textures(self):
        """Texture2D -> Textures."""
        self.assertEqual(UnityUnpacker._type_subdir_name('Texture2D'), 'Textures')

    def test_audio_clip_to_audio(self):
        """AudioClip -> Audio."""
        self.assertEqual(UnityUnpacker._type_subdir_name('AudioClip'), 'Audio')

    def test_unknown_type_passes_through(self):
        """Неизвестный тип возвращается как есть."""
        self.assertEqual(UnityUnpacker._type_subdir_name('FooBar'), 'FooBar')


class TestBuildSceneIndex(unittest.TestCase):
    """Тесты для _build_scene_index."""

    def test_nonexistent_dir(self):
        """Несуществующая папка — пустой индекс без падения."""
        idx = UnityUnpacker._build_scene_index('/nonexistent/path/xyz')
        self.assertEqual(idx['scene_names'], {})
        self.assertEqual(idx['obj_to_scenes'], {})

    def test_empty_dir(self):
        """Пустая папка — пустой индекс."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            idx = UnityUnpacker._build_scene_index(tmp)
            self.assertEqual(idx['scene_names'], {})
            self.assertEqual(idx['obj_to_scenes'], {})

    def test_dir_without_globalgamemanagers(self):
        """Папка без globalgamemanagers — пустой индекс (без сцен)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # Создаём какой-то level-файл, но без globalgamemanagers
            with open(os.path.join(tmp, 'level0'), 'w') as f:
                f.write('dummy')
            idx = UnityUnpacker._build_scene_index(tmp)
            self.assertEqual(idx['scene_names'], {})
            self.assertEqual(idx['obj_to_scenes'], {})


class TestResolveSubpath(unittest.TestCase):
    """Тесты для _resolve_subpath."""

    def _make_obj(self, path_id: int = 1, type_name: str = 'Sprite'):
        """Создаёт mock-объект."""
        class MockObj:
            pass
        o = MockObj()
        o.path_id = path_id
        o.type = MockObj()
        o.type.name = type_name
        return o

    def test_non_sprite_falls_back_to_type(self):
        """Не-Sprite типы идут в <Type>/."""
        obj = self._make_obj(type_name='AudioClip')
        scene_index = {
            'scene_names': {'level0': 'Starter'},
            'obj_to_scenes': {1: {'Starter'}},
        }
        path = UnityUnpacker._resolve_subpath(obj, 'Audio', scene_index)
        self.assertEqual(path, 'Audio')

    def test_sprite_in_scene(self):
        """Sprite привязанный к сцене → Scenes/<Scene>/Sprites/."""
        obj = self._make_obj(path_id=42, type_name='Sprite')
        scene_index = {
            'scene_names': {'level0': 'Starter'},
            'obj_to_scenes': {42: {'Starter'}},
        }
        path = UnityUnpacker._resolve_subpath(obj, 'Sprites', scene_index)
        self.assertEqual(path, os.path.join('Scenes', 'Starter', 'Sprites'))

    def test_sprite_in_multiple_scenes(self):
        """Sprite в нескольких сценах → Scenes/_Common/Sprites/."""
        obj = self._make_obj(path_id=42, type_name='Sprite')
        scene_index = {
            'scene_names': {'level0': 'Starter', 'level2': 'Menu'},
            'obj_to_scenes': {42: {'Starter', 'Menu'}},
        }
        path = UnityUnpacker._resolve_subpath(obj, 'Sprites', scene_index)
        self.assertEqual(path, os.path.join('Scenes', COMMON_DIR, 'Sprites'))

    def test_sprite_unreferenced(self):
        """Sprite не привязан ни к одной сцене → Scenes/_Unreferenced/Sprites/."""
        obj = self._make_obj(path_id=42, type_name='Sprite')
        scene_index = {
            'scene_names': {'level0': 'Starter'},
            'obj_to_scenes': {99: {'Starter'}},  # другой path_id
        }
        path = UnityUnpacker._resolve_subpath(obj, 'Sprites', scene_index)
        self.assertEqual(path, os.path.join('Scenes', UNREFERENCED_DIR, 'Sprites'))

    def test_no_scene_index(self):
        """Без scene_index всё идёт в <Type>/."""
        obj = self._make_obj(type_name='Sprite')
        path = UnityUnpacker._resolve_subpath(obj, 'Sprites', None)
        self.assertEqual(path, 'Sprites')


class TestCleanupEmptyDirs(unittest.TestCase):
    """Тесты для _cleanup_empty_dirs."""

    def test_removes_empty_dirs(self):
        """Удаляет пустые подпапки."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'empty1'))
            os.makedirs(os.path.join(tmp, 'empty2', 'nested'))
            os.makedirs(os.path.join(tmp, 'notempty'))
            with open(os.path.join(tmp, 'notempty', 'file.txt'), 'w') as f:
                f.write('x')

            u = UnityUnpacker()
            u._cleanup_empty_dirs(tmp)

            # Пустые удалены
            self.assertFalse(os.path.exists(os.path.join(tmp, 'empty1')))
            self.assertFalse(os.path.exists(os.path.join(tmp, 'empty2')))
            # Непустые остались
            self.assertTrue(os.path.exists(os.path.join(tmp, 'notempty')))

    def test_keeps_root(self):
        """Корневая папка не удаляется."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            u = UnityUnpacker()
            u._cleanup_empty_dirs(tmp)
            self.assertTrue(os.path.exists(tmp))


class TestMakeFilename(unittest.TestCase):
    """Тесты для _make_filename."""

    def _make_obj(self, path_id: int = 1, type_name: str = 'Sprite',
                  m_name: str = None):
        class MockObj:
            pass
        o = MockObj()
        o.path_id = path_id
        o.type = MockObj()
        o.type.name = type_name

        def read():
            d = MockObj()
            d.m_Name = m_name
            return d
        o.read = read
        return o

    def test_uses_m_name_when_sane(self):
        """Использует m_Name если он нормальный."""
        obj = self._make_obj(path_id=42, m_name='ava_nic_001')
        name = UnityUnpacker._make_filename(obj, 'png')
        self.assertEqual(name, 'ava_nic_001.png')

    def test_falls_back_to_path_id_when_md5(self):
        """MD5-хеш в m_Name → fallback на Type_PathID."""
        obj = self._make_obj(path_id=42, m_name='08db278ffa10df88aa80d130d1ffa85d')
        name = UnityUnpacker._make_filename(obj, 'png')
        self.assertEqual(name, 'Sprite_42.png')

    def test_falls_back_when_empty(self):
        """Пустой m_Name → fallback."""
        obj = self._make_obj(path_id=42, m_name='')
        name = UnityUnpacker._make_filename(obj, 'png')
        self.assertEqual(name, 'Sprite_42.png')

    def test_with_override(self):
        """Можно передать m_name_override напрямую."""
        obj = self._make_obj(path_id=42, m_name='old_name')
        name = UnityUnpacker._make_filename(obj, 'png', m_name_override='new_name')
        self.assertEqual(name, 'new_name.png')


if __name__ == '__main__':
    unittest.main()