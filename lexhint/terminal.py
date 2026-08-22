from __future__ import annotations


class TerminalStyle:
    """Small dependency-free ANSI style helper for human terminal output."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, value: object) -> str:
        text = str(value)
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, value: object) -> str:
        return self._wrap("1", value)

    def dim(self, value: object) -> str:
        return self._wrap("2", value)

    def green(self, value: object) -> str:
        return self._wrap("32", value)

    def yellow(self, value: object) -> str:
        return self._wrap("33", value)

    def magenta(self, value: object) -> str:
        return self._wrap("35", value)

    def cyan(self, value: object) -> str:
        return self._wrap("36", value)

    def bold_cyan(self, value: object) -> str:
        return self._wrap("1;36", value)

    def bold_magenta(self, value: object) -> str:
        return self._wrap("1;35", value)

    def dim_cyan(self, value: object) -> str:
        return self._wrap("2;36", value)
