from typing import TYPE_CHECKING, Any, MutableMapping, Optional
import contextvars
import logging
from types import TracebackType

if TYPE_CHECKING:
    _LoggerAdapter = logging.LoggerAdapter[logging.Logger]
else:
    _LoggerAdapter = logging.LoggerAdapter

_log_context: contextvars.ContextVar[str] = contextvars.ContextVar("log_context", default="")


class LogContext:
    def __init__(self, context: str) -> None:
        super().__init__()
        self._context = context
        self._old_value: Optional[contextvars.Token[str]] = None

    def __enter__(self) -> "LogContext":
        if not self._old_value:
            value = _log_context.get()
            if value:
                value = value + ": " + self._context
            else:
                value = self._context
            self._old_value = _log_context.set(value)
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._old_value:
            _log_context.reset(self._old_value)
            self._old_value = None


class Logger(_LoggerAdapter):
    def __init__(self, name: str) -> None:
        super().__init__(logging.getLogger(name))

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        value = _log_context.get()
        if value:
            msg = value + ": " + msg
        return super().process(msg, kwargs)
