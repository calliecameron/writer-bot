import datetime
import io
import re
import urllib.parse
from abc import ABC, abstractmethod
from typing import Optional

import aiohttp
import discord
import pdfminer.high_level
import pdfminer.psparser
import urlextract
from discord import app_commands
from discord.ext import commands, tasks

from writer_bot import utils

WORDCOUNT_CONTENT_TYPES = frozenset(["text/plain", "application/pdf"])
WORDCOUNT_MAX_SIZE = 30 * 1024 * 1024

_log = utils.Logger()


class StoryFile(ABC):
    def __init__(
        self, message: discord.Message, kind: str, url: str, content_type: str, size: Optional[int]
    ) -> None:
        super().__init__()
        self._message_id = message.id
        self._kind = kind
        self._url = url
        self._content_type = content_type
        self._size = size

    @property
    def description(self) -> str:
        return (
            f"message {self._message_id} {self._kind} {self._url} ({self._content_type}, "
            f"{self._size if self._size else 'unknown'} bytes)"
        )

    def can_wordcount(self) -> bool:
        return self._content_type in WORDCOUNT_CONTENT_TYPES and (
            not self._size or self._size <= WORDCOUNT_MAX_SIZE
        )

    async def wordcount(self) -> int:
        try:
            _log.info("downloading %s...", self.description)
            data = await self._download()
            _log.info("download finished")
            return self._rounded_wordcount(await self._raw_wordcount(data))
        except discord.DiscordException as e:
            _log.error("wordcount failed: %s", e)
            raise

    @abstractmethod
    async def _download(self) -> bytes:
        raise NotImplementedError

    async def _raw_wordcount(self, data: bytes) -> int:
        if self._content_type == "text/plain":
            return len(data.decode(encoding="utf-8").split())
        if self._content_type == "application/pdf":
            try:
                with io.BytesIO(data) as b:
                    return len(pdfminer.high_level.extract_text(b).split())
            except pdfminer.psparser.PSException as e:
                raise discord.DiscordException(str(e)) from e
        raise discord.DiscordException(f"can't wordcount content type {self._content_type}")

    @staticmethod
    def _rounded_wordcount(wordcount: int) -> int:
        if wordcount < 100:
            return 100
        if wordcount < 1000:
            return round(wordcount, -2)
        return round(wordcount, -3)

    @staticmethod
    async def from_message(m: discord.Message, google_api_key: str) -> "Optional[StoryFile]":
        for a in m.attachments:
            at = Attachment.from_attachment(m, a)
            if at:
                return at

        for url in urlextract.URLExtract().find_urls(
            m.content, only_unique=True, with_schema_only=True
        ):
            d = await GoogleDoc.from_url(m, url, google_api_key)
            if d:
                return d

            l = await Link.from_url(m, url)
            if l:
                return l

        return None


class Link(StoryFile):
    def __init__(
        self, message: discord.Message, url: str, content_type: str, size: Optional[int]
    ) -> None:
        super().__init__(message, "link", url, content_type, size)

    async def _download(self) -> bytes:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._url) as response:
                    data = await response.read()
                    response.raise_for_status()
                    return data
        except (aiohttp.ClientError, OSError) as e:
            raise discord.DiscordException(str(e)) from e

    @staticmethod
    async def from_url(m: discord.Message, url: str) -> "Optional[Link]":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    l = Link(m, url, response.content_type, response.content_length)
        except aiohttp.ClientError as e:
            raise discord.DiscordException(str(e)) from e
        if l.can_wordcount():
            _log.info("can wordcount %s", l.description)
            return l
        _log.info("can't wordcount %s", l.description)
        return None


class Attachment(StoryFile):
    def __init__(self, message: discord.Message, attachment: discord.Attachment) -> None:
        content_type = ""
        if attachment.content_type:
            content_type = attachment.content_type.split(";")[0].strip()
        super().__init__(
            message,
            "attachment",
            attachment.url,
            content_type,
            attachment.size,
        )
        self._attachment = attachment

    async def _download(self) -> bytes:
        return await self._attachment.read()

    @staticmethod
    def from_attachment(
        m: discord.Message, attachment: discord.Attachment
    ) -> "Optional[Attachment]":
        a = Attachment(m, attachment)
        if a.can_wordcount():
            _log.info("can wordcount %s", a.description)
            return a
        _log.info("can't wordcount %s", a.description)
        return None


class GoogleDoc(StoryFile):
    def __init__(self, message: discord.Message, doc_id: str, google_api_key: str) -> None:
        super().__init__(message, "google doc", doc_id, "text/plain", None)
        self._google_api_key = google_api_key

    async def _download(self) -> bytes:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.googleapis.com/drive/v3/files/%s/export?mimeType=text/plain&key=%s"
                    % (self._url, self._google_api_key)
                ) as response:
                    data = await response.read()
                    response.raise_for_status()
                    return data
        except (aiohttp.ClientError, OSError) as e:
            raise discord.DiscordException(str(e)) from e

    @staticmethod
    async def from_url(m: discord.Message, url: str, google_api_key: str) -> "Optional[GoogleDoc]":
        u = urllib.parse.urlparse(url)
        parts = [part for part in u.path.split("/") if part]
        if (
            u.scheme != "https"
            or u.hostname != "docs.google.com"
            or len(parts) < 3
            or parts[0] != "document"
            or parts[1] != "d"
        ):
            return None
        d = GoogleDoc(m, parts[2], google_api_key)
        if d.can_wordcount():
            _log.info("can wordcount %s", d.description)
            return d
        _log.info("can't wordcount %s", d.description)
        return None


class StoryThread:
    def __init__(self, thread: discord.Thread, google_api_key: str) -> None:
        super().__init__()
        self._thread = thread
        self._google_api_key = google_api_key

    async def update(self) -> None:
        with utils.LogContext(f"thread {self._thread.id} ({self._thread.name})"):
            _log.info("updating...")
            try:
                story = await self._find_wordcount_file()
                if not story:
                    _log.info("no wordcountable files")
                    return

                await self._set_wordcount(await story.wordcount())
            except discord.DiscordException as e:
                _log.error("update failed: %s", e)
                raise
            finally:
                _log.info("finished")

    async def _find_wordcount_file(self) -> Optional[StoryFile]:
        async for m in self._thread.history(oldest_first=True):
            if m.author.id == self._thread.owner_id:
                story = await StoryFile.from_message(m, self._google_api_key)
                if story:
                    return story
        return None

    async def _set_wordcount(self, wordcount: int) -> None:
        title, existing_wordcount = self._parse_name()
        if wordcount == existing_wordcount:
            _log.info(f"existing wordcount in title ({wordcount}) is correct")
            return
        if wordcount > 0:
            title = f"{title} [{wordcount} words]"
        await self._thread.edit(name=title)
        _log.info(f"wordcount in title set to {wordcount}")

    def _parse_name(self) -> tuple[str, int]:
        name = self._thread.name
        match = re.fullmatch(r"(.*?)(\[([0-9]+) words\])?\s*", name)
        if not match:
            raise discord.DiscordException(f"failed to extract title and word count from '{name}'")
        title = ""
        if match.group(1):
            title = match.group(1).strip()
        wordcount = 0
        if match.group(3):
            try:
                wordcount = int(match.group(3))
            except ValueError as e:
                raise discord.DiscordException(str(e)) from e
        return title, wordcount


@app_commands.guild_only()
class Stories(commands.GroupCog, name="stories"):
    def __init__(self, bot: commands.Bot, story_forum_id: int, google_api_key: str) -> None:
        super().__init__()
        self._bot = bot
        self._story_forum_id = story_forum_id
        self._google_api_key = google_api_key
        self._story_forum: discord.ForumChannel = None  # type: ignore
        self._processing_threads: set[int] = set()
        self._processing_refresh = False
        self.refresh_cron.start()  # pylint: disable=no-member

    async def cog_load(self) -> None:
        story_forum = await self._bot.fetch_channel(self._story_forum_id)
        if not isinstance(story_forum, discord.ForumChannel):
            raise discord.DiscordException("story_forum_id must be a forum channel")
        self._story_forum = story_forum

    @commands.Cog.listener()
    @utils.logged
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if thread.parent_id == self._story_forum.id:
            await self.process_thread(thread)

    @commands.Cog.listener()
    @utils.logged
    async def on_thread_update(self, _: discord.Thread, after: discord.Thread) -> None:
        if after.parent_id == self._story_forum.id:
            await self.process_thread(after)

    @commands.Cog.listener()
    @utils.logged
    async def on_message(self, message: discord.Message) -> None:
        if (
            isinstance(message.channel, discord.Thread)
            and message.channel.parent_id == self._story_forum_id
            and message.author.id == message.channel.owner_id
        ):
            await self.process_thread(message.channel)

    @commands.Cog.listener()
    @utils.logged
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        channel = self._bot.get_channel(payload.channel_id) or await self._bot.fetch_channel(
            payload.channel_id
        )
        if isinstance(channel, discord.Thread) and channel.parent_id == self._story_forum.id:
            m = payload.cached_message or await channel.fetch_message(payload.message_id)
            if m.author.id == channel.owner_id:
                await self.process_thread(channel)

    @app_commands.command(description="Refresh the wordcount for all stories.")  # type: ignore
    @app_commands.checks.has_permissions(manage_threads=True)
    @utils.logged
    async def refresh(self, interaction: discord.Interaction) -> None:
        if self._processing_refresh:
            _log.warning("refresh already running")
            await utils.warning(
                interaction, "A refresh is already running. Only one can run at a time."
            )
            return
        self._processing_refresh = True

        try:
            await interaction.response.defer()
            await self.process_all_threads()
            await utils.success(interaction, "Finished refreshing stories.")
        finally:
            self._processing_refresh = False

    @refresh.error
    @utils.logged
    async def refresh_error(
        self, interaction: discord.Interaction, e: app_commands.AppCommandError
    ) -> None:
        _log.error(str(e))
        await utils.error(interaction, str(e))

    @tasks.loop(time=[datetime.time(hour=0)])
    @utils.logged
    async def refresh_cron(self) -> None:
        if self._processing_refresh:
            _log.warning("refresh already running")
            return
        self._processing_refresh = True

        try:
            await self.process_all_threads()
        finally:
            self._processing_refresh = False

    @refresh_cron.before_loop
    async def before_refresh_cron(self) -> None:
        await self._bot.wait_until_ready()

    async def process_all_threads(self) -> None:
        for thread in self._story_forum.threads:
            await self.process_thread(thread)

    async def process_thread(self, thread: discord.Thread) -> None:
        if thread.id in self._processing_threads:
            return
        self._processing_threads.add(thread.id)
        try:
            await StoryThread(thread, self._google_api_key).update()
        finally:
            self._processing_threads.remove(thread.id)
