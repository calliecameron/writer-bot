from typing import Optional, Tuple, Union
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


WORDCOUNT_CONTENT_TYPES = frozenset(["text/plain", "application/pdf"])


class Logger:
    def __init__(self, thread: discord.Thread) -> None:
        super().__init__()
        self._thread = thread

    def log(self, msg: str) -> None:
        print(f"Thread {self._thread.id} ({self._thread.name}): {msg}")


class Story:
    def __init__(
        self,
        log: Logger,
        wordcount_script: str,
        src: Union[discord.Attachment, str],
        content_type: str,
    ) -> None:
        super().__init__()
        self._log = log
        self._wordcount_script = wordcount_script
        self._src = src
        self._content_type = content_type

    async def wordcount(self) -> int:
        filename = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as f:
                filename = f.name

            await self._download(filename)
            return await self._wordcount(filename)
        except Exception as e:
            self._log.log(f"wordcount failed: {e}")
            raise
        finally:
            if filename:
                os.remove(filename)
                self._log.log(f"deleted {filename}")

    async def _download(self, filename: str) -> None:
        if isinstance(self._src, discord.Attachment):
            self._log.log(
                f"downloading attachment {self._src.url} ({self._src.size} bytes) to {filename}..."
            )
            await self._src.save(pathlib.PurePath(filename))
            self._log.log("download finished")
        elif isinstance(self._src, str):
            self._log.log(f"downloading link {self._src} to {filename}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(self._src) as response:
                    data = await response.read()
            with open(filename, mode="wb") as f:
                f.write(data)
            self._log.log("download finished")
        else:
            raise ValueError(f"unknown src type {type(self._src)}")

    async def _wordcount(self, filename: str) -> int:
        p = await asyncio.create_subprocess_exec(
            self._wordcount_script,
            filename,
            self._content_type,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await p.communicate()

        if p.returncode != 0:
            raise ValueError(f"retcode {p.returncode}, stderr: {stderr.decode('utf-8').strip()}")

        wordcount = int(stdout.decode("utf-8").strip())
        if wordcount < 0:
            raise ValueError(f"wordcount must be positive, got {wordcount}")
        self._log.log(f"wordcount {wordcount}")
        return wordcount


class Stories(commands.Cog):
    def __init__(self, bot: commands.Bot, wordcount_script: str, story_forum_id: int) -> None:
        super().__init__()
        self._bot = bot
        self._wordcount_script = wordcount_script
        self._story_forum_id = story_forum_id
        self._story_forum: discord.ForumChannel = None  # type: ignore
        self._actively_processing = set()

    async def cog_load(self):
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
    async def refresh(self, ctx: commands.Context) -> None:
        await ctx.reply("Refreshing all stories in the forum...")
        for thread in self._story_forum.threads:
            await self.process_thread(thread)
        await ctx.reply("Finished refreshing stories")

    async def process_thread(self, thread: discord.Thread) -> None:
        if thread.id in self._actively_processing:
            return
        log = Logger(thread)
        self._actively_processing.add(thread.id)
        log.log("processing...")
        try:
            m = thread.starter_message or await thread.fetch_message(thread.id)

            story = await self.choose_file(log, m)
            if not story:
                log.log("no valid files")
                return

            wordcount = await story.wordcount()
            await self.set_wordcount(log, thread, wordcount)
        finally:
            self._actively_processing.remove(thread.id)
            log.log("finished")

    async def choose_file(self, log: Logger, m: discord.Message) -> Optional[Story]:
        for a in m.attachments:
            if not a.content_type:
                continue
            content_type = a.content_type.split(";")[0]
            if content_type in WORDCOUNT_CONTENT_TYPES:
                return Story(log, self._wordcount_script, a, content_type)

        for url in urlextract.URLExtract().find_urls(
            m.content, only_unique=True, with_schema_only=True
        ):
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    if response.content_type in WORDCOUNT_CONTENT_TYPES:
                        return Story(log, self._wordcount_script, url, response.content_type)

        return None

    async def set_wordcount(self, log: Logger, thread: discord.Thread, wordcount: int) -> None:
        wordcount = self.rounded_wordcount(wordcount)
        title, existing_wordcount = self.existing_wordcount(thread.name)
        if wordcount == existing_wordcount:
            log.log(f"existing rounded wordcount in title ({wordcount}) is correct")
            return
        if wordcount > 0:
            title = f"{title} [{wordcount} words]"
        await thread.edit(name=title)
        log.log(f"rounded wordcount in title set to {wordcount}")

    def rounded_wordcount(self, wordcount: int) -> int:
        if wordcount < 100:
            return 100
        if wordcount < 1000:
            return round(wordcount, -2)
        return round(wordcount, -3)

    def existing_wordcount(self, name: str) -> Tuple[str, int]:
        match = re.fullmatch(r"(.*?)(\[([0-9]+) words\])?\s*", name)
        if not match:
            raise ValueError(f"failed to extract title or word count from '{name}'")
        title = match.group(1).strip()
        wordcount = 0
        if match.group(3):
            wordcount = int(match.group(3))
        return title, wordcount
