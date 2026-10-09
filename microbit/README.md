# Micro:bit programs

These two MicroPython programs are designed for the two micro:bits connected to
the Raspberry Pi by USB.

## Which file goes where?

| Micro:bit | File | Purpose |
|---|---|---|
| Interaction controller | `interaction.py` | A = feed, B = pet, shake = pet |
| Room sensor | `room_sensor.py` | Measures room light using the LED matrix |

## Flashing

1. Open the official micro:bit Python editor in a browser.
2. Connect one micro:bit by USB.
3. Open the matching `.py` file from this directory.
4. Send or flash the program to the micro:bit.
5. Repeat with the other file and micro:bit.

Keep the room sensor's LED matrix facing the room. The micro:bit measures a native
0-255 value and converts it to the Pi protocol's 0-100 range before sending it.

## Messages sent to the Pi

The interaction controller sends:

```text
FEED
PLAY
```

The room sensor sends:

```text
LIGHT:0-255
```

The Pi clamps values safely to its internal 0-100 range.
