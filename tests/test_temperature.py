"""Tests for Raspberry Pi temperature telemetry."""

from tamagodji.hardware.temperature import read_cpu_temperature


def test_reads_millidegree_celsius_value(tmp_path) -> None:
    """Linux thermal sensor values are converted to Celsius."""

    sensor = tmp_path / "temp"
    sensor.write_text("37600\n", encoding="utf-8")
    assert read_cpu_temperature(sensor) == 37.6


def test_returns_none_when_sensor_is_missing(tmp_path) -> None:
    """A missing optional sensor does not stop the application."""

    assert read_cpu_temperature(tmp_path / "missing") is None
