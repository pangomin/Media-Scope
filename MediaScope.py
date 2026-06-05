"""
MediaScope - Telegram Channel Media Analyzer
Cross-platform compatible (Linux & Windows)

Requirements:
    pip install telethon rich

Usage:
    python MediaScope.py
"""

import asyncio
import logging
import sys
import os
import json
import platform
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Windows asyncio fix (must be before any event-loop usage) ──────────────
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from telethon import TelegramClient, types
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.table import Table
from rich.logging import RichHandler


# ── Configuration ─────────────────────────────────────────────────────────────

CONFIG_FILE = Path("mediascope_config.json")

@dataclass
class Config:
    API_ID: int = 0
    API_HASH: str = ""
    PHONE_NUMBER: str = ""
    SESSION_NAME: str = "persistent_session"
    BATCH_SIZE: int = 100
    OUTPUT_DIR: Path = field(default_factory=lambda: Path("."))

    def __post_init__(self):
        self.OUTPUT_DIR = Path(self.OUTPUT_DIR)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def is_complete(self) -> bool:
        return bool(self.API_ID and self.API_HASH and self.PHONE_NUMBER)

    def save(self) -> None:
        CONFIG_FILE.write_text(
            json.dumps({
                "API_ID": self.API_ID,
                "API_HASH": self.API_HASH,
                "PHONE_NUMBER": self.PHONE_NUMBER,
            }, indent=4),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                return cls(
                    API_ID=int(data.get("API_ID", 0)),
                    API_HASH=data.get("API_HASH", ""),
                    PHONE_NUMBER=data.get("PHONE_NUMBER", ""),
                )
            except (json.JSONDecodeError, ValueError):
                pass
        return cls()


def prompt_credentials(console: Console, config: Config) -> Config:
    """Interactively ask the user for missing Telegram credentials."""
    console.print("\n[bold yellow]Telegram API credentials not found.[/bold yellow]")
    console.print(
        "Get yours at [link=https://my.telegram.org]https://my.telegram.org[/link]\n"
    )

    while not config.API_ID:
        raw = input("  API ID (integer): ").strip()
        try:
            config.API_ID = int(raw)
        except ValueError:
            console.print("[red]  API ID must be a number. Try again.[/red]")

    while not config.API_HASH:
        raw = input("  API Hash: ").strip()
        if raw:
            config.API_HASH = raw
        else:
            console.print("[red]  API Hash cannot be empty. Try again.[/red]")

    while not config.PHONE_NUMBER:
        raw = input("  Phone number (e.g. +49123456789): ").strip()
        if raw:
            config.PHONE_NUMBER = raw
        else:
            console.print("[red]  Phone number cannot be empty. Try again.[/red]")

    config.save()
    console.print(f"\n[green]Credentials saved to {CONFIG_FILE}[/green]\n")
    return config


# ── Analyzer ──────────────────────────────────────────────────────────────────

class TelegramMediaAnalyzer:

    # Comprehensive extension → category map
    FILE_TYPES: dict[str, set[str]] = {
        "videos":    {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
                      ".m4v", ".3gp", ".mpeg", ".mpg", ".m2ts"},
        "audio":     {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma",
                      ".aiff", ".alac", ".opus"},
        "images":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff",
                      ".svg", ".raw", ".heic", ".avif"},
        "documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt",
                      ".xls", ".xlsx", ".ppt", ".pptx", ".odp", ".ods"},
        "archives":  {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
                      ".iso", ".zst"},
        "code":      {".py", ".js", ".ts", ".java", ".cpp", ".c", ".h",
                      ".html", ".css", ".php", ".json", ".xml", ".sql",
                      ".r", ".swift", ".go", ".rs", ".kt", ".sh", ".bat",
                      ".ps1"},
        "ebooks":    {".epub", ".mobi", ".azw", ".azw3", ".fb2"},
        "design":    {".psd", ".ai", ".xd", ".sketch", ".fig", ".xcf"},
        "data":      {".csv", ".db", ".sqlite", ".parquet", ".feather"},
        "apps":      {".apk", ".ipa", ".aab", ".exe", ".msi", ".dmg", ".deb",
                      ".rpm"},
    }

    def __init__(self, config: Config) -> None:
        self.config = config
        self.console = Console()
        self.logger = self._setup_logger()
        self.client = TelegramClient(
            str(self.config.OUTPUT_DIR / self.config.SESSION_NAME),
            self.config.API_ID,
            self.config.API_HASH,
        )
        self._reset_stats()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("MediaScope")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            logger.addHandler(
                RichHandler(console=self.console, show_path=False, markup=True)
            )
        logger.propagate = False
        return logger

    def _reset_stats(self) -> None:
        self.stats: dict = {
            "total_size": 0,
            "file_count": 0,
            "media_types": {},
            "largest_file": {"size": 0, "name": None, "type": None},
            "start_time": None,
            "end_time": None,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_media_type(self, message) -> Optional[str]:
        """Return the category string for a message's attached document."""
        if not message.media:
            return None

        if isinstance(message.media, types.MessageMediaPhoto):
            return "images"

        if not hasattr(message.media, "document"):
            return None

        doc = message.media.document
        for attr in doc.attributes:
            if isinstance(attr, types.DocumentAttributeFilename):
                ext = Path(attr.file_name).suffix.lower()
                for category, exts in self.FILE_TYPES.items():
                    if ext in exts:
                        return category
                # Fall back to Telethon attribute hints
                break

        for attr in doc.attributes:
            if isinstance(attr, types.DocumentAttributeAudio):
                return "audio"
            if isinstance(attr, types.DocumentAttributeVideo):
                return "videos"

        return "other"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Return a human-readable file size string."""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"

    def _safe_filename(self, channel_title: str) -> str:
        """Strip characters that are illegal in filenames on Windows."""
        illegal = r'\/:*?"<>|'
        return "".join(c if c not in illegal else "_" for c in channel_title)

    # ── Core analysis ─────────────────────────────────────────────────────────

    async def _ensure_connected(self) -> None:
        if not self.client.is_connected():
            await self.client.connect()
        if not await self.client.is_user_authorized():
            self.logger.info("Starting authentication — check your phone for the code.")
            await self.client.start(phone=self.config.PHONE_NUMBER)
            self.logger.info("Authentication successful.")

    async def analyze_channel(self, channel_link: str) -> None:
        """Download metadata for every file in a Telegram channel and report."""
        self._reset_stats()
        try:
            await self._ensure_connected()
            channel = await self.client.get_entity(channel_link)
            self.stats["start_time"] = datetime.now()

            with Progress(
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                console=self.console,
            ) as progress:
                task = progress.add_task(
                    f"[cyan]Scanning [bold]{channel.title}[/bold]…", total=None
                )
                async for message in self.client.iter_messages(channel):
                    if not (message.media and hasattr(message.media, "document")):
                        # Still count photo-only messages
                        if isinstance(message.media, types.MessageMediaPhoto):
                            self._record_file(0, "images", "photo")
                        continue

                    doc = message.media.document
                    size: int = doc.size
                    media_type = self._get_media_type(message)
                    file_name = getattr(message.file, "name", None) or "Unknown"

                    self._record_file(size, media_type, file_name)

                    if self.stats["file_count"] % self.config.BATCH_SIZE == 0:
                        progress.advance(task, self.config.BATCH_SIZE)

            self.stats["end_time"] = datetime.now()
            await self._display_results(channel.title)
            self._save_stats(channel.title)

        except Exception:
            self.logger.exception("Analysis failed.")
            raise
        finally:
            if self.client.is_connected():
                await self.client.disconnect()

    def _record_file(
        self, size: int, media_type: Optional[str], file_name: str
    ) -> None:
        """Update running statistics for one file."""
        self.stats["total_size"] += size
        self.stats["file_count"] += 1

        if media_type:
            bucket = self.stats["media_types"].setdefault(
                media_type, {"count": 0, "size": 0}
            )
            bucket["count"] += 1
            bucket["size"] += size

        if size > self.stats["largest_file"]["size"]:
            self.stats["largest_file"] = {
                "size": size,
                "name": file_name,
                "type": media_type,
            }

    # ── Output ────────────────────────────────────────────────────────────────

    def _save_stats(self, channel_title: str) -> None:
        """Persist analysis results as a JSON file."""
        payload = {
            "channel": channel_title,
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_files": self.stats["file_count"],
            "total_size": self.stats["total_size"],
            "total_size_human": self._format_size(self.stats["total_size"]),
            "media_types": self.stats["media_types"],
            "largest_file": {
                **self.stats["largest_file"],
                "size_human": self._format_size(self.stats["largest_file"]["size"]),
            },
            "duration": str(self.stats["end_time"] - self.stats["start_time"]),
        }
        safe_title = self._safe_filename(channel_title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = self.config.OUTPUT_DIR / f"analysis_{safe_title}_{timestamp}.json"
        out_path.write_text(
            json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8"
        )
        self.logger.info(f"Results saved → [bold]{out_path}[/bold]")

    async def _display_results(self, channel_title: str) -> None:
        self.console.print(
            f"\n[bold green]✓ Analysis complete:[/bold green] {channel_title}"
        )
        duration = self.stats["end_time"] - self.stats["start_time"]

        # ── Summary table ──
        summary = Table(show_header=True, header_style="bold magenta", box=None)
        summary.add_column("Metric", style="cyan", min_width=20)
        summary.add_column("Value", justify="right")
        summary.add_row("Total files", str(self.stats["file_count"]))
        summary.add_row("Total size", self._format_size(self.stats["total_size"]))
        summary.add_row("Duration", str(duration))
        if self.stats["largest_file"]["name"]:
            lf = self.stats["largest_file"]
            summary.add_row(
                "Largest file",
                f"{lf['name']}  ({self._format_size(lf['size'])})",
            )
        self.console.print(summary)

        # ── Per-type breakdown ──
        if self.stats["media_types"]:
            breakdown = Table(show_header=True, header_style="bold magenta", box=None)
            breakdown.add_column("Type", style="cyan")
            breakdown.add_column("Files", justify="right")
            breakdown.add_column("Size", justify="right")
            breakdown.add_column("%", justify="right")

            total = max(self.stats["total_size"], 1)
            for media_type, data in sorted(
                self.stats["media_types"].items(),
                key=lambda kv: kv[1]["size"],
                reverse=True,
            ):
                pct = data["size"] / total * 100
                breakdown.add_row(
                    media_type.capitalize(),
                    str(data["count"]),
                    self._format_size(data["size"]),
                    f"{pct:.1f}%",
                )
            self.console.print("\n[bold]Media type breakdown[/bold]")
            self.console.print(breakdown)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    console = Console()
    console.print(
        "[bold cyan]MediaScope[/bold cyan] — Telegram channel media analyzer\n"
    )

    config = Config.load()
    if not config.is_complete():
        config = prompt_credentials(console, config)

    analyzer = TelegramMediaAnalyzer(config)

    channel_link = input("Channel link or username (e.g. @channelusername): ").strip()
    if not channel_link:
        console.print("[red]No channel provided. Exiting.[/red]")
        sys.exit(1)

    await analyzer.analyze_channel(channel_link)


if __name__ == "__main__":
    asyncio.run(main())
