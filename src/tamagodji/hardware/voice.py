"""Optional offline voice output for Raspberry Pi hardware mode."""

import logging
import subprocess


LOGGER = logging.getLogger(__name__)


class EspeakVoice:
    """Speak short pet messages through the system audio output."""

    def __init__(self, language: str = "en") -> None:
        """Configure the eSpeak language used for spoken messages."""

        self.language = language

    def speak(self, message: str) -> None:
        """Speak a message without stopping the pet when audio is unavailable."""

        try:
            subprocess.run(
                ["espeak-ng", "-v", self.language, message],
                check=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as error:
            LOGGER.warning("Could not speak pet message: %s", error)
