"""Command-line entry point for Mac mock mode and Pi hardware mode."""

import argparse
import os
import time
from pathlib import Path

from .app import TamagodjiApp
from .events import Event, EventKind
from .pet import Pet
from .display.mock import MockDisplay
from .storage import PetStore


def _event_from_command(command: str) -> Event | None:
    """Parse an interactive Mac command."""

    name, _, raw_value = command.strip().lower().partition(" ")
    if name == "feed":
        return Event(EventKind.FEED, source="keyboard")
    if name == "play":
        return Event(EventKind.PLAY, source="keyboard")
    if name in {"light", "sound"}:
        try:
            value = int(raw_value)
        except ValueError:
            print(f"Usage: {name} 0-100")
            return None
        kind = EventKind.LIGHT_LEVEL if name == "light" else EventKind.SOUND_LEVEL
        return Event(kind, value=max(0, min(100, value)), source="keyboard")
    if name == "tick":
        return Event(EventKind.TICK, source="keyboard")
    return None


def _run_mock(app: TamagodjiApp, once: bool, demo: bool) -> None:
    """Run the Mac terminal simulation."""

    app.render()
    if once:
        return
    if demo:
        app.handle_many([
            Event(EventKind.FEED, source="demo"),
            Event(EventKind.PLAY, source="demo"),
            Event(EventKind.LIGHT_LEVEL, value=5, source="demo"),
            Event(EventKind.SOUND_LEVEL, value=80, source="demo"),
            Event(EventKind.LIGHT_LEVEL, value=80, source="demo"),
        ])
        return
    print("Commands: feed, play, light 0-100, sound 0-100, tick, quit")
    while True:
        command = input("> ").strip()
        if command in {"quit", "exit"}:
            return
        event = _event_from_command(command)
        if event is None:
            print("Unknown command")
            continue
        app.handle(event)


def _run_hardware(app: TamagodjiApp, interaction_port: str, room_port: str, once: bool) -> None:
    """Run the Raspberry Pi hardware loop."""

    from .display.ssd1306 import SSD1306Display
    from .hardware.audio import AlsaMicrophone
    from .hardware.microbit import MicrobitSerial

    app.display = SSD1306Display()
    interaction = MicrobitSerial(interaction_port, "interaction")
    room = MicrobitSerial(room_port, "room")
    microphone = AlsaMicrophone()
    app.render()
    while True:
        app.handle_many(interaction.poll())
        app.handle_many(room.poll())
        app.handle(microphone.read_event())
        app.tick()
        if once:
            return
        time.sleep(2)


def main() -> None:
    """Parse command-line options and run Tamagodji."""

    parser = argparse.ArgumentParser(description="Run the Tamagodji virtual pet")
    parser.add_argument("--mode", choices=("mock", "hardware"), default="mock")
    parser.add_argument("--once", action="store_true", help="Render one state and exit")
    parser.add_argument("--demo", action="store_true", help="Run a short mock demonstration")
    parser.add_argument("--db", default=os.getenv("TAMAGODJI_DB", ".data/pet.db"))
    parser.add_argument("--interaction-port", default=os.getenv("TAMAGODJI_INTERACTION_PORT"))
    parser.add_argument("--room-port", default=os.getenv("TAMAGODJI_ROOM_PORT"))
    args = parser.parse_args()
    temperature_reader = None
    if args.mode == "hardware":
        from .hardware.temperature import read_cpu_temperature

        temperature_reader = read_cpu_temperature
    store = PetStore(Path(args.db))
    pet = Pet(store.load())
    display = MockDisplay()
    app = TamagodjiApp(pet, store, display, temperature_reader=temperature_reader)
    if args.mode == "mock":
        _run_mock(app, args.once, args.demo)
        return
    if not args.interaction_port or not args.room_port:
        parser.error("hardware mode requires --interaction-port and --room-port")
    _run_hardware(app, args.interaction_port, args.room_port, args.once)


if __name__ == "__main__":
    main()
