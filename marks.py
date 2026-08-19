class MarkList:
    """Transient, in-memory list of timing marks. Never saved to disk."""

    def __init__(self, offset: float = 0.30):
        self.offset = offset
        self.marks: list[float] = []

    def mark(self, raw_seconds: float) -> float:
        value = round(max(0.0, raw_seconds - self.offset), 3)
        self.marks.append(value)
        return value

    def clear(self) -> None:
        self.marks.clear()

    def delete_last(self) -> None:
        if self.marks:
            self.marks.pop()
