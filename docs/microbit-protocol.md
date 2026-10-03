# Micro:bit USB protocol

Each micro:bit sends one uppercase, newline-terminated message over USB serial at
115200 baud. The Raspberry Pi runs two serial readers: one for interaction and one
for room sensing.

Interaction micro:bit messages:

```text
FEED
PLAY
```

Room micro:bit messages:

```text
LIGHT:0-100
```

The protocol is intentionally small so it can be implemented in MakeCode or
MicroPython. The Pi also accepts `SOUND:0-100` for future microphone or micro:bit
experiments.

