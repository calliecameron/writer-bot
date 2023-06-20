import asyncio
import io
import logging

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
    logger = utils.Logger(name)

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
