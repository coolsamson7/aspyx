"""
Utility class for Java lovers
"""
class StringBuilder:
    ___slots__ = ("_parts",)

    # constructor

    def __init__(self):
        self._parts = []

    # public

    def append(self, s: str) -> "StringBuilder":
        self._parts.append(str(s))

        return self

    def extend(self, iterable) -> "StringBuilder":
        for s in iterable:
            self._parts.append(str(s))

        return self

    def clear(self):
        self._parts.clear()

    # object

    def __str__(self):
        return ''.join(self._parts)
