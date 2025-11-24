import datetime
import io
import re
import urllib.parse
from abc import ABC, abstractmethod

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
        self,
        message: discord.Message,
        kind: str,
        url: str,
        content_type: str,
        size: int | None,
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
            f"message {self._message_id} {self._kind} {self._url} "
            f"({self._content_type}, {self._size if self._size else 'unknown'} bytes)"
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
        raise discord.DiscordException(
            f"can't wordcount content type {self._content_type}",
        )

    @staticmethod
    def _rounded_wordcount(wordcount: int) -> int:
        if wordcount < 100:  # noqa: PLR2004
            return 100
        if wordcount < 1000:  # noqa: PLR2004
            return round(wordcount, -2)
        return round(wordcount, -3)

    @staticmethod
    async def from_message(
        m: discord.Message,
        google_api_key: str,
    ) -> StoryFile | None:
        for a in m.attachments:
            at = Attachment.from_attachment(m, a)
            if at:
                return at

        for url in urlextract.URLExtract().find_urls(
            m.content,
            only_unique=True,
            with_schema_only=True,
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
        self,
        message: discord.Message,
        url: str,
        content_type: str,
        size: int | None,
    ) -> None:
        super().__init__(message, "link", url, content_type, size)

    async def _download(self) -> bytes:
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(self._url) as response,
            ):
                data = await response.read()
                response.raise_for_status()
                return data
        except (aiohttp.ClientError, OSError) as e:
            raise discord.DiscordException(str(e)) from e

    @staticmethod
    async def from_url(m: discord.Message, url: str) -> Link | None:
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.head(url) as response,
            ):
                l = Link(m, url, response.content_type, response.content_length)
        except aiohttp.ClientError as e:
            raise discord.DiscordException(str(e)) from e
        if l.can_wordcount():
            _log.info("can wordcount %s", l.description)
            return l
        _log.info("can't wordcount %s", l.description)
        return None


class Attachment(StoryFile):
    def __init__(
        self,
        message: discord.Message,
        attachment: discord.Attachment,
    ) -> None:
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
        m: discord.Message,
        attachment: discord.Attachment,
    ) -> Attachment | None:
        a = Attachment(m, attachment)
        if a.can_wordcount():
            _log.info("can wordcount %s", a.description)
            return a
        _log.info("can't wordcount %s", a.description)
        return None


class GoogleDoc(StoryFile):
    def __init__(
        self,
        message: discord.Message,
        doc_id: str,
        google_api_key: str,
    ) -> None:
        super().__init__(message, "google doc", doc_id, "text/plain", None)
        self._google_api_key = google_api_key

    async def _download(self) -> bytes:
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    f"https://www.googleapis.com/drive/v3/files/{self._url}/export?mimeType=text/plain&key={self._google_api_key}",
                ) as response,
            ):
                data = await response.read()
                response.raise_for_status()
                return data
        except (aiohttp.ClientError, OSError) as e:
            raise discord.DiscordException(str(e)) from e

    @staticmethod
    async def from_url(
        m: discord.Message,
        url: str,
        google_api_key: str,
    ) -> GoogleDoc | None:
        u = urllib.parse.urlparse(url)
        parts = [part for part in u.path.split("/") if part]
        if (
            u.scheme != "https"
            or u.hostname != "docs.google.com"
            or len(parts) < 3  # noqa: PLR2004
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
        with utils.LogContext(f"story thread {self._thread.id} ({self._thread.name})"):
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

    async def _find_wordcount_file(self) -> StoryFile | None:
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
        async with utils.unarchive_thread(self._thread):
            await self._thread.edit(name=title)
        _log.info(f"wordcount in title set to {wordcount}")

    def _parse_name(self) -> tuple[str, int]:
        name = self._thread.name
        match = re.fullmatch(r"(.*?)(\[([0-9]+) words\])?\s*", name)
        if not match:
            raise discord.DiscordException(
                f"failed to extract title and word count from '{name}'",
            )
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


class Profile:
    def __init__(
        self,
        user: discord.User,
        profile_forum: discord.ForumChannel,
        story_forum: discord.ForumChannel,
        bot_user: discord.ClientUser,
    ) -> None:
        super().__init__()
        self._user = user
        self._profile_forum = profile_forum
        self._story_forum = story_forum
        self._bot_user = bot_user

    async def update(self) -> None:
        with utils.LogContext(
            f"profile thread {self._user.id} ({self._user.display_name})",
        ):
            try:
                thread = await self._find_profile()
                if not thread:
                    _log.info("user has no profile")
                    return

                message = await self._find_message(thread)
                content = await self._generate_content()

                if message:
                    if content != message.content:
                        async with utils.unarchive_thread(thread):
                            await message.edit(content=content)
                        _log.info("updated content in existing message")
                    else:
                        _log.info("content in existing message is correct")
                else:
                    await thread.send(content)
                    _log.info("added content to new message")
            except discord.DiscordException as e:
                _log.error("update failed: %s", e)
                raise
            finally:
                _log.info("finished")

    async def _find_profile(self) -> discord.Thread | None:
        out = None
        for thread in await utils.all_forum_threads(self._profile_forum):
            if (thread.owner_id == self._user.id) and (
                not out or thread.created_at < out.created_at  # type: ignore[operator]
            ):
                out = thread
        return out

    async def _find_message(self, thread: discord.Thread) -> discord.Message | None:
        async for message in thread.history(limit=None, oldest_first=True):
            if message.author.id == self._bot_user.id:
                return message
        return None

    async def _generate_content(self) -> str:
        stories = [
            thread
            for thread in await utils.all_forum_threads(self._story_forum)
            if thread.owner_id == self._user.id
        ]

        def created_at(t: discord.Thread) -> datetime.datetime:
            return t.created_at or datetime.datetime(2000, 1, 1)  # noqa: DTZ001

        stories.sort(key=created_at, reverse=True)

        if not stories:
            return (
                "This author hasn't posted any stories yet. Links to the stories will "
                "appear here if they do."
            )

        out = ["Stories by this author:", ""] + [
            f"* [{story.name}]({story.jump_url})" for story in stories
        ]

        return "\n".join(out)


@app_commands.guild_only()
class Stories(commands.GroupCog, name="stories"):
    def __init__(
        self,
        bot: commands.Bot,
        story_forum_id: int,
        profile_forum_id: int,
        google_api_key: str,
    ) -> None:
        super().__init__()
        self._bot = bot
        self._bot_user: discord.ClientUser = None  # type: ignore[assignment]
        self._story_forum_id = story_forum_id
        self._profile_forum_id = profile_forum_id
        self._google_api_key = google_api_key
        self._story_forum: discord.ForumChannel = None  # type: ignore[assignment]
        self._profile_forum: discord.ForumChannel = None  # type: ignore[assignment]
        self._processing_stories: set[int] = set()
        self._processing_profiles: set[int] = set()
        self._processing_refresh = False
        self.refresh_cron.start()

    async def cog_load(self) -> None:
        bot_user = self._bot.user
        if not bot_user:
            raise discord.DiscordException("bot is not logged in")
        self._bot_user = bot_user

        story_forum = await self._bot.fetch_channel(self._story_forum_id)
        if not isinstance(story_forum, discord.ForumChannel):
            raise discord.DiscordException("story_forum_id must be a forum channel")
        self._story_forum = story_forum

        profile_forum = await self._bot.fetch_channel(self._profile_forum_id)
        if not isinstance(profile_forum, discord.ForumChannel):
            raise discord.DiscordException("profile_forum_id must be a forum channel")
        self._profile_forum = profile_forum

    @commands.Cog.listener()
    @utils.logged
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if thread.parent_id == self._story_forum.id:
            await self.process_story(thread)
        elif thread.parent_id == self._profile_forum.id:
            await self.process_profile(thread.owner_id)

    @commands.Cog.listener()
    @utils.logged
    async def on_thread_update(self, _: discord.Thread, after: discord.Thread) -> None:
        if after.parent_id == self._story_forum.id:
            await self.process_story(after)
        elif after.parent_id == self._profile_forum.id:
            await self.process_profile(after.owner_id)

    @commands.Cog.listener()
    @utils.logged
    async def on_message(self, message: discord.Message) -> None:
        if (
            isinstance(message.channel, discord.Thread)
            and message.channel.parent_id == self._story_forum_id
            and message.author.id == message.channel.owner_id
        ):
            await self.process_story(message.channel)

    @commands.Cog.listener()
    @utils.logged
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        channel = self._bot.get_channel(
            payload.channel_id,
        ) or await self._bot.fetch_channel(
            payload.channel_id,
        )
        if (
            isinstance(channel, discord.Thread)
            and channel.parent_id == self._story_forum.id
        ):
            m = payload.cached_message or await channel.fetch_message(
                payload.message_id,
            )
            if m.author.id == channel.owner_id:
                await self.process_story(channel)

    @app_commands.command(description="Refresh the wordcount for all stories.")
    @app_commands.checks.has_permissions(manage_threads=True)
    @utils.logged
    async def refresh(self, interaction: discord.Interaction[discord.Client]) -> None:
        if self._processing_refresh:
            _log.warning("refresh already running")
            await utils.warning(
                interaction,
                "A refresh is already running. Only one can run at a time.",
            )
            return
        self._processing_refresh = True

        try:
            await interaction.response.defer()
            if not await self.process_all_stories():
                await utils.error(
                    interaction,
                    "Some stories failed to refresh; see the log for details.",
                )
            else:
                await utils.success(interaction, "Finished refreshing stories.")
        finally:
            self._processing_refresh = False

    @refresh.error
    @utils.logged
    async def refresh_error(
        self,
        interaction: discord.Interaction[discord.Client],
        e: app_commands.AppCommandError,
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
            await self.process_all_stories()
        finally:
            self._processing_refresh = False

    @refresh_cron.before_loop
    async def before_refresh_cron(self) -> None:
        await self._bot.wait_until_ready()

    async def process_all_stories(self) -> bool:
        failures = 0
        for thread in await utils.all_forum_threads(self._story_forum):
            try:
                await self.process_story(thread)
            except discord.DiscordException as e:
                _log.error(str(e))
                failures += 1
        if failures > 0:
            _log.error(f"{failures} stories failed to refresh")
            return False
        return True

    async def process_story(self, thread: discord.Thread) -> None:
        if thread.id in self._processing_stories:
            return
        self._processing_stories.add(thread.id)
        try:
            await StoryThread(thread, self._google_api_key).update()
            await self.process_profile(thread.owner_id)
        finally:
            self._processing_stories.remove(thread.id)

    async def process_profile(self, user_id: int) -> None:
        if user_id in self._processing_profiles:
            return
        self._processing_profiles.add(user_id)
        try:
            user = self._bot.get_user(user_id) or await self._bot.fetch_user(user_id)
            await Profile(
                user,
                self._profile_forum,
                self._story_forum,
                self._bot_user,
            ).update()
        finally:
            self._processing_profiles.remove(user_id)
