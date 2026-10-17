"""Command-line entry point for Mac mock mode and Pi hardware mode."""

import argparse
from collections.abc import Callable
import os
from queue import Queue
import time
from pathlib import Path
from typing import cast

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
    if name in {"play", "pet"}:
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
    print("Commands: feed, pet, light 0-100, sound 0-100, tick, quit")
    while True:
        command = input("> ").strip()
        if command in {"quit", "exit"}:
            return
        event = _event_from_command(command)
        if event is None:
            print("Unknown command")
            continue
        app.handle(event)


def _run_hardware(
    app: TamagodjiApp,
    interaction_port: str,
    room_port: str,
    once: bool,
    microphone_enabled: bool,
    api_enabled: bool,
    api_host: str,
    api_port: int,
    api_token: str | None,
    cors_origin: str,
    brain: Callable[[str, dict[str, object]], object] | None,
) -> None:
    """Run the Raspberry Pi hardware loop."""

    from .api import ApiConfig, ApiServer
    from .display.ssd1306 import SSD1306Display
    from .hardware.audio import AlsaMicrophone
    from .hardware.microbit import MicrobitSerial

    app.display = SSD1306Display()
    interaction = MicrobitSerial(interaction_port, "interaction")
    room = MicrobitSerial(room_port, "room")
    microphone = AlsaMicrophone() if microphone_enabled else None
    commands: Queue[tuple[str, object]] = Queue()
    api = ApiServer(
        app.snapshot,
        lambda event: commands.put(("event", event)),
        config=ApiConfig(
            host=api_host,
            port=api_port,
            api_token=api_token,
            cors_origin=cors_origin,
        ),
        brain=brain,
        message_sink=lambda message: commands.put(("message", message)),
    )
    if api_enabled:
        api.start()
    app.render()
    try:
        while True:
            while not commands.empty():
                command, value = commands.get_nowait()
                if command == "event":
                    app.handle(cast(Event, value))
                else:
                    app.present_message(str(value))
            app.handle_many(interaction.poll())
            app.handle_many(room.poll())
            if microphone:
                app.handle(microphone.read_event())
            app.tick()
            if once:
                return
            time.sleep(2)
    finally:
        api.stop()


def main() -> None:
    """Parse command-line options and run Tamagodji."""

    parser = argparse.ArgumentParser(description="Run the Tamagodji virtual pet")
    parser.add_argument("--mode", choices=("mock", "hardware"), default="mock")
    parser.add_argument("--once", action="store_true", help="Render one state and exit")
    parser.add_argument("--demo", action="store_true", help="Run a short mock demonstration")
    parser.add_argument("--db", default=os.getenv("TAMAGODJI_DB", ".data/pet.db"))
    parser.add_argument("--interaction-port", default=os.getenv("TAMAGODJI_INTERACTION_PORT"))
    parser.add_argument("--room-port", default=os.getenv("TAMAGODJI_ROOM_PORT"))
    parser.add_argument(
        "--api",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("TAMAGODJI_API_ENABLED", "1") != "0",
        help="Enable the local JSON API in hardware mode",
    )
    parser.add_argument("--api-host", default=os.getenv("TAMAGODJI_API_HOST", "127.0.0.1"))
    parser.add_argument("--api-port", type=int, default=int(os.getenv("TAMAGODJI_API_PORT", "8080")))
    parser.add_argument("--api-token", default=os.getenv("TAMAGODJI_API_TOKEN"))
    parser.add_argument(
        "--cors-origin",
        default=os.getenv("TAMAGODJI_CORS_ORIGIN", "*"),
        help="Allowed browser origin, such as https://pasqualesalomone.com",
    )
    parser.add_argument(
        "--microphone",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("TAMAGODJI_MICROPHONE_ENABLED", "1") != "0",
        help="Enable USB microphone input in hardware mode",
    )
    args = parser.parse_args()
    temperature_reader = None
    voice = None
    if args.mode == "hardware":
        from .hardware.temperature import read_cpu_temperature
        from .hardware.voice import EspeakVoice
        from .llm.openrouter import OpenRouterBrain

        temperature_reader = read_cpu_temperature
        voice = EspeakVoice().speak
        configured_brain = OpenRouterBrain.from_env()
        brain = configured_brain.respond if configured_brain else None
    else:
        brain = None
    store = PetStore(Path(args.db))
    pet = Pet(store.load())
    display = MockDisplay()
    app = TamagodjiApp(
        pet,
        store,
        display,
        temperature_reader=temperature_reader,
        voice=voice,
    )
    if args.mode == "mock":
        _run_mock(app, args.once, args.demo)
        return
    if not args.interaction_port or not args.room_port:
        parser.error("hardware mode requires --interaction-port and --room-port")
    _run_hardware(
        app,
        args.interaction_port,
        args.room_port,
        args.once,
        args.microphone,
        args.api,
        args.api_host,
        args.api_port,
        args.api_token,
        args.cors_origin,
        brain,
    )


if __name__ == "__main__":
    main()
