#!/usr/bin/env python3

import os
from typing import Any

import discord
from discord.ext import commands

import writer_bot.stories
import writer_bot.utils

_log = writer_bot.utils.Logger()


class Bot(commands.Bot):
    def __init__(
        self,
        story_forum_id: int,
        profile_forum_id: int,
        google_api_key: str,
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        super().__init__(*args, **kwargs)
        self._story_forum_id = story_forum_id
        self._profile_forum_id = profile_forum_id
        self._google_api_key = google_api_key

    async def on_ready(self) -> None:
        await self.add_cog(
            writer_bot.stories.Stories(
                self,
                self._story_forum_id,
                self._profile_forum_id,
                self._google_api_key,
            ),
        )
        await self.tree.sync()
        _log.info("Connected as user: %s", self.user)


def get_token(var: str) -> str:
    file = os.getenv(var)
    if not file:
        raise ValueError(f"{var} environment variable not set")

    with open(file, encoding="utf-8") as f:
        return f.read().strip()


def get_forum_id(name: str) -> int:
    raw = os.getenv(name)
    if not raw:
        raise ValueError(f"{name} environment variable not set")
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"{name} is not an int" % name) from e


def main() -> None:
    token = get_token("TOKEN_FILE")
    google_api_key = get_token("GOOGLE_API_KEY_FILE")
    story_forum_id = get_forum_id("STORY_FORUM_ID")
    profile_forum_id = get_forum_id("PROFILE_FORUM_ID")

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    client = Bot(story_forum_id, profile_forum_id, google_api_key, [], intents=intents)

    client.run(token, root_logger=True)


if __name__ == "__main__":
    main()
