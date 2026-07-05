import argparse
import math
import queue
import random
import struct
import threading
import time
from dataclasses import dataclass, field
from itertools import permutations
from pathlib import Path
from typing import Optional

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

import pygame


ARENA_MIN_X = -2.0
ARENA_MAX_X = 2.0
ARENA_MIN_Y = 0.8
ARENA_MAX_Y = 4.5
PLAYER_RADIUS_M = 0.22
BEAM_RANGE_M = 5.0
BEAM_WIDTH_M = 0.68
BEAM_AIM_ASSIST_DEG = 20.0
BUBBLE_RADIUS_M = 0.62
BUBBLE_DURATION = 0.70
BEAM_COOLDOWN = 0.82
BUBBLE_COOLDOWN = 1.10
ROUND_RESET_DELAY = 1.8
HIT_IMPACT_DURATION = 0.150
HIT_STOP_TIME_SCALE = 0.08
PLAYER_SPRITE_HEIGHT = 152
PLAYER_SHADOW_SCALE = 0.50
RADAR_BLOB_TIMEOUT = 0.34
PLAYER_PACKET_TIMEOUT = 1.4
TRACK_DEADBAND_M = 0.025
TRACK_MAX_SPEED_MPS = 4.8
TRACK_GATE_LOCKED_M = 0.90
TRACK_GATE_UNLOCKED_M = 1.75
TRACK_LOST_AFTER = 0.70
TRACK_SNAP_DISTANCE_M = 1.15
RSSI_TRUST_DB = 7.0
RSSI_RANK_PENALTY_M = 0.62
START_SIDE_BIAS_M = 1.10
MAX_HP = 3
WIN_ROUNDS = 2
TARGET_FPS = 60
BASE_DIR = Path(__file__).resolve().parent
FONT_DIR = BASE_DIR / "assets" / "fonts"
SPRITE_DIR = BASE_DIR / "assets" / "sprites"
HELLS_BELLS_FONT = FONT_DIR / "Hells-Bells.otf"
OUTFIT_FONT = FONT_DIR / "Outfit-latin.woff2"
PLAYER_SPRITES = {
    101: SPRITE_DIR / "p1_temp.png",
    102: SPRITE_DIR / "p2_temp.png",
}

ACTION_NONE = 0
ACTION_BEAM = 1
ACTION_BUBBLE = 2
MAGCAL_COMMAND_MS = 18000
MAGCAL_DONE_HOLD_S = 6.0

MENU_STATES = {"select", "countdown", "starting"}
MENU_DUPLICATE_PICKS = True
MENU_CURSOR_HISTORY = 9
MENU_HOVER_ANIM = 0.14
MENU_SELECT_SLAM = 0.34
MENU_DESELECT_ANIM = 0.28
MENU_PANEL_REVEAL = 0.38
MENU_COUNTDOWN_STEP = 0.68
MENU_TRANSITION_DELAY = 0.55
MENU_SHAKE_SELECT = 5.0
MENU_SHAKE_GO = 13.0
MENU_SFX_MASTER_VOLUME = 0.92
MENU_SFX_VOLUME = {
    "menu_hover": 0.72,
    "menu_hover_p1": 0.76,
    "menu_hover_p2": 0.76,
    "menu_lock": 0.95,
    "menu_cancel": 0.82,
    "menu_deny": 0.75,
    "count_3": 0.92,
    "count_2": 0.92,
    "count_1": 0.98,
    "count_go": 1.0,
    "menu_panel": 0.86,
    "menu_splash": 0.78,
    "menu_fire": 0.66,
    "menu_transition": 0.92,
}

MAGCAL_ACTIVE_STATES = {"REQUESTED", "START", "RUNNING"}
MAGCAL_DONE_STATES = {"OK", "ERR", "RESET"}

PALETTE = {
    "bg": (18, 13, 11),
    "panel": (30, 22, 19),
    "panel_2": (42, 30, 25),
    "dark_brown": (97, 69, 58),
    "brown": (159, 113, 93),
    "light_brown": (237, 209, 176),
    "beige": (252, 241, 229),
    "grid": (97, 69, 58),
    "text": (232, 213, 196),
    "muted": (184, 154, 133),
    "soup": (255, 235, 173),
    "soup_deep": (239, 147, 0),
    "p1": (55, 181, 118),
    "p1_dark": (29, 98, 70),
    "p2": (255, 125, 112),
    "p2_dark": (143, 55, 47),
    "white": (255, 255, 255),
    "bubble": (56, 201, 255),
    "ice": (0, 162, 255),
    "coral": (255, 125, 112),
    "bad": (251, 44, 54),
    "backdrop": (65, 88, 97),
}

CHARACTER_SLOTS = (
    {
        "id": "broth_beast",
        "name": "Broth Beast",
        "portrait": SPRITE_DIR / "p1_temp.png",
        "theme": (55, 181, 118),
        "secondary": (255, 235, 173),
        "dark": (21, 77, 55),
        "highlight": (168, 255, 203),
        "tagline": "simmer guard",
    },
    {
        "id": "noodle_wyrm",
        "name": "Noodle Wyrm",
        "portrait": SPRITE_DIR / "p2_temp.png",
        "theme": (255, 125, 112),
        "secondary": (255, 235, 173),
        "dark": (116, 39, 43),
        "highlight": (255, 204, 166),
        "tagline": "spice striker",
    },
    {
        "id": "bloo",
        "name": "Bloo",
        "portrait": SPRITE_DIR / "bloo.png",
        "theme": (56, 201, 255),
        "secondary": (113, 255, 222),
        "dark": (18, 68, 107),
        "highlight": (223, 251, 255),
        "tagline": "cold snap",
    },
    {
        "id": "party_cat",
        "name": "Party Cat",
        "portrait": SPRITE_DIR / "party-cat.png",
        "theme": (255, 205, 64),
        "secondary": (255, 105, 180),
        "dark": (126, 73, 20),
        "highlight": (255, 249, 178),
        "tagline": "festival fury",
    },
    {
        "id": "wasteland_wing",
        "name": "Wasteland Wing",
        "portrait": SPRITE_DIR / "pigeon.png",
        "theme": (157, 132, 255),
        "secondary": (86, 226, 188),
        "dark": (54, 43, 112),
        "highlight": (232, 225, 255),
        "tagline": "scrap dive",
    },
    {
        "id": "the_goat",
        "name": "The Goat",
        "portrait": SPRITE_DIR / "the-goat.png",
        "theme": (255, 145, 48),
        "secondary": (82, 218, 128),
        "dark": (99, 48, 16),
        "highlight": (255, 222, 153),
        "tagline": "bowl bandit",
    },
)


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out_cubic(t):
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def ease_out_back(t):
    t = clamp(t, 0.0, 1.0)
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def channel(value):
    return int(clamp(round(value), 0, 255))


def rgba(color, alpha=255):
    return (
        channel(color[0]),
        channel(color[1]),
        channel(color[2]),
        channel(alpha),
    )


def rgb(color):
    return channel(color[0]), channel(color[1]), channel(color[2])


def normalize_deg(deg):
    while deg >= 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


def heading_vec(deg):
    rad = math.radians(deg)
    return math.sin(rad), math.cos(rad)


def vec_heading(dx, dy):
    return math.degrees(math.atan2(dx, dy))


def radar_to_world(raw_x_m, raw_y_m):
    return -raw_x_m, ARENA_MAX_Y - raw_y_m


def point_segment_distance(point, start, end):
    px, py = point
    ax, ay = start
    bx, by = end
    vx = bx - ax
    vy = by - ay
    length_sq = vx * vx + vy * vy
    if length_sq <= 0.0001:
        return math.hypot(px - ax, py - ay), 0.0
    t = ((px - ax) * vx + (py - ay) * vy) / length_sq
    t = clamp(t, 0.0, 1.0)
    cx = ax + vx * t
    cy = ay + vy * t
    return math.hypot(px - cx, py - cy), t


def choose_port():
    if list_ports is None:
        return None
    ports = list(list_ports.comports())
    if not ports:
        return None
    preferred = ("CP210", "CH340", "CH341", "USB Serial", "Silicon", "Espressif")
    for port in ports:
        haystack = f"{port.description} {port.manufacturer} {port.hwid}"
        if any(word.lower() in haystack.lower() for word in preferred):
            return port.device
    return ports[0].device


@dataclass
class RadarBlob:
    slot: int
    x: float = 0.0
    y: float = 0.0
    raw_x: float = 0.0
    raw_y: float = 0.0
    range_m: float = 0.0
    speed: float = 0.0
    resolution: int = 0
    seen_at: float = 0.0


@dataclass
class Player:
    player_id: int
    label: str
    color: tuple
    dark_color: tuple
    x: float
    y: float
    heading: float
    vx: float = 0.0
    vy: float = 0.0
    hp: int = MAX_HP
    wins: int = 0
    alive: bool = True
    bubble_until: float = 0.0
    beam_ready_at: float = 0.0
    bubble_ready_at: float = 0.0
    last_action_seq: int = -1
    last_seen_at: float = 0.0
    rssi: Optional[float] = None
    sprite_phase: float = 0.0
    track_updated_at: float = 0.0
    track_slot: Optional[int] = None
    track_confidence: float = 0.0

    def position(self):
        return self.x, self.y

    def bubble_active(self, now):
        return self.alive and now < self.bubble_until


@dataclass
class MagCalStatus:
    player_id: int
    state: str
    progress: int = 0
    quality: int = 0
    samples: int = 0
    elapsed_ms: int = 0
    remaining_ms: int = 0
    radius_x: int = 0
    radius_y: int = 0
    radius_z: int = 0
    avg_radius: int = 0
    flags: int = 0
    rssi: Optional[float] = None
    seen_at: float = 0.0

    def active(self, now):
        return self.state in MAGCAL_ACTIVE_STATES and now - self.seen_at < 40.0

    def visible(self, now):
        return self.active(now) or (self.state in MAGCAL_DONE_STATES and now - self.seen_at < MAGCAL_DONE_HOLD_S)


@dataclass
class BeamEffect:
    start: tuple
    end: tuple
    color: tuple
    created_at: float
    duration: float = 0.28
    hit_point: Optional[tuple] = None
    blocked: bool = False


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: tuple
    radius: float
    created_at: float
    life: float
    additive: bool = True


@dataclass
class ImpactFrame:
    kind: str
    created_at: float
    duration: float
    color: tuple
    attacker_id: Optional[int] = None
    target_id: Optional[int] = None
    hit_point: Optional[tuple] = None


@dataclass
class QueuedAction:
    player_id: int
    action: int
    queued_at: float


@dataclass
class MenuPlayerState:
    player_id: int
    hover_index: int = 0
    selected_index: Optional[int] = None
    hover_changed_at: float = 0.0
    selected_at: float = 0.0
    cancel_until: float = 0.0
    deny_until: float = 0.0
    cursor_history: list = field(default_factory=list)


@dataclass
class MenuParticle:
    x: float
    y: float
    vx: float
    vy: float
    color: tuple
    size: float
    created_at: float
    life: float
    kind: str = "pixel"
    spin: float = 0.0


@dataclass
class MenuSlash:
    x: float
    y: float
    angle: float
    length: float
    color: tuple
    created_at: float
    life: float
    width: float = 18.0


class SerialTransport:
    def __init__(self, port_name, baud, incoming):
        self.port_name = port_name
        self.baud = baud
        self.incoming = incoming
        self.outgoing = queue.Queue()
        self.stop = threading.Event()
        self.serial = None

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def write_line(self, line):
        self.outgoing.put(line.rstrip() + "\n")

    def run(self):
        if serial is None:
            self.incoming.put(("LOG", "pyserial missing; running display without hardware"))
            return
        requested = self.port_name
        while not self.stop.is_set():
            port = requested or choose_port()
            if not port:
                time.sleep(0.8)
                continue
            try:
                with serial.Serial(port, self.baud, timeout=0.04, write_timeout=0.05) as ser:
                    self.serial = ser
                    self.incoming.put(("LOG", f"serial connected: {port}"))
                    buffer = b""
                    while not self.stop.is_set():
                        try:
                            chunk = ser.read(256)
                            if chunk:
                                buffer += chunk
                                while b"\n" in buffer:
                                    raw, buffer = buffer.split(b"\n", 1)
                                    line = raw.decode("utf-8", "ignore").strip()
                                    if line:
                                        self.incoming.put(("SERIAL", line))
                            while True:
                                line = self.outgoing.get_nowait()
                                ser.write(line.encode("utf-8"))
                        except queue.Empty:
                            pass
            except Exception as exc:
                self.serial = None
                self.incoming.put(("LOG", f"serial waiting: {exc}"))
                time.sleep(0.8)


class SoundBank:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.sounds = {}
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 256)
            self.make_sounds()
        except Exception as exc:
            print(f"audio disabled: {exc}")
            self.enabled = False

    def make_sounds(self):
        self.sounds["menu_move"] = self.sequence([(880, 0.045), (1175, 0.035)], 0.28, "square")
        self.sounds["menu_select"] = self.sequence([(660, 0.055), (990, 0.055), (1320, 0.075)], 0.34, "square")
        self.sounds["menu_hover"] = self.sequence([(1046, 0.026), (1568, 0.024)], 0.34, "square")
        self.sounds["menu_hover_p1"] = self.sequence([(988, 0.024), (1480, 0.026)], 0.36, "square")
        self.sounds["menu_hover_p2"] = self.sequence([(1175, 0.024), (1760, 0.026)], 0.36, "square")
        self.sounds["menu_lock"] = self.menu_lock_sound()
        self.sounds["menu_cancel"] = self.sweep(760, 270, 0.16, 0.34, "triangle")
        self.sounds["menu_deny"] = self.sequence([(164, 0.045), (123, 0.055), (164, 0.035)], 0.32, "square")
        self.sounds["count_3"] = self.menu_count_sound(360, 650, 0.22, 0.44)
        self.sounds["count_2"] = self.menu_count_sound(520, 980, 0.20, 0.46)
        self.sounds["count_1"] = self.menu_count_sound(220, 540, 0.26, 0.54)
        self.sounds["count_go"] = self.menu_go_sound()
        self.sounds["menu_panel"] = self.sweep(420, 980, 0.12, 0.36, "triangle")
        self.sounds["menu_splash"] = self.noise_burst(0.11, 0.38, 90, 740)
        self.sounds["menu_fire"] = self.noise_burst(0.08, 0.30, 900, 2600)
        self.sounds["menu_transition"] = self.sweep(330, 1720, 0.34, 0.42, "square")
        self.sounds["ready"] = self.sequence([(392, 0.06), (523, 0.06), (784, 0.09)], 0.38, "triangle")
        self.sounds["swing"] = self.sweep(620, 980, 0.09, 0.26, "triangle")
        self.sounds["beam"] = self.beam_sound()
        self.sounds["bubble"] = self.sequence([(740, 0.04), (1046, 0.08)], 0.30, "sine")
        self.sounds["block"] = self.sequence([(1397, 0.035), (1046, 0.06), (1568, 0.08)], 0.36, "square")
        self.sounds["hit"] = self.noise_burst(0.16, 0.48, 180, 420)
        self.sounds["ko"] = self.sequence([(196, 0.12), (147, 0.12), (98, 0.22)], 0.52, "triangle")
        self.sounds["round"] = self.sequence([(523, 0.06), (659, 0.06), (784, 0.06), (1046, 0.14)], 0.42, "square")
        self.sounds["invalid"] = self.sequence([(190, 0.055), (142, 0.08)], 0.24, "square")
        self.sounds["round_win"] = self.sounds["round"]

    def envelope(self, i, total):
        if total <= 1:
            return 0.0
        a = min(1.0, i / max(1, int(total * 0.08)))
        r = min(1.0, (total - i) / max(1, int(total * 0.22)))
        return min(a, r)

    def wave_sample(self, phase, shape):
        if shape == "square":
            return 1.0 if math.sin(phase) >= 0 else -1.0
        if shape == "triangle":
            return 2.0 * abs(2.0 * ((phase / math.tau) % 1.0) - 1.0) - 1.0
        return math.sin(phase)

    def build(self, samples, gain):
        frames = bytearray()
        for sample in samples:
            value = int(clamp(sample * gain, -1.0, 1.0) * 32767)
            frames += struct.pack("<hh", value, value)
        return pygame.mixer.Sound(buffer=bytes(frames))

    def sequence(self, notes, gain, shape):
        rate = 44100
        samples = []
        for freq, duration in notes:
            total = max(1, int(rate * duration))
            for i in range(total):
                phase = math.tau * freq * (i / rate)
                samples.append(self.wave_sample(phase, shape) * self.envelope(i, total))
        return self.build(samples, gain)

    def sweep(self, start_freq, end_freq, duration, gain, shape):
        rate = 44100
        total = int(rate * duration)
        samples = []
        phase = 0.0
        for i in range(total):
            t = i / max(1, total - 1)
            freq = start_freq + (end_freq - start_freq) * t
            phase += math.tau * freq / rate
            samples.append(self.wave_sample(phase, shape) * self.envelope(i, total))
        return self.build(samples, gain)

    def beam_sound(self):
        rate = 44100
        total = int(rate * 0.32)
        samples = []
        phase_a = 0.0
        phase_b = 0.0
        rng = random.Random(2450)
        for i in range(total):
            t = i / max(1, total - 1)
            freq_a = 140 + 620 * min(1.0, t * 3.0)
            freq_b = 880 + 220 * math.sin(t * math.tau * 4)
            phase_a += math.tau * freq_a / rate
            phase_b += math.tau * freq_b / rate
            crackle = (rng.random() * 2 - 1) * 0.18 * (1.0 - t)
            body = math.sin(phase_a) * 0.65 + (1 if math.sin(phase_b) > 0 else -1) * 0.28
            samples.append((body + crackle) * self.envelope(i, total))
        return self.build(samples, 0.46)

    def menu_lock_sound(self):
        rate = 44100
        total = int(rate * 0.20)
        samples = []
        phase_low = 0.0
        phase_high = 0.0
        rng = random.Random(744)
        for i in range(total):
            t = i / max(1, total - 1)
            low_freq = 96 + 42 * (1.0 - t)
            high_freq = 1120 + 420 * t
            phase_low += math.tau * low_freq / rate
            phase_high += math.tau * high_freq / rate
            transient = (rng.random() * 2 - 1) * 0.70 * max(0.0, 1.0 - t * 12.0)
            snap = (1.0 if math.sin(phase_high) > 0 else -1.0) * 0.38
            thump = math.sin(phase_low) * 0.72 * (1.0 - t)
            samples.append((thump + snap + transient) * self.envelope(i, total))
        return self.build(samples, 0.46)

    def menu_count_sound(self, start_freq, end_freq, duration, gain):
        rate = 44100
        total = int(rate * duration)
        samples = []
        phase_a = 0.0
        phase_b = 0.0
        rng = random.Random(int(start_freq * 7 + end_freq))
        for i in range(total):
            t = i / max(1, total - 1)
            freq = start_freq + (end_freq - start_freq) * min(1.0, t * 1.6)
            phase_a += math.tau * freq / rate
            phase_b += math.tau * (freq * 0.48) / rate
            noise = (rng.random() * 2 - 1) * 0.20 * max(0.0, 1.0 - t * 5.0)
            body = math.sin(phase_b) * 0.68 * (1.0 - t * 0.35)
            edge = (1.0 if math.sin(phase_a) > 0 else -1.0) * 0.22
            samples.append((body + edge + noise) * self.envelope(i, total))
        return self.build(samples, gain)

    def menu_go_sound(self):
        rate = 44100
        total = int(rate * 0.38)
        samples = []
        phase_rise = 0.0
        phase_bass = 0.0
        rng = random.Random(2026)
        for i in range(total):
            t = i / max(1, total - 1)
            rise_freq = 220 + 1480 * (t ** 0.55)
            bass_freq = 82 + 58 * math.sin(t * math.tau)
            phase_rise += math.tau * rise_freq / rate
            phase_bass += math.tau * bass_freq / rate
            sparkle = (1.0 if math.sin(phase_rise) > 0 else -1.0) * 0.23 * (1.0 - t * 0.45)
            bass = math.sin(phase_bass) * 0.70 * (1.0 - t)
            crack = (rng.random() * 2 - 1) * 0.36 * max(0.0, 1.0 - t * 1.8)
            samples.append((sparkle + bass + crack) * self.envelope(i, total))
        return self.build(samples, 0.50)

    def noise_burst(self, duration, gain, lo, hi):
        rate = 44100
        total = int(rate * duration)
        rng = random.Random(991)
        phase = 0.0
        samples = []
        for i in range(total):
            t = i / max(1, total - 1)
            freq = lo + (hi - lo) * (1.0 - t)
            phase += math.tau * freq / rate
            tone = math.sin(phase) * 0.55
            noise = (rng.random() * 2 - 1) * 0.65
            samples.append((tone + noise) * self.envelope(i, total))
        return self.build(samples, gain)

    def play(self, name, volume=1.0):
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound:
            sound.set_volume(clamp(volume, 0.0, 1.0))
            sound.play()


class SoupocalypseApp:
    def __init__(self, args):
        if not args.no_audio:
            pygame.mixer.pre_init(44100, -16, 2, 256)
        pygame.init()
        self.args = args
        self.fullscreen = not args.windowed and not args.smoke_test
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        size = (0, 0) if self.fullscreen else (args.width, args.height)
        self.screen = pygame.display.set_mode(size, flags)
        pygame.display.set_caption("Soupocalypse: The Last Bowl")
        self.clock = pygame.time.Clock()
        self.load_fonts()
        self.sounds = SoundBank(enabled=not args.no_audio)
        self.incoming = queue.Queue()
        self.transport = None
        if not args.fake:
            self.transport = SerialTransport(args.port, args.baud, self.incoming)
            self.transport.start()
        self.players = {
            101: Player(101, "Broth Beast", PALETTE["p1"], PALETTE["p1_dark"], -0.95, 2.5, 90),
            102: Player(102, "Noodle Wyrm", PALETTE["p2"], PALETTE["p2_dark"], 0.95, 2.5, -90),
        }
        self.radar_blobs = {}
        self.particles = []
        self.beams = []
        self.impact_frames = []
        self.logs = []
        self.running = True
        self.debug_radar = args.debug_radar
        self.match_state = "select"
        self.round_message = "CHOOSE YOUR SOUP FIGHTER"
        self.round_reset_at = 0.0
        self.freeze_until = 0.0
        self.hit_stop_until = 0.0
        self.shake_until = 0.0
        self.shake_power = 0.0
        self.pending_actions = []
        self.last_tick = time.time()
        self.fake_actions = {101: 0, 102: 0}
        self.fake_last_heading = {101: 90.0, 102: -90.0}
        self.calibration_select_until = 0.0
        self.mag_cal_status = {}
        self.sprite_cache = {}
        self.player_sprite_paths = dict(PLAYER_SPRITES)
        now = time.time()
        self.menu_players = {
            101: MenuPlayerState(101, hover_index=0, hover_changed_at=now),
            102: MenuPlayerState(102, hover_index=2, hover_changed_at=now),
        }
        self.menu_particles = []
        self.menu_slashes = []
        self.menu_countdown_started_at = 0.0
        self.menu_countdown_last_step = -1
        self.menu_transition_started_at = 0.0
        self.menu_notice = ""
        self.menu_notice_until = 0.0
        self.character_cache = {}
        self.bg_cache = None
        self.bg_cache_size = None

    def load_font(self, paths, size, fallback="arial", bold=False):
        for path in paths:
            if path and Path(path).exists():
                try:
                    font = pygame.font.Font(str(path), size)
                    font.render("A", True, PALETTE["text"])
                    return font
                except Exception:
                    pass
        font = pygame.font.SysFont(fallback, size, bold=bold)
        if font is None:
            font = pygame.font.Font(None, size)
        return font

    def load_fonts(self):
        h = self.screen.get_height()
        title_size = max(62, min(118, h // 8))
        big_size = max(34, min(62, h // 15))
        body_size = max(18, min(27, h // 36))
        small_size = max(14, min(21, h // 48))
        self.font = self.load_font([OUTFIT_FONT], body_size, "arial", bold=True)
        self.small_font = self.load_font([OUTFIT_FONT], small_size, "arial")
        self.big_font = self.load_font([HELLS_BELLS_FONT, OUTFIT_FONT], big_size, "arial", bold=True)
        self.title_font = self.load_font([HELLS_BELLS_FONT, OUTFIT_FONT], title_size, "arial", bold=True)

    def log(self, msg):
        self.logs.append((time.time(), msg))
        self.logs = self.logs[-6:]

    def send_fx(self, name):
        if self.transport is not None:
            self.transport.write_line(f"FX,{name}")

    def send_player_command(self, player_id, command, value_ms=0):
        if self.transport is None:
            self.log("hardware command ignored: no bridge serial")
            self.sounds.play("invalid")
            return False
        self.transport.write_line(f"PLAYERCMD,{player_id},{command},{int(value_ms)}")
        self.log(f"P{player_id} {command} sent")
        self.sounds.play("ready")
        return True

    def set_local_magcal_requested(self, player_id, duration_ms):
        self.mag_cal_status[player_id] = MagCalStatus(
            player_id=player_id,
            state="REQUESTED",
            remaining_ms=duration_ms,
            seen_at=time.time(),
        )

    def handle_magcal_line(self, parts):
        if len(parts) < 13:
            return
        pid = int(parts[1])
        state = parts[2].upper()
        old_state = self.mag_cal_status.get(pid).state if pid in self.mag_cal_status else None
        status = MagCalStatus(
            player_id=pid,
            state=state,
            progress=clamp(int(float(parts[3])), 0, 100),
            quality=clamp(int(float(parts[4])), 0, 100),
            samples=int(float(parts[5])),
            elapsed_ms=int(float(parts[6])),
            remaining_ms=int(float(parts[7])),
            radius_x=int(float(parts[8])),
            radius_y=int(float(parts[9])),
            radius_z=int(float(parts[10])),
            avg_radius=int(float(parts[11])),
            flags=int(float(parts[12])),
            rssi=float(parts[13]) if len(parts) >= 14 else None,
            seen_at=time.time(),
        )
        self.mag_cal_status[pid] = status
        if state == "OK" and old_state != "OK":
            self.log(f"P{pid} compass calibration saved")
            self.sounds.play("round_win")
        elif state == "ERR" and old_state != "ERR":
            self.log(f"P{pid} compass calibration failed; move bigger")
            self.sounds.play("invalid")

    def reset_round(self):
        now = time.time()
        for player in self.players.values():
            player.hp = MAX_HP
            player.alive = True
            player.bubble_until = 0.0
            player.beam_ready_at = now + 0.4
            player.bubble_ready_at = now + 0.4
        self.beams.clear()
        self.particles.clear()
        self.impact_frames.clear()
        self.pending_actions.clear()
        self.hit_stop_until = 0.0
        self.freeze_until = 0.0
        self.match_state = "playing"
        self.round_message = "FIGHT"
        self.sounds.play("ready")

    def reset_match(self):
        self.apply_menu_character_choices()
        for player in self.players.values():
            player.wins = 0
        self.reset_round()

    def open_character_select(self):
        now = time.time()
        self.match_state = "select"
        self.round_message = "CHOOSE YOUR SOUP FIGHTER"
        self.round_reset_at = 0.0
        self.freeze_until = 0.0
        self.hit_stop_until = 0.0
        self.pending_actions.clear()
        self.beams.clear()
        self.impact_frames.clear()
        self.menu_particles.clear()
        self.menu_slashes.clear()
        self.menu_countdown_started_at = 0.0
        self.menu_countdown_last_step = -1
        self.menu_transition_started_at = 0.0
        for player in self.players.values():
            player.hp = MAX_HP
            player.alive = True
            player.bubble_until = 0.0
            player.beam_ready_at = 0.0
            player.bubble_ready_at = 0.0
        for state in self.menu_players.values():
            state.selected_index = None
            state.selected_at = 0.0
            state.cancel_until = 0.0
            state.deny_until = 0.0
            state.cursor_history.clear()
            state.hover_changed_at = now

    def apply_menu_character_choices(self):
        defaults = {101: 0, 102: 1}
        for pid, player in self.players.items():
            state = self.menu_players.get(pid)
            index = state.selected_index if state and state.selected_index is not None else defaults.get(pid, 0)
            character = CHARACTER_SLOTS[index]
            player.label = character["name"]
            player.color = character["theme"]
            player.dark_color = character["dark"]
            self.player_sprite_paths[pid] = character["portrait"]
        self.sprite_cache.clear()

    def play_menu_sound(self, name, extra=1.0):
        volume = MENU_SFX_VOLUME.get(name, 1.0) * MENU_SFX_MASTER_VOLUME * extra
        self.sounds.play(name, volume)

    def handle_serial_line(self, line):
        parts = [p.strip() for p in line.split(",")]
        if not parts:
            return
        tag = parts[0].upper()
        try:
            if tag == "RADAR" and len(parts) >= 6:
                slot = int(parts[1])
                raw_x = float(parts[2]) / 100.0
                raw_y = float(parts[3]) / 100.0
                x, y = radar_to_world(raw_x, raw_y)
                speed = float(parts[4])
                resolution = int(float(parts[5]))
                self.radar_blobs[slot] = RadarBlob(
                    slot, x, y, raw_x, raw_y, math.hypot(raw_x, raw_y),
                    speed, resolution, time.time()
                )
                self.update_identity_from_radar()
            elif tag == "PLAYER" and len(parts) >= 6:
                pid = int(parts[1])
                heading = float(parts[2])
                action = self.parse_action(parts[3])
                seq = int(parts[4])
                rssi = float(parts[5])
                uptime = int(float(parts[6])) if len(parts) >= 7 else 0
                self.apply_player_packet(pid, heading, action, seq, rssi, uptime)
            elif tag == "ACTION" and len(parts) >= 5:
                pid = int(parts[1])
                action = self.parse_action(parts[2])
                heading = float(parts[3])
                seq = int(parts[4])
                self.apply_player_packet(pid, heading, action, seq, None, 0)
            elif tag == "CAST" and len(parts) >= 6:
                pid = int(parts[1])
                spell = int(parts[2])
                heading = float(parts[3])
                seq = int(parts[5])
                action = ACTION_BEAM if spell == 1 else ACTION_BUBBLE if spell == 2 else ACTION_NONE
                self.apply_player_packet(pid, heading, action, seq, None, 0)
            elif tag == "STATUS" and len(parts) >= 5:
                pid = int(parts[1])
                heading = float(parts[2])
                if pid in self.players:
                    self.players[pid].heading = heading
            elif tag == "MAGCAL":
                self.handle_magcal_line(parts)
            elif tag in ("LOG", "BRIDGE_BOOT", "WARN", "ERR", "PLAYERCMD_SENT", "PLAYERCMD_ERR"):
                self.log(line[:90])
        except ValueError:
            self.log(f"bad line: {line[:80]}")

    def parse_action(self, value):
        text = str(value).strip().upper()
        if text in ("1", "BEAM", "FIRE", "ATTACK"):
            return ACTION_BEAM
        if text in ("2", "BUBBLE", "SHIELD", "DEFEND"):
            return ACTION_BUBBLE
        return ACTION_NONE

    def apply_player_packet(self, pid, heading, action, seq, rssi, uptime):
        player = self.players.get(pid)
        if player is None:
            return
        player.heading = normalize_deg(heading)
        player.last_seen_at = time.time()
        if rssi is not None and rssi < 0:
            player.rssi = rssi if player.rssi is None else player.rssi * 0.85 + rssi * 0.15
        if action != ACTION_NONE and seq != player.last_action_seq:
            player.last_action_seq = seq
            self.request_action(player, action)

    def update_identity_from_radar(self):
        now = time.time()
        blobs = [
            blob for blob in self.radar_blobs.values()
            if blob.resolution > 0 and now - blob.seen_at < RADAR_BLOB_TIMEOUT and
            ARENA_MIN_X - 0.7 <= blob.x <= ARENA_MAX_X + 0.7 and
            ARENA_MIN_Y - 0.8 <= blob.y <= ARENA_MAX_Y + 0.8
        ]
        active_players = [
            player for player in self.players.values()
            if player.rssi is not None and now - player.last_seen_at < PLAYER_PACKET_TIMEOUT
        ]
        if not blobs or not active_players:
            return
        pairs = self.assign_radar_blobs(active_players, blobs, now)

        for player, blob in pairs:
            self.move_player_toward_blob(player, blob, now)

    def assign_radar_blobs(self, active_players, blobs, now):
        players = sorted(active_players, key=lambda player: player.player_id)
        if len(blobs) == 1:
            player = self.best_single_blob_owner(players, blobs[0], now)
            return [(player, blobs[0])] if player is not None else []

        needed = min(len(players), len(blobs))
        best_pairs = []
        best_cost = float("inf")
        for player_order in permutations(players, needed):
            for blob_order in permutations(blobs, needed):
                pairs = list(zip(player_order, blob_order))
                if len({player.player_id for player, _ in pairs}) != needed:
                    continue
                cost = sum(self.blob_assignment_cost(player, blob, now) for player, blob in pairs)
                if cost >= 1000:
                    continue
                cost += self.rssi_rank_cost(pairs)
                if cost < best_cost:
                    best_cost = cost
                    best_pairs = pairs
        return best_pairs

    def best_single_blob_owner(self, players, blob, now):
        scored = []
        for player in players:
            cost = self.blob_assignment_cost(player, blob, now)
            if cost < 1000:
                scored.append((cost, player))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0])
        if len(players) > 1 and scored[0][1].track_confidence < 0.35:
            return None
        return scored[0][1]

    def blob_assignment_cost(self, player, blob, now):
        tracking_age = now - player.track_updated_at if player.track_updated_at else 999.0
        predict_dt = clamp(tracking_age, 0.0, 0.22)
        predicted_x = player.x + player.vx * predict_dt * 0.35
        predicted_y = player.y + player.vy * predict_dt * 0.35
        distance = math.hypot(blob.x - predicted_x, blob.y - predicted_y)
        gate = TRACK_GATE_UNLOCKED_M if player.track_confidence < 0.35 or tracking_age > TRACK_LOST_AFTER else TRACK_GATE_LOCKED_M
        gate += min(0.45, max(0.0, tracking_age) * TRACK_MAX_SPEED_MPS * 0.45)
        if distance > gate:
            return 1000 + distance

        cost = distance
        if player.track_confidence < 0.35 and player.track_slot is None:
            if player.player_id == 101 and blob.x > 0.0:
                cost += START_SIDE_BIAS_M + blob.x * 0.35
            elif player.player_id == 102 and blob.x < 0.0:
                cost += START_SIDE_BIAS_M + abs(blob.x) * 0.35
        if player.track_slot == blob.slot:
            cost -= 0.16 * player.track_confidence
        elif player.track_slot is not None:
            cost += 0.30 * player.track_confidence
        return cost

    def rssi_rank_cost(self, pairs):
        if len(pairs) < 2:
            return 0.0
        players = [player for player, _ in pairs if player.rssi is not None]
        if len(players) < 2:
            return 0.0
        rssis = [player.rssi for player in players]
        diff = max(rssis) - min(rssis)
        if diff < RSSI_TRUST_DB:
            return 0.0
        trust = clamp((diff - RSSI_TRUST_DB) / 12.0, 0.0, 1.0)
        assigned = {player.player_id: blob for player, blob in pairs}
        by_rssi = sorted(players, key=lambda player: player.rssi or -999, reverse=True)
        by_range = sorted((assigned[player.player_id] for player in players), key=lambda blob: blob.range_m)
        cost = 0.0
        for rank, player in enumerate(by_rssi):
            expected_blob = by_range[rank]
            if assigned[player.player_id].slot != expected_blob.slot:
                cost += RSSI_RANK_PENALTY_M * trust
        return cost

    def move_player_toward_blob(self, player, blob, now):
        old_x, old_y = player.x, player.y
        target_x = clamp(blob.x, ARENA_MIN_X, ARENA_MAX_X)
        target_y = clamp(blob.y, ARENA_MIN_Y, ARENA_MAX_Y)
        dx = target_x - old_x
        dy = target_y - old_y
        distance = math.hypot(dx, dy)
        dt = now - player.track_updated_at if player.track_updated_at else 1.0 / TARGET_FPS
        dt = clamp(dt, 1.0 / 80.0, 0.12)

        if distance < TRACK_DEADBAND_M:
            new_x, new_y = old_x, old_y
        elif player.track_updated_at == 0.0 or player.track_confidence < 0.25 or distance > TRACK_SNAP_DISTANCE_M:
            new_x, new_y = target_x, target_y
        else:
            alpha = 0.32
            if distance > 0.45:
                alpha = 0.78
            elif distance > 0.14:
                alpha = 0.56
            desired_step = distance * alpha
            max_step = TRACK_MAX_SPEED_MPS * dt
            step = min(distance, desired_step, max_step)
            scale = step / distance
            new_x = old_x + dx * scale
            new_y = old_y + dy * scale

        player.x = clamp(new_x, ARENA_MIN_X, ARENA_MAX_X)
        player.y = clamp(new_y, ARENA_MIN_Y, ARENA_MAX_Y)
        player.vx = (player.x - old_x) / dt
        player.vy = (player.y - old_y) / dt
        player.track_updated_at = now
        player.track_slot = blob.slot
        player.track_confidence = min(1.0, player.track_confidence + 0.16)

    def is_hit_stop_active(self, now=None):
        now = time.time() if now is None else now
        return now < self.hit_stop_until

    def request_action(self, player, action):
        if self.match_state in MENU_STATES:
            self.handle_menu_action(player, action)
            return
        if self.match_state != "playing":
            return
        if self.pending_actions or self.is_hit_stop_active():
            self.queue_action(player, action)
            return
        self.perform_action(player, action)

    def handle_menu_action(self, player, action):
        state = self.menu_players.get(player.player_id)
        if state is None:
            return
        now = time.time()
        if action == ACTION_BEAM:
            if state.selected_index is not None:
                self.menu_deny(state, "LOCKED")
                return
            index = state.hover_index
            if index is None or not (0 <= index < len(CHARACTER_SLOTS)):
                self.menu_deny(state, "NO TARGET")
                return
            if not MENU_DUPLICATE_PICKS:
                for other in self.menu_players.values():
                    if other.player_id != state.player_id and other.selected_index == index:
                        self.menu_deny(state, "TAKEN")
                        return
            state.selected_index = index
            state.selected_at = now
            state.cancel_until = 0.0
            character = CHARACTER_SLOTS[index]
            self.menu_notice = f"P{1 if state.player_id == 101 else 2} LOCKED!"
            self.menu_notice_until = now + 0.55
            self.play_menu_sound("menu_lock")
            self.play_menu_sound("menu_panel", 0.88)
            self.play_menu_sound("menu_splash", 0.72)
            self.spawn_menu_lock_fx(state.player_id, index)
            self.shake(0.12, MENU_SHAKE_SELECT)
            if self.all_menu_players_selected():
                self.start_menu_countdown()
            return
        if action == ACTION_BUBBLE:
            if state.selected_index is None:
                self.menu_deny(state, "PICK FIRST")
                return
            old_index = state.selected_index
            state.selected_index = None
            state.selected_at = 0.0
            state.cancel_until = now + MENU_DESELECT_ANIM
            self.cancel_menu_countdown()
            self.menu_notice = f"P{1 if state.player_id == 101 else 2} CANCELLED"
            self.menu_notice_until = now + 0.55
            self.play_menu_sound("menu_cancel")
            self.spawn_menu_cancel_fx(state.player_id, old_index)
            self.shake(0.08, 3.0)
            return
        self.menu_deny(state, "NOPE")

    def all_menu_players_selected(self):
        return all(state.selected_index is not None for state in self.menu_players.values())

    def start_menu_countdown(self):
        if self.match_state == "countdown":
            return
        now = time.time()
        self.match_state = "countdown"
        self.menu_countdown_started_at = now
        self.menu_countdown_last_step = -1
        self.menu_transition_started_at = 0.0

    def cancel_menu_countdown(self):
        if self.match_state in ("countdown", "starting"):
            self.match_state = "select"
            self.menu_countdown_started_at = 0.0
            self.menu_countdown_last_step = -1
            self.menu_transition_started_at = 0.0
            self.menu_notice = "WAIT!"
            self.menu_notice_until = time.time() + 0.65

    def menu_deny(self, state, label):
        now = time.time()
        state.deny_until = now + 0.24
        self.menu_notice = label
        self.menu_notice_until = now + 0.38
        self.play_menu_sound("menu_deny")
        self.shake(0.06, 2.2)
        x, y = self.menu_visual_cursor_pos(state.player_id)
        self.spawn_menu_sparks(x, y, PALETTE["bad"], 14, 260)

    def queue_action(self, player, action):
        now = time.time()
        for queued in self.pending_actions:
            if queued.player_id == player.player_id:
                queued.action = action
                queued.queued_at = now
                return
        self.pending_actions.append(QueuedAction(player.player_id, action, now))
        self.pending_actions.sort(key=lambda item: item.queued_at)

    def flush_queued_actions(self):
        if self.is_hit_stop_active() or self.match_state != "playing":
            return
        while self.pending_actions and self.match_state == "playing":
            queued = self.pending_actions.pop(0)
            player = self.players.get(queued.player_id)
            if player is not None:
                self.perform_action(player, queued.action)
            if self.is_hit_stop_active():
                break

    def perform_action(self, player, action):
        now = time.time()
        if not player.alive:
            self.sounds.play("invalid")
            return
        if action == ACTION_BEAM:
            if now < player.beam_ready_at:
                self.sounds.play("invalid")
                return
            player.beam_ready_at = now + BEAM_COOLDOWN
            self.fire_beam(player)
            self.sounds.play("swing", 0.45)
        elif action == ACTION_BUBBLE:
            if now < player.bubble_ready_at:
                self.sounds.play("invalid")
                return
            player.bubble_ready_at = now + BUBBLE_COOLDOWN
            player.bubble_until = now + BUBBLE_DURATION
            self.sounds.play("bubble")
            self.spawn_ring(player.x, player.y, PALETTE["bubble"], 34)
            self.send_fx("bubble")

    def assisted_beam_direction(self, player, target, dx, dy):
        if not target.alive:
            return dx, dy
        tx = target.x - player.x
        ty = target.y - player.y
        distance = math.hypot(tx, ty)
        if distance <= 0.001 or distance > BEAM_RANGE_M + PLAYER_RADIUS_M:
            return dx, dy
        target_heading = vec_heading(tx, ty)
        if abs(normalize_deg(target_heading - player.heading)) <= BEAM_AIM_ASSIST_DEG:
            return tx / distance, ty / distance
        return dx, dy

    def fire_beam(self, player):
        now = time.time()
        dx, dy = heading_vec(player.heading)
        target = self.players[102 if player.player_id == 101 else 101]
        dx, dy = self.assisted_beam_direction(player, target, dx, dy)
        start = (player.x + dx * 0.18, player.y + dy * 0.18)
        end = (player.x + dx * BEAM_RANGE_M, player.y + dy * BEAM_RANGE_M)
        hit_point = None
        blocked = False
        if target.alive:
            if target.bubble_active(now):
                distance, along = point_segment_distance(target.position(), start, end)
                if distance <= BUBBLE_RADIUS_M:
                    blocked = True
                    hit_point = target.position()
                    self.sounds.play("block")
                    self.spawn_burst(target.x, target.y, PALETTE["bubble"], 52, power=1.35)
                    self.shake(0.10, 4.0)
                    self.send_fx("bubble_block")
            if not blocked:
                distance, along = point_segment_distance(target.position(), start, end)
                if distance <= BEAM_WIDTH_M and along > 0.03:
                    hit_point = (
                        start[0] + (end[0] - start[0]) * along,
                        start[1] + (end[1] - start[1]) * along,
                    )
                    self.damage_player(player, target, hit_point)

        beam = BeamEffect(start, end, player.color, now, hit_point=hit_point, blocked=blocked)
        self.beams.append(beam)
        self.spawn_beam_particles(start, hit_point if hit_point else end, player.color)
        self.spawn_burst(start[0], start[1], player.color, 28, power=0.7)
        self.sounds.play("beam")
        self.send_fx("beam_fire")

    def damage_player(self, attacker, target, hit_point):
        now = time.time()
        target.hp -= 1
        self.sounds.play("hit")
        self.spawn_burst(hit_point[0], hit_point[1], PALETTE["white"], 34, power=1.0)
        self.spawn_burst(target.x, target.y, attacker.color, 28, power=0.8)
        self.add_impact(
            "hit", HIT_IMPACT_DURATION, attacker.color,
            attacker_id=attacker.player_id,
            target_id=target.player_id,
            hit_point=hit_point,
        )
        self.hit_stop_until = max(self.hit_stop_until, now + HIT_IMPACT_DURATION)
        self.shake(0.16, 8.0)
        self.send_fx("beam_hit")
        if target.hp <= 0:
            target.alive = False
            attacker.wins += 1
            self.handle_round_end(attacker, target)

    def handle_round_end(self, winner, loser):
        now = time.time()
        self.match_state = "round_over"
        self.round_reset_at = now + ROUND_RESET_DELAY
        self.pending_actions.clear()
        self.spawn_burst(loser.x, loser.y, PALETTE["soup"], 82, power=1.75)
        self.sounds.play("ko")
        self.send_fx("ko")
        if winner.wins >= WIN_ROUNDS:
            self.match_state = "match_over"
            self.round_message = f"{winner.label.upper()} WINS THE LAST BOWL"
            self.round_reset_at = now + 3.2
            self.sounds.play("round")
            self.send_fx("match_win")
        else:
            self.round_message = f"{winner.label.upper()} TAKES THE ROUND"

    def add_impact(self, kind, duration, color, attacker_id=None, target_id=None, hit_point=None):
        self.impact_frames.append(ImpactFrame(
            kind, time.time(), duration, color,
            attacker_id=attacker_id,
            target_id=target_id,
            hit_point=hit_point,
        ))

    def shake(self, duration, power):
        self.shake_until = max(self.shake_until, time.time() + duration)
        self.shake_power = max(self.shake_power, power)

    def spawn_burst(self, x, y, color, count, power=1.0):
        now = time.time()
        for _ in range(count):
            angle = random.random() * math.tau
            speed = random.uniform(0.6, 2.7) * power
            self.particles.append(Particle(
                x, y, math.cos(angle) * speed, math.sin(angle) * speed,
                color, random.uniform(0.035, 0.085) * power, now, random.uniform(0.22, 0.55)
            ))

    def spawn_ring(self, x, y, color, count):
        now = time.time()
        for i in range(count):
            angle = math.tau * i / count
            speed = random.uniform(0.55, 1.2)
            self.particles.append(Particle(
                x, y, math.cos(angle) * speed, math.sin(angle) * speed,
                color, 0.045, now, 0.42
            ))

    def spawn_beam_particles(self, start, end, color):
        now = time.time()
        sx, sy = start
        ex, ey = end
        vx = ex - sx
        vy = ey - sy
        length = max(0.001, math.hypot(vx, vy))
        nx, ny = -vy / length, vx / length
        for _ in range(72):
            t = random.random()
            jitter = random.uniform(-0.12, 0.12)
            x = sx + vx * t + nx * jitter
            y = sy + vy * t + ny * jitter
            drift = random.uniform(-0.8, 0.8)
            self.particles.append(Particle(
                x, y, nx * drift, ny * drift,
                color, random.uniform(0.018, 0.055), now, random.uniform(0.12, 0.34)
            ))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_RETURN:
                    if self.match_state in MENU_STATES:
                        if self.all_menu_players_selected():
                            self.start_menu_countdown()
                            self.play_menu_sound("menu_select", 0.9)
                        else:
                            self.menu_notice = "LOCK BOTH PLAYERS"
                            self.menu_notice_until = time.time() + 0.6
                            self.play_menu_sound("menu_deny")
                    else:
                        self.sounds.play("menu_select")
                        self.reset_match()
                elif event.key == pygame.K_m:
                    self.sounds.play("menu_move")
                elif event.key == pygame.K_d:
                    self.debug_radar = not self.debug_radar
                    self.sounds.play("menu_move")
                elif event.key == pygame.K_0:
                    self.calibration_select_until = time.time() + 6.0
                    self.log("calibrate: press 1 for P101 or 2 for P102")
                    self.sounds.play("menu_select")
                elif event.key in (pygame.K_1, pygame.K_2) and time.time() < self.calibration_select_until:
                    player_id = 101 if event.key == pygame.K_1 else 102
                    self.calibration_select_until = 0.0
                    if self.send_player_command(player_id, "MAGCAL", MAGCAL_COMMAND_MS):
                        self.set_local_magcal_requested(player_id, MAGCAL_COMMAND_MS)

    def update_fake_input(self, dt):
        keys = pygame.key.get_pressed()
        move_sets = {
            101: (pygame.K_a, pygame.K_d, pygame.K_w, pygame.K_s, pygame.K_q, pygame.K_e, pygame.K_f, pygame.K_r),
            102: (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN, pygame.K_COMMA, pygame.K_PERIOD, pygame.K_SLASH, pygame.K_RSHIFT),
        }
        for pid, keyset in move_sets.items():
            player = self.players[pid]
            left, right, up, down, aim_l, aim_r, beam_key, bubble_key = keyset
            mx = (1 if keys[right] else 0) - (1 if keys[left] else 0)
            my = (1 if keys[up] else 0) - (1 if keys[down] else 0)
            if mx or my:
                mag = math.hypot(mx, my)
                mx /= mag
                my /= mag
                old_x, old_y = player.x, player.y
                player.x = clamp(player.x + mx * dt * 1.6, ARENA_MIN_X, ARENA_MAX_X)
                player.y = clamp(player.y + my * dt * 1.6, ARENA_MIN_Y, ARENA_MAX_Y)
                player.vx = (player.x - old_x) / max(dt, 0.001)
                player.vy = (player.y - old_y) / max(dt, 0.001)
            else:
                player.vx *= 0.86
                player.vy *= 0.86
            if keys[aim_l]:
                player.heading = normalize_deg(player.heading - 180 * dt)
            if keys[aim_r]:
                player.heading = normalize_deg(player.heading + 180 * dt)
            if keys[beam_key] and not self.fake_actions[pid]:
                self.fake_actions[pid] = ACTION_BEAM
                self.request_action(player, ACTION_BEAM)
            elif keys[bubble_key] and not self.fake_actions[pid]:
                self.fake_actions[pid] = ACTION_BUBBLE
                self.request_action(player, ACTION_BUBBLE)
            elif not keys[beam_key] and not keys[bubble_key]:
                self.fake_actions[pid] = ACTION_NONE

    def update(self, dt):
        now = time.time()
        while True:
            try:
                kind, payload = self.incoming.get_nowait()
            except queue.Empty:
                break
            if kind == "SERIAL":
                self.handle_serial_line(payload)
            else:
                self.log(payload)

        if self.args.fake:
            self.update_fake_input(dt)

        if self.match_state in MENU_STATES:
            self.update_character_select(dt, now)

        if self.match_state in ("round_over", "match_over") and now >= self.round_reset_at:
            if self.match_state == "match_over":
                self.open_character_select()
            else:
                self.reset_round()

        self.flush_queued_actions()

        for player in self.players.values():
            player.sprite_phase += dt * (4.5 + min(3.0, math.hypot(player.vx, player.vy)))
            if not self.args.fake and player.track_updated_at and now - player.track_updated_at > RADAR_BLOB_TIMEOUT:
                player.vx *= 0.82
                player.vy *= 0.82
                player.track_confidence = max(0.0, player.track_confidence - 0.018)
                if now - player.track_updated_at > TRACK_LOST_AFTER * 2.0:
                    player.track_slot = None
        self.beams = [beam for beam in self.beams if now - beam.created_at < beam.duration]
        self.impact_frames = [frame for frame in self.impact_frames if now - frame.created_at < frame.duration]
        alive_particles = []
        for particle in self.particles:
            age = now - particle.created_at
            if age < particle.life:
                particle.x += particle.vx * dt
                particle.y += particle.vy * dt
                particle.vx *= 0.985
                particle.vy *= 0.985
                alive_particles.append(particle)
        self.particles = alive_particles[-900:]
        if now > self.shake_until:
            self.shake_power *= 0.85

    def update_character_select(self, dt, now):
        rects = self.menu_card_rects()
        for state in self.menu_players.values():
            if state.selected_index is None:
                cursor = self.menu_cursor_screen(self.players[state.player_id])
                hover = self.menu_hover_from_cursor(cursor, rects)
                if hover != state.hover_index:
                    state.hover_index = hover
                    state.hover_changed_at = now
                    sound = "menu_hover_p1" if state.player_id == 101 else "menu_hover_p2"
                    self.play_menu_sound(sound)
                    cx, cy = rects[hover].center
                    self.spawn_menu_sparks(cx, cy, self.menu_player_base_color(state.player_id), 10, 180)
            visual = self.menu_visual_cursor_pos(state.player_id, rects)
            state.cursor_history.append((visual[0], visual[1], now))
            state.cursor_history = state.cursor_history[-MENU_CURSOR_HISTORY:]

        if self.match_state == "countdown":
            self.update_menu_countdown(now)
        elif self.match_state == "starting":
            if self.menu_transition_started_at and now - self.menu_transition_started_at >= MENU_TRANSITION_DELAY:
                self.reset_match()

        alive_particles = []
        for particle in self.menu_particles:
            age = now - particle.created_at
            if age < particle.life:
                particle.x += particle.vx * dt
                particle.y += particle.vy * dt
                particle.vx *= 0.972
                particle.vy *= 0.972
                if particle.kind == "fire":
                    particle.vy -= 18.0 * dt
                particle.spin += dt * 12.0
                alive_particles.append(particle)
        self.menu_particles = alive_particles[-1200:]

        self.menu_slashes = [
            slash for slash in self.menu_slashes
            if now - slash.created_at < slash.life
        ][-80:]

    def update_menu_countdown(self, now):
        if not self.all_menu_players_selected():
            self.cancel_menu_countdown()
            return
        if self.menu_countdown_started_at <= 0.0:
            self.menu_countdown_started_at = now
        labels = ("3", "2", "1", "GO!")
        elapsed = now - self.menu_countdown_started_at
        step = int(elapsed / MENU_COUNTDOWN_STEP)
        if step < len(labels) and step != self.menu_countdown_last_step:
            self.menu_countdown_last_step = step
            sound = ("count_3", "count_2", "count_1", "count_go")[step]
            self.play_menu_sound(sound)
            self.spawn_menu_countdown_fx(labels[step], step)
            self.shake(0.10 if step < 3 else 0.20, 5.0 if step < 3 else MENU_SHAKE_GO)
        if step >= len(labels) and self.menu_transition_started_at <= 0.0:
            self.match_state = "starting"
            self.menu_transition_started_at = now
            self.play_menu_sound("menu_transition")
            self.spawn_menu_transition_fx()
            self.shake(0.24, MENU_SHAKE_GO)

    def menu_player_base_color(self, player_id):
        return PALETTE["p1"] if player_id == 101 else PALETTE["p2"]

    def selected_character_for_player(self, player_id):
        state = self.menu_players.get(player_id)
        if state is None or state.selected_index is None:
            return None
        return CHARACTER_SLOTS[state.selected_index]

    def menu_card_rects(self):
        w, h = self.screen.get_size()
        card_w = min(230, max(132, int(w * 0.145)))
        card_h = min(250, max(158, int(h * 0.245)))
        gap_x = max(18, int(w * 0.018))
        gap_y = max(16, int(h * 0.034))
        grid_w = card_w * 3 + gap_x * 2
        grid_h = card_h * 2 + gap_y
        top = max(132, int(h * 0.22))
        if top + grid_h > h - 92:
            top = max(112, h - 92 - grid_h)
        left = (w - grid_w) // 2
        rects = []
        for index in range(6):
            col = index % 3
            row = index // 3
            rects.append(pygame.Rect(left + col * (card_w + gap_x), top + row * (card_h + gap_y), card_w, card_h))
        return rects

    def menu_cursor_screen(self, player):
        w, h = self.screen.get_size()
        tx = (player.x - ARENA_MIN_X) / (ARENA_MAX_X - ARENA_MIN_X)
        ty = (player.y - ARENA_MIN_Y) / (ARENA_MAX_Y - ARENA_MIN_Y)
        sx = lerp(w * 0.12, w * 0.88, clamp(tx, 0.0, 1.0))
        sy = lerp(h * 0.76, h * 0.24, clamp(ty, 0.0, 1.0))
        return sx, sy

    def menu_hover_from_cursor(self, cursor, rects):
        cx, cy = cursor
        best_index = 0
        best_score = float("inf")
        for index, rect in enumerate(rects):
            dx = cx - rect.centerx
            dy = cy - rect.centery
            score = dx * dx + dy * dy
            if rect.inflate(54, 54).collidepoint(cx, cy):
                score *= 0.35
            if score < best_score:
                best_index = index
                best_score = score
        return best_index

    def menu_visual_cursor_pos(self, player_id, rects=None):
        player = self.players[player_id]
        state = self.menu_players[player_id]
        rects = rects or self.menu_card_rects()
        if state.selected_index is not None:
            rect = rects[state.selected_index]
            side = -1 if player_id == 101 else 1
            bob = math.sin(time.time() * 10.0 + player_id) * 5.0
            return rect.centerx + side * rect.width * 0.23, rect.top + rect.height * 0.18 + bob
        return self.menu_cursor_screen(player)

    def spawn_menu_sparks(self, x, y, color, count, speed):
        now = time.time()
        for _ in range(count):
            angle = random.random() * math.tau
            vel = random.uniform(speed * 0.35, speed)
            size = random.uniform(3.0, 8.0)
            self.menu_particles.append(MenuParticle(
                x, y, math.cos(angle) * vel, math.sin(angle) * vel,
                color, size, now, random.uniform(0.18, 0.42), "spark",
                random.uniform(-1.0, 1.0),
            ))

    def spawn_menu_pixel_fire(self, x, y, character, count):
        now = time.time()
        colors = (character["dark"], character["theme"], character["secondary"], character["highlight"])
        for _ in range(count):
            color = random.choice(colors)
            self.menu_particles.append(MenuParticle(
                x + random.uniform(-46, 46),
                y + random.uniform(-10, 30),
                random.uniform(-42, 42),
                random.uniform(-155, -55),
                color,
                random.uniform(5, 14),
                now,
                random.uniform(0.30, 0.78),
                "fire",
                random.uniform(-2.5, 2.5),
            ))

    def spawn_menu_slash(self, x, y, color, count=3, spread=0.55):
        now = time.time()
        for _ in range(count):
            angle = random.uniform(-spread, spread) + random.choice((0.0, math.pi))
            self.menu_slashes.append(MenuSlash(
                x + random.uniform(-24, 24),
                y + random.uniform(-20, 20),
                angle,
                random.uniform(120, 260),
                color,
                now,
                random.uniform(0.16, 0.28),
                random.uniform(13, 26),
            ))

    def spawn_menu_lock_fx(self, player_id, index):
        rect = self.menu_card_rects()[index]
        character = CHARACTER_SLOTS[index]
        self.spawn_menu_sparks(rect.centerx, rect.centery, character["highlight"], 36, 390)
        self.spawn_menu_pixel_fire(rect.centerx, rect.bottom - 12, character, 34)
        self.spawn_menu_slash(rect.centerx, rect.centery, character["theme"], 5)

    def spawn_menu_cancel_fx(self, player_id, index):
        rect = self.menu_card_rects()[index]
        color = self.menu_player_base_color(player_id)
        self.spawn_menu_sparks(rect.centerx, rect.centery, color, 22, 280)
        self.spawn_menu_slash(rect.centerx, rect.centery, PALETTE["bad"], 3, spread=0.95)

    def spawn_menu_countdown_fx(self, label, step):
        w, h = self.screen.get_size()
        p1_char = self.selected_character_for_player(101) or CHARACTER_SLOTS[0]
        p2_char = self.selected_character_for_player(102) or CHARACTER_SLOTS[1]
        color = (p1_char["theme"], p2_char["theme"], PALETTE["soup"], PALETTE["white"])[min(step, 3)]
        self.spawn_menu_sparks(w // 2, h // 2, color, 42 + step * 12, 430 + step * 90)
        self.spawn_menu_slash(w // 2, h // 2, color, 5 + step)
        if step >= 3:
            self.play_menu_sound("menu_fire", 1.0)
            self.spawn_menu_pixel_fire(w // 2, h // 2 + 90, p1_char, 55)
            self.spawn_menu_pixel_fire(w // 2, h // 2 + 90, p2_char, 55)

    def spawn_menu_transition_fx(self):
        w, h = self.screen.get_size()
        p1_char = self.selected_character_for_player(101) or CHARACTER_SLOTS[0]
        p2_char = self.selected_character_for_player(102) or CHARACTER_SLOTS[1]
        self.spawn_menu_sparks(w * 0.32, h * 0.52, p1_char["highlight"], 70, 520)
        self.spawn_menu_sparks(w * 0.68, h * 0.52, p2_char["highlight"], 70, 520)
        self.spawn_menu_slash(w // 2, h // 2, PALETTE["white"], 9, spread=0.22)

    def world_rect(self):
        margin = max(34, self.screen.get_width() // 28)
        hud = max(128, self.screen.get_height() // 6)
        bottom = max(52, self.screen.get_height() // 18)
        return pygame.Rect(margin, hud, self.screen.get_width() - margin * 2, self.screen.get_height() - hud - bottom)

    def world_to_screen(self, x, y, offset=(0, 0)):
        rect = self.world_rect()
        sx = rect.left + (x - ARENA_MIN_X) / (ARENA_MAX_X - ARENA_MIN_X) * rect.width
        sy = rect.bottom - (y - ARENA_MIN_Y) / (ARENA_MAX_Y - ARENA_MIN_Y) * rect.height
        return int(sx + offset[0]), int(sy + offset[1])

    def meters_to_px(self, meters):
        rect = self.world_rect()
        return int(meters / (ARENA_MAX_X - ARENA_MIN_X) * rect.width)

    def render(self):
        now = time.time()
        offset = (0, 0)
        if now < self.shake_until or self.shake_power > 0.5:
            power = self.shake_power
            offset = (random.randint(int(-power), int(power)), random.randint(int(-power), int(power)))
        if self.match_state in MENU_STATES:
            self.draw_character_select(offset)
            self.draw_magcal_overlay()
            pygame.display.flip()
            return
        self.draw_background()
        self.draw_arena(offset)
        if self.debug_radar:
            self.draw_radar_debug(offset)
        self.draw_particles(offset, below=True)
        for beam in self.beams:
            self.draw_beam(beam, offset)
        for player in self.players.values():
            self.draw_bubble(player, offset)
        for player in sorted(self.players.values(), key=lambda p: p.y, reverse=True):
            self.draw_player(player, offset)
        self.draw_particles(offset, below=False)
        self.draw_hud()
        self.draw_messages()
        self.draw_magcal_overlay()
        self.draw_impact_frames()
        pygame.display.flip()

    def draw_background(self):
        size = self.screen.get_size()
        if self.bg_cache is None or self.bg_cache_size != size:
            self.bg_cache_size = size
            self.bg_cache = pygame.Surface(size)
            h = max(1, size[1])
            for y in range(size[1]):
                t = y / h
                r = int(PALETTE["bg"][0] * (1 - t) + 31 * t)
                g = int(PALETTE["bg"][1] * (1 - t) + 21 * t)
                b = int(PALETTE["bg"][2] * (1 - t) + 15 * t)
                pygame.draw.line(self.bg_cache, (r, g, b), (0, y), (size[0], y))
            for i in range(0, size[0] + size[1], 82):
                pygame.draw.line(self.bg_cache, (36, 24, 19), (i, 0), (i - size[1], size[1]), 1)
        self.screen.blit(self.bg_cache, (0, 0))

    def draw_text_center(self, font, text, color, center, shadow=True):
        rendered = font.render(text, True, color)
        rect = rendered.get_rect(center=center)
        if shadow:
            shadow_surf = font.render(text, True, (32, 19, 13))
            self.screen.blit(shadow_surf, rect.move(3, 4))
        self.screen.blit(rendered, rect)
        return rect

    def draw_character_select(self, offset=(0, 0)):
        target = self.screen
        canvas = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        old_screen = self.screen
        try:
            self.screen = canvas
            now = time.time()
            rects = self.menu_card_rects()
            self.draw_menu_background(now)
            self.draw_menu_side_panel(101, now)
            self.draw_menu_side_panel(102, now)
            self.draw_menu_cards(rects, now)
            self.draw_menu_particles(now, below=True)
            for pid in (101, 102):
                self.draw_menu_cursor(pid, now, rects)
            self.draw_menu_particles(now, below=False)
            self.draw_menu_notice(now)
            self.draw_menu_countdown_overlay(now)
            self.draw_menu_transition(now)
        finally:
            self.screen = old_screen
        target.fill((0, 0, 0))
        target.blit(canvas, offset)

    def draw_menu_background(self, now):
        w, h = self.screen.get_size()
        self.screen.fill((14, 11, 12))
        pygame.draw.polygon(
            self.screen,
            rgba(PALETTE["p1"], 34),
            [(-80, 0), (w * 0.46, 0), (w * 0.35, h), (-120, h)],
        )
        pygame.draw.polygon(
            self.screen,
            rgba(PALETTE["p2"], 34),
            [(w * 0.54, 0), (w + 80, 0), (w + 120, h), (w * 0.65, h)],
        )
        for i in range(38):
            y = (i * 43 + now * 45) % (h + 120) - 60
            x = (i * 97 + now * 95) % (w + 240) - 120
            length = 74 + (i % 5) * 34
            color = rgba(PALETTE["light_brown"] if i % 3 else PALETTE["soup_deep"], 26 + (i % 4) * 9)
            self.draw_slanted_strip(x, y, length, 7 + (i % 3) * 3, -0.34, color)
        self.draw_halftone_field((56, 120), 170, PALETTE["p1"], 0.36, now)
        self.draw_halftone_field((w - 54, h - 110), 190, PALETTE["p2"], 0.34, now + 0.7)
        for i in range(18):
            x = (i * 151 + now * 28) % (w + 80) - 40
            y = 78 + math.sin(now * 1.7 + i) * 16
            self.draw_pixel_diamond(x, y, 5 + i % 4, rgba(PALETTE["soup"], 42))

        title_y = max(54, h // 12)
        self.draw_text_center(self.title_font, "SOUPOCALYPSE", PALETTE["soup"], (w // 2, title_y))
        self.draw_text_center(self.font, "THE LAST BOWL", PALETTE["light_brown"], (w // 2, title_y + 54), shadow=False)
        self.draw_skew_panel(
            pygame.Rect(w // 2 - min(330, w // 4), title_y + 78, min(660, w // 2), 32),
            rgba(PALETTE["panel_2"], 210),
            rgba(PALETTE["soup_deep"], 190),
            cut=16,
        )
        label = self.small_font.render("CHOOSE YOUR FIGHTER", True, PALETTE["beige"])
        self.screen.blit(label, (w // 2 - label.get_width() // 2, title_y + 84))

    def draw_menu_side_panel(self, player_id, now):
        w, h = self.screen.get_size()
        side = -1 if player_id == 101 else 1
        panel_w = min(360, max(230, w // 4))
        panel_h = min(h - 170, max(390, int(h * 0.66)))
        x = 22 if side < 0 else w - panel_w - 22
        y = max(126, int(h * 0.19))
        state = self.menu_players[player_id]
        character = self.selected_character_for_player(player_id)
        base_color = self.menu_player_base_color(player_id)
        theme = character["theme"] if character else base_color
        dark = character["dark"] if character else PALETTE["panel_2"]
        highlight = character["highlight"] if character else PALETTE["beige"]
        reveal = 1.0
        if character:
            reveal = ease_out_back((now - state.selected_at) / MENU_PANEL_REVEAL)
        slide = int((1.0 - reveal) * 90 * side)
        rect = pygame.Rect(x + slide, y, panel_w, panel_h)

        self.draw_skew_panel(rect.move(0, 10), (0, 0, 0, 150), None, cut=28)
        self.draw_skew_panel(rect, rgba(dark, 232), rgba(theme, 240), cut=28, border_width=4)
        self.draw_jagged_splash(
            (rect.centerx + side * 24, rect.centery - 40),
            min(panel_w, panel_h) * 0.42,
            theme,
            seed=player_id + (state.selected_index or 0) * 41,
            alpha=72 if character else 34,
            stretch=(0.88, 1.18),
        )

        badge = "P1" if player_id == 101 else "P2"
        self.draw_menu_badge(badge, (rect.left + 40 if side < 0 else rect.right - 40, rect.top + 28), base_color, anchor="left" if side < 0 else "right")

        if character:
            art = self.character_portrait(state.selected_index)
            art_rect = pygame.Rect(rect.left + 26, rect.top + 84, rect.width - 52, int(rect.height * 0.52))
            bob = math.sin(now * 3.2 + player_id) * 6
            self.blit_fit(art, art_rect.move(0, int(bob)), alpha=255)
            self.spawn_panel_fire_trickle(rect, character, now)
            name_rect = pygame.Rect(rect.left + 18, rect.bottom - 106, rect.width - 36, 58)
            self.draw_skew_panel(name_rect, rgba(PALETTE["bg"], 232), rgba(highlight, 220), cut=14, border_width=2)
            name = self.fit_text(self.font, character["name"].upper(), name_rect.width - 22, highlight)
            self.screen.blit(name, (name_rect.centerx - name.get_width() // 2, name_rect.top + 9))
            tag = self.small_font.render(character["tagline"].upper(), True, PALETTE["light_brown"])
            self.screen.blit(tag, (name_rect.centerx - tag.get_width() // 2, name_rect.bottom - tag.get_height() - 7))
            locked = self.big_font.render("LOCKED!", True, theme)
            locked_rect = locked.get_rect(center=(rect.centerx, rect.bottom - 28))
            shadow = self.big_font.render("LOCKED!", True, (0, 0, 0))
            self.screen.blit(shadow, locked_rect.move(3, 4))
            self.screen.blit(locked, locked_rect)
        else:
            ghost = pygame.Rect(rect.left + 34, rect.top + 100, rect.width - 68, rect.height - 190)
            for i in range(5):
                yy = ghost.top + i * ghost.height // 5 + int(math.sin(now * 2.0 + i) * 4)
                self.draw_slanted_strip(ghost.left, yy, ghost.width, 12, 0.24 * side, rgba(theme, 40 + i * 8))
            large = self.title_font.render(badge, True, rgba(theme, 230))
            self.screen.blit(large, large.get_rect(center=(rect.centerx, rect.centery - 16)))
            choosing = self.font.render("CHOOSING", True, PALETTE["beige"])
            self.screen.blit(choosing, choosing.get_rect(center=(rect.centerx, rect.bottom - 70)))

    def spawn_panel_fire_trickle(self, rect, character, now):
        if len(self.menu_particles) > 1000:
            return
        if int(now * 12 + rect.left) % 5:
            return
        for _ in range(3):
            self.menu_particles.append(MenuParticle(
                random.uniform(rect.left + 42, rect.right - 42),
                random.uniform(rect.bottom - 72, rect.bottom - 44),
                random.uniform(-12, 12),
                random.uniform(-72, -28),
                random.choice((character["theme"], character["secondary"], character["highlight"])),
                random.uniform(4, 9),
                now,
                random.uniform(0.32, 0.62),
                "fire",
            ))

    def draw_menu_cards(self, rects, now):
        for index, rect in enumerate(rects):
            hoverers = [
                state.player_id for state in self.menu_players.values()
                if state.selected_index is None and state.hover_index == index
            ]
            lockers = [
                state.player_id for state in self.menu_players.values()
                if state.selected_index == index
            ]
            hover_pop = 0.0
            for state in self.menu_players.values():
                if state.hover_index == index and state.selected_index is None:
                    hover_pop = max(hover_pop, 1.0 - clamp((now - state.hover_changed_at) / MENU_HOVER_ANIM, 0.0, 1.0))
            lock_pop = 0.0
            for state in self.menu_players.values():
                if state.selected_index == index:
                    lock_pop = max(lock_pop, 1.0 - clamp((now - state.selected_at) / MENU_SELECT_SLAM, 0.0, 1.0))
            scale = 1.0 + 0.045 * bool(hoverers) + 0.065 * ease_out_cubic(lock_pop)
            draw_rect = rect.inflate(int(rect.width * (scale - 1.0)), int(rect.height * (scale - 1.0)))
            draw_rect.center = rect.center
            self.draw_menu_card(index, draw_rect, hoverers, lockers, now, hover_pop, lock_pop)

    def draw_menu_card(self, index, rect, hoverers, lockers, now, hover_pop, lock_pop):
        character = CHARACTER_SLOTS[index]
        theme = character["theme"]
        dark = character["dark"]
        highlight = character["highlight"]
        jitter_x = int(math.sin(now * 22 + index) * 3 * lock_pop)
        jitter_y = int(math.cos(now * 19 + index) * 3 * lock_pop)
        rect = rect.move(jitter_x, jitter_y)

        self.draw_skew_panel(rect.move(0, 8), (0, 0, 0, 170), None, cut=18)
        self.draw_jagged_splash(
            (rect.centerx, rect.centery - rect.height * 0.12),
            rect.width * (0.56 + 0.08 * math.sin(now * 3 + index)),
            theme,
            seed=index * 91 + 3,
            alpha=58 + 45 * bool(lockers),
            stretch=(1.05, 0.70),
        )
        self.draw_skew_panel(rect, rgba(dark, 238), rgba(theme, 210), cut=18, border_width=3)
        inner = rect.inflate(-14, -14)
        self.draw_skew_panel(inner, rgba(PALETTE["panel"], 220), rgba(highlight, 80), cut=12, border_width=1)

        portrait_rect = pygame.Rect(inner.left + 10, inner.top + 10, inner.width - 20, inner.height - 70)
        pygame.draw.polygon(
            self.screen,
            rgba(theme, 42),
            [
                (portrait_rect.left + 12, portrait_rect.top),
                (portrait_rect.right, portrait_rect.top + 8),
                (portrait_rect.right - 10, portrait_rect.bottom),
                (portrait_rect.left, portrait_rect.bottom - 12),
            ],
        )
        self.blit_fit(self.character_portrait(index), portrait_rect)

        name_rect = pygame.Rect(inner.left + 4, inner.bottom - 56, inner.width - 8, 34)
        self.draw_skew_panel(name_rect, rgba((12, 10, 10), 224), rgba(theme, 180), cut=10, border_width=2)
        name = self.fit_text(self.font, character["name"].upper(), name_rect.width - 14, PALETTE["beige"])
        self.screen.blit(name, (name_rect.centerx - name.get_width() // 2, name_rect.centery - name.get_height() // 2))
        tag = self.fit_text(self.small_font, character["tagline"].upper(), inner.width - 22, rgba(highlight, 230))
        self.screen.blit(tag, (inner.centerx - tag.get_width() // 2, inner.bottom - 17))

        if hoverers:
            pulse = 0.55 + 0.45 * math.sin(now * 18 + index)
            for n, pid in enumerate(hoverers):
                color = self.menu_player_base_color(pid)
                outline = rect.inflate(14 + n * 10 + int(hover_pop * 8), 14 + n * 10 + int(hover_pop * 8))
                self.draw_skew_panel(outline, (0, 0, 0, 0), rgba(color, 160 + 80 * pulse), cut=22, border_width=4)
                label = "P1?" if pid == 101 else "P2?"
                anchor_x = outline.left + 36 + n * 48 if pid == 101 else outline.right - 36 - n * 48
                self.draw_menu_badge(label, (anchor_x, outline.top + 18), color)
            self.draw_menu_card_sparks(rect, hoverers, now)

        if lockers:
            for n, pid in enumerate(lockers):
                label = "P1 LOCK" if pid == 101 else "P2 LOCK"
                color = self.menu_player_base_color(pid)
                badge_y = rect.top + 20 + n * 34
                self.draw_menu_badge(label, (rect.centerx, badge_y), color)
            self.draw_skew_panel(rect.inflate(24, 24), (0, 0, 0, 0), rgba(highlight, 230), cut=26, border_width=5)
            if lock_pop > 0.0:
                self.draw_starburst((rect.centerx, rect.centery), rect.width * (0.36 + lock_pop * 0.22), highlight, 120 * lock_pop, seed=index + 19)

    def draw_menu_card_sparks(self, rect, hoverers, now):
        if int(now * 18 + rect.left) % 4:
            return
        color = self.menu_player_base_color(hoverers[0])
        x = random.choice((rect.left, rect.right)) + random.uniform(-10, 10)
        y = random.uniform(rect.top + 24, rect.bottom - 24)
        self.spawn_menu_sparks(x, y, color, 2, 110)

    def draw_menu_cursor(self, player_id, now, rects):
        state = self.menu_players[player_id]
        base = self.menu_player_base_color(player_id)
        character = self.selected_character_for_player(player_id)
        color = character["theme"] if character else base
        x, y = self.menu_visual_cursor_pos(player_id, rects)
        bob = math.sin(now * 7.0 + player_id) * 3.5
        x += math.sin(now * 4.3 + player_id) * 2.0
        y += bob

        for i, (hx, hy, ht) in enumerate(state.cursor_history):
            age = now - ht
            frac = clamp(1.0 - age / 0.26, 0.0, 1.0)
            if frac <= 0:
                continue
            self.draw_slanted_strip(hx - 24 * frac, hy + 12 * frac, 46 * frac, 6 + 5 * frac, -0.32, rgba(base, 90 * frac))

        deny = clamp((state.deny_until - now) / 0.24, 0.0, 1.0)
        if deny > 0.0:
            x += math.sin(now * 90) * 8 * deny
        side = 1 if player_id == 101 else -1
        points = self.cursor_points(x, y, side, 1.0 + 0.08 * bool(character))
        shadow = [(px + 4, py + 5) for px, py in points]
        pygame.draw.polygon(self.screen, (0, 0, 0, 180), shadow)
        pygame.draw.polygon(self.screen, rgba(color, 245), points)
        pygame.draw.polygon(self.screen, PALETTE["white"], points, 3)
        inner = self.cursor_points(x + side * 2, y + 1, side, 0.62)
        pygame.draw.polygon(self.screen, rgba(base, 235), inner)
        label = "P1" if player_id == 101 else "P2"
        text = self.small_font.render(label, True, (8, 8, 8))
        self.screen.blit(text, text.get_rect(center=(x - side * 3, y + 5)))
        if character:
            stamp = self.small_font.render("LOCKED", True, PALETTE["white"])
            stamp_rect = stamp.get_rect(center=(x, y + 43))
            self.draw_skew_panel(stamp_rect.inflate(18, 8), rgba(character["dark"], 230), rgba(character["highlight"], 200), cut=6, border_width=1)
            self.screen.blit(stamp, stamp_rect)

    def cursor_points(self, x, y, side, scale):
        pts = [
            (0, -34), (34, -2), (14, 3), (25, 31),
            (4, 23), (-16, 39), (-21, 10), (-44, 2),
        ]
        return [(x + px * side * scale, y + py * scale) for px, py in pts]

    def draw_menu_particles(self, now, below):
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for slash in self.menu_slashes:
            age = now - slash.created_at
            frac = clamp(1.0 - age / max(0.001, slash.life), 0.0, 1.0)
            if below != (slash.width > 18):
                continue
            self.draw_slash_on(surf, slash, frac)
        for particle in self.menu_particles:
            age = now - particle.created_at
            frac = clamp(1.0 - age / max(0.001, particle.life), 0.0, 1.0)
            is_big = particle.kind == "fire"
            if below != is_big:
                continue
            alpha = channel(235 * frac)
            size = max(2, int(particle.size * (0.55 + frac)))
            if particle.kind == "spark":
                points = [
                    (particle.x, particle.y - size),
                    (particle.x + size, particle.y),
                    (particle.x, particle.y + size),
                    (particle.x - size, particle.y),
                ]
                pygame.draw.polygon(surf, rgba(particle.color, alpha), points)
            else:
                rect = pygame.Rect(0, 0, size, size)
                rect.center = (particle.x, particle.y)
                pygame.draw.rect(surf, rgba(particle.color, alpha), rect)
                if frac > 0.5:
                    inner = rect.inflate(-max(1, size // 3), -max(1, size // 3))
                    pygame.draw.rect(surf, rgba(PALETTE["white"], 120 * frac), inner)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw_menu_notice(self, now):
        if now >= self.menu_notice_until or not self.menu_notice:
            return
        w, h = self.screen.get_size()
        frac = clamp((self.menu_notice_until - now) / 0.55, 0.0, 1.0)
        y = h * 0.16 + math.sin(now * 38) * 2
        surf = self.font.render(self.menu_notice, True, PALETTE["white"])
        rect = surf.get_rect(center=(w // 2, y))
        self.draw_starburst(rect.center, max(58, rect.width * 0.42), PALETTE["soup_deep"], 95 * frac, seed=len(self.menu_notice))
        self.draw_skew_panel(rect.inflate(34, 16), rgba(PALETTE["bg"], 220 * frac), rgba(PALETTE["soup"], 220 * frac), cut=12, border_width=2)
        self.screen.blit(surf, rect)

    def draw_menu_countdown_overlay(self, now):
        if self.match_state not in ("countdown", "starting"):
            return
        labels = ("3", "2", "1", "GO!")
        elapsed = max(0.0, now - self.menu_countdown_started_at)
        step = min(len(labels) - 1, int(elapsed / MENU_COUNTDOWN_STEP))
        local = (elapsed - step * MENU_COUNTDOWN_STEP) / MENU_COUNTDOWN_STEP
        label = labels[step]
        w, h = self.screen.get_size()
        p1 = self.selected_character_for_player(101) or CHARACTER_SLOTS[0]
        p2 = self.selected_character_for_player(102) or CHARACTER_SLOTS[1]
        center = (w // 2 + int(math.sin(now * 42) * (2 + step)), h // 2)
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(overlay, rgba(p1["theme"], 90), [(-60, h * 0.25), (w * 0.48, h * 0.43), (w * 0.44, h * 0.62), (-90, h * 0.78)])
        pygame.draw.polygon(overlay, rgba(p2["theme"], 90), [(w + 60, h * 0.22), (w * 0.52, h * 0.43), (w * 0.56, h * 0.64), (w + 90, h * 0.82)])
        self.screen.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)
        self.draw_starburst(center, 130 + step * 18, PALETTE["white"] if step == 3 else PALETTE["soup"], 205, seed=step * 8 + 1)
        self.draw_starburst(center, 190 + 25 * math.sin(now * 8), p1["theme"], 76, seed=37)
        self.draw_starburst(center, 174 + 22 * math.cos(now * 7), p2["theme"], 76, seed=48)
        scale = 1.35 + 0.44 * (1.0 - ease_out_cubic(local))
        angle = math.sin((local + step) * math.tau) * (7 if step < 3 else 3)
        text = self.title_font.render(label, True, (12, 10, 10) if step < 3 else PALETTE["white"])
        text = pygame.transform.rotozoom(text, angle, scale)
        text_rect = text.get_rect(center=center)
        shadow = text.copy()
        shadow.fill((0, 0, 0, 190), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(shadow, text_rect.move(7, 8))
        self.screen.blit(text, text_rect)
        for i in range(12 + step * 4):
            angle_i = i * math.tau / (12 + step * 4) + now * 0.6
            length = 96 + i % 4 * 32
            x1 = center[0] + math.cos(angle_i) * 86
            y1 = center[1] + math.sin(angle_i) * 64
            x2 = center[0] + math.cos(angle_i) * (86 + length)
            y2 = center[1] + math.sin(angle_i) * (64 + length * 0.54)
            pygame.draw.line(self.screen, rgba(PALETTE["white"], 120), (x1, y1), (x2, y2), 3)

    def draw_menu_transition(self, now):
        if self.match_state != "starting" or self.menu_transition_started_at <= 0:
            return
        w, h = self.screen.get_size()
        t = ease_out_cubic((now - self.menu_transition_started_at) / MENU_TRANSITION_DELAY)
        p1 = self.selected_character_for_player(101) or CHARACTER_SLOTS[0]
        p2 = self.selected_character_for_player(102) or CHARACTER_SLOTS[1]
        left_x = int(lerp(-w * 0.25, w * 0.62, t))
        right_x = int(lerp(w * 1.25, w * 0.38, t))
        pygame.draw.polygon(self.screen, rgba(p1["theme"], 235), [(-80, -40), (left_x, -40), (left_x - 160, h + 40), (-100, h + 40)])
        pygame.draw.polygon(self.screen, rgba(p2["theme"], 235), [(w + 80, -40), (right_x, -40), (right_x + 160, h + 40), (w + 100, h + 40)])
        for i in range(18):
            y = i * h / 17
            self.draw_slanted_strip(lerp(-180, w + 60, t) - i * 24, y, 220, 9, -0.45, rgba(PALETTE["white"], 120))
        label = self.big_font.render("FIGHT!", True, PALETTE["white"])
        label = pygame.transform.rotozoom(label, -5 + 10 * t, 1.0 + t * 0.35)
        self.screen.blit(label, label.get_rect(center=(w // 2, h // 2)))

    def draw_skew_panel(self, rect, fill, border=None, cut=18, border_width=3):
        cut = min(cut, rect.width // 3, rect.height // 2)
        points = [
            (rect.left + cut, rect.top),
            (rect.right, rect.top),
            (rect.right - cut, rect.bottom),
            (rect.left, rect.bottom),
        ]
        if fill and (len(fill) < 4 or fill[3] > 0):
            pygame.draw.polygon(self.screen, fill, points)
        if border and border_width > 0 and (len(border) < 4 or border[3] > 0):
            pygame.draw.polygon(self.screen, border, points, border_width)

    def draw_menu_badge(self, text, center, color, anchor="center"):
        surf = self.small_font.render(text, True, (12, 10, 10))
        rect = surf.get_rect()
        if anchor == "left":
            rect.midleft = center
        elif anchor == "right":
            rect.midright = center
        else:
            rect.center = center
        bg = rect.inflate(20, 10)
        self.draw_skew_panel(bg.move(3, 4), (0, 0, 0, 150), None, cut=6)
        self.draw_skew_panel(bg, rgba(color, 245), rgba(PALETTE["white"], 210), cut=6, border_width=2)
        self.screen.blit(surf, rect)

    def draw_jagged_splash(self, center, radius, color, seed, alpha=90, stretch=(1.0, 1.0)):
        rng = random.Random(seed)
        points = []
        count = 16
        for i in range(count):
            angle = i * math.tau / count
            r = radius * rng.uniform(0.58, 1.18)
            x = center[0] + math.cos(angle) * r * stretch[0]
            y = center[1] + math.sin(angle) * r * stretch[1]
            points.append((x, y))
        pygame.draw.polygon(self.screen, rgba(color, alpha), points)
        for _ in range(5):
            angle = rng.random() * math.tau
            dist = radius * rng.uniform(0.45, 1.25)
            x = center[0] + math.cos(angle) * dist * stretch[0]
            y = center[1] + math.sin(angle) * dist * stretch[1]
            self.draw_pixel_diamond(x, y, rng.uniform(5, 13), rgba(color, alpha * 0.78))

    def draw_starburst(self, center, radius, color, alpha, seed=1):
        rng = random.Random(seed)
        points = []
        count = 18
        for i in range(count):
            angle = i * math.tau / count
            r = radius * (1.0 if i % 2 == 0 else rng.uniform(0.34, 0.62))
            points.append((center[0] + math.cos(angle) * r, center[1] + math.sin(angle) * r))
        pygame.draw.polygon(self.screen, rgba(color, alpha), points)

    def draw_halftone_field(self, center, radius, color, strength, now):
        step = 18
        cx, cy = center
        for ix in range(-7, 8):
            for iy in range(-7, 8):
                x = cx + ix * step
                y = cy + iy * step
                dist = math.hypot(x - cx, y - cy)
                if dist > radius:
                    continue
                wave = 0.5 + 0.5 * math.sin(now * 2.4 + ix * 0.7 + iy * 0.4)
                size = int((1.0 - dist / radius) * 8 * strength + wave * 3)
                if size > 0:
                    pygame.draw.rect(self.screen, rgba(color, 48), (x, y, size, size))

    def draw_slanted_strip(self, x, y, length, height, slant, color):
        dx = height * slant
        points = [(x + dx, y), (x + length + dx, y), (x + length - dx, y + height), (x - dx, y + height)]
        pygame.draw.polygon(self.screen, color, points)

    def draw_slash_on(self, surf, slash, frac):
        length = slash.length * (0.35 + 0.65 * frac)
        width = slash.width * frac
        ux = math.cos(slash.angle)
        uy = math.sin(slash.angle)
        px = -uy
        py = ux
        cx = slash.x + ux * slash.length * (1.0 - frac) * 0.22
        cy = slash.y + uy * slash.length * (1.0 - frac) * 0.22
        points = [
            (cx - ux * length * 0.5 + px * width * 0.35, cy - uy * length * 0.5 + py * width * 0.35),
            (cx + ux * length * 0.5 + px * width, cy + uy * length * 0.5 + py * width),
            (cx + ux * length * 0.5 - px * width * 0.35, cy + uy * length * 0.5 - py * width * 0.35),
            (cx - ux * length * 0.5 - px * width, cy - uy * length * 0.5 - py * width),
        ]
        pygame.draw.polygon(surf, rgba(slash.color, 190 * frac), points)
        inner = [(lerp(px1, cx, 0.08), lerp(py1, cy, 0.08)) for px1, py1 in points]
        pygame.draw.polygon(surf, rgba(PALETTE["white"], 150 * frac), inner)

    def draw_pixel_diamond(self, x, y, size, color):
        points = [(x, y - size), (x + size, y), (x, y + size), (x - size, y)]
        pygame.draw.polygon(self.screen, color, points)

    def character_portrait(self, index):
        if index in self.character_cache:
            return self.character_cache[index]
        character = CHARACTER_SLOTS[index]
        path = character["portrait"]
        if path and path.exists():
            try:
                surf = pygame.image.load(str(path)).convert_alpha()
                bounds = surf.get_bounding_rect(8)
                if bounds.width > 0 and bounds.height > 0:
                    surf = surf.subsurface(bounds).copy()
                self.character_cache[index] = surf
                return surf
            except pygame.error as exc:
                self.log(f"character art failed: {path.name} {exc}")
        surf = self.procedural_character_portrait(index)
        self.character_cache[index] = surf
        return surf

    def procedural_character_portrait(self, index):
        character = CHARACTER_SLOTS[index]
        surf = pygame.Surface((220, 250), pygame.SRCALPHA)
        rng = random.Random(index * 301 + 9)
        theme = character["theme"]
        dark = character["dark"]
        highlight = character["highlight"]
        for i in range(12):
            x = rng.randint(18, 200)
            y = rng.randint(24, 228)
            size = rng.randint(8, 24)
            pygame.draw.rect(surf, rgba(theme, 28 + i * 4), (x, y, size, size))
        body = [(64, 190), (44, 104), (84, 48), (142, 52), (178, 112), (154, 196), (104, 218)]
        pygame.draw.polygon(surf, dark, body)
        pygame.draw.polygon(surf, theme, [(72, 180), (58, 108), (90, 66), (134, 68), (162, 118), (145, 184), (104, 202)])
        for x in (88, 134):
            pygame.draw.polygon(surf, PALETTE["white"], [(x - 14, 106), (x, 92), (x + 15, 106), (x, 121)])
            pygame.draw.circle(surf, (8, 8, 8), (x + 2, 107), 5)
        pygame.draw.arc(surf, (12, 10, 10), (84, 128, 60, 32), 0.1, math.pi - 0.2, 5)
        for i in range(5):
            x = 72 + i * 20
            pygame.draw.polygon(surf, highlight, [(x, 62), (x + 8, 30 + rng.randint(-8, 8)), (x + 18, 63)])
        return surf

    def blit_fit(self, surf, rect, alpha=255):
        if surf.get_width() <= 0 or surf.get_height() <= 0:
            return
        scale = min(rect.width / surf.get_width(), rect.height / surf.get_height())
        size = (max(1, int(surf.get_width() * scale)), max(1, int(surf.get_height() * scale)))
        scaled = pygame.transform.smoothscale(surf, size)
        if alpha < 255:
            scaled = scaled.copy()
            scaled.set_alpha(alpha)
        dest = scaled.get_rect(center=rect.center)
        self.screen.blit(scaled, dest)

    def fit_text(self, font, text, max_width, color):
        rendered = font.render(text, True, color)
        if rendered.get_width() <= max_width:
            return rendered
        scale = max_width / max(1, rendered.get_width())
        size = (max(1, int(rendered.get_width() * scale)), max(1, int(rendered.get_height() * scale)))
        return pygame.transform.smoothscale(rendered, size)

    def draw_arena(self, offset):
        rect = self.world_rect().move(offset)
        shadow = rect.move(0, 10)
        pygame.draw.rect(self.screen, (0, 0, 0), shadow, border_radius=22)
        pygame.draw.rect(self.screen, PALETTE["panel"], rect, border_radius=22)
        inner = rect.inflate(-22, -22)
        pygame.draw.rect(self.screen, (25, 18, 15), inner, border_radius=16)
        pygame.draw.rect(self.screen, PALETTE["dark_brown"], rect, 5, border_radius=22)
        pygame.draw.rect(self.screen, PALETTE["light_brown"], inner, 1, border_radius=16)

        for i in range(7):
            x = ARENA_MIN_X + (ARENA_MAX_X - ARENA_MIN_X) * i / 6
            sx, _ = self.world_to_screen(x, ARENA_MIN_Y, offset)
            pygame.draw.line(self.screen, rgba(PALETTE["grid"], 90), (sx, inner.top), (sx, inner.bottom), 1)
        for i in range(6):
            y = ARENA_MIN_Y + (ARENA_MAX_Y - ARENA_MIN_Y) * i / 5
            _, sy = self.world_to_screen(ARENA_MIN_X, y, offset)
            pygame.draw.line(self.screen, rgba(PALETTE["grid"], 90), (inner.left, sy), (inner.right, sy), 1)

        for x in (ARENA_MIN_X, ARENA_MAX_X):
            sx, _ = self.world_to_screen(x, ARENA_MIN_Y, offset)
            pygame.draw.line(self.screen, PALETTE["coral"], (sx, inner.top), (sx, inner.bottom), 2)

        bowl = pygame.Rect(0, 0, max(92, rect.width // 12), max(44, rect.height // 14))
        bowl.center = (rect.centerx, rect.top + bowl.height // 2 + 16)
        pygame.draw.ellipse(self.screen, PALETTE["dark_brown"], bowl.inflate(10, 10))
        pygame.draw.ellipse(self.screen, PALETTE["brown"], bowl)
        pygame.draw.ellipse(self.screen, PALETTE["soup"], bowl.inflate(-16, -18))
        for i in range(3):
            x = bowl.centerx - 24 + i * 24
            pygame.draw.arc(self.screen, rgba(PALETTE["light_brown"], 170), (x, bowl.top - 26, 20, 34), 3.7, 5.5, 2)
        text = self.small_font.render("THE LAST BOWL", True, PALETTE["light_brown"])
        self.screen.blit(text, (bowl.centerx - text.get_width() // 2, bowl.bottom + 5))

    def draw_radar_debug(self, offset):
        now = time.time()
        for blob in self.radar_blobs.values():
            if blob.resolution <= 0 or now - blob.seen_at > 0.7:
                continue
            sx, sy = self.world_to_screen(blob.x, blob.y, offset)
            if blob.slot == 3:
                color = PALETTE["ice"]
                radius = 18
                width = 4
            else:
                color = rgba(PALETTE["muted"], 120)
                radius = 11
                width = 2
            pygame.draw.circle(self.screen, color, (sx, sy), radius, width)
            pygame.draw.line(self.screen, color, (sx - radius - 5, sy), (sx + radius + 5, sy), 1)
            pygame.draw.line(self.screen, color, (sx, sy - radius - 5), (sx, sy + radius + 5), 1)
            label = self.small_font.render(
                f"T{blob.slot} raw {blob.raw_x:.1f},{blob.raw_y:.1f}m",
                True,
                color if isinstance(color, tuple) and len(color) == 3 else PALETTE["ice"],
            )
            self.screen.blit(label, (sx + radius + 6, sy - label.get_height() // 2))

    def draw_particles(self, offset, below):
        now = time.time()
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for particle in self.particles:
            if below != (particle.radius > 0.075):
                continue
            age = now - particle.created_at
            frac = clamp(1.0 - age / max(0.001, particle.life), 0.0, 1.0)
            alpha = channel(255 * frac)
            sx, sy = self.world_to_screen(particle.x, particle.y, offset)
            radius = max(1, int(self.meters_to_px(particle.radius) * (0.5 + frac)))
            pygame.draw.circle(surf, rgba(particle.color, alpha), (sx, sy), radius)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw_beam(self, beam, offset):
        now = time.time()
        age = now - beam.created_at
        frac = clamp(1.0 - age / beam.duration, 0.0, 1.0)
        start = self.world_to_screen(*beam.start, offset)
        end_point = beam.hit_point if beam.hit_point else beam.end
        end = self.world_to_screen(*end_point, offset)
        glow = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for width, alpha in ((34, 34), (22, 58), (12, 96)):
            pygame.draw.line(glow, rgba(beam.color, alpha * frac), start, end, width)
        pygame.draw.line(glow, rgba(PALETTE["white"], 240 * frac), start, end, max(2, int(6 * frac)))
        self.screen.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)
        pygame.draw.circle(self.screen, PALETTE["white"], start, max(3, int(10 * frac)))
        if beam.hit_point:
            pygame.draw.circle(self.screen, PALETTE["white"], end, max(4, int(16 * frac)), 2)

    def draw_bubble(self, player, offset):
        now = time.time()
        if not player.bubble_active(now):
            return
        left = max(0.0, player.bubble_until - now)
        frac = clamp(left / BUBBLE_DURATION, 0.0, 1.0)
        sx, sy = self.world_to_screen(player.x, player.y, offset)
        radius = self.meters_to_px(BUBBLE_RADIUS_M) * (1.0 + 0.08 * math.sin(now * 28))
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.circle(surf, rgba(PALETTE["bubble"], 38 + 42 * frac), (sx, sy), int(radius))
        pygame.draw.circle(surf, rgba(PALETTE["bubble"], 210), (sx, sy), int(radius), 4)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def creature_sprite(self, player):
        key = player.player_id
        if key in self.sprite_cache:
            return self.sprite_cache[key]
        path = self.player_sprite_paths.get(player.player_id, PLAYER_SPRITES.get(player.player_id))
        if path and path.exists():
            try:
                surf = pygame.image.load(str(path)).convert_alpha()
                bounds = surf.get_bounding_rect(8)
                if bounds.width > 0 and bounds.height > 0:
                    surf = surf.subsurface(bounds).copy()
                self.sprite_cache[key] = surf
                return surf
            except pygame.error as exc:
                self.log(f"sprite load failed: {path.name} {exc}")
        surf = pygame.Surface((128, 140), pygame.SRCALPHA)
        c = player.color
        d = player.dark_color
        pygame.draw.ellipse(surf, d, (28, 34, 72, 84))
        pygame.draw.ellipse(surf, c, (20, 24, 86, 92))
        pygame.draw.circle(surf, c, (42, 30), 24)
        pygame.draw.circle(surf, c, (84, 30), 24)
        pygame.draw.circle(surf, PALETTE["white"], (48, 54), 10)
        pygame.draw.circle(surf, PALETTE["white"], (80, 54), 10)
        pygame.draw.circle(surf, (17, 23, 28), (50, 55), 5)
        pygame.draw.circle(surf, (17, 23, 28), (78, 55), 5)
        pygame.draw.arc(surf, (17, 23, 28), (46, 64, 36, 24), 0.1, math.pi - 0.1, 4)
        pygame.draw.polygon(surf, PALETTE["soup"], [(58, 15), (66, 3), (74, 15)])
        self.sprite_cache[key] = surf
        return surf

    def player_sprite_pose(self, player, offset=(0, 0), target_pop=False):
        sx, sy = self.world_to_screen(player.x, player.y, offset)
        speed = math.hypot(player.vx, player.vy)
        squash = 1.0 + math.sin(player.sprite_phase) * 0.025
        if speed > 0.15:
            squash += 0.05
        sway = math.sin(player.sprite_phase * 1.4) * min(8.0, speed * 2.2)
        sprite = self.creature_sprite(player)
        aspect = sprite.get_width() / max(1, sprite.get_height())
        base_h = PLAYER_SPRITE_HEIGHT * (1.08 if target_pop else 1.0)
        base_w = base_h * aspect
        scaled = pygame.transform.smoothscale(
            sprite,
            (max(1, int(base_w * (1.0 / squash))), max(1, int(base_h * squash))),
        )
        rotated = pygame.transform.rotate(scaled, sway)
        rect = rotated.get_rect()
        rect.midbottom = (sx, sy + 6)
        return rotated, rect

    def draw_player(self, player, offset):
        sx, sy = self.world_to_screen(player.x, player.y, offset)
        shadow_w = max(4, int(self.meters_to_px(PLAYER_RADIUS_M * 2.2) * PLAYER_SHADOW_SCALE))
        shadow = pygame.Surface((shadow_w * 2, shadow_w), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 82), shadow.get_rect())
        self.screen.blit(shadow, (sx - shadow.get_width() // 2, sy - shadow.get_height() // 2 + 5))

        dx, dy = heading_vec(player.heading)
        aim_end = self.world_to_screen(player.x + dx * 0.55, player.y + dy * 0.55, offset)
        pygame.draw.line(self.screen, (*player.color,), (sx, sy), aim_end, 4)
        pygame.draw.circle(self.screen, player.color, aim_end, 6)

        rotated, rect = self.player_sprite_pose(player, offset)
        if not player.alive:
            ghost = rotated.copy()
            ghost.fill((90, 90, 90, 145), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(ghost, rect)
        else:
            self.screen.blit(rotated, rect)
        label = self.font.render(player.label, True, PALETTE["text"])
        self.screen.blit(label, (sx - label.get_width() // 2, rect.top - 24))

    def draw_hud(self):
        w = self.screen.get_width()
        top = pygame.Rect(0, 0, w, max(112, self.screen.get_height() // 7))
        pygame.draw.rect(self.screen, rgba(PALETTE["panel"], 238), top)
        pygame.draw.line(self.screen, PALETTE["dark_brown"], (0, top.bottom), (w, top.bottom), 4)
        self.draw_text_center(self.title_font, "SOUPOCALYPSE", PALETTE["soup"], (w // 2, top.top + top.height // 2 - 8))
        # self.draw_text_center(self.small_font, "THE LAST BOWL", PALETTE["light_brown"], (w // 2, top.bottom - 18), shadow=False)

        panel_w = min(390, max(320, w // 4))
        self.draw_player_hud(self.players[101], 24, 22, panel_w)
        self.draw_player_hud(self.players[102], w - panel_w - 24, 22, panel_w)
        footer_text = (
            "FAKE: P1 WASD QE F/R     P2 ARROWS , .  / RSHIFT     ENTER RESET     D RADAR DEBUG"
            if self.args.fake else self.hardware_status_text()
        )
        if time.time() < self.calibration_select_until:
            footer_text = "CALIBRATE: PRESS 1 FOR P101 OR 2 FOR P102     DO FIGURE-EIGHTS UNTIL SAVED"
        else:
            status = self.current_magcal_status()
            if status and status.active(time.time()):
                footer_text = (
                    f"P{status.player_id} COMPASS CAL {status.progress}%     "
                    f"{self.format_seconds(status.remaining_ms)} LEFT     QUALITY {status.quality}%"
                )
        text = self.small_font.render(footer_text, True, PALETTE["muted"])
        footer = pygame.Rect(0, self.screen.get_height() - 38, w, 38)
        pygame.draw.rect(self.screen, rgba(PALETTE["panel"], 225), footer)
        self.screen.blit(text, (w // 2 - text.get_width() // 2, footer.centery - text.get_height() // 2))
        for i, (_, log) in enumerate(self.logs[-3:]):
            line = self.small_font.render(log, True, PALETTE["muted"])
            self.screen.blit(line, (24, self.screen.get_height() - 106 + i * 20))

    def current_magcal_status(self):
        now = time.time()
        visible = [status for status in self.mag_cal_status.values() if status.visible(now)]
        if not visible:
            return None
        active = [status for status in visible if status.active(now)]
        candidates = active or visible
        return max(candidates, key=lambda status: status.seen_at)

    def format_seconds(self, ms):
        seconds = max(0, int(round(ms / 1000.0)))
        return f"{seconds}s"

    def magcal_instruction(self, status):
        if status.state == "REQUESTED":
            return "Waiting for controller. Keep it away from metal."
        if status.state == "OK":
            return "Saved. Recenter heading in play position."
        if status.state == "ERR":
            return "Failed. Use bigger figure-eights away from metal."
        if status.state == "RESET":
            return "Reset. Run calibration again before trusting aim."
        if status.radius_x < 80 or status.radius_y < 80:
            return "Wide figure-eights. Rotate through lots of yaw."
        if status.radius_z < 45 and status.remaining_ms > 2500:
            return "X/Y good. Tilt and roll for Z coverage."
        return "Almost there. Keep moving until this says SAVED."

    def draw_progress_bar(self, rect, value, max_value, color, label):
        pygame.draw.rect(self.screen, PALETTE["dark_brown"], rect, border_radius=5)
        frac = 0.0 if max_value <= 0 else clamp(value / max_value, 0.0, 1.0)
        fill = rect.copy()
        fill.width = max(3, int(rect.width * frac))
        pygame.draw.rect(self.screen, color, fill, border_radius=5)
        text = self.small_font.render(label, True, PALETTE["beige"])
        self.screen.blit(text, (rect.left, rect.top - text.get_height() - 3))

    def draw_magcal_overlay(self):
        status = self.current_magcal_status()
        if not status:
            return
        w, h = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(720, w - 80), 194)
        panel.center = (w // 2, max(260, h // 3))
        pygame.draw.rect(self.screen, (0, 0, 0), panel.move(0, 7), border_radius=16)
        pygame.draw.rect(self.screen, PALETTE["panel_2"], panel, border_radius=16)
        pygame.draw.rect(self.screen, PALETTE["light_brown"], panel, 3, border_radius=16)

        title_color = PALETTE["soup"] if status.state != "ERR" else PALETTE["bad"]
        state_label = "SAVED" if status.state == "OK" else "FAILED" if status.state == "ERR" else status.state
        title = f"P{status.player_id} COMPASS CALIBRATION - {state_label}"
        self.draw_text_center(self.font, title, title_color, (panel.centerx, panel.top + 28), shadow=False)

        progress_rect = pygame.Rect(panel.left + 34, panel.top + 58, panel.width - 68, 22)
        self.draw_progress_bar(progress_rect, status.progress, 100, PALETTE["soup_deep"], f"progress {status.progress}%")

        detail = (
            f"quality {status.quality}%     samples {status.samples}     "
            f"elapsed {self.format_seconds(status.elapsed_ms)}     left {self.format_seconds(status.remaining_ms)}"
        )
        detail_surf = self.small_font.render(detail, True, PALETTE["muted"])
        self.screen.blit(detail_surf, (panel.centerx - detail_surf.get_width() // 2, panel.top + 90))

        bar_w = (panel.width - 92) // 3
        for i, (label, value, needed) in enumerate((
            ("X", status.radius_x, 80),
            ("Y", status.radius_y, 80),
            ("Z", status.radius_z, 45),
        )):
            rect = pygame.Rect(panel.left + 34 + i * (bar_w + 12), panel.top + 130, bar_w, 16)
            self.draw_progress_bar(rect, value, needed, PALETTE["p1"] if value >= needed else PALETTE["coral"], f"{label} {value}/{needed}")

        instruction = self.magcal_instruction(status)
        instruction_surf = self.small_font.render(instruction, True, PALETTE["beige"])
        self.screen.blit(instruction_surf, (panel.centerx - instruction_surf.get_width() // 2, panel.bottom - 24))

    def hardware_status_text(self):
        now = time.time()
        live_blobs = [
            blob for blob in self.radar_blobs.values()
            if blob.resolution > 0 and now - blob.seen_at < 0.7
        ]
        if live_blobs:
            blob = max(live_blobs, key=lambda item: item.resolution)
            radar = (
                f"RADAR T{blob.slot} x={blob.x:.2f}m y={blob.y:.2f}m "
                f"rawY={blob.raw_y:.2f}m res={blob.resolution}"
            )
        else:
            radar = "RADAR waiting"
        player_bits = []
        for player in self.players.values():
            if player.last_seen_at and now - player.last_seen_at < 1.4:
                rssi = f"{player.rssi:.0f}dBm" if player.rssi is not None else "?dBm"
                player_bits.append(
                    f"P{player.player_id} hdg={player.heading:.0f} {rssi} lock={player.track_confidence:.1f}"
                )
        players = " | ".join(player_bits) if player_bits else "PLAYERS waiting"
        return f"{radar}     {players}"

    def draw_player_hud(self, player, x, y, width):
        panel = pygame.Rect(x, y, width, 78)
        pygame.draw.rect(self.screen, (0, 0, 0), panel.move(0, 5), border_radius=10)
        pygame.draw.rect(self.screen, PALETTE["panel_2"], panel, border_radius=10)
        pygame.draw.rect(self.screen, PALETTE["dark_brown"], panel, 2, border_radius=10)
        pygame.draw.rect(self.screen, player.color, panel.inflate(-8, -8), 2, border_radius=8)
        name = self.font.render(player.label.upper(), True, player.color)
        self.screen.blit(name, (x + 14, y + 10))
        hp_label = self.small_font.render("HP", True, PALETTE["muted"])
        self.screen.blit(hp_label, (x + 14, y + 42))
        for i in range(MAX_HP):
            bx = x + 48 + i * 36
            color = PALETTE["soup"] if i < player.hp else PALETTE["dark_brown"]
            pygame.draw.rect(self.screen, color, (bx, y + 44, 28, 18), border_radius=4)
        score = self.small_font.render(f"ROUNDS {player.wins}/{WIN_ROUNDS}", True, PALETTE["text"])
        self.screen.blit(score, (panel.right - score.get_width() - 14, y + 45))

    def draw_messages(self):
        if self.match_state in ("ready", "round_over", "match_over"):
            text = self.big_font.render(self.round_message, True, PALETTE["beige"])
            rect = text.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2))
            bg = rect.inflate(56, 34)
            pygame.draw.rect(self.screen, (0, 0, 0), bg.move(0, 7), border_radius=14)
            pygame.draw.rect(self.screen, PALETTE["dark_brown"], bg, border_radius=14)
            pygame.draw.rect(self.screen, PALETTE["light_brown"], bg, 2, border_radius=14)
            self.screen.blit(text, rect)

    def draw_impact_frames(self):
        if not self.impact_frames:
            return
        now = time.time()
        frame = self.impact_frames[-1]
        age = now - frame.created_at
        frac = clamp(1.0 - age / max(0.001, frame.duration), 0.0, 1.0)
        if frame.kind != "hit":
            return
        frame_index = int(age * TARGET_FPS)
        inverted = frame_index >= 4
        bg = (0, 0, 0) if inverted else PALETTE["white"]
        fg = PALETTE["white"] if inverted else (0, 0, 0)
        accent = PALETTE["soup"] if inverted else frame.color
        self.screen.fill(bg)
        for player in sorted(self.players.values(), key=lambda p: p.y, reverse=True):
            target_pop = player.player_id == frame.target_id and frame_index < 6
            sprite, rect = self.player_sprite_pose(player, target_pop=target_pop)
            if target_pop:
                shove = 5 if frame_index % 2 == 0 else -5
                rect.move_ip(shove, 0)
            silhouette = self.sprite_silhouette(sprite, rgba(fg, 255))
            self.screen.blit(silhouette, rect)
        self.draw_impact_hit_marks(frame, fg, accent, frac, frame_index)

    def sprite_silhouette(self, sprite, color):
        mask = pygame.mask.from_surface(sprite, 8)
        return mask.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0)).convert_alpha()

    def draw_impact_hit_marks(self, frame, fg, accent, frac, frame_index):
        if frame.hit_point is None:
            return
        hx, hy = self.world_to_screen(frame.hit_point[0], frame.hit_point[1])
        twist = 0.24 if frame_index % 2 else 0.0
        spokes = 10
        for i in range(spokes):
            angle = twist + i * math.tau / spokes
            length = 42 + int(48 * frac) + (18 if i % 2 == 0 else 0)
            inner = 8 + (i % 2) * 3
            x1 = hx + math.cos(angle) * inner
            y1 = hy + math.sin(angle) * inner
            x2 = hx + math.cos(angle) * length
            y2 = hy + math.sin(angle) * length
            pygame.draw.line(self.screen, accent, (x1, y1), (x2, y2), 5)
            pygame.draw.line(self.screen, fg, (x1, y1), (x2, y2), 2)
        pygame.draw.circle(self.screen, accent, (hx, hy), 14 + int(12 * frac), 4)

    def game_time_scale(self, now):
        if now < self.freeze_until:
            return 0.0
        if now < self.hit_stop_until:
            return HIT_STOP_TIME_SCALE
        return 1.0

    def run(self):
        frames = 0
        while self.running:
            self.handle_events()
            now = time.time()
            raw_dt = min(0.05, now - self.last_tick)
            self.last_tick = now
            dt = raw_dt * self.game_time_scale(now)
            self.update(dt)
            self.render()
            self.clock.tick(TARGET_FPS)
            frames += 1
            if self.args.smoke_test and frames >= self.args.smoke_test:
                self.running = False
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description="Soupocalypse: The Last Bowl")
    parser.add_argument("--fake", action="store_true", help="Run without hardware using keyboard controls.")
    parser.add_argument("--port", help="Bridge serial port, for example COM4. Auto-detects if omitted.")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--windowed", action="store_true", help="Run in a window instead of native fullscreen.")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--debug-radar", action="store_true", help="Draw live radar target debug markers, including T3.")
    parser.add_argument("--smoke-test", type=int, default=0, help="Run this many frames and exit.")
    args = parser.parse_args()
    SoupocalypseApp(args).run()


if __name__ == "__main__":
    main()
