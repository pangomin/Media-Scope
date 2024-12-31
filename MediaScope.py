import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
import os
import json
from telethon import TelegramClient, types
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.table import Table

@dataclass
class Config:
    API_ID: str = 'API ID'
    API_HASH: str = 'HASH'
    PHONE_NUMBER: str = 'PHONE'
    SESSION_NAME: str = 'persistent_session'
    BATCH_SIZE: int = 100

class TelegramMediaAnalyzer:
    def __init__(self, config: Config):
        self.config = config
        self.console = Console()
        self.logger = self._setup_logger()
        self.client = TelegramClient(
            self.config.SESSION_NAME,
            self.config.API_ID,
            self.config.API_HASH
        )
        self.stats = {
            'total_size': 0,
            'file_count': 0,
            'media_types': {},  # Tracks count and size for each media type
            'largest_file': {'size': 0, 'name': None, 'type': None},
            'start_time': None,
            'end_time': None
        }
        # Comprehensive file type mappings
        self.file_types = {
            # Videos
            'videos': {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpeg', '.mpg', '.m2ts'},
            # Audio
            'audio': {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma', '.aiff', '.alac'},
            # Images
            'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.raw', '.heic'},
            # Documents
            'documents': {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx'},
            # Archives
            'archives': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso'},
            # Programming
            'code': {'.py', '.js', '.java', '.cpp', '.c', '.html', '.css', '.php', '.json', '.xml', '.sql', '.r', '.swift'},
            # Ebooks
            'ebooks': {'.epub', '.mobi', '.azw', '.azw3'},
            # Design
            'design': {'.psd', '.ai', '.xd', '.sketch', '.fig', '.xcf'},
            # Data
            'data': {'.csv', '.db', '.sql', '.sqlite', '.xlsx', '.json', '.xml'},
            # Mobile Apps
            'apps': {'.apk', '.ipa', '.aab'}
        }

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger('TelegramMediaAnalyzer')
        logger.setLevel(logging.INFO)  # Set to INFO to avoid debug logs
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        return logger

    def _get_media_type(self, message) -> Optional[str]:
        """Enhanced media type detection"""
        if not message.media:
            return None
        if hasattr(message.media, 'document'):
            filename = None
            for attribute in message.media.document.attributes:
                if isinstance(attribute, types.DocumentAttributeFilename):
                    filename = attribute.file_name.lower()
                    extension = Path(filename).suffix.lower()
                    # Check against our comprehensive file type mappings
                    for type_name, extensions in self.file_types.items():
                        if extension in extensions:
                            return type_name
                    # Special case for audio and video files
                    if isinstance(attribute, types.DocumentAttributeAudio):
                        return 'audio'
                    elif isinstance(attribute, types.DocumentAttributeVideo):
                        return 'video'
            return 'other'  # If no match is found, return 'other'
        elif isinstance(message.media, types.MessageMediaPhoto):
            return 'images'
        return None

    def _format_size(self, size_bytes: int) -> str:
        """Format size into human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"  # Handling larger units if needed

    async def analyze_channel(self, channel_link: str) -> None:
        """Analyze media files in a Telegram channel."""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            if not await self.client.is_user_authorized():
                self.logger.info("New session. Starting authentication process...")
                await self.client.start(phone=self.config.PHONE_NUMBER)
                self.logger.info("Authentication successful!")
            channel = await self.client.get_entity(channel_link)
            self.stats['start_time'] = datetime.now()
            with Progress(
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("[cyan]Analyzing messages...", total=None)
                async for message in self.client.iter_messages(channel):
                    if hasattr(message.media, 'document'):
                        size = message.media.document.size
                        media_type = self._get_media_type(message)
                        
                        self.stats['total_size'] += size
                        self.stats['file_count'] += 1
                        
                        # Track the size of each media type separately
                        if media_type:
                            if media_type not in self.stats['media_types']:
                                self.stats['media_types'][media_type] = {'count': 0, 'size': 0}
                            self.stats['media_types'][media_type]['count'] += 1
                            self.stats['media_types'][media_type]['size'] += size
                        
                        if size > self.stats['largest_file']['size']:
                            self.stats['largest_file'] = {
                                'size': size,
                                'name': getattr(message.file, 'name', 'Unknown'),
                                'type': media_type
                            }
                        if self.stats['file_count'] % self.config.BATCH_SIZE == 0:
                            progress.update(task, advance=self.config.BATCH_SIZE)
                self.stats['end_time'] = datetime.now()
                await self._display_results(channel.title)
                self._save_stats(channel.title)
        except Exception as e:
            self.logger.error(f"An error occurred: {str(e)}")
            raise

    def _save_stats(self, channel_title: str):
        """Save analysis results to a JSON file"""
        stats_to_save = {
            'channel': channel_title,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_files': self.stats['file_count'],
            'total_size': self.stats['total_size'],
            'media_types': self.stats['media_types'],
            'largest_file': self.stats['largest_file'],
            'duration': str(self.stats['end_time'] - self.stats['start_time'])
        }
        filename = f"channel_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(stats_to_save, f, indent=4, ensure_ascii=False)
        self.logger.info(f"Analysis results saved to {filename}")

    async def _display_results(self, channel_title: str) -> None:
        self.console.print(f"\n[bold green]Analysis Complete for {channel_title}[/bold green]")
        duration = self.stats['end_time'] - self.stats['start_time']
        
        # Main stats table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Total Files", str(self.stats['file_count']))
        table.add_row("Total Size", self._format_size(self.stats['total_size']))
        table.add_row("Analysis Duration", str(duration))
        if self.stats['largest_file']['name']:
            table.add_row(
                "Largest File",
                f"{self.stats['largest_file']['name']} "
                f"({self._format_size(self.stats['largest_file']['size'])})"
            )
        self.console.print(table)

        # Media type distribution table
        if self.stats['media_types']:
            type_table = Table(show_header=True, header_style="bold magenta")
            type_table.add_column("Media Type", style="cyan")
            type_table.add_column("Count", justify="right")
            type_table.add_column("Size", justify="right")
            type_table.add_column("Percentage", justify="right")
            
            for media_type, data in sorted(self.stats['media_types'].items()):
                count = data['count']
                size = data['size']
                percentage = (size / self.stats['total_size']) * 100
                type_table.add_row(
                    media_type.capitalize() if media_type else 'Unknown',
                    str(count),
                    self._format_size(size),
                    f"{percentage:.1f}%"
                )
            
            self.console.print("\n[bold]Media Type Distribution[/bold]")
            self.console.print(type_table)

async def main():
    config = Config()
    analyzer = TelegramMediaAnalyzer(config)
    channel_link = input("Enter the Telegram channel link: ")
    await analyzer.analyze_channel(channel_link)

if __name__ == '__main__':
    asyncio.run(main())
