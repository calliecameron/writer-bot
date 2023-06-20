#!/usr/bin/env python3

import argparse
import logging
from typing import Any

import discord
from discord.ext import commands

import writer_bot.stories


class Bot(commands.Bot):
    def __init__(self, story_forum_id: int, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._story_forum_id = story_forum_id

    async def on_ready(self) -> None:
        await self.add_cog(writer_bot.stories.Stories(self, self._story_forum_id))
        logging.getLogger(__name__).info("Connected as user: %s", self.user)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("token_file")
    parser.add_argument("story_forum_id", type=int)
    args = parser.parse_args()

    with open(args.token_file, encoding="utf-8") as f:
        token = f.read().strip()

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    client = Bot(args.story_forum_id, "$", intents=intents)

    client.run(token, root_logger=True)


if __name__ == "__main__":
    main()
