"""Small renderers shared by the terminal and OLED displays."""

from .pet import PetState


def frame_for_state(state: PetState) -> str:
    """Create a compact text frame for a terminal or tiny OLED."""

    face = {
        "sleeping": "(-_-) zZ",
        "hungry": "(o_O) !",
        "happy": "(^_^) ♥",
        "sad": "(T_T) .",
        "tired": "(=_=) .",
        "content": "(^_^) .",
    }[state.mood]
    return (
        f"{face}\n"
        f"mood: {state.mood}\n"
        f"food: {100 - state.hunger:3d}%  joy: {state.happiness:3d}%\n"
        f"energy: {state.energy:3d}%  light: {state.light_level:3d}%"
    )

