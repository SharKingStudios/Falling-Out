# Soupocalypse: The Last Bowl

Two players are mutant creatures fighting over the last bowl of authentic Chinese soup. The arena is tracked by an HLK-LD2450 radar, player controllers provide compass heading and swing actions, and the laptop renders a fast local beam duel with impact frames and crunchy interaction sounds.

## Run The Game

Install dependencies on a Python install with Pygame support:

```powershell
python -m pip install -r code/server/requirements.txt
```

Run without hardware:

```powershell
python code/server/soupocalypse.py --fake
```

The game opens native fullscreen by default. Use `--windowed` while tuning:

```powershell
python code/server/soupocalypse.py --fake --windowed
```

Headless smoke test:

```powershell
$env:SDL_VIDEODRIVER='dummy'; $env:SDL_AUDIODRIVER='dummy'; python code/server/soupocalypse.py --fake --no-audio --smoke-test 5
```

Run with the bridge:

```powershell
python code/server/soupocalypse.py --port COM4
```

Fake controls:

```text
P1 move: WASD
P1 aim: Q/E
P1 beam: F
P1 bubble: R

P2 move: arrow keys
P2 aim: comma / period
P2 beam: slash
P2 bubble: right shift

Enter: reset/start match
Esc: quit
```

## Game Rules

- Best of 3 rounds.
- Forward/down swing fires a beam.
- Up swing creates a bubble shield.
- Beam hit removes HP.
- Bubble blocks one beam while active.
- KO ends the round.

The MVP intentionally does not include beam clashes, pickups, creature commands, or extra spell systems. The feel comes from the beam, bubble, hit freeze, impact frames, screen shake, particles, and original console-like sounds.

## Visual Theme

The laptop display uses the Fallout event palette from `fallout.hackclub.com`:

```text
dark brown #61453a
brown #9f715d
light brown #edd1b0
beige #fcf1e5
blue #38c9ff
green #37b576
yellow #ffebad
coral #ff7d70
```

Downloaded site fonts live in `code/server/assets/fonts/`. `Hells-Bells.otf` is used for the big title text when available. The site's Outfit webfont is also included, but the game falls back safely if SDL_ttf cannot render a webfont on the current machine.

## Serial Protocol

Bridge to laptop:

```text
RADAR,slot,xCm,yCm,speed,resolution
PLAYER,id,headingDeg,action,seq,rssi,uptimeMs
```

Actions:

```text
0 none
1 beam
2 bubble
```

Laptop to bridge:

```text
FX,beam_fire
FX,beam_hit
FX,bubble
FX,bubble_block
FX,ko
FX,match_win
RELAY,light,on,250
RELAY,fan,on,1000
```

## Player Wiring

Keep the MPU6050 wiring from FFMS and add the QMC5883L on the same I2C bus:

```text
ESP32 3V3  -> MPU6050 VCC, QMC5883L VCC, OLED VCC
ESP32 GND  -> MPU6050 GND, QMC5883L GND, OLED GND
GPIO21 SDA -> MPU6050 SDA + QMC5883L SDA + OLED SDA
GPIO22 SCL -> MPU6050 SCL + QMC5883L SCL + OLED SCL
GPIO23     -> recenter/calibrate button to GND
```

Existing FFMS player pins:

```text
MPU6050 address: 0x68
QMC5883L typical address: 0x0D
OLED typical address: 0x3C
Health LEDs: GPIO 32, 33, 25, 26, 27
FX LEDs: GPIO 16, 17, 18, 19
```

Set `PLAYER_ID` in `code/player/player.ino` to `101` for player 1 and `102` for player 2 before uploading.

## Bridge Wiring

```text
ESP32 GND     -> LD2450 GND + FX supply GND
ESP32 5V/VIN  -> LD2450 VCC if module requires 5V
LD2450 TX     -> ESP32 RX2 GPIO16
LD2450 RX     -> ESP32 TX2 GPIO17
LED strip DIN -> GPIO27 through about 330 ohm resistor
Relay/light   -> GPIO25
Relay/fan     -> GPIO26
Spare FX      -> GPIO18, GPIO19
```

The bridge can compile without `Adafruit_NeoPixel`; it will still drive relays/spare FX pins. If the library is installed, `FX` commands also animate a WS2812 strip.

## Arena

Tape the playable radar area conservatively:

```text
x = -2.0m to +2.0m
y = 0.8m to 4.5m
```

Keep all player movement inside that rectangle and keep spectators outside the radar cone. Shrink the area if the radar gets unstable at the edges.

## Test Checklist

- Run an I2C scanner or watch boot serial output for MPU6050 and QMC5883L.
- Press the player button while facing arena-forward to calibrate heading.
- Verify bridge prints `RADAR` lines when people stand in the arena.
- Verify bridge prints `PLAYER` lines with RSSI when controllers are powered.
- Run `--fake` first to tune visuals/audio.
- Then run with bridge serial and test beam hit, beam miss, bubble block, KO, and best-of-3 reset.
