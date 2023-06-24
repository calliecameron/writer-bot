import unittest.mock
from typing import Any

import discord
import discord.ext.test as dpytest
import pytest
import pytest_asyncio
from aioresponses import aioresponses
from discord.ext import commands
from discord.ext.test import backend, factories
from pyfakefs import fake_filesystem  # pylint: disable=no-name-in-module

from writer_bot.stories import Attachment, Link, StoryFile, StoryThread

# pylint: disable=protected-access,unused-argument,redefined-outer-name


@pytest_asyncio.fixture
async def bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    b = commands.Bot(command_prefix="!", intents=intents)
    await b._async_setup_hook()
    dpytest.configure(b)
    return b


class FakeStoryFile(StoryFile):
    def __init__(self, *args: Any) -> None:
        super().__init__("fake", *args)

    async def _download(self) -> bytes:
        return "foo bar baz\n".encode(encoding="utf-8")


class TestStoryFile:
    def test_description(self) -> None:
        assert (
            FakeStoryFile("foo", "text/plain", 10).description == "fake foo (text/plain, 10 bytes)"
        )
        assert (
            FakeStoryFile("foo", "text/plain", None).description
            == "fake foo (text/plain, unknown bytes)"
        )

    def test_can_wordcount(self) -> None:
        assert FakeStoryFile("foo", "text/plain", None).can_wordcount()
        assert FakeStoryFile("foo", "text/plain", 10).can_wordcount()
        assert not FakeStoryFile("foo", "text/plain", 40 * 1024 * 1024).can_wordcount()
        assert FakeStoryFile("foo", "application/pdf", None).can_wordcount()
        assert FakeStoryFile("foo", "application/pdf", 10).can_wordcount()
        assert not FakeStoryFile("foo", "application/pdf", 40 * 1024 * 1024).can_wordcount()
        assert not FakeStoryFile("foo", "bar", None).can_wordcount()

    @pytest.mark.asyncio
    async def test_raw_wordcount(self) -> None:
        with open("testdata/test.txt", mode="rb") as f:
            assert await FakeStoryFile("foo", "text/plain", 10)._raw_wordcount(f.read()) == 4

        with open("testdata/test.pdf", mode="rb") as f:
            assert await FakeStoryFile("foo", "application/pdf", 10)._raw_wordcount(f.read()) == 229

        with open("testdata/test.txt", mode="rb") as f:
            with pytest.raises(discord.DiscordException):
                await FakeStoryFile("foo", "image/jpeg", 10)._raw_wordcount(f.read())

    def test_rounded_wordcount(self) -> None:
        assert StoryFile._rounded_wordcount(10) == 100
        assert StoryFile._rounded_wordcount(120) == 100
        assert StoryFile._rounded_wordcount(160) == 200
        assert StoryFile._rounded_wordcount(1020) == 1000
        assert StoryFile._rounded_wordcount(12345) == 12000

    @pytest.mark.asyncio
    async def test_wordcount(self) -> None:
        f = FakeStoryFile("foo", "text/plain", 10)
        assert await f.wordcount() == 100

    @pytest.mark.asyncio
    async def test_from_message_none(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message("foo bar", u, c)

        assert await StoryFile.from_message(m) is None

    @pytest.mark.asyncio
    async def test_from_message_none_valid(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message(
            "foo http://example.com/test1.jpg bar http://example.com/test2.jpg baz "
            "http://example.com/test3.jpg quux",
            u,
            c,
            attachments=[
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.jpg",
                        proxy_url="http://example.com/test5.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test6.jpg",
                        size=12,
                        url="http://example.com/test6.jpg",
                        proxy_url="http://example.com/test6.jpg",
                        content_type="image/jpeg",
                    ),
                ),
            ],
        )

        with aioresponses() as mock:
            mock.head(
                "http://example.com/test1.jpg",
                status=200,
                headers={"content-type": "image/jpeg", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test2.jpg",
                status=200,
                headers={"content-type": "image/jpeg", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test3.jpg",
                status=200,
                headers={"content-type": "image/jpeg", "content-length": "10"},
            )

            assert await StoryFile.from_message(m) is None

    @pytest.mark.asyncio
    async def test_from_message_attachment(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)

        m = backend.make_message(
            "foo http://example.com/test1.jpg bar http://example.com/test2.txt baz "
            "http://example.com/test3.txt quux",
            u,
            c,
            attachments=[
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.txt",
                        proxy_url="http://example.com/test5.txt",
                        content_type="text/plain",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test6.txt",
                        size=12,
                        url="http://example.com/test6.txt",
                        proxy_url="http://example.com/test6.txt",
                        content_type="text/plain",
                    ),
                ),
            ],
        )

        with aioresponses() as mock:
            mock.head(
                "http://example.com/test1.jpg",
                status=200,
                headers={"content-type": "image/jpeg", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test2.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test3.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )

            s = await StoryFile.from_message(m)
            assert s is not None
            assert s.description == "attachment http://example.com/test5.txt (text/plain, 12 bytes)"

    @pytest.mark.asyncio
    async def test_from_message_link(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message(
            "foo http://example.com/test1.jpg bar http://example.com/test2.txt baz "
            "http://example.com/test3.txt quux",
            u,
            c,
            attachments=[
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.jpg",
                        proxy_url="http://example.com/test5.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore
                        filename="test6.jpg",
                        size=12,
                        url="http://example.com/test6.jpg",
                        proxy_url="http://example.com/test6.jpg",
                        content_type="image/jpeg",
                    ),
                ),
            ],
        )

        with aioresponses() as mock:
            mock.head(
                "http://example.com/test1.jpg",
                status=200,
                headers={"content-type": "image/jpeg", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test2.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test3.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )

            s = await StoryFile.from_message(m)
            assert s is not None
            assert s.description == "link http://example.com/test2.txt (text/plain, 10 bytes)"


class TestLink:
    @pytest.mark.asyncio
    async def test_download(self) -> None:
        with aioresponses() as m:
            m.get("http://example.com/test.txt", status=200, body="foo bar baz")
            l = Link("http://example.com/test.txt", "text/plain", None)
            data = await l._download()
            assert data.decode(encoding="utf-8").strip() == "foo bar baz"

    @pytest.mark.asyncio
    async def test_from_url(self) -> None:
        with aioresponses() as m:
            m.head(
                "http://example.com/test.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )
            l = await Link.from_url("http://example.com/test.txt")
            assert l is not None
            assert l.description == "link http://example.com/test.txt (text/plain, 10 bytes)"

        with aioresponses() as m:
            m.head(
                "http://example.com/test.txt",
                status=200,
                headers={"content-type": "image/jpeg"},
            )
            l = await Link.from_url("http://example.com/test.txt")
            assert l is None


class TestAttachment:
    @pytest.mark.asyncio
    async def test_download(self, bot: commands.Bot, fs: fake_filesystem.FakeFilesystem) -> None:
        fs.create_file("test.txt", contents="foo bar baz 2")
        a = Attachment(
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(  # type: ignore
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="text/plain",
                ),
            )
        )
        data = await a._download()
        assert data.decode(encoding="utf-8").strip() == "foo bar baz 2"

    def test_from_attachment(self) -> None:
        a = Attachment.from_attachment(
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(  # type: ignore
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="text/plain",
                ),
            )
        )
        assert a is not None
        assert a.description == "attachment http://example.com/test.txt (text/plain, 12 bytes)"

        a = Attachment.from_attachment(
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(  # type: ignore
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="image/jpeg",
                ),
            )
        )
        assert a is None


class TestStoryThread:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name,expected_name,expected_wordcount",
        [
            ("foo bar", "foo bar", 0),
            ("  foo bar [baz]  [100 words]  ", "foo bar [baz]", 100),
            ("[100 words]", "", 100),
        ],
    )
    async def test_parse_name(
        self, bot: commands.Bot, name: str, expected_name: str, expected_wordcount: int
    ) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message("foo bar", u, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u.id,
                "name": name,
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                },
            },
        )
        assert StoryThread(t)._parse_name() == (expected_name, expected_wordcount)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name,wordcount,expected,called",
        [
            ("foo bar", 0, "foo bar", False),
            ("foo bar", 10, "foo bar [10 words]", True),
            ("foo bar [10 words]", 10, "foo bar [10 words]", False),
            ("foo bar [10 words]", 100, "foo bar [100 words]", True),
            ("foo bar [10 words]", 0, "foo bar", True),
        ],
    )
    async def test_set_wordcount(
        self, bot: commands.Bot, name: str, wordcount: int, expected: str, called: bool
    ) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message("foo bar", u, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u.id,
                "name": name,
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                },
            },
        )
        with unittest.mock.patch.object(discord.Thread, "edit") as mock:
            await StoryThread(t)._set_wordcount(wordcount)
        mock.assert_has_calls([unittest.mock.call(name=expected)] if called else [])

    @pytest.mark.asyncio
    async def test_update_none(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message("foo bar", u, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                },
            },
        )

        output = ""

        async def edit(_: Any, name: str) -> None:
            nonlocal output
            output = name

        with unittest.mock.patch.object(discord.Thread, "edit", edit):
            await StoryThread(t).update()

        assert output == ""

    @pytest.mark.asyncio
    async def test_update_no_starter_message(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message("foo bar", u, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                },
            },
        )
        await m.delete()

        output = ""

        async def edit(_: Any, name: str) -> None:
            nonlocal output
            output = name

        async def get_message(_: Any, *args: Any) -> Any:
            raise discord.NotFound(backend.FakeRequest(404, "404"), "404")

        with unittest.mock.patch.object(discord.Thread, "edit", edit):
            with unittest.mock.patch.object(backend.FakeHttp, "get_message", get_message):
                await StoryThread(t).update()

        assert output == ""

    @pytest.mark.asyncio
    async def test_update(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message("foo http://example.com/test.txt bar", u, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                },
            },
        )

        output = ""

        async def edit(_: Any, name: str) -> None:
            nonlocal output
            output = name

        with unittest.mock.patch.object(discord.Thread, "edit", edit):
            with aioresponses() as mock:
                mock.head(
                    "http://example.com/test.txt",
                    status=200,
                    headers={"content-type": "text/plain", "content-length": "10"},
                )
                mock.get("http://example.com/test.txt", status=200, body="foo bar baz")
                await StoryThread(t).update()

        assert output == "foo bar [100 words]"
