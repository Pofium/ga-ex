"""CLI режим для GA Extractor.

Использование:
    python cli.py file.rpa [-o OUTPUT]
    python cli.py folder/ [-o OUTPUT] [--auto-detect]
    python cli.py file.pak --aes-key 0x...

Поддерживает как одиночные файлы, так и папки с автодетектом.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.detector import FormatDetector, GameFormat
from core.base_unpacker import UnpackOptions
from core.extractor import (
    ElectronAsarUnpacker,
    GaxUnpacker,
    GodotPckUnpacker,
    GsNwjsUnpacker,
    MajiroArcUnpacker,
    RpaUnpacker,
    RpgmUnpacker,
    SevenZipUnpacker,
    TelltaleUnpacker,
    UnrealPakUnpacker,
    WolfUnpacker,
    Xp3Unpacker,
)
from unpackers import UNITY_AVAILABLE
from unpackers.pak_unpacker import normalize_unreal_aes_key
from unpackers.unity_unpacker import UnityUnpacker


def _get_unpacker_for_format(fmt: GameFormat):
    """Возвращает распаковщик по детектнутому формату."""
    if fmt == GameFormat.RENPY_RPA:
        return RpaUnpacker()
    if fmt == GameFormat.KIRIKIRI_XP3:
        return Xp3Unpacker()
    if fmt in (
        GameFormat.RPG_MAKER_RGSSAD,
        GameFormat.RPG_MAKER_RGSS2A,
        GameFormat.RPG_MAKER_RGSS3A,
        GameFormat.RPG_MAKER_MV,
    ):
        return RpgmUnpacker()
    if fmt == GameFormat.TELLTALE_TTARCH:
        return TelltaleUnpacker()
    if fmt == GameFormat.WOLF_RPG:
        return WolfUnpacker()
    if fmt == GameFormat.UNREAL_PAK:
        return UnrealPakUnpacker()
    if fmt == GameFormat.GODOT_PCK:
        return GodotPckUnpacker()
    if fmt == GameFormat.CATSYSTEM2_GAX:
        return GaxUnpacker()
    if fmt == GameFormat.MAJIRO_ARC:
        return MajiroArcUnpacker()
    if fmt == GameFormat.ELECTRON_ASAR:
        return ElectronAsarUnpacker()
    if fmt == GameFormat.GS_NWJS:
        return GsNwjsUnpacker()
    if fmt == GameFormat.GENERIC_7ZIP:
        return SevenZipUnpacker()
    if fmt == GameFormat.UNITY_ASSET and UNITY_AVAILABLE:
        return UnityUnpacker()
    return None


def _collect_assets(detector: FormatDetector, target: str) -> list:
    """Собирает подходящие ассеты из файла или папки."""
    if os.path.isfile(target):
        fmt = detector.detect_file(target)
        if fmt == GameFormat.UNKNOWN:
            return []
        size = 0
        try:
            size = os.path.getsize(target)
        except OSError:
            pass
        from core.detector import AssetInfo
        return [AssetInfo(path=target, size=size, format=fmt)]

    if os.path.isdir(target):
        info = detector.detect_folder(target)
        return info.assets

    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='ga-ex',
        description='Game archive extractor with format auto-detection',
    )
    parser.add_argument('target', help='Path to archive file or game folder')
    parser.add_argument('-o', '--output', default='./output',
                        help='Output directory (default: ./output)')
    parser.add_argument('--auto-detect', action='store_true',
                        help='Auto-detect supported archives in target folder')
    parser.add_argument('--no-sanitize', action='store_true',
                        help='Disable sanitization of invalid filename characters')
    parser.add_argument('--no-long-paths', action='store_true',
                        help='Disable Windows long path support')
    parser.add_argument('--strict', action='store_true',
                        help='Stop on first error instead of continuing')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing files')
    parser.add_argument('--no-subdirs', action='store_true',
                        help='Do not create subdirectories per archive')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')
    parser.add_argument('--game-exe',
                        help='Path to CatSystem2 game exe for .gax decryption')
    parser.add_argument('--aes-key',
                        help='AES key for encrypted Unreal .pak archives (hex)')
    parser.add_argument('--version', action='store_true',
                        help='Show version')

    args = parser.parse_args()

    if args.version:
        print('GA Extractor CLI v0.12.13')
        return 0

    if not os.path.exists(args.target):
        print(f'Error: target not found: {args.target}', file=sys.stderr)
        return 2

    try:
        unreal_aes_key = normalize_unreal_aes_key(args.aes_key)
    except ValueError as e:
        print(f'Error: invalid Unreal AES key: {e}', file=sys.stderr)
        return 2

    detector = FormatDetector()

    # Собираем список файлов для распаковки
    if os.path.isfile(args.target):
        files = _collect_assets(detector, args.target)
        if not files:
            print(f'Error: unsupported or invalid file: {args.target}', file=sys.stderr)
            return 1
    elif os.path.isdir(args.target):
        if not args.auto_detect:
            print('Hint: use --auto-detect to scan a folder for supported archives',
                  file=sys.stderr)
        files = _collect_assets(detector, args.target)
        if not files:
            print(f'Error: no supported archives found in: {args.target}', file=sys.stderr)
            return 1
    else:
        print(f'Error: target is neither file nor folder: {args.target}',
              file=sys.stderr)
        return 1

    # Параметры
    options = UnpackOptions(
        output_dir=args.output,
        sanitize_names=not args.no_sanitize,
        continue_on_error=not args.strict,
        use_long_paths=not args.no_long_paths,
        overwrite=args.overwrite,
        create_subdirs=not args.no_subdirs,
        game_exe_path=args.game_exe,
        unreal_aes_key=unreal_aes_key,
    )

    total_extracted = 0
    total_skipped = 0
    total_errors = 0

    print(f'ga-ex: found {len(files)} archive(s)')
    for asset in files:
        rpa_path = asset.path
        fmt = asset.format
        unpacker = _get_unpacker_for_format(fmt)
        if unpacker is None:
            total_errors += 1
            print(
                f'  FAILED: unsupported format for CLI: {fmt.value}',
                file=sys.stderr,
            )
            continue

        rpa_name = os.path.splitext(os.path.basename(rpa_path))[0]
        target_dir = (os.path.join(options.output_dir, rpa_name)
                      if options.create_subdirs else options.output_dir)
        asset_options = UnpackOptions(
            output_dir=target_dir,
            sanitize_names=options.sanitize_names,
            continue_on_error=options.continue_on_error,
            use_long_paths=options.use_long_paths,
            overwrite=options.overwrite,
            create_subdirs=options.create_subdirs,
            game_exe_path=options.game_exe_path,
            unreal_aes_key=options.unreal_aes_key,
        )

        if args.verbose:
            print(f'\nProcessing: {rpa_path}')
            print(f'  Format: {fmt.value}')
            print(f'  Output: {target_dir}')

        def progress(filename, current, total):
            if args.verbose:
                print(f'  [{current}/{total}] {filename}')

        try:
            result = unpacker.unpack(rpa_path, asset_options, progress)
            total_extracted += len(result.files_extracted)
            total_skipped += len(result.skipped)
            if result.errors:
                total_errors += len(result.errors)
                for err in result.errors:
                    print(f'  Error: {err}', file=sys.stderr)
            if result.skipped:
                print(f'  Skipped: {len(result.skipped)} files')
                for skip in result.skipped[:5]:
                    print(f'    - {skip["path"]}: {skip["reason"]}')
                if len(result.skipped) > 5:
                    print(f'    ... and {len(result.skipped) - 5} more')
            print(f'  Extracted: {len(result.files_extracted)} files')
        except Exception as e:
            total_errors += 1
            print(f'  FAILED: {e}', file=sys.stderr)

    print(f'\nDone. Extracted: {total_extracted}, Skipped: {total_skipped}, '
          f'Errors: {total_errors}')
    return 0 if total_errors == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
