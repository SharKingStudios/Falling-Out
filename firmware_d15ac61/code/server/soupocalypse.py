import argparse
import math
import queue
import random
import struct
import threading
import time
from dataclasses import dataclass
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
BEAM_WIDTH_M = 0.34
BUBBLE_RADIUS_M = 0.62
BUBBLE_DURATION = 0.70
BEAM_COOLDOWN = 0.82
BUBBLE_COOLDOWN = 1.10
ROUND_RESET_DELAY = 1.8
HIT_IMPACT_DURATION = 0.150
HIT_STOP_TIME_SCALE = 0.08
PLAYER_SPRITE_HEIGHT = 152
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


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


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
        self.sounds["ready"] = self.sequence([(392, 0.06), (523, 0.06), (784, 0.09)], 0.38, "triangle")
        self.sounds["swing"] = self.sweep(620, 980, 0.09, 0.26, "triangle")
        self.sounds["beam"] = self.beam_sound()
        self.sounds["bubble"] = self.sequence([(740, 0.04), (1046, 0.08)], 0.30, "sine")
        self.sounds["block"] = self.sequence([(1397, 0.035), (1046, 0.06), (1568, 0.08)], 0.36, "square")
        self.sounds["hit"] = self.noise_burst(0.16, 0.48, 180, 420)
        self.sounds["ko"] = self.sequence([(196, 0.12), (147, 0.12), (98, 0.22)], 0.52, "triangle")
        self.sounds["round"] = self.sequence([(523, 0.06), (659, 0.06), (784, 0.06), (1046, 0.14)], 0.42, "square")
        self.sounds["invalid"] = self.sequence([(190, 0.055), (142, 0.08)], 0.24, "square")

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
            sound.set_volume(volume)
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
        self.match_state = "ready"
        self.round_message = "PRESS ENTER - FIGHT FOR THE LAST BOWL"
        self.round_reset_at = 0.0
        self.freeze_until = 0.0
        self.hit_stop_until = 0.0
        self.shake_until = 0.0
        self.shake_power = 0.0
        self.pending_actions = []
        self.last_tick = time.time()
        self.fake_actions = {101: 0, 102: 0}
        self.fake_last_heading = {101: 90.0, 102: -90.0}
        self.sprite_cache = {}
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

    def reset_round(self):
        now = time.time()
        for player in self.players.values():
            player.hp = MAX_HP
            player.alive = True
            player.bubble_until = 0.0
            player.beam_ready_at = now + 0.4
            player.bubble_ready_at = now + 0.4
            player.track_updated_at = 0.0
            player.track_slot = None
            player.track_confidence = 0.0
        self.players[101].x, self.players[101].y, self.players[101].heading = -0.95, 2.55, 90
        self.players[102].x, self.players[102].y, self.players[102].heading = 0.95, 2.55, -90
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
        for player in self.players.values():
            player.wins = 0
        self.reset_round()

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
            elif tag in ("LOG", "BRIDGE_BOOT", "WARN", "ERR"):
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
        if self.match_state == "ready":
            self.reset_match()
            return
        if self.match_state != "playing":
            return
        if self.pending_actions or self.is_hit_stop_active():
            self.queue_action(player, action)
            return
        self.perform_action(player, action)

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

    def fire_beam(self, player):
        now = time.time()
        dx, dy = heading_vec(player.heading)
        start = (player.x + dx * 0.18, player.y + dy * 0.18)
        end = (player.x + dx * BEAM_RANGE_M, player.y + dy * BEAM_RANGE_M)
        target = self.players[102 if player.player_id == 101 else 101]
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
        self.spawn_beam_particles(start, end, player.color)
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
                    self.sounds.play("menu_select")
                    self.reset_match()
                elif event.key == pygame.K_m:
                    self.sounds.play("menu_move")
                elif event.key == pygame.K_d:
                    self.debug_radar = not self.debug_radar
                    self.sounds.play("menu_move")

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

        if self.match_state in ("round_over", "match_over") and now >= self.round_reset_at:
            if self.match_state == "match_over":
                self.match_state = "ready"
                self.round_message = "PRESS ENTER - FIGHT FOR THE LAST BOWL"
                for player in self.players.values():
                    player.wins = 0
                    player.hp = MAX_HP
                    player.alive = True
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
        path = PLAYER_SPRITES.get(player.player_id)
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
        shadow_w = self.meters_to_px(PLAYER_RADIUS_M * 2.2)
        shadow = pygame.Surface((shadow_w * 2, shadow_w), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 98), shadow.get_rect())
        self.screen.blit(shadow, (sx - shadow.get_width() // 2, sy - shadow.get_height() // 2 + 10))

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
        self.draw_text_center(self.small_font, "THE LAST BOWL", PALETTE["light_brown"], (w // 2, top.bottom - 18), shadow=False)

        panel_w = min(390, max(320, w // 4))
        self.draw_player_hud(self.players[101], 24, 22, panel_w)
        self.draw_player_hud(self.players[102], w - panel_w - 24, 22, panel_w)
        footer_text = (
            "FAKE: P1 WASD QE F/R     P2 ARROWS , .  / RSHIFT     ENTER RESET     D RADAR DEBUG"
            if self.args.fake else self.hardware_status_text()
        )
        text = self.small_font.render(footer_text, True, PALETTE["muted"])
        footer = pygame.Rect(0, self.screen.get_height() - 38, w, 38)
        pygame.draw.rect(self.screen, rgba(PALETTE["panel"], 225), footer)
        self.screen.blit(text, (w // 2 - text.get_width() // 2, footer.centery - text.get_height() // 2))
        for i, (_, log) in enumerate(self.logs[-3:]):
            line = self.small_font.render(log, True, PALETTE["muted"])
            self.screen.blit(line, (24, self.screen.get_height() - 106 + i * 20))

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
