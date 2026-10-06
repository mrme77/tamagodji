"""Small renderers shared by the terminal and OLED displays."""

from textwrap import wrap

from .pet import PetState


def frame_for_state(
    state: PetState,
    message: str | None = None,
    temperature_c: float | None = None,
) -> str:
    """Create a compact text frame for a terminal or tiny OLED."""

    face = {
        "sleeping": "(-_-) zZ",
        "hungry": "(o_O) !",
        "happy": "(^_^) ♥",
        "sad": "(T_T) .",
        "tired": "(=_=) .",
        "sick": "(x_x) !",
        "content": "(^_^) .",
    }[state.mood]
    temperature_line = f"Pi: {temperature_c:.1f}C" if temperature_c is not None else None
    if message:
        lines = wrap(message, width=20) + [face, state.mood]
        if temperature_line:
            lines.append(temperature_line)
        return "\n".join(lines)
    lines = [
        face,
        f"mood: {state.mood}",
        f"full: {100 - state.hunger:3d}%  joy: {state.happiness:3d}%",
        f"energy: {state.energy:3d}%  light: {state.light_level:3d}%",
    ]
    if temperature_line:
        lines.append(temperature_line)
    return (
        "\n".join(lines)
    )
