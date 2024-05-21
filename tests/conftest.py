import discord
import discord.ext.test as dpytest
import pytest_asyncio
from discord.ext import commands


@pytest_asyncio.fixture
async def bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    b = commands.Bot(command_prefix="!", intents=intents)
    await b._async_setup_hook()  # noqa: SLF001
    dpytest.configure(b)
    return b
