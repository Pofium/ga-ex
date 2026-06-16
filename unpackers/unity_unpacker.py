"""Распаковщик Unity-ассетов через UnityPy."""
import os
import sys
from typing import Optional, List, Set

from core.base_unpacker import BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback


# Список типов Unity, которые можно экспортировать
EXPORTABLE_TYPES = {
    'Texture2D': 'png',
    'Sprite': 'png',
    'TextAsset': 'txt',
    'MonoBehaviour': 'bin',
    'AudioClip': 'wav',
    'Mesh': 'obj',
    'Font': 'ttf',
    'VideoClip': 'mp4',
    'MovieTexture': 'mp4',
    'Shader': 'shader',
}


def _check_unitypy():
    """Проверяет наличие UnityPy и выбрасывает понятную ошибку."""
    try:
        import UnityPy
        return UnityPy
    except ImportError:
        raise ImportError(
            "UnityPy is not installed. Install with: pip install UnityPy"
        )


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
        """Распаковывает Unity-ассеты в указанную папку."""
        self._cancel_requested = False
        output_dir = os.path.abspath(options.output_dir)
        os.makedirs(output_dir, exist_ok=True)

        result = UnpackResult(success=True, output_dir=output_dir)

        try:
            UnityPy = _check_unitypy()
            env = UnityPy.load(target)
        except Exception as e:
            result.success = False
            result.errors.append(f"Cannot load Unity file: {e}")
            return result

        # Собираем объекты для экспорта
        objects = list(env.objects)
        total = len(objects)

        # Если ничего нет — это всё ещё валидный пустой файл
        if total == 0:
            return result

        # Поддерживаемые для экспорта типы
        supported_types: Set[str] = set(EXPORTABLE_TYPES.keys())

        # Подсчёт: оставляем только экспортируемые
        exportable = [o for o in objects if o.type.name in supported_types]
        skipped_count = total - len(exportable)

        for i, obj in enumerate(exportable):
            if self._cancel_requested:
                result.errors.append("Cancelled by user")
                break

            tname = obj.type.name
            ext = EXPORTABLE_TYPES[tname]
            filename = f'{tname}_{obj.path_id}.{ext}'

            if progress_callback:
                progress_callback(filename, i + 1, len(exportable))

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
                else:
                    continue

                result.files_extracted.append(filename)
            except Exception as e:
                result.skipped.append({
                    'path': filename,
                    'reason': f'{tname}: {e}',
                })
                if not options.continue_on_error:
                    result.success = False
                    result.errors.append(f"Error at {filename}: {e}")
                    return result

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
        data = obj.read()
        img = data.image
        path = os.path.join(output_dir, filename)
        img.save(path)

    def _export_sprite(self, obj, filename: str, output_dir: str) -> None:
        data = obj.read()
        if hasattr(data, 'image') and data.image:
            path = os.path.join(output_dir, filename)
            data.image.save(path)

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


def options_safe(s: str) -> bool:
    """Проверяет что строка не содержит запрещённых символов."""
    bad = '<>:"/\\|?*'
    return not any(c in bad for c in s)
