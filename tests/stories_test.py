import unittest.mock
from collections.abc import AsyncIterator
from typing import Any, cast

import discord
import pytest
from aioresponses import aioresponses
from discord.ext import commands
from discord.ext.test import backend, factories
from pyfakefs import fake_filesystem

import writer_bot.utils
from writer_bot.stories import Attachment, GoogleDoc, Link, Profile, StoryFile, StoryThread

# ruff: noqa: SLF001, PLR2004, ARG001, ARG002, E741, ANN401


class FakeMessage:
    def __init__(self) -> None:
        super().__init__()
        self.id = 1234


class FakeStoryFile(StoryFile):
    def __init__(
        self,
        *args: Any,
    ) -> None:
        super().__init__(cast(discord.Message, FakeMessage()), "fake", *args)

    async def _download(self) -> bytes:
        return b"foo bar baz\n"


class TestStoryFile:
    def test_description(self) -> None:
        assert (
            FakeStoryFile("foo", "text/plain", 10).description
            == "message 1234 fake foo (text/plain, 10 bytes)"
        )
        assert (
            FakeStoryFile("foo", "text/plain", None).description
            == "message 1234 fake foo (text/plain, unknown bytes)"
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
        with open("testdata/test.txt", mode="rb") as f:  # noqa: ASYNC101
            assert await FakeStoryFile("foo", "text/plain", 10)._raw_wordcount(f.read()) == 4

        with open("testdata/test.pdf", mode="rb") as f:  # noqa: ASYNC101
            assert await FakeStoryFile("foo", "application/pdf", 10)._raw_wordcount(f.read()) == 229

        with (
            open("testdata/test.txt", mode="rb") as f,  # noqa: ASYNC101
            pytest.raises(discord.DiscordException),
        ):
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

        assert await StoryFile.from_message(m, "1234") is None

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
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.jpg",
                        proxy_url="http://example.com/test5.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
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

            assert await StoryFile.from_message(m, "1234") is None

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
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.txt",
                        proxy_url="http://example.com/test5.txt",
                        content_type="text/plain",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
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

            s = await StoryFile.from_message(m, "1234")
            assert s is not None
            assert (
                s.description
                == f"message {m.id} attachment http://example.com/test5.txt (text/plain, 12 bytes)"
            )

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
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.jpg",
                        proxy_url="http://example.com/test5.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
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

            s = await StoryFile.from_message(m, "1234")
            assert s is not None
            assert (
                s.description
                == f"message {m.id} link http://example.com/test2.txt (text/plain, 10 bytes)"
            )

    @pytest.mark.asyncio
    async def test_from_message_google_doc(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message(
            "foo http://example.com/test1.jpg bar http://example.com/test2.txt baz "
            "https://docs.google.com/document/d/abcd "
            "http://example.com/test3.txt quux "
            "https://docs.google.com/document/d/efgh/edit",
            u,
            c,
            attachments=[
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.jpg",
                        proxy_url="http://example.com/test5.jpg",
                        content_type="image/jpeg",
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(  # type: ignore[arg-type]
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
                headers={"content-type": "image/jpeg", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test3.txt",
                status=200,
                headers={"content-type": "image/jpeg", "content-length": "10"},
            )

            s = await StoryFile.from_message(m, "1234")
            assert s is not None
            assert s.description == f"message {m.id} google doc abcd (text/plain, unknown bytes)"


class TestLink:
    @pytest.mark.asyncio
    async def test_download(self) -> None:
        with aioresponses() as m:
            m.get("http://example.com/test.txt", status=200, body="foo bar baz")
            l = Link(
                cast(discord.Message, FakeMessage()),
                "http://example.com/test.txt",
                "text/plain",
                None,
            )
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
            l = await Link.from_url(
                cast(discord.Message, FakeMessage()),
                "http://example.com/test.txt",
            )
            assert l is not None
            assert (
                l.description
                == "message 1234 link http://example.com/test.txt (text/plain, 10 bytes)"
            )

        with aioresponses() as m:
            m.head(
                "http://example.com/test.txt",
                status=200,
                headers={"content-type": "image/jpeg"},
            )
            l = await Link.from_url(
                cast(discord.Message, FakeMessage()),
                "http://example.com/test.txt",
            )
            assert l is None


class TestAttachment:
    @pytest.mark.asyncio
    async def test_download(self, bot: commands.Bot, fs: fake_filesystem.FakeFilesystem) -> None:
        fs.create_file("test.txt", contents="foo bar baz 2")
        a = Attachment(
            cast(discord.Message, FakeMessage()),
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(  # type: ignore[arg-type]
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="text/plain",
                ),
            ),
        )
        data = await a._download()
        assert data.decode(encoding="utf-8").strip() == "foo bar baz 2"

    def test_from_attachment(self) -> None:
        a = Attachment.from_attachment(
            cast(discord.Message, FakeMessage()),
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(  # type: ignore[arg-type]
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="text/plain",
                ),
            ),
        )
        assert a is not None
        assert (
            a.description
            == "message 1234 attachment http://example.com/test.txt (text/plain, 12 bytes)"
        )

        a = Attachment.from_attachment(
            cast(discord.Message, FakeMessage()),
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(  # type: ignore[arg-type]
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="image/jpeg",
                ),
            ),
        )
        assert a is None


class TestGoogleDoc:
    @pytest.mark.asyncio
    async def test_download(self) -> None:
        with aioresponses() as m:
            m.get(
                "https://www.googleapis.com/drive/v3/files/abcd/export"
                "?mimeType=text/plain&key=1234",
                status=200,
                body="foo bar baz",
            )
            l = GoogleDoc(cast(discord.Message, FakeMessage()), "abcd", "1234")
            data = await l._download()
            assert data.decode(encoding="utf-8").strip() == "foo bar baz"

    @pytest.mark.asyncio
    async def test_from_url(self) -> None:
        d = await GoogleDoc.from_url(
            cast(discord.Message, FakeMessage()),
            "https://docs.google.com/document/d/abcd",
            "1234",
        )
        assert d is not None
        assert d.description == "message 1234 google doc abcd (text/plain, unknown bytes)"

        d = await GoogleDoc.from_url(
            cast(discord.Message, FakeMessage()),
            "https://docs.google.com/document/d/abcd/edit?foo=bar",
            "1234",
        )
        assert d is not None
        assert d.description == "message 1234 google doc abcd (text/plain, unknown bytes)"

        d = await GoogleDoc.from_url(
            cast(discord.Message, FakeMessage()),
            "http://example.com/test.txt",
            "1234",
        )
        assert d is None


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
        self,
        bot: commands.Bot,
        name: str,
        expected_name: str,
        expected_wordcount: int,
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
        assert StoryThread(t, "1234")._parse_name() == (expected_name, expected_wordcount)

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
        self,
        bot: commands.Bot,
        name: str,
        wordcount: int,
        expected: str,
        called: bool,
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
            await StoryThread(t, "1234")._set_wordcount(wordcount)
        mock.assert_has_calls([unittest.mock.call(name=expected)] if called else [])

    @pytest.mark.asyncio
    async def test_find_wordcount_file_none(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u1, c)
        m2 = backend.make_message("http://example.com/test,txt", u2, c)
        m3 = backend.make_message("blah yay", u1, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m1, m2, m3):
                yield m

        with unittest.mock.patch.object(discord.Thread, "history", history):
            f = await StoryThread(t, "1234")._find_wordcount_file()

        assert f is None

    @pytest.mark.asyncio
    async def test_find_wordcount_file_first_message(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar http://example.com/test1.txt", u1, c)
        m2 = backend.make_message("baz quux", u2, c)
        m3 = backend.make_message("blah yay http://example.com/test2.txt", u1, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m1, m2, m3):
                yield m

        with unittest.mock.patch.object(discord.Thread, "history", history), aioresponses() as mock:
            mock.head(
                "http://example.com/test1.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test2.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "12"},
            )
            f = await StoryThread(t, "1234")._find_wordcount_file()

        assert f is not None
        assert (
            f.description
            == f"message {m1.id} link http://example.com/test1.txt (text/plain, 10 bytes)"
        )

    @pytest.mark.asyncio
    async def test_find_wordcount_file_last_message(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar http://example.com/test1.jpg", u1, c)
        m2 = backend.make_message("baz quux", u2, c)
        m3 = backend.make_message("blah yay http://example.com/test2.txt", u1, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m1, m2, m3):
                yield m

        with unittest.mock.patch.object(discord.Thread, "history", history), aioresponses() as mock:
            mock.head(
                "http://example.com/test1.jpg",
                status=200,
                headers={"content-type": "image/jpeg", "content-length": "10"},
            )
            mock.head(
                "http://example.com/test2.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "12"},
            )
            f = await StoryThread(t, "1234")._find_wordcount_file()

        assert f is not None
        assert (
            f.description
            == f"message {m3.id} link http://example.com/test2.txt (text/plain, 12 bytes)"
        )

    @pytest.mark.asyncio
    async def test_update_none(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u1, c)
        m2 = backend.make_message("baz quux http://example.com/test2.txt", u2, c)
        m3 = backend.make_message("blah yay", u1, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m1, m2, m3):
                yield m

        with (
            unittest.mock.patch.object(discord.Thread, "edit", edit),
            unittest.mock.patch.object(discord.Thread, "history", history),
        ):
            await StoryThread(t, "1234").update()

        assert output == ""

    @pytest.mark.asyncio
    async def test_update_first_message(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo http://example.com/test.txt bar", u1, c)
        m2 = backend.make_message("baz quux http://example.com/test2.txt", u2, c)
        m3 = backend.make_message("blah yay http://example.com/test3.txt", u1, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m1, m2, m3):
                yield m

        with (
            unittest.mock.patch.object(discord.Thread, "edit", edit),
            unittest.mock.patch.object(discord.Thread, "history", history),
            aioresponses() as mock,
        ):
            mock.head(
                "http://example.com/test.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )
            mock.get("http://example.com/test.txt", status=200, body="foo bar baz")
            await StoryThread(t, "1234").update()

        assert output == "foo bar [100 words]"

    @pytest.mark.asyncio
    async def test_update_last_message(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u1, c)
        m2 = backend.make_message("baz quux http://example.com/test2.txt", u2, c)
        m3 = backend.make_message("blah yay http://example.com/test3.txt", u1, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m1, m2, m3):
                yield m

        with (
            unittest.mock.patch.object(discord.Thread, "edit", edit),
            unittest.mock.patch.object(discord.Thread, "history", history),
            aioresponses() as mock,
        ):
            mock.head(
                "http://example.com/test3.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )
            mock.get("http://example.com/test3.txt", status=200, body="foo bar baz")
            await StoryThread(t, "1234").update()

        assert output == "foo bar [100 words]"

    @pytest.mark.asyncio
    async def test_update_no_starter_message(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u1, c)
        m2 = backend.make_message("baz quux http://example.com/test2.txt", u2, c)
        m3 = backend.make_message("blah yay http://example.com/test3.txt", u1, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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
        await m1.delete()

        output = ""

        async def edit(_: Any, name: str) -> None:
            nonlocal output
            output = name

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m2, m3):
                yield m

        with (
            unittest.mock.patch.object(discord.Thread, "edit", edit),
            unittest.mock.patch.object(discord.Thread, "history", history),
            aioresponses() as mock,
        ):
            mock.head(
                "http://example.com/test3.txt",
                status=200,
                headers={"content-type": "text/plain", "content-length": "10"},
            )
            mock.get("http://example.com/test3.txt", status=200, body="foo bar baz")
            await StoryThread(t, "1234").update()

        assert output == "foo bar [100 words]"


class TestProfile:
    @pytest.mark.asyncio
    async def test_find_profile_existing(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u1, c)
        m2 = backend.make_message("baz quux", u2, c)
        m3 = backend.make_message("blah yay", u1, c)
        t1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )
        t2 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m2.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u2.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-10",
                },
            },
        )
        t3 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m3.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-11",
                },
            },
        )

        async def all_forum_threads(*args: Any, **kwargs: Any) -> list[discord.Thread]:
            return [t1, t2, t3]

        with unittest.mock.patch.object(writer_bot.utils, "all_forum_threads", all_forum_threads):
            t = await Profile(
                u1,
                cast(discord.ForumChannel, c),
                cast(discord.ForumChannel, c),
                cast(discord.ClientUser, u2),
            )._find_profile()

        assert t and t.id == m3.id

    @pytest.mark.asyncio
    async def test_find_profile_none(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u2, c)
        t1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u2.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )

        async def all_forum_threads(*args: Any, **kwargs: Any) -> list[discord.Thread]:
            return [t1]

        with unittest.mock.patch.object(writer_bot.utils, "all_forum_threads", all_forum_threads):
            t = await Profile(
                u1,
                cast(discord.ForumChannel, c),
                cast(discord.ForumChannel, c),
                cast(discord.ClientUser, u2),
            )._find_profile()

        assert t is None

    @pytest.mark.asyncio
    async def test_find_message_existing(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u1, c)
        m2 = backend.make_message("baz quux", u2, c)
        m3 = backend.make_message("blah yay", u2, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m1, m2, m3):
                yield m

        with unittest.mock.patch.object(discord.Thread, "history", history):
            m = await Profile(
                u1,
                cast(discord.ForumChannel, c),
                cast(discord.ForumChannel, c),
                cast(discord.ClientUser, u2),
            )._find_message(t)

        assert m and m.id == m2.id

    @pytest.mark.asyncio
    async def test_find_message_none(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u1, c)
        t = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
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

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (m1,):
                yield m

        with unittest.mock.patch.object(discord.Thread, "history", history):
            m = await Profile(
                u1,
                cast(discord.ForumChannel, c),
                cast(discord.ForumChannel, c),
                cast(discord.ClientUser, u2),
            )._find_message(t)

        assert m is None

    @pytest.mark.asyncio
    async def test_generate_content_existing(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u1, c)
        m2 = backend.make_message("baz quux", u1, c)
        m3 = backend.make_message("blah yay", u1, c)
        t1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )
        t2 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m2.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
                "name": "baz quux",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-10",
                },
            },
        )
        t3 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m3.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u1.id,
                "name": "blah yay",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-11",
                },
            },
        )

        async def all_forum_threads(*args: Any, **kwargs: Any) -> list[discord.Thread]:
            return [t1, t2, t3]

        with unittest.mock.patch.object(writer_bot.utils, "all_forum_threads", all_forum_threads):
            m = await Profile(
                u1,
                cast(discord.ForumChannel, c),
                cast(discord.ForumChannel, c),
                cast(discord.ClientUser, u2),
            )._generate_content()

        assert (
            m
            == f"""Stories by this author:

* [foo bar](https://discord.com/channels/{g.id}/{m1.id})
* [blah yay](https://discord.com/channels/{g.id}/{m3.id})
* [baz quux](https://discord.com/channels/{g.id}/{m2.id})"""
        )

    @pytest.mark.asyncio
    async def test_generate_content_none(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m1 = backend.make_message("foo bar", u2, c)
        t1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": m1.id,
                "guild_id": g.id,
                "parent_id": c.id,
                "owner_id": u2.id,
                "name": "foo bar",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )

        async def all_forum_threads(*args: Any, **kwargs: Any) -> list[discord.Thread]:
            return [t1]

        with unittest.mock.patch.object(writer_bot.utils, "all_forum_threads", all_forum_threads):
            m = await Profile(
                u1,
                cast(discord.ForumChannel, c),
                cast(discord.ForumChannel, c),
                cast(discord.ClientUser, u2),
            )._generate_content()

        assert m == "Stories by this author: none yet."

    @pytest.mark.asyncio
    async def test_update_no_profile(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        sc = backend.make_text_channel("stories", g)
        pc = backend.make_text_channel("profiles", g)
        sm1 = backend.make_message("story 1", u1, sc)
        st1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": sm1.id,
                "guild_id": g.id,
                "parent_id": sc.id,
                "owner_id": u1.id,
                "name": "story 1",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )

        async def all_forum_threads(forum: discord.ForumChannel) -> list[discord.Thread]:
            if forum.id == sc.id:
                return [st1]
            if forum.id == pc.id:
                return []
            raise ValueError("unknown forum")

        edited = ""

        async def edit(_: Any, content: str) -> None:
            nonlocal edited
            edited = content

        sent = ""

        async def send(_: Any, content: str) -> None:
            nonlocal sent
            sent = content

        with (
            unittest.mock.patch.object(discord.Message, "edit", edit),
            unittest.mock.patch.object(discord.Thread, "send", send),
            unittest.mock.patch.object(
                writer_bot.utils,
                "all_forum_threads",
                all_forum_threads,
            ),
        ):
            await Profile(
                u1,
                cast(discord.ForumChannel, pc),
                cast(discord.ForumChannel, sc),
                cast(discord.ClientUser, u2),
            ).update()

        assert edited == "" and sent == ""

    @pytest.mark.asyncio
    async def test_update_new_message(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        sc = backend.make_text_channel("stories", g)
        pc = backend.make_text_channel("profiles", g)
        sm1 = backend.make_message("story 1", u1, sc)
        st1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": sm1.id,
                "guild_id": g.id,
                "parent_id": sc.id,
                "owner_id": u1.id,
                "name": "story 1",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )
        pm1 = backend.make_message("profile 1", u1, pc)
        pt1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": pm1.id,
                "guild_id": g.id,
                "parent_id": pc.id,
                "owner_id": u1.id,
                "name": "profile 1",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )

        async def all_forum_threads(forum: discord.ForumChannel) -> list[discord.Thread]:
            if forum.id == sc.id:
                return [st1]
            if forum.id == pc.id:
                return [pt1]
            raise ValueError("unknown forum")

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            yield pm1

        edited = ""

        async def edit(_: Any, content: str) -> None:
            nonlocal edited
            edited = content

        sent = ""

        async def send(_: Any, content: str) -> None:
            nonlocal sent
            sent = content

        with (
            unittest.mock.patch.object(discord.Message, "edit", edit),
            unittest.mock.patch.object(discord.Thread, "send", send),
            unittest.mock.patch.object(discord.Thread, "history", history),
            unittest.mock.patch.object(
                writer_bot.utils,
                "all_forum_threads",
                all_forum_threads,
            ),
        ):
            await Profile(
                u1,
                cast(discord.ForumChannel, pc),
                cast(discord.ForumChannel, sc),
                cast(discord.ClientUser, u2),
            ).update()

        assert (
            edited == ""
            and sent
            == f"""Stories by this author:

* [story 1](https://discord.com/channels/{g.id}/{sm1.id})"""
        )

    @pytest.mark.asyncio
    async def test_update_existing_message_same(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        sc = backend.make_text_channel("stories", g)
        pc = backend.make_text_channel("profiles", g)
        sm1 = backend.make_message("story 1", u1, sc)
        st1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": sm1.id,
                "guild_id": g.id,
                "parent_id": sc.id,
                "owner_id": u1.id,
                "name": "story 1",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )
        pm1 = backend.make_message("profile 1", u1, sc)
        pt1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": pm1.id,
                "guild_id": g.id,
                "parent_id": pc.id,
                "owner_id": u1.id,
                "name": "profile 1",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )
        pm2 = discord.Message(
            channel=st1,
            state=backend.get_state(),
            data={
                "id": factories.make_id(),
                "channel_id": pt1.id,
                "author": {
                    "id": u2.id,
                    "username": u2.name,
                    "discriminator": u2.discriminator,
                    "bot": u2.bot,
                    "system": u2.system,
                    "mfa_enabled": False,
                    "locale": "en-GB",
                    "verified": False,
                    "flags": 0,
                    "premium_type": 0,
                    "public_flags": 0,
                    "avatar": None,
                    "global_name": None,
                },
                "content": f"""Stories by this author:

* [story 1](https://discord.com/channels/{g.id}/{sm1.id})""",
                "timestamp": "2023-12-12",
                "edited_timestamp": "2023-12-12",
                "tts": False,
                "mention_everyone": False,
                "mentions": [],
                "mention_roles": [],
                "attachments": [],
                "embeds": [],
                "pinned": False,
                "type": 0,
            },
        )

        async def all_forum_threads(forum: discord.ForumChannel) -> list[discord.Thread]:
            if forum.id == sc.id:
                return [st1]
            if forum.id == pc.id:
                return [pt1]
            raise ValueError("unknown forum")

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (pm1, pm2):
                yield m

        edited = ""

        async def edit(_: Any, content: str) -> None:
            nonlocal edited
            edited = content

        sent = ""

        async def send(_: Any, content: str) -> None:
            nonlocal sent
            sent = content

        with (
            unittest.mock.patch.object(discord.Message, "edit", edit),
            unittest.mock.patch.object(discord.Thread, "send", send),
            unittest.mock.patch.object(discord.Thread, "history", history),
            unittest.mock.patch.object(
                writer_bot.utils,
                "all_forum_threads",
                all_forum_threads,
            ),
        ):
            await Profile(
                u1,
                cast(discord.ForumChannel, pc),
                cast(discord.ForumChannel, sc),
                cast(discord.ClientUser, u2),
            ).update()

        assert edited == "" and sent == ""

    @pytest.mark.asyncio
    async def test_update_existing_message_different(self, bot: commands.Bot) -> None:
        u1 = backend.make_user("user1", 1)
        u2 = backend.make_user("user2", 1)
        g = backend.make_guild("test")
        sc = backend.make_text_channel("stories", g)
        pc = backend.make_text_channel("profiles", g)
        sm1 = backend.make_message("story 1", u1, sc)
        st1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": sm1.id,
                "guild_id": g.id,
                "parent_id": sc.id,
                "owner_id": u1.id,
                "name": "story 1",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )
        pm1 = backend.make_message("profile 1", u1, sc)
        pt1 = discord.Thread(
            guild=g,
            state=backend.get_state(),
            data={
                "id": pm1.id,
                "guild_id": g.id,
                "parent_id": pc.id,
                "owner_id": u1.id,
                "name": "profile 1",
                "type": 11,
                "message_count": 1,
                "member_count": 1,
                "rate_limit_per_user": 1,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2023-12-12",
                    "create_timestamp": "2023-12-12",
                },
            },
        )
        pm2 = discord.Message(
            channel=st1,
            state=backend.get_state(),
            data={
                "id": factories.make_id(),
                "channel_id": pt1.id,
                "author": {
                    "id": u2.id,
                    "username": u2.name,
                    "discriminator": u2.discriminator,
                    "bot": u2.bot,
                    "system": u2.system,
                    "mfa_enabled": False,
                    "locale": "en-GB",
                    "verified": False,
                    "flags": 0,
                    "premium_type": 0,
                    "public_flags": 0,
                    "avatar": None,
                    "global_name": None,
                },
                "content": "foo",
                "timestamp": "2023-12-12",
                "edited_timestamp": "2023-12-12",
                "tts": False,
                "mention_everyone": False,
                "mentions": [],
                "mention_roles": [],
                "attachments": [],
                "embeds": [],
                "pinned": False,
                "type": 0,
            },
        )

        async def all_forum_threads(forum: discord.ForumChannel) -> list[discord.Thread]:
            if forum.id == sc.id:
                return [st1]
            if forum.id == pc.id:
                return [pt1]
            raise ValueError("unknown forum")

        async def history(_: Any, *args: Any, **kwargs: Any) -> AsyncIterator[discord.Message]:
            for m in (pm1, pm2):
                yield m

        edited = ""

        async def edit(_: Any, content: str) -> None:
            nonlocal edited
            edited = content

        sent = ""

        async def send(_: Any, content: str) -> None:
            nonlocal sent
            sent = content

        with (
            unittest.mock.patch.object(discord.Message, "edit", edit),
            unittest.mock.patch.object(discord.Thread, "send", send),
            unittest.mock.patch.object(discord.Thread, "history", history),
            unittest.mock.patch.object(
                writer_bot.utils,
                "all_forum_threads",
                all_forum_threads,
            ),
        ):
            await Profile(
                u1,
                cast(discord.ForumChannel, pc),
                cast(discord.ForumChannel, sc),
                cast(discord.ClientUser, u2),
            ).update()

        assert (
            edited
            == f"""Stories by this author:

* [story 1](https://discord.com/channels/{g.id}/{sm1.id})"""
            and sent == ""
        )
