import discord
import discord.ext.test as dpytest
import pytest_asyncio
from discord.ext import commands

# pylint: disable=protected-access


@pytest_asyncio.fixture
async def bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    b = commands.Bot(command_prefix="!", intents=intents)
    await b._async_setup_hook()
    dpytest.configure(b)
    return b
