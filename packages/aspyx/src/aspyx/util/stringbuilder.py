"""
Utility class for Java lovers
"""
class StringBuilder:
    """
    A StringBuilder is used to build a string by multiple append calls.
    """
    ___slots__ = ("_parts",)

    # constructor

    def __init__(self):
        self._parts = []

    # public

    def append(self, s: str) -> "StringBuilder":
        """
        append a string to the end of the string builder

        Args:
            s (str): the string

        Returns:
            StringBuilder: self
        """
        self._parts.append(str(s))

        return self

    def extend(self, iterable) -> "StringBuilder":
        for s in iterable:
            self._parts.append(str(s))

        return self

    def clear(self):
        """
        clear the content
        """
        self._parts.clear()

    # object

    def __str__(self):
        return ''.join(self._parts)
