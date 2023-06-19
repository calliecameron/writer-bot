import pathlib
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

from writer_bot.stories import Attachment, FileSrc, Link

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


class FakeFileSrc(FileSrc):
    def __init__(self, *args: Any) -> None:
        super().__init__("fake", *args)

    async def _download_to(self, filename: str) -> None:
        with open(filename, mode="w", encoding="utf-8") as f:
            f.write("foo bar baz\n")


class TestFileSrc:
    def test_description(self) -> None:
        assert FakeFileSrc("foo", "text/plain", 10).description == "fake foo (text/plain, 10 bytes)"
        assert (
            FakeFileSrc("foo", "text/plain", None).description
            == "fake foo (text/plain, unknown bytes)"
        )

    def test_can_wordcount(self) -> None:
        assert FakeFileSrc("foo", "text/plain", None).can_wordcount()
        assert FakeFileSrc("foo", "text/plain", 10).can_wordcount()
        assert not FakeFileSrc("foo", "text/plain", 40 * 1024 * 1024).can_wordcount()
        assert FakeFileSrc("foo", "application/pdf", None).can_wordcount()
        assert FakeFileSrc("foo", "application/pdf", 10).can_wordcount()
        assert not FakeFileSrc("foo", "application/pdf", 40 * 1024 * 1024).can_wordcount()
        assert not FakeFileSrc("foo", "bar", None).can_wordcount()

    @pytest.mark.asyncio
    async def test_wordcount_file(self) -> None:
        f = FakeFileSrc("foo", "bar", 10)
        with unittest.mock.patch(
            "writer_bot.stories.WORDCOUNT_SCRIPT",
            str(pathlib.Path(__file__).resolve().parent.parent / "testdata" / "wordcount_good.sh"),
        ):
            assert await f._wordcount_file("foo") == 10

        with unittest.mock.patch(
            "writer_bot.stories.WORDCOUNT_SCRIPT",
            str(pathlib.Path(__file__).resolve().parent.parent / "testdata" / "wordcount_error.sh"),
        ):
            with pytest.raises(discord.DiscordException):
                await f._wordcount_file("foo")

        with unittest.mock.patch(
            "writer_bot.stories.WORDCOUNT_SCRIPT",
            str(
                pathlib.Path(__file__).resolve().parent.parent / "testdata" / "wordcount_string.sh"
            ),
        ):
            with pytest.raises(discord.DiscordException):
                await f._wordcount_file("foo")

        with unittest.mock.patch(
            "writer_bot.stories.WORDCOUNT_SCRIPT",
            str(
                pathlib.Path(__file__).resolve().parent.parent
                / "testdata"
                / "wordcount_negative.sh"
            ),
        ):
            with pytest.raises(discord.DiscordException):
                await f._wordcount_file("foo")

    def test_rounded_wordcount(self) -> None:
        assert FileSrc._rounded_wordcount(10) == 100
        assert FileSrc._rounded_wordcount(120) == 100
        assert FileSrc._rounded_wordcount(160) == 200
        assert FileSrc._rounded_wordcount(1020) == 1000
        assert FileSrc._rounded_wordcount(12345) == 12000

    @pytest.mark.asyncio
    async def test_wordcount(self) -> None:
        f = FakeFileSrc("foo", "text/plain", 10)
        assert await f.wordcount() == 100

    @pytest.mark.asyncio
    async def test_from_message_none(self, bot: commands.Bot) -> None:
        u = backend.make_user("user", 1)
        g = backend.make_guild("test")
        c = backend.make_text_channel("channel", g)
        m = backend.make_message("foo bar", u, c)

        assert await FileSrc.from_message(m) is None

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
                    data=factories.make_attachment_dict(
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",  # type: ignore
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.jpg",
                        proxy_url="http://example.com/test5.jpg",
                        content_type="image/jpeg",  # type: ignore
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(
                        filename="test6.jpg",
                        size=12,
                        url="http://example.com/test6.jpg",
                        proxy_url="http://example.com/test6.jpg",
                        content_type="image/jpeg",  # type: ignore
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

            assert await FileSrc.from_message(m) is None

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
                    data=factories.make_attachment_dict(
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",  # type: ignore
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.txt",
                        proxy_url="http://example.com/test5.txt",
                        content_type="text/plain",  # type: ignore
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(
                        filename="test6.txt",
                        size=12,
                        url="http://example.com/test6.txt",
                        proxy_url="http://example.com/test6.txt",
                        content_type="text/plain",  # type: ignore
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

            s = await FileSrc.from_message(m)
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
                    data=factories.make_attachment_dict(
                        filename="test4.jpg",
                        size=12,
                        url="http://example.com/test4.jpg",
                        proxy_url="http://example.com/test4.jpg",
                        content_type="image/jpeg",  # type: ignore
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(
                        filename="test5.txt",
                        size=12,
                        url="http://example.com/test5.jpg",
                        proxy_url="http://example.com/test5.jpg",
                        content_type="image/jpeg",  # type: ignore
                    ),
                ),
                discord.Attachment(
                    state=backend.get_state(),
                    data=factories.make_attachment_dict(
                        filename="test6.jpg",
                        size=12,
                        url="http://example.com/test6.jpg",
                        proxy_url="http://example.com/test6.jpg",
                        content_type="image/jpeg",  # type: ignore
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

            s = await FileSrc.from_message(m)
            assert s is not None
            assert s.description == "link http://example.com/test2.txt (text/plain, 10 bytes)"


class TestLink:
    @pytest.mark.asyncio
    async def test_download_to(self, fs: fake_filesystem.FakeFilesystem) -> None:
        with aioresponses() as m:
            m.get("http://example.com/test.txt", status=200, body="foo bar baz")
            l = Link("http://example.com/test.txt", "text/plain", None)
            await l._download_to("foo.txt")
            assert pathlib.Path("foo.txt").read_text(encoding="utf-8").strip() == "foo bar baz"

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
    async def test_download_to(self, bot: commands.Bot, fs: fake_filesystem.FakeFilesystem) -> None:
        fs.create_file("test.txt", contents="foo bar baz 2")
        a = Attachment(
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="text/plain",  # type: ignore
                ),
            )
        )
        await a._download_to("foo.txt")
        assert pathlib.Path("foo.txt").read_text(encoding="utf-8").strip() == "foo bar baz 2"

    def test_from_attachment(self) -> None:
        a = Attachment.from_attachment(
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="text/plain",  # type: ignore
                ),
            )
        )
        assert a is not None
        assert a.description == "attachment http://example.com/test.txt (text/plain, 12 bytes)"

        a = Attachment.from_attachment(
            discord.Attachment(
                state=backend.get_state(),
                data=factories.make_attachment_dict(
                    filename="test.txt",
                    size=12,
                    url="http://example.com/test.txt",
                    proxy_url="http://example.com/test.txt",
                    content_type="image/jpeg",  # type: ignore
                ),
            )
        )
        assert a is None
