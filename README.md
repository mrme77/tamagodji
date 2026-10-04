# Tamagodji

A small virtual pet designed to run on a Raspberry Pi 3 with a 0.96-inch I²C
SSD1306 OLED, two USB-connected micro:bits, and a USB microphone.

## Development model

Develop and test on a Mac in `mock` mode. Deploy the same repository to the Pi and
run `hardware` mode there. The pet logic and SQLite persistence are shared between
both environments; only the display and sensor adapters change.

## Run on a Mac

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m tamagodji --mode mock --demo
```

For interactive development:

```bash
python -m tamagodji --mode mock
```

Available commands are `feed`, `play`, `light 0-100`, `sound 0-100`, `tick`, and
`quit`.

The pet's needs use persisted elapsed time rather than loop count. Fullness falls
slowly while awake and more slowly while asleep. Darkness and daylight create
one-time `Good night!` and `Good morning!` messages. Prolonged hunger can make the
pet sick, but feeding it can recover the pet; there is no permanent death in this
version. In hardware mode, the OLED also shows the Raspberry Pi CPU temperature;
this is a system temperature, not the room temperature.

Run tests with:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Raspberry Pi setup

Clone the repository on the Pi, enable I²C, and install the optional hardware
dependencies:

```bash
git clone <your-github-repository-url> tamagodji
cd tamagodji
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r requirements-pi.txt
```

The OLED wiring is:

```text
OLED GND → Pi pin 6 (GND)
OLED VCC → Pi pin 1 (3.3V)
OLED SCL → Pi pin 5 (GPIO3 / SCL)
OLED SDA → Pi pin 3 (GPIO2 / SDA)
```

Start hardware mode after identifying the two serial ports:

```bash
python -m tamagodji --mode hardware \
  --interaction-port /dev/ttyACM0 \
  --room-port /dev/ttyACM1
```

### Run automatically at boot

The repository includes a `systemd` service configured for the current Pi user
(`mrme77`) and the stable `/dev/serial/by-id/` paths for the two micro:bits. After
pulling the repository on the Pi, install and start it with:

```bash
sudo cp deploy/tamagodji.service /etc/systemd/system/tamagodji.service
sudo systemctl daemon-reload
sudo systemctl enable tamagodji
sudo systemctl start tamagodji
sudo systemctl status tamagodji
```

View live application logs with:

```bash
sudo journalctl -u tamagodji -f
```

The service restarts the application after a failure and starts it again after a
Pi reboot. The SQLite state remains in `.data/pet.db`. The service also selects the
USB microphone explicitly so ALSA's default device does not change its behavior
after a reboot.

The micro:bit message format is documented in
[`docs/microbit-protocol.md`](docs/microbit-protocol.md). A web API will be added
after the first always-on hardware service is verified.

Voice output is intentionally optional for now. The OLED displays the sleep and
wake messages; a small powered speaker can be added later for spoken greetings.

## Flash the micro:bits

The two MicroPython programs are in [`microbit/`](microbit/):

- [`interaction.py`](microbit/interaction.py) goes on the handheld controller.
- [`room_sensor.py`](microbit/room_sensor.py) goes on the fixed room-light sensor.

See [`microbit/README.md`](microbit/README.md) for the flashing steps. After both
micro:bits are connected to the Pi, identify their serial ports and start hardware
mode with those two paths.
