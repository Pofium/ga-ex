"""Распаковщик Unity-ассетов через UnityPy."""
import os
import re
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Optional, List, Set, Tuple, Dict

from core.base_unpacker import BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback


# Список типов Unity, которые можно экспортировать
EXPORTABLE_TYPES = {
    'Texture2D': 'png',
    'Sprite': 'png',
    'TextAsset': 'txt',
    'MonoBehaviour': 'bin',
    'MonoScript': 'cs',
    'AudioClip': 'wav',
    'Mesh': 'obj',
    'Font': 'ttf',
    'VideoClip': 'mp4',
    'MovieTexture': 'mp4',
    'Shader': 'shader',
}

# Папка для ассетов, не привязанных ни к одной сцене
UNREFERENCED_DIR = '_Unreferenced'

# Папка для ассетов, используемых в нескольких сценах
COMMON_DIR = '_Common'

# Регулярка для MD5-хеша (32 hex chars)
_MD5_RE = re.compile(r'^[0-9a-f]{32}$', re.IGNORECASE)


def _is_sane_filename(name: str) -> bool:
    """Проверяет, годится ли m_Name в качестве имени файла.

    Returns False для пустых имён, MD5-хешей, имён с запрещёнными символами.
    """
    if not name:
        return False
    # MD5-хеш бесполезен как имя файла
    if _MD5_RE.match(name):
        return False
    # Слишком длинные имена
    if len(name) > 100:
        return False
    return True

# Таймаут на экспорт одного объекта (секунды)
PER_OBJECT_TIMEOUT = 10


def _sanitize_for_path(name: str) -> str:
    """Очищает имя от символов, недопустимых в путях Windows."""
    if not name:
        return ''
    # Запрещаем: \ / : * ? " < > | и управляющие символы
    bad = '<>:"/\\|?*\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
    cleaned = ''.join('_' if c in bad else c for c in name)
    # Заменяем пробелы в начале/конце и двойные пробелы
    cleaned = cleaned.strip().strip('.')
    if not cleaned:
        return ''
    return cleaned[:120]  # Ограничиваем длину


def _check_unitypy():
    """Проверяет наличие UnityPy и выбрасывает понятную ошибку."""
    try:
        import UnityPy
        return UnityPy
    except ImportError:
        raise ImportError(
            "UnityPy is not installed. Install with: pip install UnityPy"
        )


def _log_error(message: str) -> None:
    """Логирует ошибку в %TEMP%/rpa-ex-errors.log для отладки."""
    try:
        log_path = os.path.join(tempfile.gettempdir(), 'rpa-ex-errors.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f'\n{message}\n')
    except Exception:
        pass


class UnityUnpacker(BaseUnpacker):
    """Распаковщик Unity-ассетов (.assets, .bundle, .unity3d, .resource, etc.)"""

    name = 'unity'

    def __init__(self):
        self._cancel_requested = False

    def detect(self, target: str) -> bool:
        """Проверяет что target — это валидный Unity-файл."""
        if not os.path.isfile(target):
            return False
        try:
            UnityPy = _check_unitypy()
            env = UnityPy.load(target)
            # Проверяем что есть хотя бы один объект
            return any(True for _ in env.objects)
        except Exception:
            return False

    def analyze(self, target: str) -> dict:
        """Возвращает статистику по Unity-файлу."""
        UnityPy = _check_unitypy()
        env = UnityPy.load(target)
        type_counts = {}
        total = 0
        for obj in env.objects:
            tname = obj.type.name
            type_counts[tname] = type_counts.get(tname, 0) + 1
            total += 1
        return {
            'total_objects': total,
            'type_counts': type_counts,
            'file_size': os.path.getsize(target),
        }

    @staticmethod
    def _build_scene_index(game_dir: str) -> Dict:
        """Строит индекс сцен по level-файлам.

        Возвращает dict:
          {
            'scene_names': {level_filename: scene_name, ...},
            'obj_to_scenes': {path_id: set(scene_names), ...},
          }

        Если game_dir не содержит globalgamemanagers или level-файлов,
        возвращает {'scene_names': {}, 'obj_to_scenes': {}}.
        """
        result = {'scene_names': {}, 'obj_to_scenes': {}}
        if not game_dir or not os.path.isdir(game_dir):
            return result

        UnityPy = _check_unitypy()

        # 1. Парсим globalgamemanagers → имена сцен для каждого level-файла
        ggm_path = os.path.join(game_dir, 'globalgamemanagers')
        scene_names = {}
        if os.path.isfile(ggm_path):
            try:
                env = UnityPy.load(ggm_path)
                for obj in env.objects:
                    if obj.type.name == 'BuildSettings':
                        try:
                            tree = obj.read_typetree()
                            # Формат зависит от версии Unity:
                            # - Новый: m_Scenes — [{first: level_file, second: scene_name}, ...]
                            # - Старый: scenes — ['Assets/.../SceneName.unity', ...]
                            if 'm_Scenes' in tree and tree['m_Scenes']:
                                for s in tree['m_Scenes']:
                                    level_fname = s.get('first', '')
                                    scene_name = s.get('second', '')
                                    if level_fname and scene_name:
                                        scene_names[level_fname] = scene_name
                            elif 'scenes' in tree and tree['scenes']:
                                # Старый формат: имена сцен берём из пути,
                                # а level-файлы по порядку: level0, level1, ...
                                for idx, scene_path in enumerate(tree['scenes']):
                                    if not scene_path:
                                        continue
                                    scene_name = os.path.splitext(
                                        os.path.basename(scene_path)
                                    )[0]
                                    level_fname = f'level{idx}'
                                    scene_names[level_fname] = scene_name
                        except Exception:
                            pass
            except Exception:
                pass

        result['scene_names'] = scene_names
        if not scene_names:
            return result

        # 2. Для каждого level-файла собираем path_id всех Sprite/Texture2D refs
        obj_to_scenes: Dict[int, Set[str]] = {}
        for level_fname, scene_name in scene_names.items():
            level_path = os.path.join(game_dir, level_fname)
            if not os.path.isfile(level_path):
                continue
            try:
                env = UnityPy.load(level_path)
                for obj in env.objects:
                    if obj.type.name == 'MonoBehaviour':
                        try:
                            tree = obj.read_typetree()
                            # Рекурсивно ищем все PPtr (dict с m_PathID)
                            def _collect_pptrs(node):
                                if isinstance(node, dict):
                                    pid = node.get('m_PathID')
                                    if pid and pid != 0:
                                        obj_to_scenes.setdefault(
                                            pid, set()
                                        ).add(scene_name)
                                    for v in node.values():
                                        _collect_pptrs(v)
                                elif isinstance(node, list):
                                    for v in node:
                                        _collect_pptrs(v)
                            _collect_pptrs(tree)
                        except Exception:
                            continue
            except Exception:
                continue

        result['obj_to_scenes'] = obj_to_scenes
        return result

    @staticmethod
    def _resolve_subpath(
        obj,
        type_name: str,
        scene_index: Optional[Dict],
        obj_type_for_scene: str = 'Sprite',
    ) -> str:
        """Возвращает относительный подпуть для экспорта ассета.

        Структура:
          Scenes/<Scene>/<Type>/<filename>   — привязан к одной сцене
          Scenes/_Common/<Type>/<filename>   — привязан к нескольким сценам
          Scenes/_Unreferenced/<Type>/...    — не привязан ни к одной
          <Type>/<filename>                  — для типов без scene-индекса

        Sprite-ассеты ищутся по path_id; Texture2D-ассеты — по своему
        собственному path_id (часто Sprite ссылается на Texture2D).
        """
        if not scene_index or obj.type.name not in ('Sprite', 'Texture2D'):
            return type_name

        scenes_for_obj = scene_index['obj_to_scenes'].get(obj.path_id)
        if scenes_for_obj is None:
            # Для Sprite попробуем найти по path_id через typetree — нет, проще
            # через прямое попадание. Если ничего — Unreferenced.
            return os.path.join('Scenes', UNREFERENCED_DIR, type_name)

        if len(scenes_for_obj) == 1:
            scene = next(iter(scenes_for_obj))
            return os.path.join('Scenes', scene, type_name)
        return os.path.join('Scenes', COMMON_DIR, type_name)

    @staticmethod
    def _make_filename(
        obj, ext: str, m_name_override: Optional[str] = None,
    ) -> str:
        """Генерирует имя файла для ассета.

        Приоритеты:
          1. m_Name если он «адекватный» (не MD5, не пустой, не слишком длинный)
          2. Type_PathID.ext
        """
        m_name = m_name_override
        if m_name is None:
            try:
                data = obj.read()
                m_name = getattr(data, 'm_Name', None)
            except Exception:
                m_name = None

        if m_name and _is_sane_filename(m_name):
            base = _sanitize_for_path(m_name)
            if base:
                return f'{base}.{ext}'

        return f'{obj.type.name}_{obj.path_id}.{ext}'

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        """Распаковывает Unity-ассеты в указанную папку.
        Каждый объект обрабатывается с таймаутом PER_OBJECT_TIMEOUT секунд,
        чтобы один зависший объект не блокировал всю распаковку.
        """
        self._cancel_requested = False
        output_dir = os.path.abspath(options.output_dir)

        # Защита: ВСЕГДА создаём безопасную подпапку если есть риск писать в исходники
        target_dir = os.path.dirname(os.path.abspath(target))
        target_dir_norm = os.path.normcase(target_dir)
        output_dir_norm = os.path.normcase(output_dir)

        # 1. output_dir совпадает с target_dir — добавляем _extracted
        if output_dir_norm == target_dir_norm:
            output_dir = os.path.join(output_dir, '_extracted')
            _log_error(f'output_dir == target_dir, using {output_dir}')

        # 2. output_dir ВНУТРИ target_dir (типа ../Data/sharedassets0/) —
        # это то что делает ExtractThread для каждого файла. Но если файлов
        # с таким именем нет в target_dir — безопасно. Если есть — опасно.
        # Всегда используем имя архива как подпапку для ясности
        target_name = os.path.splitext(os.path.basename(target))[0]
        if output_dir_norm.startswith(target_dir_norm + os.sep):
            # Если последний компонент output_dir совпадает с именем архива — норм
            last_part = os.path.basename(output_dir)
            if last_part != target_name:
                output_dir = os.path.join(output_dir, target_name)
                _log_error(f'output_dir inside target, using {output_dir}')

        # 3. target_dir ВНУТРИ output_dir (output_dir = корень игры) —
        # создаём _extracted
        elif target_dir_norm.startswith(output_dir_norm + os.sep):
            output_dir = os.path.join(output_dir, '_extracted')
            _log_error(f'target inside output_dir, using {output_dir}')

        os.makedirs(output_dir, exist_ok=True)

        result = UnpackResult(success=True, output_dir=output_dir)

        # Строим scene-индекс по level-файлам (если target в Data/ — папка игры)
        # Поищем globalgamemanagers в target_dir или его родителе (Data/...)
        scene_index = None
        try:
            game_dir_candidate = os.path.dirname(os.path.abspath(target))
            # Если target_dir — это Data/, ищем уровни там; иначе — в target_dir
            if os.path.isfile(os.path.join(game_dir_candidate, 'globalgamemanagers')):
                scene_index = self._build_scene_index(game_dir_candidate)
            else:
                # Возможно target в глубже — попробуем поискать уровни среди соседей
                if any(
                    fn.startswith('level') and fn[len('level'):].split('.')[0].isdigit()
                    for fn in os.listdir(game_dir_candidate)
                    if os.path.isfile(os.path.join(game_dir_candidate, fn))
                ):
                    scene_index = self._build_scene_index(game_dir_candidate)
        except Exception:
            scene_index = None

        # Создаём work_dir и копируем туда .resS/.resource (fmod toolkit их там ищет)
        try:
            import tempfile as _tempfile
            import io
            work_dir = _tempfile.mkdtemp(prefix='rpa-work-')
        except Exception:
            work_dir = _tempfile.gettempdir()

        # Копируем связанные .resS/.resource в work_dir чтобы fmod мог их найти
        try:
            target_basename = os.path.basename(target)
            target_dir_orig = os.path.dirname(target)
            base_part = target_basename.split('.')[0]
            for fname in os.listdir(target_dir_orig):
                full = os.path.join(target_dir_orig, fname)
                if not os.path.isfile(full) or fname == target_basename:
                    continue
                if fname.startswith(base_part + '.') and ('.resS' in fname or fname.endswith('.resource')):
                    try:
                        with open(full, 'rb') as src_f:
                            d = src_f.read()
                        with open(os.path.join(work_dir, fname), 'wb') as dst_f:
                            dst_f.write(d)
                    except Exception:
                        pass
        except Exception:
            pass

        # Загружаем через BytesIO + меняем CWD — fmod toolkit пишет временные
        # файлы в CWD, поэтому меняем на work_dir
        try:
            UnityPy = _check_unitypy()
            file_data = None
            try:
                with open(target, 'rb') as src_f:
                    file_data = src_f.read()
            except Exception as read_err:
                _log_error(f'Cannot read target: {read_err}')
                file_data = None

            if file_data is not None:
                old_cwd = os.getcwd()
                try:
                    os.chdir(work_dir)
                    env = UnityPy.load(io.BytesIO(file_data))
                finally:
                    try:
                        os.chdir(old_cwd)
                    except Exception:
                        pass
            else:
                env = UnityPy.load(target)
        except Exception as e:
            result.success = False
            result.errors.append(f"Cannot load Unity file: {e}")
            _log_error(f"LOAD ERROR for {target}: {e}")
            return result

        objects = list(env.objects)
        total = len(objects)

        if total == 0:
            return result

        supported_types: Set[str] = set(EXPORTABLE_TYPES.keys())
        exportable = [o for o in objects if o.type.name in supported_types]
        skipped_count = total - len(exportable)

        def _export_one(obj) -> Tuple[str, str, Optional[str]]:
            """Экспортирует один объект. Возвращает (rel_filename, tname, error_msg)."""
            tname = obj.type.name
            ext = EXPORTABLE_TYPES[tname]
            type_subdir = self._type_subdir_name(tname)
            subpath = self._resolve_subpath(obj, type_subdir, scene_index)
            target_dir_for_obj = os.path.join(output_dir, subpath)
            os.makedirs(target_dir_for_obj, exist_ok=True)
            filename = self._make_filename(obj, ext)

            try:
                if tname == 'Texture2D':
                    self._export_texture(obj, filename, target_dir_for_obj)
                elif tname == 'Sprite':
                    self._export_sprite(obj, filename, target_dir_for_obj)
                elif tname == 'TextAsset':
                    self._export_text(obj, filename, target_dir_for_obj)
                elif tname == 'AudioClip':
                    self._export_audio(obj, filename, target_dir_for_obj)
                elif tname == 'Mesh':
                    self._export_mesh(obj, filename, target_dir_for_obj)
                elif tname == 'Font':
                    self._export_font(obj, filename, target_dir_for_obj)
                elif tname in ('VideoClip', 'MovieTexture'):
                    self._export_video(obj, filename, target_dir_for_obj)
                elif tname == 'Shader':
                    self._export_shader(obj, filename, target_dir_for_obj)
                elif tname == 'MonoBehaviour':
                    self._export_monobehaviour(obj, filename, target_dir_for_obj)
                elif tname == 'MonoScript':
                    self._export_monoscript(obj, filename, target_dir_for_obj)
                else:
                    return (filename, tname, 'unsupported type')

                full_path = os.path.join(target_dir_for_obj, filename)
                if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
                    return (filename, tname, 'no data (empty or missing)')
                rel = os.path.join(subpath, filename) if subpath else filename
                return (rel, tname, None)
            except Exception as e:
                return (filename, tname, f'{type(e).__name__}: {e}')

        # Обрабатываем батчами для ускорения
        BATCH_SIZE = 100
        processed = 0
        with ThreadPoolExecutor(max_workers=4) as executor:
            for batch_start in range(0, len(exportable), BATCH_SIZE):
                if self._cancel_requested:
                    result.errors.append("Cancelled by user")
                    break

                batch = exportable[batch_start:batch_start + BATCH_SIZE]
                futures = []
                for obj in batch:
                    tname = obj.type.name
                    # Используем улучшенное имя файла для отображения прогресса
                    try:
                        display_name = self._make_filename(
                            obj, EXPORTABLE_TYPES[tname]
                        )
                    except Exception:
                        display_name = f'{tname}_{obj.path_id}.{EXPORTABLE_TYPES[tname]}'
                    future = executor.submit(_export_one, obj)
                    futures.append((future, display_name, tname))

                # Собираем результаты батча
                for future, filename, tname in futures:
                    processed += 1
                    if progress_callback:
                        progress_callback(filename, processed, len(exportable))
                    try:
                        fname, tn, err = future.result(timeout=PER_OBJECT_TIMEOUT)
                        if err is None:
                            result.files_extracted.append(fname)
                        else:
                            result.skipped.append({
                                'path': fname,
                                'reason': f'{tn}: {err}',
                            })
                            _log_error(f'SKIP {fname}: {err}')
                    except FutureTimeout:
                        result.skipped.append({
                            'path': filename,
                            'reason': f'{tname}: timeout',
                        })
                        _log_error(f'TIMEOUT {filename}')

        if skipped_count > 0:
            result.skipped.append({
                'path': f'<{skipped_count} non-exportable objects>',
                'reason': 'skipped (not in supported types)',
            })

        # Удаляем пустые папки, которые могли остаться после неудачного экспорта
        self._cleanup_empty_dirs(output_dir)

        return result

    def cancel(self) -> None:
        self._cancel_requested = True

    # ---- Методы экспорта по типам ----

    def _safe_path(self, output_dir: str, filename: str) -> str:
        """Возвращает безопасный путь для записи."""
        # Очистка имени файла
        safe_name = filename.replace('..', '_').replace('/', '_').replace('\\', '_')
        if not options_safe(safe_name):  # защита от запрещённых символов
            safe_name = ''.join(c if c.isalnum() or c in '._-' else '_' for c in safe_name)
        return os.path.join(output_dir, safe_name)

    @staticmethod
    def _type_subdir_name(type_name: str) -> str:
        """Возвращает имя подпапки для типа ассета.

        В основном — это просто имя типа. Используется как корневая
        папка для ассетов этого типа.
        """
        # Sprite → Sprites (множественное число для UX)
        mapping = {
            'Sprite': 'Sprites',
            'Texture2D': 'Textures',
            'AudioClip': 'Audio',
            'MonoBehaviour': 'MonoBehaviours',
            'MonoScript': 'Scripts',
        }
        return mapping.get(type_name, type_name)

    def _cleanup_empty_dirs(self, root: str) -> None:
        """Удаляет пустые подпапки в root (рекурсивно, снизу вверх)."""
        try:
            for dirpath, dirnames, filenames in os.walk(root, topdown=False):
                # Пропускаем саму root
                if os.path.normcase(dirpath) == os.path.normcase(root):
                    continue
                # Проверяем реальное состояние папки (после удаления детей dirnames
                # может быть устаревшим, поэтому используем os.listdir)
                try:
                    actual = os.listdir(dirpath)
                except OSError:
                    continue
                if not actual:
                    try:
                        os.rmdir(dirpath)
                    except OSError:
                        pass
        except Exception:
            pass

    def _export_texture(self, obj, filename: str, output_dir: str) -> None:
        try:
            data = obj.read()
        except Exception as e:
            raise RuntimeError(f'obj.read() failed: {type(e).__name__}: {e}')

        # Некоторые текстуры имеют image=None (битые, или требуют fmod)
        img = getattr(data, 'image', None)
        if img is None:
            # Попробуем сохранить raw texture данные если есть
            try:
                raw = getattr(data, 'image_data', None) or getattr(data, 'm_StreamData', None)
                if raw:
                    bin_path = os.path.join(output_dir, filename + '.bin')
                    raw_bytes = bytes(raw) if not isinstance(raw, (bytes, bytearray)) else raw
                    with open(bin_path, 'wb') as f:
                        f.write(raw_bytes)
                    return
            except Exception:
                pass
            raise RuntimeError('Texture2D has no image (fmod missing or corrupt)')

        path = os.path.join(output_dir, filename)
        try:
            # fmod делает распаковку через временный файл — ставим TMPDIR на наш tempdir
            import tempfile
            old_tmp = os.environ.get('TMPDIR', None)
            new_tmp = os.path.abspath(tempfile.gettempdir())
            os.environ['TMPDIR'] = new_tmp
            try:
                img.save(path)
            finally:
                if old_tmp:
                    os.environ['TMPDIR'] = old_tmp
                else:
                    os.environ.pop('TMPDIR', None)
        except Exception as e:
            raise RuntimeError(f'save failed: {type(e).__name__}: {e}')

    def _export_sprite(self, obj, filename: str, output_dir: str) -> None:
        try:
            data = obj.read()
        except Exception as e:
            raise RuntimeError(f'obj.read() failed: {type(e).__name__}: {e}')

        img = getattr(data, 'image', None)
        if not img:
            raise RuntimeError('Sprite has no image (fmod missing or corrupt)')

        path = os.path.join(output_dir, filename)
        try:
            import tempfile
            old_tmp = os.environ.get('TMPDIR', None)
            new_tmp = os.path.abspath(tempfile.gettempdir())
            os.environ['TMPDIR'] = new_tmp
            try:
                img.save(path)
            finally:
                if old_tmp:
                    os.environ['TMPDIR'] = old_tmp
                else:
                    os.environ.pop('TMPDIR', None)
        except Exception as e:
            raise RuntimeError(f'save failed: {type(e).__name__}: {e}')

    def _export_text(self, obj, filename: str, output_dir: str) -> None:
        data = obj.read()
        # TextAsset: text — str, или bytes если бинарный
        path = os.path.join(output_dir, filename)
        if isinstance(data.text, str):
            with open(path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(data.text)
        else:
            with open(path, 'wb') as f:
                f.write(data.text)

    def _export_audio(self, obj, filename: str, output_dir: str) -> None:
        data = obj.read()
        # AudioClip: samples — bytes, в формате WAV после конвертации
        path = os.path.join(output_dir, filename)
        if hasattr(data, 'samples') and data.samples:
            import wave
            sample_data = data.samples
            try:
                with wave.open(path, 'wb') as wav:
                    wav.setnchannels(data.channels or 2)
                    wav.setsampwidth(2)  # 16-bit
                    wav.setframerate(data.frequency or 44100)
                    wav.writeframes(sample_data)
            except Exception:
                # fallback — пишем как есть
                with open(path, 'wb') as f:
                    f.write(sample_data)

    def _export_mesh(self, obj, filename: str, output_dir: str) -> None:
        """Экспорт меша в OBJ (vertex + triangle)."""
        data = obj.read()
        path = os.path.join(output_dir, filename)
        try:
            mesh = data.mesh
            # Сборка OBJ вручную
            lines = ['# Exported by GA Extractor', f'o {obj.path_id}']
            # Vertices
            verts = mesh.m_Vertices
            for v in verts:
                lines.append(f'v {v.x} {v.y} {v.z}')
            # UVs
            if hasattr(mesh, 'm_UV0') and mesh.m_UV0 is not None:
                for uv in mesh.m_UV0:
                    lines.append(f'vt {uv.x} {uv.y}')
            # Faces (submeshes)
            if hasattr(mesh, 'm_SubMeshes'):
                for si, sub in enumerate(mesh.m_SubMeshes):
                    if sub.indexCount == 0:
                        continue
                    lines.append(f'g submesh_{si}')
                    indices = mesh.m_Indices
                    for i in range(0, sub.indexCount, 3):
                        try:
                            a = indices[sub.firstByte // 2 + i] + 1
                            b = indices[sub.firstByte // 2 + i + 1] + 1
                            c = indices[sub.firstByte // 2 + i + 2] + 1
                            lines.append(f'f {a} {b} {c}')
                        except Exception:
                            pass
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception:
            # Если что-то не так — пишем бинарный дамп
            with open(path, 'wb') as f:
                f.write(data.m_IndexBuffer if hasattr(data, 'm_IndexBuffer') else b'')

    def _export_font(self, obj, filename: str, output_dir: str) -> None:
        data = obj.read()
        path = os.path.join(output_dir, filename)
        if hasattr(data, 'm_FontData') and data.m_FontData:
            with open(path, 'wb') as f:
                f.write(data.m_FontData)

    def _export_video(self, obj, filename: str, output_dir: str) -> None:
        """Видео — просто дамп raw data, ffmpeg может потом конвертировать."""
        data = obj.read()
        path = os.path.join(output_dir, filename)
        if hasattr(data, 'm_VideoData') and data.m_VideoData:
            with open(path, 'wb') as f:
                f.write(data.m_VideoData)
        elif hasattr(data, 'data') and data.data:
            with open(path, 'wb') as f:
                f.write(data.data)

    def _export_shader(self, obj, filename: str, output_dir: str) -> None:
        data = obj.read()
        path = os.path.join(output_dir, filename)
        if hasattr(data, 'm_Script') and data.m_Script:
            with open(path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(str(data.m_Script))

    def _export_monobehaviour(self, obj, filename: str, output_dir: str) -> None:
        """Экспорт MonoBehaviour — это сырой binary dump, часто содержит ScriptableObject данные."""
        data = obj.read()
        path = os.path.join(output_dir, filename)
        if hasattr(data, 'raw_data') and data.raw_data:
            with open(path, 'wb') as f:
                f.write(data.raw_data)
        elif hasattr(data, 'm_Name') and data.m_Name:
            # Создаём пустой файл с именем (чтобы не скипать)
            with open(path + '.name.txt', 'w', encoding='utf-8') as f:
                f.write(data.m_Name)

    def _export_monoscript(self, obj, filename: str, output_dir: str) -> None:
        """Экспорт MonoScript — информация о классе."""
        data = obj.read()
        path = os.path.join(output_dir, filename)
        info = []
        if hasattr(data, 'm_Name') and data.m_Name:
            info.append(f'Name: {data.m_Name}')
        if hasattr(data, 'm_ClassName') and data.m_ClassName:
            info.append(f'ClassName: {data.m_ClassName}')
        if hasattr(data, 'm_Namespace') and data.m_Namespace:
            info.append(f'Namespace: {data.m_Namespace}')
        if info:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(info))
        else:
            # Если нет данных — всё равно создаём файл чтобы не скипать
            with open(path, 'wb') as f:
                pass


def options_safe(s: str) -> bool:
    """Проверяет что строка не содержит запрещённых символов."""
    bad = '<>:"/\\|?*'
    return not any(c in bad for c in s)
