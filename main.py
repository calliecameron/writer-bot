#!/usr/bin/env python3

import os
from typing import Any

import discord
from discord.ext import commands

import writer_bot.stories
import writer_bot.utils

_log = writer_bot.utils.Logger()


class Bot(commands.Bot):
    def __init__(self, story_forum_id: int, google_api_key: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._story_forum_id = story_forum_id
        self._google_api_key = google_api_key

    async def on_ready(self) -> None:
        await self.add_cog(
            writer_bot.stories.Stories(self, self._story_forum_id, self._google_api_key)
        )
        await self.tree.sync()
        _log.info("Connected as user: %s", self.user)


def get_token(var: str) -> str:
    file = os.getenv(var)
    if not file:
        raise ValueError("%s environment variable not set" % var)

    with open(file, encoding="utf-8") as f:
        return f.read().strip()


def main() -> None:
    token = get_token("TOKEN_FILE")
    google_api_key = get_token("GOOGLE_API_KEY_FILE")

    story_forum_id_raw = os.getenv("STORY_FORUM_ID")
    if not story_forum_id_raw:
        raise ValueError("STORY_FORUM_ID environment variable not set")
    try:
        story_forum_id = int(story_forum_id_raw)
    except ValueError as e:
        raise ValueError("story_forum_id is not an int") from e

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    client = Bot(story_forum_id, google_api_key, [], intents=intents)

    client.run(token, root_logger=True)


if __name__ == "__main__":
    main()
