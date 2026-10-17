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

Available commands are `feed`, `pet`, `light 0-100`, `sound 0-100`, `tick`, and
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
after a reboot. Install offline voice output on the Pi with:

```bash
sudo apt update
sudo apt install espeak-ng
```

The micro:bit message format is documented in
[`docs/microbit-protocol.md`](docs/microbit-protocol.md). The local API and its
website/tunnel guidance are documented below.

In hardware mode, the Pi speaks `Good morning, fellas! I am awake!` and `Good
night, fellas! I am going to sleep!` through the configured audio output. Voice
errors are logged without stopping the OLED or pet service. A powered speaker or
amplifier is required for the Pi's line-level 3.5 mm output.

USB microphone input is optional. The boot service currently disables it so a
problematic microphone cannot stop the pet, display, or voice greetings. Re-enable
it later with `TAMAGODJI_MICROPHONE_ENABLED=1` after testing the USB audio device.

## Local API and website display

Hardware mode starts a small JSON API on `127.0.0.1:8080`. It runs inside the
same process as the pet, so the API cannot accidentally create a second SQLite
writer. The API reads the live state and queues actions for the normal pet loop.

Check it from the Pi with:

```bash
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/pet
```

The state response includes the pet meters, mood, CPU temperature, and the text
frame currently suitable for the OLED. Website actions use:

```bash
curl -X POST http://127.0.0.1:8080/api/interactions \
  -H 'Content-Type: application/json' \
  -d '{"action":"feed"}'
```

The accepted actions are `feed` and `play`. The API initially binds only to the
Pi itself. For a public website, put it behind a Cloudflare Tunnel and set a
long random `TAMAGODJI_API_TOKEN` in the Pi's private `.env` file. When a token is
configured, write requests must send `Authorization: Bearer <token>`. Keep the
website origin in `TAMAGODJI_CORS_ORIGIN`, for example
`https://pasqualesalomone.com`. Do not put the token in public browser code; a
public website should normally call a small server-side proxy for write actions.

## OpenRouter LLM brain

The deterministic pet state machine remains authoritative for sleep, light,
food, energy, sickness, and persistence. OpenRouter adds personality and chat;
it does not receive permission to write the database or invent hardware commands.
The Pi sends the current state and a user message to the OpenRouter chat
completions endpoint. The expected result is a short reply plus one optional
validated action: `FEED`, `PLAY`, or `NONE`.

Configure it only on the Pi, never in website JavaScript or Git:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Set `OPENROUTER_API_KEY` and, optionally, `OPENROUTER_MODEL`. The service loads
`.env` at boot. Without a key, `/api/chat` returns a clear not-configured
response and the rest of the pet continues working offline. With a key, a chat
request looks like:

```bash
curl -X POST http://127.0.0.1:8080/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"I am here to take care of you"}'
```

If `TAMAGODJI_API_TOKEN` is configured, add the bearer header to that request as
well. The API implementation uses OpenRouter's OpenAI-compatible
`/api/v1/chat/completions` endpoint. For a website, the safest first version is
read-only polling of `/api/pet` every 2–5 seconds; add authenticated actions
through a server-side website route after the display is working.

## Flash the micro:bits

The two MicroPython programs are in [`microbit/`](microbit/):

- [`interaction.py`](microbit/interaction.py) goes on the handheld controller.
- [`room_sensor.py`](microbit/room_sensor.py) goes on the fixed room-light sensor.

See [`microbit/README.md`](microbit/README.md) for the flashing steps. After both
micro:bits are connected to the Pi, identify their serial ports and start hardware
mode with those two paths.
