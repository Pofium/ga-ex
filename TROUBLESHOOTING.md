# Troubleshooting

Типичные проблемы при установке и использовании **GA Extractor**.

## Содержание

- [PySide6 не найден](#pyside6-не-найден)
- [UnityPy не найден](#unitypy-не-найден)
- [fmod.dll missing](#fmoddll-missing)
- [EXE не запускается / Windows SmartScreen](#exe-не-запускается--windows-smartscreen)
- [Путь слишком длинный](#путь-слишком-длинный)
- [CS2 .gax не расшифровывается](#cs2-gax-не-расшифровывается)
- [Unity: пустые папки и странные имена](#unity-пустые-папки-и-странные-имена)

---

## PySide6 не найден

**Симптом:**
```
ModuleNotFoundError: No module named 'PySide6'
```

**Причина:** GAExtractor.exe из релиза — **standalone** (включает все зависимости). Но если вы запускаете `app.py` напрямую из исходников, нужно установить PySide6.

**Решение:**

```bash
# Установить все зависимости
pip install -r requirements.txt

# Или конкретно PySide6
pip install "PySide6>=6.6.0"
```

**Альтернатива:** используйте EXE из [Releases](https://github.com/Pofium/ga-ex/releases/latest) — там всё включено.

---

## UnityPy не найден

**Симптом:**
```
ModuleNotFoundError: No module named 'UnityPy'
```

**Решение:**

```bash
pip install "UnityPy>=1.25.0"
```

**Если ошибка остаётся после установки:**
- Проверьте, что используется тот же `python`, в который установлен пакет:
  ```bash
  which python
  python -m pip show UnityPy
  ```
- Проверьте путь `C:\Python314\Lib\site-packages\UnityPy` (или аналогичный) — папка должна существовать.

---

## fmod.dll missing

**Симптом:**
```
FileNotFoundError: fmod.dll
```
или при распаковке Unity-ассета:
```
Texture2D has no image (fmod missing or corrupt)
```

**Причина:** `fmod` — нативная библиотека для декодирования текстур Unity (LZ4/ZSTD/LZMA сжатие). В standalone EXE она включена, в исходниках — нет.

**Решение:**

```bash
pip install fmod_toolkit
```

Если не помогает — установите вручную:
1. Скачайте `fmod.dll` из [UnityPy releases](https://github.com/K0lb3/UnityPy/releases)
2. Положите в корень проекта или в `C:\Windows\System32`

---

## EXE не запускается / Windows SmartScreen

**Симптом:** Windows блокирует запуск GAExtractor.exe предупреждением «неизвестный издатель».

**Решение:**

1. Нажмите **Подробнее → Выполнить в любом случае**
2. Или: ПКМ по файлу → Свойства → внизу «Разблокировать» → Применить
3. Или: используйте EXE, скачанный по HTTPS с официального [github.com/Pofium/ga-ex/releases](https://github.com/Pofium/ga-ex/releases)

Это нормально для неподписанных open-source приложений. Код [GAExtractor](https://github.com/Pofium/ga-ex) открыт — можете собрать EXE самостоятельно.

---

## Путь слишком длинный

**Симптом:**
```
err.path.length: Путь слишком длинный
```

**Причина:** Windows по умолчанию ограничивает путь 260 символами. Игра глубоко в `C:\Users\...\Downloads\...\Game_Data\sharedassets0.assets\` + длинные имена ассетов → превышение.

**Решение 1:** В GUI включите опцию **«Поддержка длинных путей Windows»**

**Решение 2:** Переместите игру ближе к корню диска:
```
C:\Games\MyGame\          ← хорошо
C:\Users\Vasya\Downloads\Games\VN\VN_pack_2_with_extra_stuff\MyGame\  ← плохо
```

**Решение 3:** Включите длинные пути в Windows 10+:
```
gpedit.msc → Computer Configuration → Administrative Templates → System → Filesystem → Enable Win32 long paths → Enabled
```

---

## CS2 .gax не расшифровывается

**Симптом:**
```
Не удалось расшифровать ни один из 697 .gax файлов.
CatSystem2 использует сложное per-game XOR-шифрование...
```

**Причина:** CatSystem2 (японский движок визуальных новелл от 戯画) использует per-game 32-битный XOR-ключ, **захардкоженный в exe**. GAExtractor может извлечь ключ только если он расположен рядом с известными маркерами (`CatScene`, `CatSystem2`, `.gax`, `.pck`, `.int`, `RENDER_TEX`).

**Если указали exe игры и всё равно не работает:**

Ключ в exe находится в неизвестном смещении. Это требует ручного reverse engineering конкретной игры.

**Решение:** Используйте специализированные инструменты с базой per-game смещений:
- **[crass](https://github.com/KatyushaScarlet/crass)** — Ciri's CS2 unpacker
- **[arc_conv](http://www.vector.co.jp/soft/dl/win95/art/se475839.html)** — японский конвертер
- **[Galatea](https://github.com/vn-tools/galatea)** — VN archive extractor
- **ExtractData**

GAExtractor сохранит .bin-файлы, которые можно скормить этим инструментам.

**Известные игры с этой проблемой:**
- *Kabe no Mukou no Tsuma no Koe 3* (`Wall.exe`)
- Многие другие CatSystem2-игры без маркеров в exe

---

## Unity: пустые папки и странные имена

**Симптом (старая версия ≤ v0.12.0):**
```
extracted/
├── 08db278ffa10df88aa80d130d1ffa85d/  ← пустая папка с MD5-хешем
├── sxo_0001/                          ← странное имя
│   └── Sprite_-9086712520569837023.png ← нечитаемое имя
├── play_ser/
│   └── Texture2D_-4031585411286485519.png
└── ... (ещё 6800 пустых папок)
```

**Решение:** Обновитесь до **v0.12.1+**. Новая структура:
```
extracted/
├── Scenes/
│   ├── Starter/Sprites/ava_ser.png  ← осмысленное имя из m_Name
│   ├── Menu/Textures/Background.png
│   ├── _Common/...                   ← ассеты в нескольких сценах
│   └── _Unreferenced/...             ← не привязаны ни к одной сцене
├── Audio/, Font/, MonoBehaviours/, Scripts/
└── 0 пустых папок
```

**Если папки всё равно создаются пустыми:** это нормально, они автоматически удаляются в конце распаковки.

---

## Другие проблемы

### Видео не извлекается
Unity `.mp4`/`.mov`/`.webm` — не все версии Unity поддерживаются UnityPy. Если Texture2D/Mesh выходят, а Video — нет, это нормальное ограничение.

### Звук — тишина / мусор
Unity AudioClip хранится в сжатом формате (FMOD/ADPCM/Vorbis). UnityPy пытается распаковать, но иногда нужно указывать sample rate вручную. См. [Unity Audio в UnityPy docs](https://github.com/K0lb3/UnityPy).

### «Не удалось прочитать индекс»
Файл повреждён или нестандартного формата. Попробуйте открыть в оригинальной игре — если там тоже не работает, значит архив битый.

### Программа не отвечает при распаковке больших архивов
Это нормально — UnityPy работает в GUI-потоке. Для архивов >500 MB используйте CLI:
```bash
GAExtractor.exe C:\Games\BigGame -o C:\Output --auto-detect
```

---

## Сообщить о баге

Нашли проблему? Создайте [Issue на GitHub](https://github.com/Pofium/ga-ex/issues) с:
1. Версия GAExtractor (Help → About или `GAExtractor.exe --version`)
2. Игра и движок (Ren'Py / Unity / RPG Maker / и т.д.)
3. Полный текст ошибки
4. Шаги для воспроизведения

Включите лог из `%TEMP%\rpa-ex-errors.log` если есть.