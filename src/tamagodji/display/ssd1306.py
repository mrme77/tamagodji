"""Optional SSD1306 I²C OLED implementation for Raspberry Pi."""


class SSD1306Display:
    """Render text frames on a 128x64 SSD1306 OLED."""

    def __init__(self, address: int = 0x3C) -> None:
        """Connect to an SSD1306 using Raspberry Pi I²C bus 1."""

        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as error:
            raise RuntimeError(
                "SSD1306 support needs requirements-pi.txt installed on the Pi"
            ) from error
        self._image = Image.new("1", (128, 64))
        self._draw = ImageDraw.Draw(self._image)
        self._font = ImageFont.load_default()
        self._device = ssd1306(i2c(port=1, address=address))

    def show(self, frame: str) -> None:
        """Draw a text frame and send it to the OLED."""

        self._draw.rectangle((0, 0, 127, 63), fill=0)
        self._draw.multiline_text((0, 0), frame, fill=1, font=self._font, spacing=2)
        self._device.display(self._image)

