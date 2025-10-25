import contextvars
import functools
import inspect
import logging
from collections.abc import AsyncIterator, Callable, Coroutine, MutableMapping
from contextlib import asynccontextmanager
from types import TracebackType
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import discord

if TYPE_CHECKING:
    _LoggerAdapter = logging.LoggerAdapter[logging.Logger]
else:
    _LoggerAdapter = logging.LoggerAdapter

T = TypeVar("T")
P = ParamSpec("P")

_log_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "log_context",
    default="",
)


class LogContext:
    def __init__(self, context: str) -> None:
        super().__init__()
        self._context = context
        self._old_value: contextvars.Token[str] | None = None

    def __enter__(self) -> "LogContext":
        if not self._old_value:
            value = _log_context.get()
            value = value + ": " + self._context if value else self._context
            self._old_value = _log_context.set(value)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._old_value:
            _log_context.reset(self._old_value)
            self._old_value = None


class _Logger(_LoggerAdapter):
    def __init__(self, name: str) -> None:
        super().__init__(logging.getLogger(name))

    def process(
        self,
        msg: Any,  # noqa: ANN401
        kwargs: MutableMapping[str, Any],
    ) -> tuple[Any, MutableMapping[str, Any]]:
        value = _log_context.get()
        if value:
            msg = value + ": " + msg
        return super().process(msg, kwargs)


class Logger(_Logger):
    def __init__(self) -> None:
        module = inspect.getmodule(inspect.stack()[1].frame)
        if not module:
            raise ValueError("Can't get caller module")
        super().__init__(module.__name__)


def logged[**P, T](
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]:
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        log = _Logger(func.__module__)
        with LogContext(func.__qualname__):
            log.info("started")
            try:
                return await func(*args, **kwargs)
            finally:
                log.info("finished")

    return wrapper


async def respond(
    interaction: discord.Interaction[discord.Client],
    embed: discord.Embed,
) -> None:
    try:
        await interaction.response.send_message(embed=embed)
    except discord.InteractionResponded:
        m = await interaction.original_response()
        await m.edit(embed=embed)


async def success(interaction: discord.Interaction[discord.Client], msg: str) -> None:
    await respond(
        interaction,
        discord.Embed(colour=discord.Colour.green(), description=msg),
    )


async def warning(interaction: discord.Interaction[discord.Client], msg: str) -> None:
    await respond(
        interaction,
        discord.Embed(colour=discord.Colour.orange(), description=msg),
    )


async def error(interaction: discord.Interaction[discord.Client], msg: str) -> None:
    await respond(
        interaction,
        discord.Embed(colour=discord.Colour.red(), title="Error", description=msg),
    )


async def all_forum_threads(forum: discord.ForumChannel) -> list[discord.Thread]:
    out = forum.threads
    async for thread in forum.archived_threads(limit=None):
        out.append(thread)
    return out


@asynccontextmanager
async def unarchive_thread(thread: discord.Thread) -> AsyncIterator[None]:
    archived = thread.archived
    if archived:
        await thread.edit(archived=False)
    try:
        yield
    finally:
        if archived:
            await thread.edit(archived=True)
