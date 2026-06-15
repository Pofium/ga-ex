"""CLI режим для rpa-ex.

Использование:
    python cli.py file.rpa [-o OUTPUT]
    python cli.py folder/ [-o OUTPUT] [--auto-detect]
    python cli.py file.rpa --no-sanitize --no-long-paths --strict

Поддерживает как одиночные файлы, так и папки с автодетектом.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.detector import FormatDetector, GameFormat
from core.base_unpacker import UnpackOptions
from unpackers.rpa_unpacker import RpaUnpacker


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='rpa-ex',
        description='RPA archive extractor for Ren\'Py games',
    )
    parser.add_argument('target', help='Path to .rpa file or folder with the game')
    parser.add_argument('-o', '--output', default='./output',
                        help='Output directory (default: ./output)')
    parser.add_argument('--auto-detect', action='store_true',
                        help='Auto-detect all .rpa files in target folder')
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
    parser.add_argument('--version', action='store_true',
                        help='Show version')

    args = parser.parse_args()

    if args.version:
        print('rpa-ex v0.9.0')
        return 0

    if not os.path.exists(args.target):
        print(f'Error: target not found: {args.target}', file=sys.stderr)
        return 2

    detector = FormatDetector()
    unpacker = RpaUnpacker()

    # Собираем список файлов для распаковки
    if os.path.isfile(args.target):
        files = detector.collect_rpa_files(args.target)
        if not files:
            print(f'Error: not a valid RPA file: {args.target}', file=sys.stderr)
            return 1
    elif os.path.isdir(args.target):
        if not args.auto_detect:
            print('Hint: use --auto-detect to scan a folder for .rpa files',
                  file=sys.stderr)
        files = detector.collect_rpa_files(args.target)
        if not files:
            print(f'Error: no .rpa files found in: {args.target}', file=sys.stderr)
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
    )

    total_extracted = 0
    total_skipped = 0
    total_errors = 0

    print(f'rpa-ex: found {len(files)} archive(s)')
    for asset in files:
        rpa_path = asset.path
        rpa_name = os.path.splitext(os.path.basename(rpa_path))[0]
        target_dir = (os.path.join(options.output_dir, rpa_name)
                      if options.create_subdirs else options.output_dir)

        if args.verbose:
            print(f'\nProcessing: {rpa_path}')
            print(f'  Output: {target_dir}')

        def progress(filename, current, total):
            if args.verbose:
                print(f'  [{current}/{total}] {filename}')

        try:
            result = unpacker.unpack(rpa_path, options, progress)
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
