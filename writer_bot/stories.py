from typing import Optional
from abc import ABC, abstractmethod
import asyncio
import os
import pathlib
import re
import subprocess
import tempfile
import aiohttp
import discord
from discord.ext import commands
import urlextract
from writer_bot import utils


WORDCOUNT_CONTENT_TYPES = frozenset(["text/plain", "application/pdf"])
WORDCOUNT_MAX_SIZE = 30 * 1024 * 1024
WORDCOUNT_SCRIPT = str(pathlib.Path(__file__).resolve().parent.parent / "bin" / "wordcount.sh")

_log = utils.Logger(__name__)


class FileSrc(ABC):
    def __init__(self, kind: str, url: str, content_type: str, size: Optional[int]) -> None:
        super().__init__()
        self._kind = kind
        self._url = url
        self._content_type = content_type
        self._size = size

    @property
    def description(self) -> str:
        return (
            f"{self._kind} {self._url} ({self._content_type}, "
            f"{self._size if self._size else 'unknown'} bytes)"
        )

    def can_wordcount(self) -> bool:
        return self._content_type in WORDCOUNT_CONTENT_TYPES and (
            not self._size or self._size <= WORDCOUNT_MAX_SIZE
        )

    async def wordcount(self) -> int:
        try:
            filename = None
            try:
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    filename = f.name
                _log.info("downloading %s to %s...", self.description, filename)
                await self._download_to(filename)
                _log.info("download finished")
                return self._rounded_wordcount(await self._wordcount_file(filename))
            finally:
                if filename:
                    os.remove(filename)
                    _log.info(f"deleted {filename}")
        except (discord.DiscordException, OSError) as e:
            _log.error("wordcount failed: %s", e)
            raise discord.DiscordException(str(e)) from e

    @abstractmethod
    async def _download_to(self, filename: str) -> None:
        raise NotImplementedError

    async def _wordcount_file(self, filename: str) -> int:
        p = await asyncio.create_subprocess_exec(
            WORDCOUNT_SCRIPT,
            filename,
            self._content_type,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await p.communicate()

        if p.returncode != 0:
            raise discord.DiscordException(
                f"retcode {p.returncode}, stderr: {stderr.decode('utf-8').strip()}"
            )

        try:
            wordcount = int(stdout.decode("utf-8").strip())
        except ValueError as e:
            raise discord.DiscordException(str(e)) from e

        if wordcount < 0:
            raise discord.DiscordException(f"wordcount must be positive, got {wordcount}")

        return wordcount

    @staticmethod
    def _rounded_wordcount(wordcount: int) -> int:
        if wordcount < 100:
            return 100
        if wordcount < 1000:
            return round(wordcount, -2)
        return round(wordcount, -3)

    @staticmethod
    async def from_message(m: discord.Message) -> "Optional[FileSrc]":
        for a in m.attachments:
            at = Attachment.from_attachment(a)
            if at:
                return at

        for url in urlextract.URLExtract().find_urls(
            m.content, only_unique=True, with_schema_only=True
        ):
            l = await Link.from_url(url)
            if l:
                return l

        return None


class Link(FileSrc):
    def __init__(self, url: str, content_type: str, size: Optional[int]) -> None:
        super().__init__("link", url, content_type, size)

    async def _download_to(self, filename: str) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._url) as response:
                    data = await response.read()
            with open(filename, mode="wb") as f:
                f.write(data)
        except (aiohttp.ClientError, OSError) as e:
            raise discord.DiscordException(str(e)) from e

    @staticmethod
    async def from_url(url: str) -> "Optional[Link]":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    l = Link(url, response.content_type, response.content_length)
        except aiohttp.ClientError as e:
            raise discord.DiscordException(str(e)) from e
        if l.can_wordcount():
            _log.info("can wordcount %s", l.description)
            return l
        _log.info("can't wordcount %s", l.description)
        return None


class Attachment(FileSrc):
    def __init__(self, attachment: discord.Attachment) -> None:
        content_type = ""
        if attachment.content_type:
            content_type = attachment.content_type.split(";")[0].strip()
        super().__init__(
            "attachment",
            attachment.url,
            content_type,
            attachment.size,
        )
        self._attachment = attachment

    async def _download_to(self, filename: str) -> None:
        await self._attachment.save(pathlib.PurePath(filename))

    @staticmethod
    def from_attachment(attachment: discord.Attachment) -> "Optional[Attachment]":
        a = Attachment(attachment)
        if a.can_wordcount():
            _log.info("can wordcount %s", a.description)
            return a
        _log.info("can't wordcount %s", a.description)
        return None


class StoryFile:
    def __init__(self, src: FileSrc) -> None:
        super().__init__()
        self._src = src

    async def wordcount(self) -> int:
        return await self._src.wordcount()

    @staticmethod
    async def from_message(m: discord.Message) -> "Optional[StoryFile]":
        s = await FileSrc.from_message(m)
        if s:
            return StoryFile(s)
        return None


class Stories(commands.Cog):
    def __init__(self, bot: commands.Bot, story_forum_id: int) -> None:
        super().__init__()
        self._bot = bot
        self._story_forum_id = story_forum_id
        self._story_forum: discord.ForumChannel = None  # type: ignore
        self._actively_processing: set[int] = set()

    async def cog_load(self) -> None:
        story_forum = await self._bot.fetch_channel(self._story_forum_id)
        if not isinstance(story_forum, discord.ForumChannel):
            raise ValueError("story_forum_id must be a forum channel")
        self._story_forum = story_forum

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if thread.parent_id == self._story_forum.id:
            await self.process_thread(thread)

    @commands.Cog.listener()
    async def on_thread_update(self, _: discord.Thread, after: discord.Thread) -> None:
        if after.parent_id == self._story_forum.id:
            await self.process_thread(after)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.message_id != payload.channel_id:
            # Not a thread starter message
            return

        channel = self._bot.get_channel(payload.channel_id) or await self._bot.fetch_channel(
            payload.channel_id
        )
        if isinstance(channel, discord.Thread) and channel.parent_id == self._story_forum.id:
            await self.process_thread(channel)

    @commands.command()
    async def refresh(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply("Refreshing all stories in the forum...")
        for thread in self._story_forum.threads:
            await self.process_thread(thread)
        await ctx.reply("Finished refreshing stories")

    async def process_thread(self, thread: discord.Thread) -> None:
        if thread.id in self._actively_processing:
            return
        with utils.LogContext(f"thread {thread.id} ({thread.name})"):
            self._actively_processing.add(thread.id)
            _log.info("processing...")
            try:
                m = thread.starter_message or await thread.fetch_message(thread.id)

                story = await StoryFile.from_message(m)
                if not story:
                    _log.info("no valid files")
                    return

                wordcount = await story.wordcount()
                await self.set_wordcount(thread, wordcount)
            finally:
                self._actively_processing.remove(thread.id)
                _log.info("finished")

    async def set_wordcount(self, thread: discord.Thread, wordcount: int) -> None:
        title, existing_wordcount = self.existing_wordcount(thread.name)
        if wordcount == existing_wordcount:
            _log.info(f"existing rounded wordcount in title ({wordcount}) is correct")
            return
        if wordcount > 0:
            title = f"{title} [{wordcount} words]"
        await thread.edit(name=title)
        _log.info(f"rounded wordcount in title set to {wordcount}")

    def existing_wordcount(self, name: str) -> tuple[str, int]:
        match = re.fullmatch(r"(.*?)(\[([0-9]+) words\])?\s*", name)
        if not match:
            raise ValueError(f"failed to extract title or word count from '{name}'")
        title = match.group(1).strip()
        wordcount = 0
        if match.group(3):
            wordcount = int(match.group(3))
        return title, wordcount
