"""Распаковщик Unity-ассетов через UnityPy."""
import os
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Optional, List, Set, Tuple

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
            """Экспортирует один объект. Возвращает (filename, tname, error_msg)."""
            tname = obj.type.name
            ext = EXPORTABLE_TYPES[tname]
            filename = f'{tname}_{obj.path_id}.{ext}'

            try:
                if tname == 'Texture2D':
                    self._export_texture(obj, filename, output_dir)
                elif tname == 'Sprite':
                    self._export_sprite(obj, filename, output_dir)
                elif tname == 'TextAsset':
                    self._export_text(obj, filename, output_dir)
                elif tname == 'AudioClip':
                    self._export_audio(obj, filename, output_dir)
                elif tname == 'Mesh':
                    self._export_mesh(obj, filename, output_dir)
                elif tname == 'Font':
                    self._export_font(obj, filename, output_dir)
                elif tname in ('VideoClip', 'MovieTexture'):
                    self._export_video(obj, filename, output_dir)
                elif tname == 'Shader':
                    self._export_shader(obj, filename, output_dir)
                elif tname == 'MonoBehaviour':
                    self._export_monobehaviour(obj, filename, output_dir)
                elif tname == 'MonoScript':
                    self._export_monoscript(obj, filename, output_dir)
                else:
                    return (filename, tname, 'unsupported type')

                # Проверяем файл в любой подпапке (m_Name группирует в подпапку)
                # Сначала ищем в output_dir/<filename>, потом в подпапках
                full_path = os.path.join(output_dir, filename)
                if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
                    # Ищем в подпапках (scene_name)
                    for entry in os.listdir(output_dir):
                        subdir = os.path.join(output_dir, entry)
                        if os.path.isdir(subdir):
                            candidate = os.path.join(subdir, filename)
                            if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                                full_path = candidate
                                break
                    else:
                        return (filename, tname, 'no data (empty or missing)')
                return (os.path.basename(os.path.dirname(full_path)) + '/' + filename if os.path.dirname(full_path) != output_dir else filename, tname, None)
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
                    filename = f'{tname}_{obj.path_id}.{EXPORTABLE_TYPES[tname]}'
                    future = executor.submit(_export_one, obj)
                    futures.append((future, filename, tname))

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

    def _export_texture(self, obj, filename: str, output_dir: str) -> None:
        try:
            data = obj.read()
        except Exception as e:
            raise RuntimeError(f'obj.read() failed: {type(e).__name__}: {e}')

        # Иерархия: используем m_Name как подпапку (напр. 'loca_bathroom' = папка сцены)
        scene_name = None
        try:
            m_name = getattr(data, 'm_Name', None)
            if m_name:
                scene_name = _sanitize_for_path(m_name)
        except Exception:
            pass

        # Некоторые текстуры имеют image=None (битые, или требуют fmod)
        img = getattr(data, 'image', None)
        if img is None:
            # Попробуем сохранить raw texture данные если есть
            try:
                raw = getattr(data, 'image_data', None) or getattr(data, 'm_StreamData', None)
                if raw:
                    if scene_name:
                        bin_path = os.path.join(output_dir, scene_name, filename + '.bin')
                        os.makedirs(os.path.dirname(bin_path), exist_ok=True)
                    else:
                        bin_path = os.path.join(output_dir, filename + '.bin')
                    raw_bytes = bytes(raw) if not isinstance(raw, (bytes, bytearray)) else raw
                    with open(bin_path, 'wb') as f:
                        f.write(raw_bytes)
                    return
            except Exception:
                pass
            raise RuntimeError('Texture2D has no image (fmod missing or corrupt)')

        if scene_name:
            subdir = os.path.join(output_dir, scene_name)
            os.makedirs(subdir, exist_ok=True)
            path = os.path.join(subdir, filename)
        else:
            path = os.path.join(output_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
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
        # Иерархия: m_Name как подпапка
        scene_name = None
        try:
            m_name = getattr(data, 'm_Name', None)
            if m_name:
                scene_name = _sanitize_for_path(m_name)
        except Exception:
            pass
        if scene_name:
            subdir = os.path.join(output_dir, scene_name)
            os.makedirs(subdir, exist_ok=True)
            path = os.path.join(subdir, filename)
        else:
            path = os.path.join(output_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
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
