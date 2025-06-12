class StringBuilder:
    def __init__(self):
        self._parts = []

    def append(self, s: str) -> "StringBuilder":
        self._parts.append(str(s))

        return self

    def extend(self, iterable) -> "StringBuilder":
        for s in iterable:
            self._parts.append(str(s))

        return self

    def __str__(self):
        return ''.join(self._parts)

    def clear(self):
        self._parts.clear()