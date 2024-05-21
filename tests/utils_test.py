import asyncio
import io
import logging
import unittest.mock
from collections.abc import AsyncIterator
from typing import Any, cast

import discord
import pytest
from discord.ext import commands
from discord.ext.test import backend

from writer_bot import utils


def test_log_context() -> None:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    name = "test_log_context"
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    logger = utils._Logger(name)  # noqa: SLF001

    # The context is task-local, so interleaved log entries from different tasks should have their
    # own context.

    async def test1() -> None:
        logger.info("foo")
        with utils.LogContext("context1"):
            logger.info("bar")
            await asyncio.sleep(0.1)
            with utils.LogContext("context2"):
                logger.info("baz")
            logger.info("quux")
        logger.info("yay")

    async def test2() -> None:
        logger.info("test2")
        with utils.LogContext("context3"):
            logger.info("test3")

    tasks = set()

    async def test_all() -> None:
        tasks.add(asyncio.create_task(test1()))
        tasks.add(asyncio.create_task(test2()))
        await asyncio.wait(tasks)

    asyncio.run(test_all())

    assert (
        output.getvalue()
        == """foo
context1: bar
test2
context3: test3
context1: context2: baz
context1: quux
yay
"""
    )


@pytest.mark.asyncio
async def test_logged() -> None:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    logger = utils.Logger()

    @utils.logged
    async def test1() -> None:
        logger.info("foo")

    await test1()

    assert (
        output.getvalue()
        == """test_logged.<locals>.test1: started
test_logged.<locals>.test1: foo
test_logged.<locals>.test1: finished
"""
    )


@pytest.mark.asyncio
async def test_all_forum_threads(bot: commands.Bot) -> None:  # noqa: ARG001
    u = backend.make_user("user", 1)
    g = backend.make_guild("test")
    c = backend.make_text_channel("channel", g)
    m1 = backend.make_message("foo bar", u, c)
    t1 = discord.Thread(
        guild=g,
        state=backend.get_state(),
        data={
            "id": m1.id,
            "guild_id": g.id,
            "parent_id": c.id,
            "owner_id": u.id,
            "name": "T1",
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
    m2 = backend.make_message("foo bar", u, c)
    t2 = discord.Thread(
        guild=g,
        state=backend.get_state(),
        data={
            "id": m2.id,
            "guild_id": g.id,
            "parent_id": c.id,
            "owner_id": u.id,
            "name": "T1",
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
    m3 = backend.make_message("foo bar", u, c)
    t3 = discord.Thread(
        guild=g,
        state=backend.get_state(),
        data={
            "id": m3.id,
            "guild_id": g.id,
            "parent_id": c.id,
            "owner_id": u.id,
            "name": "T1",
            "type": 11,
            "message_count": 1,
            "member_count": 1,
            "rate_limit_per_user": 1,
            "thread_metadata": {
                "archived": True,
                "auto_archive_duration": 60,
                "archive_timestamp": "2023-12-12",
            },
        },
    )
    m4 = backend.make_message("foo bar", u, c)
    t4 = discord.Thread(
        guild=g,
        state=backend.get_state(),
        data={
            "id": m4.id,
            "guild_id": g.id,
            "parent_id": c.id,
            "owner_id": u.id,
            "name": "T1",
            "type": 11,
            "message_count": 1,
            "member_count": 1,
            "rate_limit_per_user": 1,
            "thread_metadata": {
                "archived": True,
                "auto_archive_duration": 60,
                "archive_timestamp": "2023-12-12",
            },
        },
    )

    @property  # type: ignore[misc]
    def threads(_: Any) -> list[discord.Thread]:  # noqa: ANN401
        return [t1, t2]

    async def archived_threads(
        _: Any,  # noqa: ANN401
        *args: Any,  # noqa: ANN401, ARG001
        **kwargs: Any,  # noqa: ANN401, ARG001
    ) -> AsyncIterator[discord.Thread]:
        for t in (t3, t4):
            yield t

    with (
        unittest.mock.patch.object(discord.TextChannel, "threads", threads),
        unittest.mock.patch.object(discord.TextChannel, "archived_threads", archived_threads),
    ):
        assert [t.id for t in await utils.all_forum_threads(cast(discord.ForumChannel, c))] == [
            m1.id,
            m2.id,
            m3.id,
            m4.id,
        ]
