# Changelog

All notable changes to MediaScope are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.2.0] — 2026-06-05

### Added
- **Interactive credential wizard** (`prompt_credentials`): on first run the user
  is guided through entering API ID, API Hash, and phone number with inline
  validation; no more editing source code.
- **Persistent config file** (`mediascope_config.json`): credentials are saved
  locally after the first run and reloaded automatically on subsequent runs.
- `Config.load()` class-method — reads and validates `mediascope_config.json`,
  falls back to an empty `Config` on parse errors.
- `Config.save()` — serialises credentials to `mediascope_config.json`.
- `Config.is_complete()` — guard that checks all three required credential fields
  are non-empty before attempting to connect.

### Fixed
- **`ValueError: invalid literal for int() with base 10: 'API_ID'`** — `API_ID`
  is now typed as `int` (default `0`) instead of a placeholder string, so
  `TelegramClient` no longer crashes on startup when credentials are missing.

---

## [1.1.0] — 2026-06-05

### Added
- **Windows compatibility** — `asyncio.WindowsSelectorEventLoopPolicy` is applied
  at startup when running on Windows; Telethon's networking works correctly under
  the Selector event loop.
- **`_safe_filename()`** — strips Windows-illegal filename characters
  (`\ / : * ? " < > |`) before writing JSON output files.
- **`Config.OUTPUT_DIR`** — configurable output directory for both the session
  file and JSON results; created automatically via `Path.mkdir(parents=True)`.
- **`RichHandler` logging** — replaces the plain `StreamHandler` so log output
  shares the same styled console as Rich progress bars and tables.
- **`_reset_stats()`** — called at the start of each `analyze_channel` run so the
  analyzer object can be reused within the same process.
- **`client.disconnect()` in `finally`** — session is cleanly closed even when an
  exception is raised during analysis.
- **Duplicate handler guard** — `if not logger.handlers` prevents accumulating
  duplicate `RichHandler` entries on repeated instantiation.
- **Photo counting** — `MessageMediaPhoto` messages (photos without a document
  attachment) are now counted and reported under the `images` category.
- **Division-by-zero guard** — percentage calculation uses `max(total_size, 1)`
  so channels with zero bytes don't crash the display step.
- **Human-readable size in JSON output** — `total_size_human` and
  `size_human` fields added alongside raw byte counts.
- **Breakdown sorted by size** — media-type table is ordered largest-first.
- **Expanded file-type registry** — added `.opus`, `.avif`, `.zst`, `.ts`, `.go`,
  `.rs`, `.kt`, `.sh`, `.bat`, `.ps1`, `.exe`, `.msi`, `.dmg`, `.deb`, `.rpm`,
  `.parquet`, `.feather`, `.fb2`, `.odp`, `.ods`.

### Changed
- `Config.API_ID` type changed from `str` to `int` (required by Telethon).
- Session file path uses `pathlib.Path` throughout for cross-platform separators.
- `logger.propagate = False` prevents duplicate log lines from the root logger.

### Removed
- Hardcoded placeholder strings (`"API_ID"`, `"API_HASH"`, `"PHONE"`) from
  `Config` defaults.

---

## [1.0.0] — 2026-06-04 (original)

### Added
- Initial release by original author.
- Async Telegram channel scanner using Telethon.
- Media-type detection across videos, audio, images, documents, archives, code,
  ebooks, design files, data files, and mobile apps.
- Rich terminal UI with progress spinner and results tables.
- JSON export of analysis results with per-type counts and sizes.
- `_format_size()` helper for human-readable byte counts.
- Largest-file tracking across the full channel scan.

---

[1.2.0]: https://github.com/youruser/mediascope/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/youruser/mediascope/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/youruser/mediascope/releases/tag/v1.0.0
