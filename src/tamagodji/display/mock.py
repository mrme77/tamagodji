"""Terminal display used during Mac development."""


class MockDisplay:
    """Print frames and retain the latest one for tests."""

    def __init__(self) -> None:
        """Create an empty mock display."""

        self.last_frame = ""

    def show(self, frame: str) -> None:
        """Render a frame in the terminal."""

        self.last_frame = frame
        print("\033[2J\033[H" + frame)

