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

        # Копируем target во временную папку (с .resS если есть) — это решает
        # проблему fmod toolkit, который пишет временные файлы рядом с target
        work_target = target
        # fmod toolkit иногда пишет в work_dir — не помогает с PermissionError
        # Но мы пробуем с уникальным именем tempdir чтобы избежать конфликтов
        try:
            import tempfile
            work_dir = tempfile.mkdtemp(prefix='rpa-work-')
        except Exception:
            work_dir = tempfile.gettempdir()

        try:
            UnityPy = _check_unitypy()
            env = UnityPy.load(work_target)
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

                full_path = os.path.join(output_dir, filename)
                if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
                    return (filename, tname, 'no data (empty or missing)')
                return (filename, tname, None)
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

        # Некоторые текстуры имеют image=None (битые, или требуют fmod)
        img = getattr(data, 'image', None)
        if img is None:
            # Попробуем сохранить raw texture данные если есть
            try:
                raw = getattr(data, 'image_data', None) or getattr(data, 'm_StreamData', None)
                if raw:
                    path = os.path.join(output_dir, filename + '.bin')
                    with open(path, 'wb') as f:
                        f.write(bytes(raw) if not isinstance(raw, (bytes, bytearray)) else raw)
                    return
            except Exception:
                pass
            raise RuntimeError('Texture2D has no image (fmod missing or corrupt)')

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
            lines = ['# Exported by RPA Extractor', f'o {obj.path_id}']
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
