"""Raspberry Pi temperature telemetry."""

from pathlib import Path


CPU_TEMPERATURE_PATH = Path("/sys/class/thermal/thermal_zone0/temp")


def read_cpu_temperature(path: Path = CPU_TEMPERATURE_PATH) -> float | None:
    """Read the Raspberry Pi CPU temperature in degrees Celsius.

    Return ``None`` when the Linux thermal sensor is unavailable or contains an
    invalid value. Temperature telemetry is optional and must not stop the pet.
    """

    try:
        raw_value = path.read_text(encoding="utf-8").strip()
        return int(raw_value) / 1000
    except (OSError, ValueError):
        return None
