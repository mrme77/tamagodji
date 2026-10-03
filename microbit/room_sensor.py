"""Tamagodji room-light sensor for a micro:bit.

Flash this file to the micro:bit that stays in the room. The micro:bit's LED
matrix is used as its built-in light sensor, so the matrix should face the room
and should not be covered.
"""

from microbit import display, sleep, uart


BAUD_RATE = 115200
REPORT_INTERVAL_MS = 2000
MIN_CHANGE = 3


def send_light_level(level):
    """Send a normalized light reading to the Raspberry Pi."""

    uart.write("LIGHT:" + str(level) + "\n")


def main():
    """Report light changes periodically until the micro:bit is reset."""

    uart.init(baudrate=BAUD_RATE)
    previous_level = -1
    display.show("L")
    sleep(500)
    display.clear()

    while True:
        raw_level = display.read_light_level()
        level = (raw_level * 100) // 255
        if previous_level < 0 or abs(level - previous_level) >= MIN_CHANGE:
            send_light_level(level)
            previous_level = level
        sleep(REPORT_INTERVAL_MS)


main()
