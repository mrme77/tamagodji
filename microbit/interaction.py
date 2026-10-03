"""Tamagodji interaction controller for a micro:bit.

Flash this file to the micro:bit connected to the Raspberry Pi as the
interaction device. It sends only protocol messages over USB serial; display
feedback stays on the micro:bit's LED matrix.
"""

from microbit import (
    Image,
    accelerometer,
    button_a,
    button_b,
    display,
    running_time,
    sleep,
    uart,
)


BAUD_RATE = 115200
SHAKE_COOLDOWN_MS = 1500


def send(message):
    """Send one newline-terminated command to the Raspberry Pi."""

    uart.write(message + "\n")


def show_action(image):
    """Show brief local feedback without sending display data to the Pi."""

    display.show(image)
    sleep(350)
    display.clear()


def main():
    """Read buttons and gestures until the micro:bit is reset."""

    uart.init(baudrate=BAUD_RATE)
    display.show(Image.HAPPY)
    sleep(600)
    display.clear()
    last_shake = -SHAKE_COOLDOWN_MS

    while True:
        now = running_time()
        if button_a.was_pressed():
            send("FEED")
            show_action(Image.YES)
        if button_b.was_pressed():
            send("PLAY")
            show_action(Image.HAPPY)
        if accelerometer.was_gesture("shake") and now - last_shake >= SHAKE_COOLDOWN_MS:
            send("PLAY")
            show_action(Image.HAPPY)
            last_shake = now
        sleep(50)


main()
