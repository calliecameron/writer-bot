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

    async def download_to(self, _: str) -> None:
        return


class TestFileSrc:
    def test_content_type(self) -> None:
        assert FakeFileSrc("foo", "bar", 10).content_type == "bar"

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
            assert await f.wordcount_file("foo") == 10

        with unittest.mock.patch(
            "writer_bot.stories.WORDCOUNT_SCRIPT",
            str(pathlib.Path(__file__).resolve().parent.parent / "testdata" / "wordcount_error.sh"),
        ):
            with pytest.raises(discord.DiscordException):
                await f.wordcount_file("foo")

        with unittest.mock.patch(
            "writer_bot.stories.WORDCOUNT_SCRIPT",
            str(
                pathlib.Path(__file__).resolve().parent.parent / "testdata" / "wordcount_string.sh"
            ),
        ):
            with pytest.raises(discord.DiscordException):
                await f.wordcount_file("foo")

        with unittest.mock.patch(
            "writer_bot.stories.WORDCOUNT_SCRIPT",
            str(
                pathlib.Path(__file__).resolve().parent.parent
                / "testdata"
                / "wordcount_negative.sh"
            ),
        ):
            with pytest.raises(discord.DiscordException):
                await f.wordcount_file("foo")


class TestLink:
    @pytest.mark.asyncio
    async def test_download_to(self, fs: fake_filesystem.FakeFilesystem) -> None:
        with aioresponses() as m:
            m.get("http://example.com/test.txt", status=200, body="foo bar baz")
            l = Link("http://example.com/test.txt", "text/plain", None)
            await l.download_to("foo.txt")
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
        await a.download_to("foo.txt")
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
