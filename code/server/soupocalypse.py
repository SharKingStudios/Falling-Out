import argparse
import math
import queue
import random
import struct
import threading
import time
import wave
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
GENERATED_AUDIO_DIR = BASE_DIR / "assets" / "generated_audio" / "fight"
MUSIC_DIR = BASE_DIR / "assets" / "music"
SOUP_PLACEHOLDER_SPRITE = SPRITE_DIR / "soup.jpg"
CEILING_SEAL_SPRITE = SPRITE_DIR / "ceiling_seal_plush.png"
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
ENABLE_FIGHT_JUICE = True
ENABLE_SCREEN_SHAKE = True
ENABLE_HIT_STOP = True
ENABLE_GENERATED_PARTICLES = True
ENABLE_CHARACTER_ATTACK_DESCRIPTORS = True
ENABLE_PROCEDURAL_AUDIO_GENERATION = False
ENABLE_VICTORY_SCREEN = True
FIGHT_MAX_PARTICLES = 1300
FIGHT_SFX_MASTER_VOLUME = 0.96
FIGHT_VOICE_MASTER_VOLUME = 0.82
ATTACK_LINE_COOLDOWN = 1.05
ROUND_WIN_PRESENTATION = 3.10
NEXT_ROUND_COUNTDOWN_STEP = 0.62
NEXT_ROUND_COUNTDOWN_TOTAL = NEXT_ROUND_COUNTDOWN_STEP * 4
MATCH_WIN_SCREEN_MIN_DURATION = 5.2
FIGHT_FLASH_DURATION = 0.16
FIGHT_SHAKE_ATTACK = 3.2
FIGHT_SHAKE_HIT = 9.0
FIGHT_SHAKE_KO = 14.0
FIGHT_SHAKE_MATCH_WIN = 18.0
ATTACK_EFFECT_INTENSITY = 1.18
ATTACK_STARTUP_VISUAL = 0.075
ATTACK_MUZZLE_BURST_SIZE = 1.18
ATTACK_HIT_BURST_SIZE = 1.20
ATTACK_AFTERIMAGE_DURATION = 0.38
ATTACK_MISS_BURST_SIZE = 0.58
ATTACK_MOTION_TRAIL_LENGTH = 0.24
ATTACK_MAX_PARTICLES = 150
SHIELD_BLOCK_SHAKE = 5.2
SHIELD_BLOCK_SPARK_COUNT = 50
IMPACT_FRAME_FLASH_FRAMES = 2
IMPACT_FRAME_INVERT_FRAME = 6
IMPACT_FRAME_REENTRY_FRAME = 11
IMPACT_FRAME_SHAKE = 3.5
GENERATED_ICON_SIZE = 64
EMBLEM_SPIN_SPEED = 420.0
LIGHTNING_REDRAW_RATE = 48.0
FIRE_FLICKER_RATE = 24.0
STEAM_FADE_DURATION = 0.72
SLASH_SHARD_COUNT = 18
HIT_TYPOGRAPHY = True
FIGHT_SFX_VOLUME = {
    "fight_razor": 0.92,
    "fight_torrent": 0.94,
    "fight_emblem": 0.88,
    "fight_chain": 0.94,
    "fight_fire": 0.94,
    "fight_spiral": 0.90,
    "fight_hit": 0.96,
    "fight_shield": 0.82,
    "fight_shield_hit": 0.94,
    "fight_round_win": 0.96,
    "fight_match_win": 1.0,
    "fight_count_3": 0.84,
    "fight_count_2": 0.86,
    "fight_count_1": 0.90,
    "fight_count_go": 1.0,
}
AUDIO_EXTENSIONS = (".wav", ".ogg", ".mp3")
RADAR_SPLIT_X = 0.0
MUSIC_TRACK_FILES = {
    "lobby1": MUSIC_DIR / "lobby1",
    "lobby2": MUSIC_DIR / "lobby2",
    "battle1": MUSIC_DIR / "battle1",
    "battle2": MUSIC_DIR / "battle2",
    "battle3": MUSIC_DIR / "battle3",
}
MUSIC_GROUPS = {
    "lobby": ("lobby1", "lobby2"),
    "battle": ("battle1", "battle2", "battle3"),
}
MUSIC_TOTAL_CHANNELS = 32
MUSIC_RESERVED_CHANNELS = len(MUSIC_TRACK_FILES)
PRIORITY_SOUND_CHANNELS = 3
RESERVED_MIXER_CHANNELS = MUSIC_RESERVED_CHANNELS + PRIORITY_SOUND_CHANNELS
MUSIC_MASTER_VOLUME = 0.625
MUSIC_FADE_SPEED = 1.55
MUSIC_GROUP_FADE_MS = 700
PRIORITY_SOUND_NAMES = {"ko", "round", "round_win", "fight_round_win", "fight_match_win"}

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
        "name": "Aarav",
        "portrait": SPRITE_DIR / "p1_temp.png",
        "theme": (55, 181, 118),
        "secondary": (255, 235, 173),
        "dark": (21, 77, 55),
        "highlight": (168, 255, 203),
        "accent": (255, 246, 122),
        "tagline": "Zhifubao",
        "attack_type": "payment",
    },
    {
        "id": "noodle_wyrm",
        "name": "Will",
        "portrait": SPRITE_DIR / "p2_temp.png",
        "theme": (255, 125, 112),
        "secondary": (255, 235, 173),
        "dark": (116, 39, 43),
        "highlight": (255, 204, 166),
        "accent": (255, 79, 86),
        "tagline": "Builds",
        "attack_type": "youtube",
    },
    {
        "id": "bloo",
        "name": "Acon",
        "portrait": SPRITE_DIR / "bloo.png",
        "theme": (56, 201, 255),
        "secondary": (113, 255, 222),
        "dark": (18, 68, 107),
        "highlight": (223, 251, 255),
        "accent": (123, 145, 255),
        "tagline": "Bloo",
        "attack_type": "emblem",
    },
    {
        "id": "party_cat",
        "name": "Tongyu",
        "portrait": SPRITE_DIR / "party-cat.png",
        "theme": (255, 205, 64),
        "secondary": (255, 105, 180),
        "dark": (126, 73, 20),
        "highlight": (255, 249, 178),
        "accent": (128, 255, 93),
        "tagline": "Ceiling!",
        "attack_type": "ceiling",
    },
    {
        "id": "wasteland_wing",
        "name": "Nathan",
        "portrait": SPRITE_DIR / "pigeon.png",
        "theme": (157, 132, 255),
        "secondary": (86, 226, 188),
        "dark": (54, 43, 112),
        "highlight": (232, 225, 255),
        "accent": (255, 96, 188),
        "tagline": "TODO",
        "attack_type": "fire",
    },
    {
        "id": "the_goat",
        "name": "Zach Latta",
        "portrait": SPRITE_DIR / "the-goat.png",
        "theme": (255, 145, 48),
        "secondary": (82, 218, 128),
        "dark": (99, 48, 16),
        "highlight": (255, 222, 153),
        "accent": (255, 86, 56),
        "tagline": "The Goat",
        "attack_type": "spiral",
    },
)

ATTACK_PROFILES = {
    "razor": {
        "id": "razor",
        "display_name": "Razor Soup Beam",
        "sound": "fight_razor",
        "beam_shape": "jagged_ribbon",
        "muzzle": "slash_burst",
        "trail": "angular_shards",
        "impact": "slash_star",
        "screen": "palette_flash",
        "camera_shake": 4.0,
        "hit_shake": 10.0,
        "hit_stop": HIT_IMPACT_DURATION,
        "intensity": 1.0,
        "debug_name": "slash-ribbon",
    },
    "torrent": {
        "id": "torrent",
        "display_name": "Boiling Particle Torrent",
        "sound": "fight_torrent",
        "beam_shape": "particle_tunnel",
        "muzzle": "pressure_burst",
        "trail": "steam_pixels",
        "impact": "soup_splash",
        "screen": "warm_splash",
        "camera_shake": 4.5,
        "hit_shake": 10.5,
        "hit_stop": HIT_IMPACT_DURATION * 0.95,
        "intensity": 1.15,
        "debug_name": "particle-torrent",
    },
    "emblem": {
        "id": "emblem",
        "display_name": "Spinning Emblem Beam",
        "sound": "fight_emblem",
        "beam_shape": "emblem_path",
        "muzzle": "stamp_launch",
        "trail": "image_particles",
        "impact": "icon_spinout",
        "screen": "sticker_pop",
        "camera_shake": 3.7,
        "hit_shake": 9.0,
        "hit_stop": HIT_IMPACT_DURATION,
        "intensity": 1.0,
        "debug_name": "emblem-spin",
    },
    "chain": {
        "id": "chain",
        "display_name": "Crackling Chain Beam",
        "sound": "fight_chain",
        "beam_shape": "lightning_chain",
        "muzzle": "zap_burst",
        "trail": "branch_arcs",
        "impact": "electric_crawl",
        "screen": "electric_invert",
        "camera_shake": 4.0,
        "hit_shake": 10.0,
        "hit_stop": HIT_IMPACT_DURATION * 1.05,
        "intensity": 1.08,
        "debug_name": "chain-lightning",
    },
    "fire": {
        "id": "fire",
        "display_name": "Pixel Fire Beam",
        "sound": "fight_fire",
        "beam_shape": "pixel_fire",
        "muzzle": "ember_burst",
        "trail": "fire_chunks",
        "impact": "ember_wrap",
        "screen": "hot_flash",
        "camera_shake": 4.4,
        "hit_shake": 11.0,
        "hit_stop": HIT_IMPACT_DURATION,
        "intensity": 1.2,
        "debug_name": "pixel-fire",
    },
    "spiral": {
        "id": "spiral",
        "display_name": "Noodle Spiral Beam",
        "sound": "fight_spiral",
        "beam_shape": "spiral_ribbon",
        "muzzle": "noodle_twist",
        "trail": "orbiting_sparks",
        "impact": "spiral_ring",
        "screen": "rubber_pop",
        "camera_shake": 3.5,
        "hit_shake": 8.5,
        "hit_stop": HIT_IMPACT_DURATION * 0.9,
        "intensity": 1.0,
        "debug_name": "noodle-spiral",
    },
    "payment": {
        "id": "payment",
        "display_name": "Jirfubao Payment Blast",
        "sound": "fight_razor",
        "beam_shape": "payment_scan",
        "muzzle": "scan_terminal",
        "trail": "qr_money_glyphs",
        "impact": "qr_approved",
        "screen": "cyan_transaction_flash",
        "camera_shake": 4.0,
        "hit_shake": 10.0,
        "hit_stop": HIT_IMPACT_DURATION,
        "intensity": 1.08,
        "debug_name": "payment-qr-scan",
    },
    "youtube": {
        "id": "youtube",
        "display_name": "Algorithm Engagement Cannon",
        "sound": "fight_torrent",
        "beam_shape": "youtube_feed",
        "muzzle": "play_button_slam",
        "trail": "engagement_icons",
        "impact": "subscribe_crush",
        "screen": "video_red_flash",
        "camera_shake": 4.5,
        "hit_shake": 10.5,
        "hit_stop": HIT_IMPACT_DURATION * 0.95,
        "intensity": 1.15,
        "debug_name": "youtube-feed-blast",
    },
    "ceiling": {
        "id": "ceiling",
        "display_name": "Ceiling Seal Avalanche",
        "sound": "fight_chain",
        "beam_shape": "seal_avalanche",
        "muzzle": "plush_cannon",
        "trail": "seal_stampede",
        "impact": "plush_pileup",
        "screen": "bonk_avalanche",
        "camera_shake": 4.0,
        "hit_shake": 10.0,
        "hit_stop": HIT_IMPACT_DURATION * 1.05,
        "intensity": 1.16,
        "debug_name": "ceiling-seal-avalanche",
    },
}

ATTACK_STAGE_CONFIG = {
    "razor": {
        "attackId": "broth_three_cut",
        "attackType": "three_cut_slash",
        "startupVisualDuration": 0.075,
        "muzzleEffectType": "slash_fan",
        "travelEffectType": "triple_jagged_ribbon",
        "hitEffectType": "directional_slash_burst",
        "victimReactionType": "slash_scars",
        "impactFrameMotif": "giant_claw_cuts",
        "aftermathEffectType": "blade_shards",
        "missEffectType": "snap_shards",
        "shieldBlockEffectType": "shield_crack_scrape",
        "hitWord": "CHOP",
        "particleDensity": 1.05,
        "paletteFlashOpacity": 104,
        "effectLifetime": 0.34,
    },
    "torrent": {
        "attackId": "noodle_pressure_torrent",
        "attackType": "pressure_stream",
        "startupVisualDuration": 0.090,
        "muzzleEffectType": "steam_pressure_pop",
        "travelEffectType": "banded_particle_torrent",
        "hitEffectType": "directional_soup_splat",
        "victimReactionType": "drip_and_steam",
        "impactFrameMotif": "pressure_cone_splash",
        "aftermathEffectType": "falling_droplets",
        "missEffectType": "steam_evaporation",
        "shieldBlockEffectType": "wet_shield_deform",
        "hitWord": "SPLASH",
        "particleDensity": 1.35,
        "paletteFlashOpacity": 94,
        "effectLifetime": 0.54,
    },
    "emblem": {
        "attackId": "bloo_sticker_storm",
        "attackType": "stamp_sticker_beam",
        "startupVisualDuration": 0.070,
        "muzzleEffectType": "emblem_stamp",
        "travelEffectType": "spinning_emblem_path",
        "hitEffectType": "stamp_spinout",
        "victimReactionType": "peeling_stickers",
        "impactFrameMotif": "printed_offset_stamps",
        "aftermathEffectType": "falling_stickers",
        "missEffectType": "flutter_away",
        "shieldBlockEffectType": "stick_and_repel",
        "hitWord": "STAMP",
        "particleDensity": 1.05,
        "paletteFlashOpacity": 84,
        "effectLifetime": 0.48,
    },
    "chain": {
        "attackId": "party_crackle_chain",
        "attackType": "branch_lightning",
        "startupVisualDuration": 0.060,
        "muzzleEffectType": "electric_corona",
        "travelEffectType": "redrawn_branch_chain",
        "hitEffectType": "voltage_knot",
        "victimReactionType": "outline_crawl",
        "impactFrameMotif": "full_screen_branches",
        "aftermathEffectType": "jitter_sparks",
        "missEffectType": "snap_fizzle",
        "shieldBlockEffectType": "panel_crawl",
        "hitWord": "ZAP",
        "particleDensity": 1.12,
        "paletteFlashOpacity": 96,
        "effectLifetime": 0.34,
    },
    "fire": {
        "attackId": "wing_pixel_foom",
        "attackType": "pixel_fire_jet",
        "startupVisualDuration": 0.082,
        "muzzleEffectType": "fire_cough",
        "travelEffectType": "flickering_pixel_fire",
        "hitEffectType": "ember_wrap",
        "victimReactionType": "ember_outline",
        "impactFrameMotif": "blocky_flame_wrap",
        "aftermathEffectType": "embers_and_smoke",
        "missEffectType": "burnout_puff",
        "shieldBlockEffectType": "fire_rim_sizzle",
        "hitWord": "FOOM",
        "particleDensity": 1.42,
        "paletteFlashOpacity": 112,
        "effectLifetime": 0.62,
    },
    "spiral": {
        "attackId": "goat_noodle_lariat",
        "attackType": "spiral_vortex",
        "startupVisualDuration": 0.080,
        "muzzleEffectType": "spiral_knot",
        "travelEffectType": "three_strand_vortex",
        "hitEffectType": "wrap_and_snap",
        "victimReactionType": "noodle_wrap",
        "impactFrameMotif": "coiling_bands",
        "aftermathEffectType": "unwinding_curls",
        "missEffectType": "unravel",
        "shieldBlockEffectType": "rim_wrap_snap",
        "hitWord": "WHIP",
        "particleDensity": 1.16,
        "paletteFlashOpacity": 88,
        "effectLifetime": 0.46,
    },
    "payment": {
        "attackId": "aarav_jirfubao_scan",
        "attackType": "payment_scan_corridor",
        "startupVisualDuration": 0.075,
        "muzzleEffectType": "qr_terminal_crack",
        "travelEffectType": "transaction_corridor",
        "hitEffectType": "fake_qr_approved_burst",
        "victimReactionType": "scan_box_currency_crawl",
        "impactFrameMotif": "fake_qr_supermove",
        "aftermathEffectType": "receipt_currency_confetti",
        "missEffectType": "failed_payment_cloud",
        "shieldBlockEffectType": "qr_shatter_on_glass",
        "hitWord": "JIRFUBAO",
        "particleDensity": 1.18,
        "paletteFlashOpacity": 110,
        "effectLifetime": 0.42,
    },
    "youtube": {
        "attackId": "will_algorithm_cannon",
        "attackType": "content_feed_beam",
        "startupVisualDuration": 0.090,
        "muzzleEffectType": "play_tile_slam",
        "travelEffectType": "engagement_feed_stream",
        "hitEffectType": "subscribe_play_tile_crush",
        "victimReactionType": "video_ui_frame_echoes",
        "impactFrameMotif": "smash_that_supercut",
        "aftermathEffectType": "likes_comments_bells",
        "missEffectType": "buffering_fragments",
        "shieldBlockEffectType": "blocked_video_bend",
        "hitWord": "SMASH THAT",
        "particleDensity": 1.28,
        "paletteFlashOpacity": 106,
        "effectLifetime": 0.50,
    },
    "ceiling": {
        "attackId": "tongyu_ceiling_avalanche",
        "attackType": "seal_plush_avalanche",
        "startupVisualDuration": 0.070,
        "muzzleEffectType": "seal_cannon_pop",
        "travelEffectType": "plush_stampede_corridor",
        "hitEffectType": "seal_pileup_bonk",
        "victimReactionType": "buried_in_ceiling",
        "impactFrameMotif": "giant_seal_bonk",
        "aftermathEffectType": "plush_bounce_cloud",
        "missEffectType": "seal_skid_pile",
        "shieldBlockEffectType": "seals_on_bubble",
        "hitWord": "CEILING",
        "particleDensity": 1.20,
        "paletteFlashOpacity": 92,
        "effectLifetime": 0.50,
    },
}

for attack_id, stage_config in ATTACK_STAGE_CONFIG.items():
    ATTACK_PROFILES[attack_id].update(stage_config)
    ATTACK_PROFILES[attack_id].setdefault("displayName", ATTACK_PROFILES[attack_id].get("display_name", attack_id))
    ATTACK_PROFILES[attack_id].setdefault("palette", ())
    ATTACK_PROFILES[attack_id].setdefault("muzzleSound", ATTACK_PROFILES[attack_id]["sound"])
    ATTACK_PROFILES[attack_id].setdefault("travelSound", ATTACK_PROFILES[attack_id]["sound"])
    ATTACK_PROFILES[attack_id].setdefault("hitSound", "fight_hit")
    ATTACK_PROFILES[attack_id].setdefault("shieldHitSound", "fight_shield_hit")
    ATTACK_PROFILES[attack_id].setdefault("missSound", None)
    ATTACK_PROFILES[attack_id].setdefault("impactFrameSound", "fight_hit")
    ATTACK_PROFILES[attack_id].setdefault("particleTexture", None)
    ATTACK_PROFILES[attack_id].setdefault("hitSpinoutTexture", None)
    ATTACK_PROFILES[attack_id].setdefault("generatedIconStyle", attack_id)
    ATTACK_PROFILES[attack_id].setdefault("screenShakeAmount", ATTACK_PROFILES[attack_id].get("camera_shake", FIGHT_SHAKE_ATTACK))
    ATTACK_PROFILES[attack_id].setdefault("screenShakeDuration", 0.08)
    ATTACK_PROFILES[attack_id].setdefault("hitStopDuration", ATTACK_PROFILES[attack_id].get("hit_stop", HIT_IMPACT_DURATION))
    ATTACK_PROFILES[attack_id].setdefault("impactFrameDuration", HIT_IMPACT_DURATION)
    ATTACK_PROFILES[attack_id].setdefault("renderPriority", 0)
    ATTACK_PROFILES[attack_id].setdefault("debugName", ATTACK_PROFILES[attack_id].get("debug_name", attack_id))


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


def normalize_vec(dx, dy, fallback=(0.0, 1.0)):
    length = math.hypot(dx, dy)
    if length <= 0.0001:
        return fallback
    return dx / length, dy / length


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
    character_id: str = "broth_beast"
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
    attacker_id: Optional[int] = None
    attack_type: str = "razor"
    direction: tuple = (0.0, 1.0)


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
    attack_type: str = "razor"
    direction: tuple = (0.0, 1.0)


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


@dataclass
class FightParticle:
    x: float
    y: float
    vx: float
    vy: float
    color: tuple
    size: float
    created_at: float
    life: float
    shape: str = "pixel"
    layer: str = "front"
    angle: float = 0.0
    spin: float = 0.0
    gravity: float = 0.0
    alpha: float = 255.0
    sprite_key: Optional[str] = None


@dataclass
class FightSplat:
    x: float
    y: float
    color: tuple
    dark_color: tuple
    highlight: tuple
    created_at: float
    life: float
    radius: float
    seed: int
    kind: str = "splat"
    direction: tuple = (0.0, 1.0)


@dataclass
class ScreenFlash:
    color: tuple
    created_at: float
    duration: float
    alpha: float = 100.0


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
        self.line_sounds = {}
        self.last_line_at = {}
        self.music_sounds = {}
        self.music_channels = {}
        self.music_volumes = {}
        self.music_active_group = ""
        self.priority_channels = []
        self.priority_channel_index = 0
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 256)
            pygame.mixer.set_num_channels(max(pygame.mixer.get_num_channels(), MUSIC_TOTAL_CHANNELS))
            pygame.mixer.set_reserved(RESERVED_MIXER_CHANNELS)
            for index, track in enumerate(MUSIC_TRACK_FILES):
                self.music_channels[track] = pygame.mixer.Channel(index)
                self.music_volumes[track] = 0.0
            first_priority_channel = MUSIC_RESERVED_CHANNELS
            for index in range(PRIORITY_SOUND_CHANNELS):
                self.priority_channels.append(pygame.mixer.Channel(first_priority_channel + index))
            if ENABLE_PROCEDURAL_AUDIO_GENERATION:
                self.ensure_generated_fight_audio()
            self.make_sounds()
            self.load_generated_fight_audio()
            self.load_music()
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
        self.sounds["fight_razor"] = self.fight_attack_sound(940, 1880, 0.20, 0.50, 0.10)
        self.sounds["fight_torrent"] = self.noise_burst(0.24, 0.54, 110, 920)
        self.sounds["fight_emblem"] = self.fight_attack_sound(520, 1320, 0.22, 0.42, 0.28)
        self.sounds["fight_chain"] = self.electric_sound()
        self.sounds["fight_fire"] = self.noise_burst(0.20, 0.52, 860, 2600)
        self.sounds["fight_spiral"] = self.fight_attack_sound(360, 1140, 0.24, 0.44, 0.40)
        self.sounds["fight_hit"] = self.noise_burst(0.16, 0.58, 80, 520)
        self.sounds["fight_shield"] = self.sequence([(622, 0.04), (932, 0.06), (1244, 0.05)], 0.38, "sine")
        self.sounds["fight_shield_hit"] = self.sequence([(1397, 0.035), (740, 0.055), (1865, 0.08)], 0.50, "square")
        self.sounds["fight_round_win"] = self.sequence([(392, 0.08), (523, 0.07), (659, 0.07), (1046, 0.18)], 0.48, "square")
        self.sounds["fight_match_win"] = self.menu_go_sound()
        self.sounds["fight_count_3"] = self.menu_count_sound(320, 620, 0.18, 0.46)
        self.sounds["fight_count_2"] = self.menu_count_sound(420, 820, 0.18, 0.48)
        self.sounds["fight_count_1"] = self.menu_count_sound(180, 520, 0.22, 0.54)
        self.sounds["fight_count_go"] = self.menu_go_sound()

    def audio_path_variants(self, path):
        if path.suffix:
            yield path
            for ext in AUDIO_EXTENSIONS:
                if path.suffix.lower() != ext:
                    yield path.with_suffix(ext)
            return
        for ext in AUDIO_EXTENSIONS:
            yield path.with_suffix(ext)

    def load_audio_file(self, path):
        for candidate in self.audio_path_variants(path):
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                return pygame.mixer.Sound(str(candidate))
            except pygame.error as exc:
                print(f"audio asset skipped: {candidate} ({exc})")
        return None

    def load_first_audio_file(self, paths):
        for path in paths:
            sound = self.load_audio_file(path)
            if sound is not None:
                return sound
        return None

    def load_music(self):
        self.music_sounds.clear()
        for name, path in MUSIC_TRACK_FILES.items():
            sound = self.load_audio_file(path)
            if sound is not None:
                self.music_sounds[name] = sound

    def music_group_for_track(self, track):
        for group, tracks in MUSIC_GROUPS.items():
            if track in tracks:
                return group
        return ""

    def ensure_music_group(self, group):
        next_tracks = set(MUSIC_GROUPS.get(group, ()))
        for track in next_tracks:
            sound = self.music_sounds.get(track)
            channel = self.music_channels.get(track)
            if sound is None or channel is None:
                continue
            if not channel.get_busy():
                channel.play(sound, loops=-1)
                channel.set_volume(self.music_volumes.get(track, 0.0))
        self.music_active_group = group

    def update_music(self, target_track, dt):
        if not self.enabled:
            return
        if target_track not in self.music_sounds:
            target_track = None
        group = self.music_group_for_track(target_track) if target_track else ""
        if group:
            self.ensure_music_group(group)
        else:
            self.music_active_group = ""
        group_tracks = set(MUSIC_GROUPS.get(group, ()))
        step = MUSIC_FADE_SPEED * max(0.001, dt)
        for track, channel in self.music_channels.items():
            goal = MUSIC_MASTER_VOLUME if track == target_track else 0.0
            if group and track not in group_tracks:
                goal = 0.0
            current = self.music_volumes.get(track, 0.0)
            if current < goal:
                current = min(goal, current + step)
            elif current > goal:
                current = max(goal, current - step)
            self.music_volumes[track] = current
            channel.set_volume(current)
            if current <= 0.001 and track not in group_tracks and channel.get_busy():
                channel.stop()

    def is_generated_voice_placeholder(self, cid, category, path):
        stem = path.stem.lower()
        prefix = f"{cid}_{category}_"
        if not stem.startswith(prefix):
            return False
        tail = stem[len(prefix):]
        return len(tail) == 2 and tail.isdigit()

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

    def fight_attack_sound(self, start_freq, end_freq, duration, gain, wobble):
        rate = 44100
        total = int(rate * duration)
        samples = []
        phase = 0.0
        phase_b = 0.0
        rng = random.Random(int(start_freq + end_freq + wobble * 1000))
        for i in range(total):
            t = i / max(1, total - 1)
            freq = start_freq + (end_freq - start_freq) * (t ** 0.72)
            freq += math.sin(t * math.tau * 8.0) * wobble * 130.0
            phase += math.tau * freq / rate
            phase_b += math.tau * (freq * 0.52) / rate
            noise = (rng.random() * 2 - 1) * 0.22 * max(0.0, 1.0 - t * 2.2)
            sample = self.wave_sample(phase, "square") * 0.30 + math.sin(phase_b) * 0.58 + noise
            samples.append(sample * self.envelope(i, total))
        return self.build(samples, gain)

    def electric_sound(self):
        rate = 44100
        total = int(rate * 0.20)
        samples = []
        rng = random.Random(508)
        phase = 0.0
        for i in range(total):
            t = i / max(1, total - 1)
            freq = 940 + 720 * math.sin(t * math.tau * 13.0)
            phase += math.tau * freq / rate
            crackle = (rng.random() * 2 - 1) * (0.75 if rng.random() > 0.72 else 0.28)
            sample = math.sin(phase) * 0.42 + crackle * (1.0 - t * 0.55)
            samples.append(sample * self.envelope(i, total))
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

    def ensure_generated_fight_audio(self):
        rate = 22050
        for folder in ("ui", "rounds", "impacts"):
            (GENERATED_AUDIO_DIR / folder).mkdir(parents=True, exist_ok=True)
        generated = {
            GENERATED_AUDIO_DIR / "ui" / "countdown_3.wav": self.wav_tone_stack(rate, 300, 610, 0.22, 0.46, 11),
            GENERATED_AUDIO_DIR / "ui" / "countdown_2.wav": self.wav_tone_stack(rate, 420, 820, 0.22, 0.46, 12),
            GENERATED_AUDIO_DIR / "ui" / "countdown_1.wav": self.wav_tone_stack(rate, 180, 520, 0.24, 0.52, 13),
            GENERATED_AUDIO_DIR / "ui" / "fight.wav": self.wav_tone_stack(rate, 260, 1480, 0.36, 0.58, 14),
            GENERATED_AUDIO_DIR / "rounds" / "round_win.wav": self.wav_tone_stack(rate, 360, 1040, 0.42, 0.50, 15),
            GENERATED_AUDIO_DIR / "rounds" / "match_win.wav": self.wav_tone_stack(rate, 220, 1720, 0.62, 0.58, 16),
            GENERATED_AUDIO_DIR / "impacts" / "hit_crack.wav": self.wav_noise_chirp(rate, 0.18, 0.55, 17),
            GENERATED_AUDIO_DIR / "impacts" / "shield_hit.wav": self.wav_tone_stack(rate, 760, 1560, 0.20, 0.45, 18),
        }
        for path, samples in generated.items():
            self.write_wav_if_missing(path, samples, rate)
        for index, character in enumerate(CHARACTER_SLOTS):
            cid = character["id"]
            root = GENERATED_AUDIO_DIR / "characters" / cid
            for category in ("select", "attack", "hit", "victory"):
                (root / category).mkdir(parents=True, exist_ok=True)
            base = 230 + index * 73
            for n in range(1, 3):
                self.write_wav_if_missing(
                    root / "select" / f"{cid}_select_{n:02d}.wav",
                    self.wav_voice_placeholder(rate, base + n * 23, 0.38, index * 10 + n),
                    rate,
                )
            for n in range(1, 4):
                self.write_wav_if_missing(
                    root / "attack" / f"{cid}_attack_{n:02d}.wav",
                    self.wav_voice_placeholder(rate, base + 120 + n * 31, 0.28, index * 20 + n),
                    rate,
                )
            self.write_wav_if_missing(
                root / "hit" / f"{cid}_hit_01.wav",
                self.wav_noise_chirp(rate, 0.20, 0.42, index * 30 + 4),
                rate,
            )
            self.write_wav_if_missing(
                root / "victory" / f"{cid}_victory_01.wav",
                self.wav_voice_placeholder(rate, base + 280, 0.58, index * 40 + 5),
                rate,
            )

    def write_wav_if_missing(self, path, samples, rate):
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        peak = max(0.001, max(abs(sample) for sample in samples))
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            frames = bytearray()
            for sample in samples:
                value = int(clamp(sample / peak * 0.78, -1.0, 1.0) * 32767)
                frames += struct.pack("<h", value)
            wav.writeframes(bytes(frames))

    def wav_tone_stack(self, rate, start_freq, end_freq, duration, gain, seed):
        rng = random.Random(seed)
        total = int(rate * duration)
        samples = []
        phase_a = 0.0
        phase_b = 0.0
        for i in range(total):
            t = i / max(1, total - 1)
            freq = start_freq + (end_freq - start_freq) * (t ** 0.65)
            phase_a += math.tau * freq / rate
            phase_b += math.tau * (freq * 0.5 + 14 * math.sin(t * math.tau * 6)) / rate
            noise = (rng.random() * 2 - 1) * 0.10 * max(0.0, 1.0 - t * 3)
            samples.append((math.sin(phase_a) * 0.44 + math.sin(phase_b) * 0.42 + noise) * gain * self.envelope(i, total))
        return samples

    def wav_noise_chirp(self, rate, duration, gain, seed):
        rng = random.Random(seed)
        total = int(rate * duration)
        phase = 0.0
        samples = []
        for i in range(total):
            t = i / max(1, total - 1)
            phase += math.tau * (120 + 800 * (1.0 - t)) / rate
            samples.append((math.sin(phase) * 0.35 + (rng.random() * 2 - 1) * 0.75) * gain * self.envelope(i, total))
        return samples

    def wav_voice_placeholder(self, rate, base_freq, duration, seed):
        rng = random.Random(seed)
        total = int(rate * duration)
        samples = []
        phase = 0.0
        for i in range(total):
            t = i / max(1, total - 1)
            syllable = 1.0 if int(t * 10) % 3 != 1 else 0.45
            freq = base_freq * (1.0 + 0.18 * math.sin(t * math.tau * 5 + seed))
            freq += rng.choice((-18, 0, 24)) if i % 900 == 0 else 0
            phase += math.tau * freq / rate
            buzz = 1.0 if math.sin(phase) > 0 else -1.0
            tone = math.sin(phase * 0.51) * 0.36 + buzz * 0.18
            samples.append(tone * syllable * 0.55 * self.envelope(i, total))
        return samples

    def load_generated_fight_audio(self):
        self.line_sounds.clear()
        replacements = {
            "count_3": [GENERATED_AUDIO_DIR / "ui" / "countdown_3"],
            "count_2": [GENERATED_AUDIO_DIR / "ui" / "countdown_2"],
            "count_1": [GENERATED_AUDIO_DIR / "ui" / "countdown_1"],
            "count_go": [GENERATED_AUDIO_DIR / "ui" / "fight"],
            "fight_count_3": [GENERATED_AUDIO_DIR / "ui" / "countdown_3"],
            "fight_count_2": [GENERATED_AUDIO_DIR / "ui" / "countdown_2"],
            "fight_count_1": [GENERATED_AUDIO_DIR / "ui" / "countdown_1"],
            "fight_count_go": [GENERATED_AUDIO_DIR / "ui" / "fight"],
            "ready": [GENERATED_AUDIO_DIR / "ui" / "fight"],
            "fight_hit": [GENERATED_AUDIO_DIR / "impacts" / "hit_crack"],
            "hit": [GENERATED_AUDIO_DIR / "impacts" / "hit_crack"],
            "fight_shield_hit": [GENERATED_AUDIO_DIR / "impacts" / "shield_hit"],
            "block": [GENERATED_AUDIO_DIR / "impacts" / "shield_hit"],
            "round": [GENERATED_AUDIO_DIR / "rounds" / "round_win"],
            "round_win": [GENERATED_AUDIO_DIR / "rounds" / "round_win"],
            "fight_round_win": [GENERATED_AUDIO_DIR / "rounds" / "round_win"],
            "fight_match_win": [GENERATED_AUDIO_DIR / "rounds" / "match_win"],
        }
        for key, paths in replacements.items():
            sound = self.load_first_audio_file(paths)
            if sound is not None:
                self.sounds[key] = sound

        for character in CHARACTER_SLOTS:
            cid = character["id"]
            root = GENERATED_AUDIO_DIR / "characters" / cid
            for category in ("select", "attack", "hit", "victory"):
                key = (cid, category)
                self.line_sounds[key] = []
                folder = root / category
                if not folder.exists():
                    continue
                paths = sorted(
                    path for path in folder.iterdir()
                    if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
                )
                custom_paths = [
                    path for path in paths
                    if not self.is_generated_voice_placeholder(cid, category, path)
                ]
                for path in (custom_paths or paths):
                    try:
                        self.line_sounds[key].append(pygame.mixer.Sound(str(path)))
                    except pygame.error:
                        pass

    def play(self, name, volume=1.0):
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound:
            if name in PRIORITY_SOUND_NAMES:
                self.play_priority_sound(sound, volume)
                return
            self.play_sound(sound, volume)

    def play_priority_sound(self, sound, volume=1.0):
        volume = clamp(volume, 0.0, 1.0)
        for channel in self.priority_channels:
            if not channel.get_busy():
                channel.play(sound)
                channel.set_volume(volume)
                return
        if not self.priority_channels:
            self.play_sound(sound, volume)
            return
        channel = self.priority_channels[self.priority_channel_index % len(self.priority_channels)]
        self.priority_channel_index += 1
        channel.play(sound)
        channel.set_volume(volume)

    def play_sound(self, sound, volume=1.0):
        volume = clamp(volume, 0.0, 1.0)
        channel = pygame.mixer.find_channel(force=True)
        if channel is None:
            sound.set_volume(volume)
            sound.play()
            return
        channel.play(sound)
        channel.set_volume(volume)

    def play_line(self, character_id, category, volume=1.0, cooldown=0.0):
        if not self.enabled:
            return
        now = time.time()
        key = (character_id, category)
        last = self.last_line_at.get(key, 0.0)
        if cooldown and now - last < cooldown:
            return
        choices = self.line_sounds.get(key, [])
        if not choices:
            return
        sound = random.choice(choices)
        self.play_sound(sound, volume)
        self.last_line_at[key] = now


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
            101: Player(101, "Broth Beast", PALETTE["p1"], PALETTE["p1_dark"], -0.95, 2.5, 90, "broth_beast"),
            102: Player(102, "Noodle Wyrm", PALETTE["p2"], PALETTE["p2_dark"], 0.95, 2.5, -90, "noodle_wyrm"),
        }
        self.radar_blobs = {}
        self.particles = []
        self.fight_particles = []
        self.fight_splats = []
        self.screen_flashes = []
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
        self.arena_pulse_until = 0.0
        self.round_winner_id = None
        self.match_winner_id = None
        self.round_presentation_started_at = 0.0
        self.round_countdown_started_at = 0.0
        self.round_countdown_last_step = -1
        self.match_win_started_at = 0.0
        self.hp_flash_until = {101: 0.0, 102: 0.0}
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
        self.icon_cache = {}
        self.bg_cache = None
        self.bg_cache_size = None
        self.soup_placeholder_cache = None
        self.soup_placeholder_cache_size = None

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

    def mark_magcal_command_sent(self, parts):
        if len(parts) < 5:
            return
        pid = int(parts[1])
        command = int(float(parts[2]))
        if command != 1:
            return
        duration_ms = int(float(parts[4]))
        self.mag_cal_status[pid] = MagCalStatus(
            player_id=pid,
            state="RUNNING",
            progress=8,
            quality=0,
            elapsed_ms=0,
            remaining_ms=duration_ms,
            flags=0x80,
            seen_at=time.time(),
        )
        self.log(f"P{pid} compass calibration started")

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

    def reset_round(self, start_playing=True):
        now = time.time()
        for player in self.players.values():
            player.hp = MAX_HP
            player.alive = True
            player.bubble_until = 0.0
            player.beam_ready_at = now + 0.4
            player.bubble_ready_at = now + 0.4
        self.beams.clear()
        self.particles.clear()
        self.fight_particles.clear()
        self.fight_splats.clear()
        self.impact_frames.clear()
        self.pending_actions.clear()
        self.hit_stop_until = 0.0
        self.freeze_until = 0.0
        self.screen_flashes.clear()
        self.arena_pulse_until = now + 0.34
        if start_playing:
            self.round_winner_id = None
            self.round_presentation_started_at = 0.0
            self.round_countdown_started_at = 0.0
            self.match_state = "playing"
            self.round_message = "FIGHT"
            self.sounds.play("ready")

    def reset_match(self):
        self.apply_menu_character_choices()
        for player in self.players.values():
            player.wins = 0
        self.reset_round()

    def start_next_round_countdown(self):
        now = time.time()
        self.reset_round(start_playing=False)
        self.match_state = "round_countdown"
        self.round_message = "NEXT ROUND"
        self.round_countdown_started_at = now
        self.round_countdown_last_step = -1
        self.add_screen_flash(PALETTE["soup"], 0.18, 80)

    def finish_next_round_countdown(self):
        now = time.time()
        self.match_state = "playing"
        self.round_message = "FIGHT"
        for player in self.players.values():
            player.beam_ready_at = now + 0.16
            player.bubble_ready_at = now + 0.16
        self.add_screen_flash(PALETTE["white"], 0.16, 120)
        self.shake(0.18, 8.0)

    def open_character_select(self):
        now = time.time()
        self.match_state = "select"
        self.round_message = "CHOOSE YOUR SOUP FIGHTER"
        self.round_reset_at = 0.0
        self.freeze_until = 0.0
        self.hit_stop_until = 0.0
        self.round_winner_id = None
        self.match_winner_id = None
        self.round_presentation_started_at = 0.0
        self.round_countdown_started_at = 0.0
        self.round_countdown_last_step = -1
        self.match_win_started_at = 0.0
        self.pending_actions.clear()
        self.beams.clear()
        self.impact_frames.clear()
        self.fight_particles.clear()
        self.fight_splats.clear()
        self.screen_flashes.clear()
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
            player.character_id = character["id"]
            self.player_sprite_paths[pid] = character["portrait"]
        self.sprite_cache.clear()

    def play_menu_sound(self, name, extra=1.0):
        volume = MENU_SFX_VOLUME.get(name, 1.0) * MENU_SFX_MASTER_VOLUME * extra
        self.sounds.play(name, volume)

    def character_by_id(self, character_id):
        for character in CHARACTER_SLOTS:
            if character["id"] == character_id:
                return character
        return CHARACTER_SLOTS[0]

    def character_for_player(self, player):
        return self.character_by_id(player.character_id)

    def attack_profile_for_player(self, player):
        character = self.character_for_player(player)
        return ATTACK_PROFILES.get(character.get("attack_type", "razor"), ATTACK_PROFILES["razor"])

    def play_fight_sound(self, name, extra=1.0):
        volume = FIGHT_SFX_VOLUME.get(name, 1.0) * FIGHT_SFX_MASTER_VOLUME * extra
        self.sounds.play(name, volume)

    def play_character_line(self, player, category, cooldown=0.0, extra=1.0):
        self.sounds.play_line(
            player.character_id,
            category,
            FIGHT_VOICE_MASTER_VOLUME * extra,
            cooldown=cooldown,
        )

    def desired_music_track(self):
        if self.match_state in MENU_STATES:
            selected = any(state.selected_index is not None for state in self.menu_players.values())
            return "lobby2" if selected else "lobby1"
        if self.match_state == "match_over":
            return None
        if self.match_state in ("playing", "round_over", "round_countdown"):
            match_point = any(player.wins >= WIN_ROUNDS - 1 for player in self.players.values())
            if (
                match_point
                and self.match_state == "playing"
                and any(player.alive and player.hp <= 1 for player in self.players.values())
            ):
                return "battle3"
            if match_point:
                return "battle2"
            return "battle1"
        return "lobby1"

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
            elif tag == "PLAYER_LOCAL" and len(parts) >= 5:
                pid = int(parts[1])
                heading = float(parts[2])
                action = self.parse_action(parts[3])
                seq = int(parts[4])
                self.apply_player_packet(pid, heading, action, seq, None, 0)
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
            elif tag == "PLAYERCMD_SENT":
                self.mark_magcal_command_sent(parts)
                self.log(line[:90])
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
        now = time.time()
        player = self.players.get(pid)
        if player is None:
            if action != ACTION_NONE:
                self.log(f"unknown P{pid} action={action} seq={seq}")
            return
        player.heading = normalize_deg(heading)
        player.last_seen_at = now
        if rssi is not None and rssi < 0:
            player.rssi = rssi if player.rssi is None else player.rssi * 0.85 + rssi * 0.15
        if action != ACTION_NONE and seq != player.last_action_seq:
            player.last_action_seq = seq
            label = "beam" if action == ACTION_BEAM else "bubble" if action == ACTION_BUBBLE else str(action)
            self.log(f"P{pid} {label} seq={seq} state={self.match_state}")
            self.request_action(player, action)

    def update_identity_from_radar(self):
        now = time.time()
        blobs = [
            blob for blob in self.radar_blobs.values()
            if blob.resolution > 0 and now - blob.seen_at < RADAR_BLOB_TIMEOUT and
            ARENA_MIN_X - 0.7 <= blob.x <= ARENA_MAX_X + 0.7 and
            ARENA_MIN_Y - 0.8 <= blob.y <= ARENA_MAX_Y + 0.8
        ]
        if not blobs:
            return
        left_blobs = [blob for blob in blobs if blob.x <= RADAR_SPLIT_X]
        right_blobs = [blob for blob in blobs if blob.x > RADAR_SPLIT_X]
        pairs = []
        p1_blob = self.choose_side_blob(self.players[101], left_blobs, now)
        if p1_blob is not None:
            pairs.append((self.players[101], p1_blob))
        p2_blob = self.choose_side_blob(self.players[102], right_blobs, now)
        if p2_blob is not None:
            pairs.append((self.players[102], p2_blob))

        for player, blob in pairs:
            self.move_player_toward_blob(player, blob, now)

    def choose_side_blob(self, player, blobs, now):
        if not blobs:
            return None
        tracking_age = now - player.track_updated_at if player.track_updated_at else 999.0
        predict_dt = clamp(tracking_age, 0.0, 0.22)
        predicted_x = player.x + player.vx * predict_dt * 0.35
        predicted_y = player.y + player.vy * predict_dt * 0.35
        return min(
            blobs,
            key=lambda blob: (
                math.hypot(blob.x - predicted_x, blob.y - predicted_y)
                - (0.22 * max(0.35, player.track_confidence) if player.track_slot == blob.slot else 0.0),
                blob.range_m,
                blob.slot,
            ),
        )

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
        if action == ACTION_BEAM and state.selected_index is None:
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
            self.sounds.play_line(character["id"], "select", FIGHT_VOICE_MASTER_VOLUME * 0.82, cooldown=0.2)
            self.spawn_menu_lock_fx(state.player_id, index)
            self.shake(0.12, MENU_SHAKE_SELECT)
            if self.all_menu_players_selected():
                self.start_menu_countdown()
            return
        if action == ACTION_BUBBLE and state.selected_index is None:
            self.menu_deny(state, "NOT LOCKED")
            return
        if action in (ACTION_BEAM, ACTION_BUBBLE):
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
            self.play_fight_sound("fight_shield")
            self.spawn_ring(player.x, player.y, PALETTE["bubble"], 34)
            self.spawn_shield_flare(player)
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
        character = self.character_for_player(player)
        profile = self.attack_profile_for_player(player)
        dx, dy = heading_vec(player.heading)
        target = self.players[102 if player.player_id == 101 else 101]
        dx, dy = self.assisted_beam_direction(player, target, dx, dy)
        direction = (dx, dy)
        start = (player.x + dx * 0.18, player.y + dy * 0.18)
        end = (player.x + dx * BEAM_RANGE_M, player.y + dy * BEAM_RANGE_M)
        self.spawn_startup_fx(player, start, direction)
        hit_point = None
        blocked = False
        if target.alive:
            if target.bubble_active(now):
                distance, along = point_segment_distance(target.position(), start, end)
                if distance <= BUBBLE_RADIUS_M:
                    blocked = True
                    hit_point = target.position()
                    self.sounds.play("block")
                    self.play_fight_sound(profile.get("shieldHitSound", "fight_shield_hit"))
                    self.spawn_burst(target.x, target.y, PALETTE["bubble"], 52, power=1.35)
                    self.spawn_shield_block_fx(target, hit_point, character, profile, direction)
                    self.shake(0.10, SHIELD_BLOCK_SHAKE)
                    self.send_fx("bubble_block")
            if not blocked:
                distance, along = point_segment_distance(target.position(), start, end)
                if distance <= BEAM_WIDTH_M and along > 0.03:
                    hit_point = (
                        start[0] + (end[0] - start[0]) * along,
                        start[1] + (end[1] - start[1]) * along,
                    )
                    self.damage_player(player, target, hit_point, direction)

        beam = BeamEffect(
            start, end, player.color, now,
            hit_point=hit_point,
            blocked=blocked,
            attacker_id=player.player_id,
            attack_type=profile["id"],
            direction=direction,
        )
        self.beams.append(beam)
        visible_end = hit_point if hit_point else end
        self.spawn_attack_particles(player, start, visible_end, hit_point, blocked, direction)
        if hit_point is None:
            self.spawn_miss_fx(player, end, direction)
        self.spawn_burst(start[0], start[1], player.color, 16, power=0.65)
        self.play_fight_sound(profile.get("muzzleSound", profile["sound"]))
        travel_sound = profile.get("travelSound")
        if travel_sound and travel_sound != profile.get("muzzleSound", profile["sound"]):
            self.play_fight_sound(travel_sound, extra=0.62)
        self.play_character_line(player, "attack", cooldown=ATTACK_LINE_COOLDOWN, extra=0.92)
        self.add_screen_flash(character["theme"], 0.10, profile.get("paletteFlashOpacity", 44) * 0.42)
        self.arena_pulse_until = max(self.arena_pulse_until, now + 0.22)
        self.shake(profile.get("screenShakeDuration", 0.08), profile.get("screenShakeAmount", profile["camera_shake"]))
        self.send_fx("beam_fire")

    def damage_player(self, attacker, target, hit_point, direction):
        now = time.time()
        profile = self.attack_profile_for_player(attacker)
        character = self.character_for_player(attacker)
        target.hp -= 1
        self.hp_flash_until[target.player_id] = now + 0.52
        self.play_fight_sound(profile.get("hitSound", "fight_hit"))
        self.play_character_line(target, "hit", cooldown=0.65, extra=0.64)
        self.spawn_burst(hit_point[0], hit_point[1], PALETTE["white"], 34, power=1.0)
        self.spawn_burst(target.x, target.y, attacker.color, 28, power=0.8)
        self.spawn_hit_presentation(attacker, target, hit_point, direction)
        self.add_screen_flash(character["highlight"], FIGHT_FLASH_DURATION, profile.get("paletteFlashOpacity", 92))
        self.add_impact(
            "hit", profile.get("impactFrameDuration", HIT_IMPACT_DURATION), attacker.color,
            attacker_id=attacker.player_id,
            target_id=target.player_id,
            hit_point=hit_point,
            attack_type=profile["id"],
            direction=direction,
        )
        if ENABLE_HIT_STOP:
            self.hit_stop_until = max(self.hit_stop_until, now + profile.get("hitStopDuration", profile["hit_stop"]))
        self.shake(0.16, profile["hit_shake"])
        self.send_fx("beam_hit")
        if target.hp <= 0:
            target.alive = False
            attacker.wins += 1
            self.handle_round_end(attacker, target)

    def handle_round_end(self, winner, loser):
        now = time.time()
        self.match_state = "round_over"
        self.round_reset_at = now + ROUND_WIN_PRESENTATION
        self.round_winner_id = winner.player_id
        self.round_presentation_started_at = now
        self.pending_actions.clear()
        self.spawn_burst(loser.x, loser.y, PALETTE["soup"], 82, power=1.75)
        self.spawn_round_win_fx(winner, loser)
        match_won = winner.wins >= WIN_ROUNDS
        self.sounds.play("ko")
        if match_won:
            self.play_fight_sound("fight_match_win")
            self.play_character_line(winner, "victory", cooldown=0.0, extra=1.0)
        else:
            self.play_fight_sound("fight_round_win")
            self.play_character_line(winner, "victory", cooldown=1.0, extra=0.8)
        self.add_screen_flash(winner.color, 0.20, 110)
        self.shake(0.24, FIGHT_SHAKE_KO)
        self.send_fx("ko")
        if match_won:
            self.match_state = "match_over"
            self.round_message = f"{winner.label.upper()} WINS THE LAST BOWL"
            self.round_reset_at = now + MATCH_WIN_SCREEN_MIN_DURATION
            self.match_winner_id = winner.player_id
            self.match_win_started_at = now
            self.add_screen_flash(winner.color, 0.32, 150)
            self.shake(0.32, FIGHT_SHAKE_MATCH_WIN)
            self.send_fx("match_win")
        else:
            self.round_message = f"{winner.label.upper()} TAKES THE ROUND"

    def add_impact(self, kind, duration, color, attacker_id=None, target_id=None, hit_point=None, attack_type="razor", direction=(0.0, 1.0)):
        self.impact_frames.append(ImpactFrame(
            kind, time.time(), duration, color,
            attacker_id=attacker_id,
            target_id=target_id,
            hit_point=hit_point,
            attack_type=attack_type,
            direction=direction,
        ))

    def shake(self, duration, power):
        if not ENABLE_SCREEN_SHAKE:
            return
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
                    elif self.match_state == "match_over":
                        self.sounds.play("menu_select")
                        self.open_character_select()
                    else:
                        self.sounds.play("menu_select")
                        self.reset_match()
                elif event.key == pygame.K_m:
                    self.sounds.play("menu_move")
                elif event.key == pygame.K_z:
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
                elif self.args.fake and event.key in (pygame.K_f, pygame.K_r, pygame.K_SLASH, pygame.K_RSHIFT) and self.match_state in MENU_STATES:
                    player_id = 101 if event.key in (pygame.K_f, pygame.K_r) else 102
                    action = ACTION_BEAM if event.key in (pygame.K_f, pygame.K_SLASH) else ACTION_BUBBLE
                    player = self.players.get(player_id)
                    if player:
                        self.request_action(player, action)
                elif event.key in (pygame.K_1, pygame.K_2) and self.match_state in MENU_STATES:
                    player_id = 101 if event.key == pygame.K_1 else 102
                    self.force_menu_lock(player_id)
                elif event.key in (pygame.K_f, pygame.K_SLASH) and self.match_state in MENU_STATES:
                    player_id = 101 if event.key == pygame.K_f else 102
                    self.force_menu_lock(player_id)

    def force_menu_lock(self, player_id):
        player = self.players.get(player_id)
        if player is None:
            return
        self.log(f"force P{player_id} select")
        self.request_action(player, ACTION_BEAM)

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
            button_action = ACTION_BEAM if keys[beam_key] else ACTION_BUBBLE if keys[bubble_key] else ACTION_NONE
            if self.match_state in MENU_STATES:
                self.fake_actions[pid] = button_action
                continue
            if button_action != ACTION_NONE and self.fake_actions[pid] == ACTION_NONE:
                self.request_action(player, button_action)
            self.fake_actions[pid] = button_action

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

        if self.match_state == "round_over" and now >= self.round_reset_at:
            self.start_next_round_countdown()

        if self.match_state == "round_countdown":
            self.update_round_countdown(now)

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
        self.update_fight_particles(dt, now)
        if now > self.shake_until:
            self.shake_power *= 0.85
        self.sounds.update_music(self.desired_music_track(), dt)

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

    def update_round_countdown(self, now):
        labels = ("3", "2", "1", "FIGHT!")
        elapsed = now - self.round_countdown_started_at
        step = int(elapsed / NEXT_ROUND_COUNTDOWN_STEP)
        if step < len(labels) and step != self.round_countdown_last_step:
            self.round_countdown_last_step = step
            sound = ("fight_count_3", "fight_count_2", "fight_count_1", "fight_count_go")[step]
            self.play_fight_sound(sound)
            color = self.players[101].color if step % 2 == 0 else self.players[102].color
            self.add_screen_flash(color, 0.12 if step < 3 else 0.18, 70 if step < 3 else 115)
            self.spawn_countdown_fx(color, step)
            self.shake(0.08 if step < 3 else 0.16, 4.0 if step < 3 else 8.0)
        if elapsed >= NEXT_ROUND_COUNTDOWN_TOTAL:
            self.finish_next_round_countdown()

    def update_fight_particles(self, dt, now):
        alive = []
        for particle in self.fight_particles:
            age = now - particle.created_at
            if age < particle.life:
                particle.x += particle.vx * dt
                particle.y += particle.vy * dt
                particle.vy += particle.gravity * dt
                particle.vx *= 0.986
                particle.vy *= 0.986
                particle.angle += particle.spin * dt
                alive.append(particle)
        self.fight_particles = alive[-FIGHT_MAX_PARTICLES:]
        self.fight_splats = [
            splat for splat in self.fight_splats
            if now - splat.created_at < splat.life
        ][-80:]
        self.screen_flashes = [
            flash for flash in self.screen_flashes
            if now - flash.created_at < flash.duration
        ][-16:]

    def add_screen_flash(self, color, duration, alpha):
        if not ENABLE_FIGHT_JUICE:
            return
        self.screen_flashes.append(ScreenFlash(color, time.time(), duration, alpha))

    def spawn_fight_particle(self, x, y, vx, vy, color, size, life, shape="pixel", layer="front", angle=0.0, spin=0.0, gravity=0.0, alpha=255.0, sprite_key=None):
        if not ENABLE_GENERATED_PARTICLES:
            return
        self.fight_particles.append(FightParticle(
            x, y, vx, vy, color, size, time.time(), life,
            shape=shape, layer=layer, angle=angle, spin=spin,
            gravity=gravity, alpha=alpha, sprite_key=sprite_key,
        ))

    def attack_particle_budget(self, profile, base_count):
        density = profile.get("particleDensity", 1.0) * ATTACK_EFFECT_INTENSITY
        return max(6, min(ATTACK_MAX_PARTICLES, int(base_count * density)))

    def attack_colors(self, character):
        return (
            character["dark"],
            character["theme"],
            character["secondary"],
            character["highlight"],
            character["accent"],
            PALETTE["white"],
        )

    def themed_particle_key(self, attack_type, role, index=0):
        if attack_type == "payment":
            return random.choice((
                "fx:qr", "fx:qr", "fx:yen", "fx:yuan",
                "fx:receipt", "fx:red_packet", "fx:check", "fx:scan",
            ))
        if attack_type == "youtube":
            return random.choice((
                "yt:play", "yt:play", "yt:triangle", "yt:like",
                "yt:subscribe", "yt:comment", "yt:bell", "yt:timeline",
            ))
        if attack_type == "ceiling":
            return "ceiling:seal" if role != "spark" or index % 4 else "ceiling:seal_face"
        return None

    def spawn_startup_fx(self, player, start, direction):
        character = self.character_for_player(player)
        profile = self.attack_profile_for_player(player)
        attack_type = profile["id"]
        dx, dy = normalize_vec(*direction)
        nx, ny = -dy, dx
        sx, sy = start
        now = time.time()
        life = profile.get("startupVisualDuration", ATTACK_STARTUP_VISUAL)
        self.fight_splats.append(FightSplat(
            player.x, player.y + 0.18,
            character["theme"], character["dark"], character["highlight"],
            now, max(0.12, life * 2.8), 0.34, random.randint(0, 999999),
            kind=f"startup_{attack_type}", direction=direction,
        ))
        count = self.attack_particle_budget(profile, 18 if attack_type != "torrent" else 30)
        if attack_type in ("payment", "youtube", "ceiling"):
            count = self.attack_particle_budget(profile, 30 if attack_type != "ceiling" else 22)
        for i in range(count):
            angle = math.tau * i / count + random.uniform(-0.30, 0.30)
            orbit = random.uniform(0.14, 0.44)
            px = sx + math.cos(angle) * orbit + nx * random.uniform(-0.05, 0.05)
            py = sy + math.sin(angle) * orbit + ny * random.uniform(-0.05, 0.05)
            vx = (sx - px) * random.uniform(5.5, 9.5) + dx * random.uniform(0.1, 0.5)
            vy = (sy - py) * random.uniform(5.5, 9.5) + dy * random.uniform(0.1, 0.5)
            shape = {
                "razor": "slash",
                "torrent": "steam",
                "emblem": "image",
                "chain": "spark",
                "fire": "ember",
                "spiral": "streak",
            }.get(attack_type, "diamond")
            if attack_type in ("payment", "youtube", "ceiling"):
                shape = "image" if i % 2 == 0 or attack_type == "ceiling" else random.choice(("pixel", "streak", "diamond"))
            sprite_key = f"{character['id']}:attack" if shape == "image" else None
            if shape == "image" and attack_type in ("payment", "youtube", "ceiling"):
                sprite_key = self.themed_particle_key(attack_type, "startup", i)
            self.spawn_fight_particle(
                px, py, vx, vy,
                random.choice(self.attack_colors(character)),
                random.uniform(0.018, 0.080 if attack_type in ("payment", "youtube") else 0.130),
                random.uniform(0.10, 0.30 if attack_type in ("payment", "youtube", "ceiling") else 0.22),
                shape=shape,
                layer="back" if i % 3 == 0 else "front",
                angle=math.atan2(dy, dx) + random.uniform(-1.0, 1.0),
                spin=random.uniform(-18.0, 18.0),
                sprite_key=sprite_key,
                alpha=185,
            )

    def spawn_attack_particles(self, player, start, end, hit_point, blocked, direction=None):
        character = self.character_for_player(player)
        profile = self.attack_profile_for_player(player)
        attack_type = profile["id"]
        sx, sy = start
        ex, ey = end
        vx = ex - sx
        vy = ey - sy
        length = max(0.001, math.hypot(vx, vy))
        dx, dy = normalize_vec(*(direction if direction else (vx, vy)))
        nx = -dy
        ny = dx
        base_count = {
            "razor": 56,
            "torrent": 118,
            "emblem": 42,
            "chain": 72,
            "fire": 122,
            "spiral": 72,
            "payment": 112,
            "youtube": 118,
            "ceiling": 118,
        }.get(attack_type, 58)
        count = self.attack_particle_budget(profile, base_count)
        colors = self.attack_colors(character)
        for i in range(count):
            t = random.random()
            pressure_band = 0.65 + 0.35 * math.sin(t * math.tau * 3.0 + time.time() * 12.0)
            spread = 0.035 + t * 0.13
            if attack_type in ("torrent", "fire", "youtube"):
                spread *= 1.75 + 0.35 * pressure_band
            if attack_type == "payment":
                spread *= 1.35
            if attack_type == "ceiling":
                spread *= 2.15
            if attack_type == "spiral":
                spread += abs(math.sin(t * math.tau * 3.0)) * 0.16
            px = sx + vx * t + nx * random.uniform(-spread, spread)
            py = sy + vy * t + ny * random.uniform(-spread, spread)
            forward = random.uniform(0.45, 1.8)
            side = random.uniform(-0.85, 0.85)
            shape = "pixel"
            size = random.uniform(0.018, 0.06)
            life = random.uniform(0.14, 0.42)
            gravity = 0.0
            alpha = 230.0
            if attack_type == "razor":
                shape = random.choice(("slash", "diamond", "streak"))
                size = random.uniform(0.025, 0.078)
            elif attack_type == "torrent":
                shape = random.choice(("pixel", "droplet", "steam", "streak"))
                size = random.uniform(0.018, 0.090)
                life = random.uniform(0.24, STEAM_FADE_DURATION)
                alpha = 205.0
            elif attack_type == "emblem":
                shape = "image" if i % 3 == 0 else random.choice(("diamond", "spark", "streak"))
                size = random.uniform(0.04, 0.11)
                life = random.uniform(0.22, 0.52)
            elif attack_type == "chain":
                shape = random.choice(("spark", "streak", "diamond"))
                size = random.uniform(0.018, 0.058)
                life = random.uniform(0.11, 0.32)
            elif attack_type == "fire":
                shape = random.choice(("ember", "pixel", "steam"))
                size = random.uniform(0.025, 0.095)
                gravity = random.uniform(-0.38, -0.12)
                life = random.uniform(0.26, 0.68)
            elif attack_type == "spiral":
                shape = random.choice(("diamond", "streak", "droplet"))
                size = random.uniform(0.02, 0.068)
                side += math.sin(t * math.tau * 4.0) * 0.65
            elif attack_type == "payment":
                shape = "image" if i % 2 == 0 else random.choice(("pixel", "streak", "diamond"))
                size = random.uniform(0.026, 0.088)
                life = random.uniform(0.18, 0.48)
                alpha = 235.0 if i % 4 else 170.0
            elif attack_type == "youtube":
                shape = "image" if i % 2 == 0 else random.choice(("pixel", "streak", "diamond"))
                size = random.uniform(0.032, 0.105)
                life = random.uniform(0.16, 0.46)
            elif attack_type == "ceiling":
                shape = "image" if i % 3 != 0 else random.choice(("steam", "streak", "diamond"))
                size = random.uniform(0.095, 0.230)
                life = random.uniform(0.42, 1.05)
                alpha = 255.0
                side += math.sin(t * math.tau * 5.0) * 0.55
            sprite_key = f"{character['id']}:attack" if shape == "image" else None
            if shape == "image" and attack_type in ("payment", "youtube", "ceiling"):
                sprite_key = self.themed_particle_key(attack_type, "travel", i)
            self.spawn_fight_particle(
                px, py,
                dx * forward + nx * side,
                dy * forward + ny * side + (-0.35 if attack_type == "fire" else 0.0),
                random.choice(colors),
                size,
                life,
                shape=shape,
                layer="front" if i % 4 else "back",
                angle=math.atan2(dy, dx) + random.uniform(-0.7, 0.7),
                spin=random.uniform(-9.0, 9.0),
                gravity=gravity,
                alpha=alpha,
                sprite_key=sprite_key,
            )

        self.spawn_muzzle_fx(start, dx, dy, character, attack_type, profile)
        if hit_point:
            self.spawn_hit_splat(hit_point[0], hit_point[1], character, attack_type, direction=direction, kind=f"contact_{attack_type}")

    def spawn_muzzle_fx(self, start, dx, dy, character, attack_type, profile=None):
        sx, sy = start
        nx, ny = -dy, dx
        profile = profile or ATTACK_PROFILES.get(attack_type, ATTACK_PROFILES["razor"])
        self.fight_splats.append(FightSplat(
            sx, sy, character["theme"], character["dark"], character["highlight"],
            time.time(), 0.18, 0.22 * ATTACK_MUZZLE_BURST_SIZE,
            random.randint(0, 999999), kind=f"muzzle_{attack_type}", direction=(dx, dy),
        ))
        count = self.attack_particle_budget(profile, 26)
        for i in range(count):
            side = random.uniform(-1.15, 1.15)
            power = random.uniform(0.6, 2.6) * ATTACK_MUZZLE_BURST_SIZE
            if attack_type == "razor":
                shape = "slash"
                side += (i % 3 - 1) * 0.7
            elif attack_type == "torrent":
                shape = random.choice(("droplet", "steam", "streak"))
            elif attack_type == "emblem":
                shape = "image" if i % 3 == 0 else "spark"
            elif attack_type == "chain":
                shape = "spark"
            elif attack_type == "fire":
                shape = random.choice(("ember", "pixel", "steam"))
            elif attack_type == "spiral":
                shape = random.choice(("streak", "droplet"))
                side += math.sin(i * math.tau / max(1, count)) * 0.85
            elif attack_type in ("payment", "youtube", "ceiling"):
                shape = "image" if i % 2 == 0 or attack_type == "ceiling" else random.choice(("streak", "diamond", "pixel"))
            else:
                shape = "streak"
            sprite_key = f"{character['id']}:attack" if shape == "image" else None
            if shape == "image" and attack_type in ("payment", "youtube", "ceiling"):
                sprite_key = self.themed_particle_key(attack_type, "muzzle", i)
            particle_size = random.uniform(0.025, 0.090)
            particle_life = random.uniform(0.14, 0.36)
            if attack_type == "ceiling":
                particle_size = random.uniform(0.085, 0.210)
                particle_life = random.uniform(0.38, 0.82)
            self.spawn_fight_particle(
                sx - dx * random.uniform(0.0, 0.05), sy - dy * random.uniform(0.0, 0.05),
                dx * power + nx * side,
                dy * power + ny * side + (-0.25 if attack_type == "fire" else 0.0),
                random.choice((character["theme"], character["secondary"], character["highlight"], character["accent"])),
                particle_size,
                particle_life,
                shape=shape,
                angle=math.atan2(dy, dx) + random.uniform(-0.35, 0.35),
                spin=random.uniform(-16, 16),
                gravity=-0.10 if attack_type == "fire" else 0.0,
                sprite_key=sprite_key,
            )

    def spawn_miss_fx(self, player, end, direction):
        character = self.character_for_player(player)
        profile = self.attack_profile_for_player(player)
        attack_type = profile["id"]
        dx, dy = normalize_vec(*direction)
        nx, ny = -dy, dx
        ex, ey = end
        self.fight_splats.append(FightSplat(
            ex, ey, character["theme"], character["dark"], character["highlight"],
            time.time(), 0.26 + profile.get("effectLifetime", 0.34) * 0.28,
            0.22, random.randint(0, 999999),
            kind=f"miss_{attack_type}", direction=direction,
        ))
        count = self.attack_particle_budget(profile, 14 if attack_type != "torrent" else 24)
        for i in range(count):
            side = random.uniform(-1.3, 1.3)
            back = random.uniform(-0.8, 0.35)
            shape = {
                "razor": "slash",
                "torrent": "steam",
                "emblem": "image",
                "chain": "spark",
                "fire": "steam",
                "spiral": "streak",
                "payment": "image",
                "youtube": "image",
                "ceiling": "image",
            }.get(attack_type, "diamond")
            sprite_key = f"{character['id']}:attack" if shape == "image" else None
            if shape == "image" and attack_type in ("payment", "youtube", "ceiling"):
                sprite_key = self.themed_particle_key(attack_type, "miss", i)
            particle_size = random.uniform(0.018, 0.060) * ATTACK_MISS_BURST_SIZE
            particle_life = random.uniform(0.20, 0.48)
            particle_alpha = 175
            if attack_type == "ceiling":
                particle_size = random.uniform(0.085, 0.190)
                particle_life = random.uniform(0.42, 0.92)
                particle_alpha = 235
            self.spawn_fight_particle(
                ex + nx * random.uniform(-0.10, 0.10),
                ey + ny * random.uniform(-0.10, 0.10),
                dx * back + nx * side,
                dy * back + ny * side + (-0.25 if attack_type == "fire" else 0.0),
                random.choice(self.attack_colors(character)),
                particle_size,
                particle_life,
                shape=shape,
                angle=math.atan2(dy, dx) + random.uniform(-1.0, 1.0),
                spin=random.uniform(-12, 12),
                gravity=-0.12 if attack_type in ("fire", "torrent") else 0.0,
                sprite_key=sprite_key,
                alpha=particle_alpha,
            )

    def spawn_hit_presentation(self, attacker, target, hit_point, direction):
        character = self.character_for_player(attacker)
        profile = self.attack_profile_for_player(attacker)
        attack_type = profile["id"]
        dx, dy = normalize_vec(*direction)
        nx, ny = -dy, dx
        self.spawn_hit_splat(hit_point[0], hit_point[1], character, attack_type, direction=direction, kind=f"hit_{attack_type}")
        self.fight_splats.append(FightSplat(
            target.x, target.y + 0.24,
            character["theme"], character["dark"], character["highlight"],
            time.time(), max(0.26, profile.get("effectLifetime", 0.38) + 0.08),
            0.45 * ATTACK_HIT_BURST_SIZE,
            random.randint(0, 999999),
            kind=f"reaction_{attack_type}", direction=direction,
        ))
        count = self.attack_particle_budget(profile, {
            "razor": 42,
            "torrent": 70,
            "emblem": 34,
            "chain": 48,
            "fire": 66,
            "spiral": 46,
            "payment": 78,
            "youtube": 82,
            "ceiling": 102,
        }.get(attack_type, 44))
        for i in range(count):
            angle = math.atan2(dy, dx) + random.uniform(-1.35, 1.35)
            if attack_type == "spiral":
                angle += math.pi * 0.5 * random.choice((-1, 1))
            speed = random.uniform(0.35, 2.3) * ATTACK_HIT_BURST_SIZE
            shape = random.choice(("diamond", "streak", "spark"))
            gravity = 0.0
            sprite_key = None
            if attack_type == "razor":
                shape = random.choice(("slash", "diamond", "streak"))
            elif attack_type == "torrent":
                shape = random.choice(("droplet", "steam", "pixel", "streak"))
                gravity = random.uniform(0.12, 0.40)
            elif attack_type == "emblem":
                shape = "image" if i % 2 == 0 else random.choice(("spark", "diamond"))
                sprite_key = f"{character['id']}:hit" if shape == "image" else None
                gravity = 0.35
            elif attack_type == "chain":
                shape = random.choice(("spark", "streak"))
            elif attack_type == "fire":
                shape = random.choice(("ember", "pixel", "steam"))
                gravity = random.uniform(-0.30, -0.05)
            elif attack_type == "spiral":
                shape = random.choice(("streak", "droplet", "diamond"))
            elif attack_type == "payment":
                shape = "image" if i % 2 == 0 else random.choice(("pixel", "streak", "diamond"))
                sprite_key = self.themed_particle_key(attack_type, "hit", i) if shape == "image" else None
            elif attack_type == "youtube":
                shape = "image" if i % 2 == 0 else random.choice(("pixel", "streak", "diamond"))
                sprite_key = self.themed_particle_key(attack_type, "hit", i) if shape == "image" else None
            elif attack_type == "ceiling":
                shape = "image" if i % 3 != 0 else random.choice(("steam", "streak", "diamond"))
                sprite_key = self.themed_particle_key(attack_type, "hit", i) if shape == "image" else None
                gravity = random.uniform(-0.06, 0.12)
                speed *= 1.18
            origin_x = target.x + dx * random.uniform(-0.02, 0.18) + nx * random.uniform(-0.18, 0.18)
            origin_y = target.y + 0.22 + dy * random.uniform(-0.02, 0.18) + ny * random.uniform(-0.14, 0.14)
            particle_size = random.uniform(0.020, 0.090)
            particle_life = random.uniform(0.20, profile.get("effectLifetime", 0.42) + 0.18)
            if attack_type == "ceiling":
                particle_size = random.uniform(0.090, 0.240) if shape == "image" else random.uniform(0.035, 0.095)
                particle_life = random.uniform(0.48, 1.10)
            self.spawn_fight_particle(
                origin_x, origin_y,
                math.cos(angle) * speed + dx * 0.45,
                math.sin(angle) * speed + dy * 0.45,
                random.choice(self.attack_colors(character)),
                particle_size,
                particle_life,
                shape=shape,
                layer="front",
                angle=math.atan2(dy, dx) + random.uniform(-1.2, 1.2),
                spin=random.uniform(-18, 18),
                gravity=gravity,
                sprite_key=sprite_key,
            )

    def spawn_hit_splat(self, x, y, character, attack_type, direction=(0.0, 1.0), kind=None):
        profile = ATTACK_PROFILES.get(attack_type, ATTACK_PROFILES["razor"])
        self.fight_splats.append(FightSplat(
            x, y,
            character["theme"],
            character["dark"],
            character["highlight"],
            time.time(),
            max(0.28, profile.get("effectLifetime", 0.36)),
            (0.36 if attack_type != "spiral" else 0.46) * ATTACK_HIT_BURST_SIZE,
            random.randint(0, 999999),
            kind=kind or attack_type,
            direction=direction,
        ))

    def spawn_shield_flare(self, player):
        character = self.character_for_player(player)
        now = time.time()
        self.fight_splats.append(FightSplat(
            player.x, player.y, character["secondary"], character["dark"], character["highlight"],
            now, 0.34, BUBBLE_RADIUS_M, random.randint(0, 999999), kind="shield"
        ))
        for i in range(24):
            angle = math.tau * i / 24
            self.spawn_fight_particle(
                player.x + math.cos(angle) * 0.12,
                player.y + math.sin(angle) * 0.12,
                math.cos(angle) * 0.8,
                math.sin(angle) * 0.8,
                character["secondary"],
                0.035,
                0.34,
                shape="diamond",
            )

    def spawn_shield_block_fx(self, player, hit_point, attacker_character=None, profile=None, direction=(0.0, 1.0)):
        defender = self.character_for_player(player)
        attacker_character = attacker_character or defender
        profile = profile or ATTACK_PROFILES["razor"]
        attack_type = profile["id"]
        dx, dy = normalize_vec(*direction)
        nx, ny = -dy, dx
        x, y = hit_point
        self.fight_splats.append(FightSplat(
            x, y, PALETTE["bubble"], defender["dark"], defender["highlight"],
            time.time(), 0.46, BUBBLE_RADIUS_M * 0.82,
            random.randint(0, 999999), kind=f"shield_block_{attack_type}", direction=direction,
        ))
        self.fight_splats.append(FightSplat(
            x - dx * 0.06, y - dy * 0.06, attacker_character["theme"], attacker_character["dark"], attacker_character["highlight"],
            time.time(), 0.34, BUBBLE_RADIUS_M * 0.54,
            random.randint(0, 999999), kind=f"blocked_attack_{attack_type}", direction=direction,
        ))
        for i in range(SHIELD_BLOCK_SPARK_COUNT):
            angle = math.atan2(-dy, -dx) + random.uniform(-1.35, 1.35)
            if i % 3 == 0:
                angle = random.random() * math.tau
            speed = random.uniform(0.35, 1.9)
            shape = random.choice(("spark", "diamond", "streak"))
            if attack_type == "razor":
                shape = random.choice(("slash", "diamond", "streak"))
            elif attack_type == "torrent":
                shape = random.choice(("droplet", "steam", "streak"))
            elif attack_type == "emblem":
                shape = "image" if i % 4 == 0 else "spark"
            elif attack_type == "fire":
                shape = random.choice(("ember", "pixel", "steam"))
            elif attack_type == "spiral":
                angle += math.sin(i) * 0.7
                shape = random.choice(("streak", "droplet"))
            elif attack_type in ("payment", "youtube", "ceiling"):
                shape = "image" if i % 2 == 0 or attack_type == "ceiling" else random.choice(("spark", "diamond", "streak"))
            sprite_key = f"{attacker_character['id']}:hit" if shape == "image" else None
            if shape == "image" and attack_type in ("payment", "youtube", "ceiling"):
                sprite_key = self.themed_particle_key(attack_type, "block", i)
            color_pool = (PALETTE["bubble"], defender["highlight"], PALETTE["white"], attacker_character["theme"], attacker_character["accent"])
            particle_size = random.uniform(0.018, 0.068)
            particle_life = random.uniform(0.18, 0.48)
            particle_alpha = 255.0
            if attack_type == "ceiling":
                particle_size = random.uniform(0.080, 0.185) if shape == "image" else random.uniform(0.028, 0.075)
                particle_life = random.uniform(0.42, 0.88)
                particle_alpha = 240.0
            self.spawn_fight_particle(
                x + nx * random.uniform(-0.06, 0.06),
                y + ny * random.uniform(-0.06, 0.06),
                math.cos(angle) * speed + nx * random.uniform(-0.35, 0.35),
                math.sin(angle) * speed + ny * random.uniform(-0.35, 0.35),
                random.choice(color_pool),
                particle_size,
                particle_life,
                shape=shape,
                angle=math.atan2(dy, dx) + random.uniform(-1.0, 1.0),
                spin=random.uniform(-14, 14),
                gravity=-0.10 if attack_type == "fire" else 0.0,
                sprite_key=sprite_key,
                alpha=particle_alpha,
            )

    def spawn_round_win_fx(self, winner, loser):
        character = self.character_for_player(winner)
        self.fight_splats.append(FightSplat(
            winner.x, winner.y + 0.4, character["theme"], character["dark"], character["highlight"],
            time.time(), 1.2, 0.85, random.randint(0, 999999), kind="round_win"
        ))
        for _ in range(90):
            angle = random.random() * math.tau
            self.spawn_fight_particle(
                winner.x, winner.y + random.uniform(0.0, 0.55),
                math.cos(angle) * random.uniform(0.4, 2.2),
                math.sin(angle) * random.uniform(0.4, 2.2),
                random.choice((character["theme"], character["secondary"], character["highlight"], character["accent"])),
                random.uniform(0.025, 0.09),
                random.uniform(0.38, 1.1),
                shape=random.choice(("spark", "diamond", "streak", "pixel")),
            )

    def spawn_countdown_fx(self, color, step):
        x = 0.0
        y = (ARENA_MIN_Y + ARENA_MAX_Y) * 0.5
        for _ in range(38 + step * 10):
            angle = random.random() * math.tau
            speed = random.uniform(0.7, 2.8)
            self.spawn_fight_particle(
                x + math.cos(angle) * random.uniform(0, 0.28),
                y + math.sin(angle) * random.uniform(0, 0.20),
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                color,
                random.uniform(0.025, 0.09),
                random.uniform(0.18, 0.48),
                shape=random.choice(("spark", "diamond", "streak")),
            )

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
        self.draw_fight_splats(offset, below=True)
        self.draw_particles(offset, below=True)
        self.draw_fight_particles(offset, below=True)
        for beam in self.beams:
            self.draw_beam(beam, offset)
        for player in self.players.values():
            self.draw_bubble(player, offset)
        for player in sorted(self.players.values(), key=lambda p: p.y, reverse=True):
            self.draw_player(player, offset)
        self.draw_particles(offset, below=False)
        self.draw_fight_splats(offset, below=False)
        self.draw_fight_particles(offset, below=False)
        self.draw_hud()
        self.draw_messages()
        self.draw_round_presentation()
        self.draw_round_countdown_overlay()
        self.draw_match_win_screen()
        self.draw_magcal_overlay()
        self.draw_screen_flashes()
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
        now = time.time()
        w, h = size
        for i in range(24):
            x = (i * 143 + now * 42) % (w + 180) - 90
            y = (i * 71 + now * 22) % (h + 120) - 60
            color = rgba(PALETTE["soup_deep"] if i % 4 == 0 else PALETTE["light_brown"], 18 + (i % 3) * 9)
            self.draw_slanted_strip(x, y, 90 + (i % 5) * 28, 4 + (i % 3) * 3, -0.42, color)
        p1 = self.players[101].color if 101 in self.players else PALETTE["p1"]
        p2 = self.players[102].color if 102 in self.players else PALETTE["p2"]
        self.draw_halftone_field((72, h - 86), 150, p1, 0.28, now)
        self.draw_halftone_field((w - 72, 110), 150, p2, 0.28, now + 0.9)

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

    def soup_placeholder_image(self, target_size):
        target_size = (max(1, int(target_size[0])), max(1, int(target_size[1])))
        if self.soup_placeholder_cache_size == target_size:
            return self.soup_placeholder_cache
        self.soup_placeholder_cache_size = target_size
        self.soup_placeholder_cache = None
        if not SOUP_PLACEHOLDER_SPRITE.exists():
            return None
        try:
            surf = pygame.image.load(str(SOUP_PLACEHOLDER_SPRITE)).convert_alpha()
            bounds = surf.get_bounding_rect(8)
            if bounds.width > 0 and bounds.height > 0:
                surf = surf.subsurface(bounds).copy()
            scale = min(target_size[0] / surf.get_width(), target_size[1] / surf.get_height())
            size = (
                max(1, int(surf.get_width() * scale)),
                max(1, int(surf.get_height() * scale)),
            )
            self.soup_placeholder_cache = pygame.transform.smoothscale(surf, size)
        except pygame.error as exc:
            self.log(f"soup placeholder failed: {exc}")
        return self.soup_placeholder_cache

    def draw_last_bowl_emblem(self, arena_rect):
        emblem = pygame.Rect(0, 0, max(118, arena_rect.width // 10), max(68, arena_rect.height // 8))
        emblem.center = (arena_rect.centerx, arena_rect.top + emblem.height // 2 + 14)
        panel = emblem.inflate(22, 18)
        self.draw_skew_panel(panel.move(0, 5), (0, 0, 0, 150), None, cut=12)
        self.draw_skew_panel(panel, rgba(PALETTE["bg"], 196), rgba(PALETTE["soup_deep"], 210), cut=12, border_width=2)

        image = self.soup_placeholder_image(emblem.size)
        if image is not None:
            self.screen.blit(image, image.get_rect(center=emblem.center))
        else:
            bowl = emblem.inflate(-8, -18)
            pygame.draw.ellipse(self.screen, PALETTE["dark_brown"], bowl.inflate(10, 10))
            pygame.draw.ellipse(self.screen, PALETTE["brown"], bowl)
            pygame.draw.ellipse(self.screen, PALETTE["soup"], bowl.inflate(-16, -18))
            for i in range(3):
                x = bowl.centerx - 24 + i * 24
                pygame.draw.arc(self.screen, rgba(PALETTE["light_brown"], 170), (x, bowl.top - 26, 20, 34), 3.7, 5.5, 2)

        text = self.small_font.render("THE LAST BOWL", True, PALETTE["soup"])
        label = text.get_rect(center=(arena_rect.centerx, panel.bottom + 13))
        self.draw_skew_panel(label.inflate(22, 10), rgba(PALETTE["bg"], 185), rgba(PALETTE["light_brown"], 150), cut=7, border_width=1)
        shadow = self.small_font.render("THE LAST BOWL", True, (0, 0, 0))
        self.screen.blit(shadow, label.move(2, 2))
        self.screen.blit(text, label)

    def draw_arena(self, offset):
        rect = self.world_rect().move(offset)
        shadow = rect.move(0, 10)
        pygame.draw.rect(self.screen, (0, 0, 0), shadow, border_radius=22)
        pygame.draw.rect(self.screen, PALETTE["panel"], rect, border_radius=22)
        inner = rect.inflate(-22, -22)
        pygame.draw.rect(self.screen, (25, 18, 15), inner, border_radius=16)
        pygame.draw.rect(self.screen, PALETTE["dark_brown"], rect, 5, border_radius=22)
        pygame.draw.rect(self.screen, PALETTE["light_brown"], inner, 1, border_radius=16)
        pulse = clamp((self.arena_pulse_until - time.time()) / 0.34, 0.0, 1.0)
        if pulse > 0.0:
            pulse_color = self.players.get(self.round_winner_id, self.players[101]).color if self.round_winner_id else PALETTE["soup"]
            pygame.draw.rect(self.screen, rgba(pulse_color, 180 * pulse), rect.inflate(int(18 * pulse), int(18 * pulse)), max(2, int(5 * pulse)), border_radius=24)

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

        self.draw_last_bowl_emblem(rect)

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

    def draw_fight_splats(self, offset, below):
        now = time.time()
        for splat in self.fight_splats:
            back_layer = splat.kind in ("round_win", "shield") or splat.kind.startswith("startup_")
            if below != back_layer:
                continue
            age = now - splat.created_at
            frac = clamp(1.0 - age / max(0.001, splat.life), 0.0, 1.0)
            sx, sy = self.world_to_screen(splat.x, splat.y, offset)
            attack_type = self.attack_type_from_splat(splat.kind)
            if splat.kind == "shield" or splat.kind.startswith("shield_block"):
                self.draw_shield_splat((sx, sy), splat, frac)
            elif splat.kind.startswith("blocked_attack_"):
                self.draw_attack_hit_splat((sx, sy), splat, frac, attack_type, blocked=True)
            elif splat.kind.startswith("reaction_"):
                self.draw_victim_reaction_splat((sx, sy), splat, frac, attack_type)
            elif splat.kind.startswith("hit_") or splat.kind.startswith("contact_"):
                self.draw_attack_hit_splat((sx, sy), splat, frac, attack_type)
            elif splat.kind.startswith("miss_"):
                self.draw_miss_splat((sx, sy), splat, frac, attack_type)
            elif splat.kind.startswith("muzzle_"):
                self.draw_muzzle_splat((sx, sy), splat, frac, attack_type)
            elif splat.kind.startswith("startup_"):
                self.draw_startup_splat((sx, sy), splat, frac, attack_type)
            elif splat.kind == "spiral":
                self.draw_spiral_splat((sx, sy), splat, frac)
            else:
                self.draw_jagged_splash((sx, sy), self.meters_to_px(splat.radius) * (1.0 + 0.25 * (1 - frac)), splat.color, splat.seed, alpha=105 * frac, stretch=(1.25, 0.78))
                self.draw_starburst((sx, sy), self.meters_to_px(splat.radius) * 0.65, splat.highlight, 90 * frac, seed=splat.seed + 8)

    def attack_type_from_splat(self, kind):
        for attack_type in ATTACK_PROFILES:
            if kind == attack_type or kind.endswith(f"_{attack_type}"):
                return attack_type
        return "razor"

    def screen_direction(self, direction):
        dx, dy = normalize_vec(*direction)
        return normalize_vec(dx, -dy)

    def draw_shield_splat(self, center, splat, frac):
        attack_type = self.attack_type_from_splat(splat.kind)
        radius = self.meters_to_px(splat.radius) * (0.85 + 0.22 * (1 - frac))
        contact_dx, contact_dy = self.screen_direction(splat.direction)
        dent = 1.0 + (0.18 if splat.kind.startswith("shield_block") else 0.0)
        for i in range(8):
            angle = i * math.tau / 8 + time.time() * 2.8
            pulse = 1.0 + (0.12 * math.cos(angle - math.atan2(contact_dy, contact_dx)) if splat.kind.startswith("shield_block") else 0.0)
            p1 = (center[0] + math.cos(angle) * radius * 0.72 * pulse, center[1] + math.sin(angle) * radius * 0.72 * pulse)
            p2 = (center[0] + math.cos(angle + 0.36) * radius * dent, center[1] + math.sin(angle + 0.36) * radius * dent)
            pygame.draw.line(self.screen, rgba(splat.highlight, 125 * frac), p1, p2, max(2, int(5 * frac)))
        pygame.draw.circle(self.screen, rgba(splat.color, 55 * frac), center, int(radius))
        self.draw_broken_ring(center, splat.highlight, int(radius), frac, splat.seed, direction=splat.direction, attack_type="shield")
        if splat.kind.startswith("shield_block"):
            for i in range(5):
                offset = (i - 2) * radius * 0.12
                p1 = (center[0] - contact_dx * radius * 0.18 - contact_dy * offset, center[1] - contact_dy * radius * 0.18 + contact_dx * offset)
                p2 = (center[0] - contact_dx * radius * 0.82 - contact_dy * offset * 0.55, center[1] - contact_dy * radius * 0.82 + contact_dx * offset * 0.55)
                color = splat.highlight if attack_type in ("chain", "emblem") else splat.color
                pygame.draw.line(self.screen, rgba(color, 150 * frac), p1, p2, max(2, int(3 * frac)))
            if attack_type == "payment":
                self.draw_scan_brackets(center, radius * 0.72, splat.highlight, 135 * frac)
                self.draw_currency_burst((center[0] - contact_dx * radius * 0.68, center[1] - contact_dy * radius * 0.68), radius * 0.35, splat, frac)
            elif attack_type == "youtube":
                self.draw_ui_bars((center[0] - contact_dx * radius * 0.42, center[1] - contact_dy * radius * 0.42), radius * 0.48, splat.color, frac)
            elif attack_type == "ceiling":
                self.draw_ceiling_splat((center[0] - contact_dx * radius * 0.52, center[1] - contact_dy * radius * 0.52), radius * 0.54, splat, frac, count=3)

    def draw_spiral_splat(self, center, splat, frac):
        points = []
        radius = self.meters_to_px(splat.radius)
        phase = time.time() * 8
        for i in range(46):
            t = i / 45
            angle = t * math.tau * 2.5 + phase
            r = radius * t * (0.4 + 0.8 * frac)
            points.append((center[0] + math.cos(angle) * r, center[1] + math.sin(angle) * r * 0.72))
        if len(points) > 2:
            pygame.draw.lines(self.screen, rgba(splat.dark_color, 130 * frac), False, points, 9)
            pygame.draw.lines(self.screen, rgba(splat.color, 220 * frac), False, points, 5)
            pygame.draw.lines(self.screen, rgba(splat.highlight, 190 * frac), False, points, 2)

    def draw_startup_splat(self, center, splat, frac, attack_type):
        radius = self.meters_to_px(splat.radius) * (0.55 + 0.45 * (1 - frac))
        dx, dy = self.screen_direction(splat.direction)
        nx, ny = -dy, dx
        if attack_type == "razor":
            for i in range(3):
                side = (i - 1) * radius * 0.22
                p1 = (center[0] - dx * radius * 0.55 + nx * side, center[1] - dy * radius * 0.55 + ny * side)
                p2 = (center[0] + dx * radius * 0.72 + nx * side * 0.35, center[1] + dy * radius * 0.72 + ny * side * 0.35)
                pygame.draw.line(self.screen, rgba(splat.dark_color, 115 * frac), p1, p2, max(2, int(7 * frac)))
                pygame.draw.line(self.screen, rgba(splat.highlight, 125 * frac), p1, p2, max(1, int(2 * frac)))
        elif attack_type == "emblem":
            self.draw_starburst(center, radius * 0.70, splat.color, 80 * frac, seed=splat.seed)
            self.draw_broken_ring(center, splat.highlight, int(radius * 0.92), frac, splat.seed + 3, attack_type="emblem")
        elif attack_type == "spiral":
            self.draw_spiral_splat(center, splat, frac)
        elif attack_type == "payment":
            self.draw_payment_startup_splat(center, radius, splat, frac)
        elif attack_type == "youtube":
            self.draw_youtube_play_splat(center, radius * 1.15, frac, angle=-8, alpha=150)
        elif attack_type == "ceiling":
            self.draw_ceiling_splat(center, radius, splat, frac, count=3)
        else:
            self.draw_broken_ring(center, splat.highlight, int(radius), frac, splat.seed, direction=splat.direction, attack_type=attack_type)

    def draw_muzzle_splat(self, center, splat, frac, attack_type):
        radius = self.meters_to_px(splat.radius) * (0.65 + 0.75 * (1 - frac))
        dx, dy = self.screen_direction(splat.direction)
        nx, ny = -dy, dx
        if attack_type == "razor":
            for i, color in enumerate((splat.dark_color, splat.color, splat.highlight)):
                width = max(2, int((13 - i * 4) * frac))
                offset = (i - 1) * radius * 0.18
                p1 = (center[0] - dx * radius * 0.22 + nx * offset, center[1] - dy * radius * 0.22 + ny * offset)
                p2 = (center[0] + dx * radius * 1.25 + nx * offset * 0.45, center[1] + dy * radius * 1.25 + ny * offset * 0.45)
                pygame.draw.line(self.screen, rgba(color, 205 * frac), p1, p2, width)
        elif attack_type == "torrent":
            self.draw_jagged_splash(center, radius, splat.highlight, splat.seed, alpha=95 * frac, stretch=(1.20, 0.86))
            self.draw_broken_ring(center, splat.color, int(radius * 1.15), frac, splat.seed, attack_type="torrent")
        elif attack_type == "emblem":
            self.draw_starburst(center, radius, splat.color, 125 * frac, seed=splat.seed)
            self.draw_broken_ring(center, splat.highlight, int(radius * 0.78), frac, splat.seed, attack_type="emblem")
        elif attack_type == "chain":
            for i in range(10):
                angle = i * math.tau / 10 + random.Random(splat.seed + i).uniform(-0.2, 0.2)
                p1 = (center[0] + math.cos(angle) * radius * 0.25, center[1] + math.sin(angle) * radius * 0.25)
                p2 = (center[0] + math.cos(angle) * radius * 1.20, center[1] + math.sin(angle) * radius * 1.20)
                pygame.draw.line(self.screen, rgba(splat.highlight, 150 * frac), p1, p2, max(1, int(3 * frac)))
        elif attack_type == "fire":
            self.draw_blocky_burst(center, radius, splat, frac, count=14)
        elif attack_type == "spiral":
            self.draw_spiral_splat(center, splat, frac)
        elif attack_type == "payment":
            self.draw_scan_brackets(center, radius * 1.15, splat.highlight, 195 * frac)
            self.draw_fake_qr_tile(center, radius * 0.82, splat.seed, frac, angle=time.time() * 120)
        elif attack_type == "youtube":
            self.draw_youtube_play_splat(center, radius * 1.28, frac, angle=math.degrees(math.atan2(dy, dx)), alpha=210)
            self.draw_ui_bars(center, radius, splat.color, frac)
        elif attack_type == "ceiling":
            self.draw_starburst(center, radius * 1.15, PALETTE["white"], 90 * frac, seed=splat.seed)
            self.draw_ceiling_splat(center, radius * 1.10, splat, frac, count=5)

    def draw_attack_hit_splat(self, center, splat, frac, attack_type, blocked=False):
        radius = self.meters_to_px(splat.radius) * (0.75 + 0.55 * (1 - frac))
        dx, dy = self.screen_direction(splat.direction)
        nx, ny = -dy, dx
        alpha = 145 * frac if not blocked else 105 * frac
        if attack_type == "razor":
            for i in range(3):
                angle = math.atan2(dy, dx) + (i - 1) * 0.36
                ux, uy = math.cos(angle), math.sin(angle)
                px, py = -uy, ux
                length = radius * (1.25 - i * 0.12)
                width = max(3, int((12 - i * 3) * frac))
                p1 = (center[0] - ux * length * 0.55 + px * radius * 0.10, center[1] - uy * length * 0.55 + py * radius * 0.10)
                p2 = (center[0] + ux * length * 0.70 - px * radius * 0.06, center[1] + uy * length * 0.70 - py * radius * 0.06)
                pygame.draw.line(self.screen, rgba(splat.dark_color, alpha), p1, p2, width + 5)
                pygame.draw.line(self.screen, rgba(splat.highlight if i == 1 else splat.color, 210 * frac), p1, p2, width)
            self.draw_broken_ring(center, splat.highlight, int(radius * 0.72), frac, splat.seed, direction=splat.direction, attack_type=attack_type)
        elif attack_type == "torrent":
            self.draw_jagged_splash(center, radius, splat.color, splat.seed, alpha=alpha, stretch=(1.45, 0.82))
            for i in range(9):
                t = i / 8
                p1 = (center[0] - dx * radius * 0.25 + nx * (t - 0.5) * radius * 1.35, center[1] - dy * radius * 0.25 + ny * (t - 0.5) * radius * 1.35)
                p2 = (p1[0] + dx * radius * 0.45, p1[1] + dy * radius * 0.45)
                pygame.draw.line(self.screen, rgba(splat.highlight, 80 * frac), p1, p2, max(1, int(3 * frac)))
            self.draw_broken_ring(center, splat.highlight, int(radius * 0.80), frac, splat.seed, direction=splat.direction, attack_type=attack_type)
        elif attack_type == "emblem":
            self.draw_starburst(center, radius * 0.82, splat.color, alpha, seed=splat.seed)
            for i in range(5):
                angle = i * math.tau / 5 + time.time() * 2.8
                c = (center[0] + math.cos(angle) * radius * 0.52, center[1] + math.sin(angle) * radius * 0.38)
                self.draw_starburst(c, radius * 0.24, splat.highlight, 120 * frac, seed=splat.seed + i)
            self.draw_broken_ring(center, splat.highlight, int(radius * 0.70), frac, splat.seed, attack_type=attack_type)
        elif attack_type == "chain":
            rng = random.Random(splat.seed + int(time.time() * LIGHTNING_REDRAW_RATE))
            for _ in range(13):
                p1 = (center[0] + rng.uniform(-radius, radius), center[1] + rng.uniform(-radius * 0.70, radius * 0.70))
                p2 = (p1[0] + rng.uniform(-radius * 0.45, radius * 0.45), p1[1] + rng.uniform(-radius * 0.45, radius * 0.45))
                pygame.draw.line(self.screen, rgba(splat.color, 150 * frac), p1, p2, max(2, int(4 * frac)))
                pygame.draw.line(self.screen, rgba(PALETTE["white"], 190 * frac), p1, p2, max(1, int(2 * frac)))
            self.draw_broken_ring(center, splat.highlight, int(radius * 0.72), frac, splat.seed, attack_type=attack_type)
        elif attack_type == "fire":
            self.draw_blocky_burst(center, radius, splat, frac, count=22)
            self.draw_broken_ring(center, splat.highlight, int(radius * 0.76), frac, splat.seed, direction=splat.direction, attack_type=attack_type)
        elif attack_type == "spiral":
            self.draw_spiral_splat(center, splat, frac)
            for i in range(3):
                arc_radius = radius * (0.48 + i * 0.22)
                rect = pygame.Rect(0, 0, arc_radius * 2, arc_radius * 2)
                rect.center = center
                pygame.draw.arc(self.screen, rgba(splat.highlight, 150 * frac), rect, time.time() * 4 + i, time.time() * 4 + i + 2.7, max(2, int(5 * frac)))
        elif attack_type == "payment":
            self.draw_fake_qr_tile(center, radius * 1.16, splat.seed, frac, angle=time.time() * 260)
            self.draw_scan_brackets(center, radius * 1.30, splat.highlight, 210 * frac)
            self.draw_currency_burst(center, radius, splat, frac)
        elif attack_type == "youtube":
            self.draw_youtube_play_splat(center, radius * 1.34, frac, angle=-6 + time.time() * 80, alpha=220)
            self.draw_ui_bars(center, radius * 1.18, splat.color, frac)
            self.draw_starburst(center, radius * 0.92, PALETTE["white"], 90 * frac, seed=splat.seed)
        elif attack_type == "ceiling":
            self.draw_starburst(center, radius * 1.28, splat.highlight, 100 * frac, seed=splat.seed)
            self.draw_ceiling_splat(center, radius * 1.20, splat, frac, count=8)

    def draw_victim_reaction_splat(self, center, splat, frac, attack_type):
        radius = self.meters_to_px(splat.radius) * (0.90 + 0.14 * math.sin(time.time() * 18))
        dx, dy = self.screen_direction(splat.direction)
        nx, ny = -dy, dx
        if attack_type == "razor":
            for i in range(4):
                offset = (i - 1.5) * radius * 0.19
                p1 = (center[0] - dx * radius * 0.62 + nx * offset, center[1] - dy * radius * 0.62 + ny * offset)
                p2 = (center[0] + dx * radius * 0.46 + nx * offset * 0.35, center[1] + dy * radius * 0.46 + ny * offset * 0.35)
                pygame.draw.line(self.screen, rgba(splat.dark_color, 115 * frac), p1, p2, max(2, int(7 * frac)))
                pygame.draw.line(self.screen, rgba(splat.highlight, 150 * frac), p1, p2, max(1, int(2 * frac)))
        elif attack_type == "torrent":
            self.draw_jagged_splash(center, radius * 0.72, splat.color, splat.seed, alpha=70 * frac, stretch=(1.25, 0.95))
            for i in range(7):
                x = center[0] + (i - 3) * radius * 0.17
                y1 = center[1] + radius * 0.05
                y2 = y1 + radius * (0.28 + (i % 3) * 0.08) * (1.0 - frac * 0.25)
                pygame.draw.line(self.screen, rgba(splat.highlight, 80 * frac), (x, y1), (x + math.sin(time.time() * 8 + i) * 8, y2), 3)
        elif attack_type == "emblem":
            for i in range(6):
                angle = i * math.tau / 6 + time.time() * 2.2
                c = (center[0] + math.cos(angle) * radius * 0.50, center[1] + math.sin(angle) * radius * 0.36)
                self.draw_starburst(c, radius * (0.13 + 0.04 * (i % 2)), splat.highlight, 115 * frac, seed=splat.seed + i)
        elif attack_type == "chain":
            for i in range(7):
                angle = i * math.tau / 7 + time.time() * 5.0
                p1 = (center[0] + math.cos(angle) * radius * 0.30, center[1] + math.sin(angle) * radius * 0.58)
                p2 = (center[0] + math.cos(angle + 0.36) * radius * 0.62, center[1] + math.sin(angle + 0.36) * radius * 0.72)
                pygame.draw.line(self.screen, rgba(splat.highlight, 135 * frac), p1, p2, max(1, int(3 * frac)))
        elif attack_type == "fire":
            self.draw_blocky_burst(center, radius * 0.78, splat, frac, count=16)
            pygame.draw.circle(self.screen, rgba(splat.highlight, 72 * frac), center, int(radius * 0.62), max(1, int(4 * frac)))
        elif attack_type == "spiral":
            self.draw_spiral_splat(center, splat, frac)
        elif attack_type == "payment":
            self.draw_scan_brackets(center, radius * 0.86, splat.highlight, 170 * frac)
            self.draw_fake_qr_tile(center, radius * 0.52, splat.seed, frac * 0.86, angle=0)
            self.draw_currency_burst(center, radius * 0.72, splat, frac * 0.75)
        elif attack_type == "youtube":
            self.draw_ui_bars(center, radius * 0.95, splat.color, frac)
            self.draw_youtube_play_splat(center, radius * 0.72, frac, angle=0, alpha=150)
        elif attack_type == "ceiling":
            self.draw_ceiling_splat(center, radius * 0.92, splat, frac, count=5)

    def draw_miss_splat(self, center, splat, frac, attack_type):
        radius = self.meters_to_px(splat.radius) * (0.65 + 0.45 * (1 - frac))
        if attack_type == "fire":
            self.draw_blocky_burst(center, radius, splat, frac * 0.75, count=10)
        elif attack_type == "spiral":
            self.draw_spiral_splat(center, splat, frac * 0.75)
        elif attack_type == "emblem":
            self.draw_starburst(center, radius * 0.72, splat.color, 75 * frac, seed=splat.seed)
        elif attack_type == "payment":
            self.draw_scan_brackets(center, radius, splat.highlight, 130 * frac)
            self.draw_currency_burst(center, radius * 0.72, splat, frac * 0.65)
        elif attack_type == "youtube":
            self.draw_buffering_splat(center, radius, splat, frac)
        elif attack_type == "ceiling":
            self.draw_ceiling_splat(center, radius * 0.92, splat, frac * 0.8, count=4)
        else:
            self.draw_broken_ring(center, splat.highlight, int(radius), frac * 0.75, splat.seed, direction=splat.direction, attack_type=attack_type)

    def draw_blocky_burst(self, center, radius, splat, frac, count=18):
        rng = random.Random(splat.seed)
        colors = (splat.dark_color, splat.color, splat.highlight, PALETTE["white"])
        for _ in range(count):
            angle = rng.random() * math.tau
            dist = radius * rng.uniform(0.12, 1.05) * (1.05 - frac * 0.20)
            size = max(3, int(radius * rng.uniform(0.045, 0.14) * (0.65 + frac)))
            rect = pygame.Rect(0, 0, size, size)
            rect.center = (center[0] + math.cos(angle) * dist, center[1] + math.sin(angle) * dist * 0.78)
            pygame.draw.rect(self.screen, rgba(rng.choice(colors), 130 * frac), rect)

    def draw_payment_startup_splat(self, center, radius, splat, frac):
        self.draw_fake_qr_tile(center, radius * 0.95, splat.seed, frac, angle=-8 + time.time() * 90)
        self.draw_scan_brackets(center, radius * 1.25, splat.highlight, 185 * frac)
        self.draw_currency_burst(center, radius * 0.70, splat, frac * 0.75)

    def draw_fake_qr_tile(self, center, radius, seed, frac, angle=0.0):
        side = max(24, int(radius * 2))
        surf = pygame.Surface((side, side), pygame.SRCALPHA)
        rng = random.Random(seed)
        navy = (5, 22, 52)
        blue = (0, 160, 233)
        cyan = (83, 231, 255)
        pygame.draw.rect(surf, rgba(navy, 225 * frac), (0, 0, side, side), border_radius=max(3, side // 14))
        pygame.draw.rect(surf, rgba(blue, 215 * frac), (side * 0.06, side * 0.06, side * 0.88, side * 0.88), max(2, side // 18), border_radius=max(2, side // 18))
        cells = 13
        pad = side * 0.14
        cell = (side - pad * 2) / cells
        for gy in range(cells):
            for gx in range(cells):
                finder = (gx < 4 and gy < 4) or (gx > cells - 5 and gy < 4) or (gx < 4 and gy > cells - 5)
                if finder or rng.random() > 0.55:
                    color = PALETTE["white"] if finder or rng.random() > 0.34 else cyan
                    jitter = 0.76 + 0.22 * math.sin(time.time() * 22 + gx * 2.1 + gy * 1.3)
                    rect = pygame.Rect(pad + gx * cell, pad + gy * cell, max(1, cell * jitter), max(1, cell * jitter))
                    pygame.draw.rect(surf, rgba(color, 215 * frac), rect)
        img = pygame.transform.rotozoom(surf, angle, 1.0)
        self.screen.blit(img, img.get_rect(center=center), special_flags=pygame.BLEND_ADD)

    def draw_scan_brackets(self, center, radius, color, alpha):
        cx, cy = center
        arm = radius * 0.36
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            x = cx + sx * radius
            y = cy + sy * radius
            pygame.draw.line(self.screen, rgba(color, alpha), (x, y), (x - sx * arm, y), max(2, int(radius * 0.06)))
            pygame.draw.line(self.screen, rgba(color, alpha), (x, y), (x, y - sy * arm), max(2, int(radius * 0.06)))

    def draw_currency_burst(self, center, radius, splat, frac):
        rng = random.Random(splat.seed + 99)
        labels = ("YEN", "CNY", "OK", "PAY")
        for i in range(8):
            angle = rng.random() * math.tau
            dist = radius * rng.uniform(0.25, 1.22)
            label = self.small_font.render(rng.choice(labels), True, splat.highlight if i % 2 else splat.color)
            label.set_alpha(channel(145 * frac))
            pos = (center[0] + math.cos(angle) * dist, center[1] + math.sin(angle) * dist * 0.76)
            self.screen.blit(label, label.get_rect(center=pos))
            size = rng.randint(4, 10)
            pygame.draw.rect(self.screen, rgba(splat.highlight, 125 * frac), (pos[0] - size * 0.5, pos[1] - size * 0.5, size, size))

    def draw_youtube_play_splat(self, center, radius, frac, angle=0.0, alpha=210):
        surf = pygame.Surface((max(2, int(radius * 2.0)), max(2, int(radius * 1.25))), pygame.SRCALPHA)
        red = (255, 0, 0)
        rect = surf.get_rect()
        pygame.draw.rect(surf, rgba((16, 16, 16), alpha * 0.65 * frac), rect.move(4, 5), border_radius=max(4, rect.height // 4))
        pygame.draw.rect(surf, rgba(red, alpha * frac), rect.inflate(-4, -4), border_radius=max(4, rect.height // 4))
        tri = [
            (rect.centerx - rect.width * 0.12, rect.centery - rect.height * 0.23),
            (rect.centerx - rect.width * 0.12, rect.centery + rect.height * 0.23),
            (rect.centerx + rect.width * 0.24, rect.centery),
        ]
        pygame.draw.polygon(surf, rgba(PALETTE["white"], 240 * frac), tri)
        img = pygame.transform.rotozoom(surf, angle, 1.0)
        self.screen.blit(img, img.get_rect(center=center), special_flags=pygame.BLEND_ADD)

    def draw_ui_bars(self, center, radius, color, frac):
        cx, cy = center
        for i in range(5):
            y = cy + (i - 2) * radius * 0.18
            length = radius * (0.75 + 0.18 * i)
            pygame.draw.line(self.screen, rgba((18, 18, 18), 110 * frac), (cx - length * 0.55, y + 5), (cx + length * 0.55, y + 5), max(3, int(8 * frac)))
            pygame.draw.line(self.screen, rgba(color if i % 2 else PALETTE["white"], 155 * frac), (cx - length * 0.55, y), (cx + length * 0.55, y), max(2, int(5 * frac)))
        self.draw_youtube_play_splat((cx - radius * 0.48, cy - radius * 0.35), radius * 0.28, frac, angle=-12, alpha=160)
        self.draw_youtube_play_splat((cx + radius * 0.52, cy + radius * 0.30), radius * 0.22, frac, angle=14, alpha=135)

    def draw_buffering_splat(self, center, radius, splat, frac):
        rng = random.Random(splat.seed)
        for i in range(12):
            angle = i * math.tau / 12 + time.time() * 4.4
            r = radius * 0.58
            alpha = 35 + 135 * ((i + int(time.time() * 10)) % 12) / 11
            pygame.draw.circle(self.screen, rgba(splat.color if i % 2 else PALETTE["white"], alpha * frac), (int(center[0] + math.cos(angle) * r), int(center[1] + math.sin(angle) * r)), rng.randint(3, 8))
        self.draw_ui_bars(center, radius * 0.75, splat.color, frac * 0.7)

    def draw_ceiling_splat(self, center, radius, splat, frac, count=5):
        rng = random.Random(splat.seed + int(time.time() * 8))
        seal = self.fx_icon_surface("ceiling", "seal")
        pop = clamp(frac / 0.30, 0.0, 1.0)
        alpha_frac = 1.0 if frac > 0.30 else pop * pop
        pop_scale = 1.0 + (1.0 - alpha_frac) * 0.34
        for i in range(count):
            angle = rng.random() * math.tau
            dist = radius * rng.uniform(0.05, 0.88)
            scale = (0.44 + rng.random() * 0.48) * pop_scale
            img = pygame.transform.rotozoom(seal, rng.uniform(-35, 35), scale)
            img.set_alpha(channel(240 * alpha_frac))
            pos = (center[0] + math.cos(angle) * dist, center[1] + math.sin(angle) * dist * 0.72)
            self.screen.blit(img, img.get_rect(center=pos))
        for i in range(10):
            angle = rng.random() * math.tau
            dist = radius * rng.uniform(0.20, 1.18)
            pygame.draw.circle(self.screen, rgba((220, 210, 190), 70 * alpha_frac), (int(center[0] + math.cos(angle) * dist), int(center[1] + math.sin(angle) * dist * 0.80)), rng.randint(5, 18))
            if i % 3 == 0:
                self.draw_starburst((center[0] + math.cos(angle) * dist, center[1] + math.sin(angle) * dist * 0.8), rng.uniform(8, 18), splat.highlight, 100 * alpha_frac, seed=splat.seed + i)

    def draw_fight_particles(self, offset, below):
        now = time.time()
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for particle in self.fight_particles:
            if below != (particle.layer == "back"):
                continue
            age = now - particle.created_at
            frac = clamp(1.0 - age / max(0.001, particle.life), 0.0, 1.0)
            if frac <= 0:
                continue
            sx, sy = self.world_to_screen(particle.x, particle.y, offset)
            alpha = channel(particle.alpha * frac)
            size = max(2, int(self.meters_to_px(particle.size) * (0.65 + frac)))
            if particle.shape == "image" and particle.sprite_key:
                self.draw_fight_icon_particle(particle, (sx, sy), frac)
                continue
            if particle.shape in ("pixel", "ember"):
                rect = pygame.Rect(0, 0, size, size)
                rect.center = (sx, sy)
                pygame.draw.rect(surf, rgba(particle.color, alpha), rect)
                if particle.shape == "ember":
                    inner = rect.inflate(-max(1, size // 3), -max(1, size // 3))
                    pygame.draw.rect(surf, rgba(PALETTE["white"], 105 * frac), inner)
            elif particle.shape in ("spark", "diamond", "droplet"):
                points = [(sx, sy - size), (sx + size, sy), (sx, sy + size), (sx - size, sy)]
                if particle.shape == "droplet":
                    points = [(sx, sy - size * 1.4), (sx + size * 0.75, sy), (sx, sy + size * 1.2), (sx - size * 0.75, sy)]
                pygame.draw.polygon(surf, rgba(particle.color, alpha), points)
            elif particle.shape in ("slash", "streak"):
                length = size * (4.0 if particle.shape == "slash" else 3.0)
                ux = math.cos(particle.angle)
                uy = math.sin(particle.angle)
                px = -uy
                py = ux
                width = max(2, size * 0.42)
                points = [
                    (sx - ux * length + px * width, sy - uy * length + py * width),
                    (sx + ux * length + px * width * 0.28, sy + uy * length + py * width * 0.28),
                    (sx + ux * length - px * width, sy + uy * length - py * width),
                    (sx - ux * length - px * width * 0.28, sy - uy * length - py * width * 0.28),
                ]
                pygame.draw.polygon(surf, rgba(particle.color, alpha), points)
            elif particle.shape == "steam":
                pygame.draw.arc(surf, rgba(particle.color, alpha * 0.55), (sx - size, sy - size, size * 2, size * 2), particle.angle, particle.angle + 1.7, max(1, size // 3))
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw_fight_icon_particle(self, particle, center, frac):
        family, kind = particle.sprite_key.split(":", 1) if ":" in particle.sprite_key else ("fx", particle.sprite_key)
        if family in ("fx", "yt", "ceiling"):
            icon = self.fx_icon_surface(family, kind)
            if family == "ceiling":
                pop = clamp(frac / 0.28, 0.0, 1.0)
                alpha_frac = 1.0 if frac > 0.28 else pop * pop
                pop_scale = 1.0 + (1.0 - alpha_frac) * 0.38
                scale = max(0.16, particle.size * 5.2 * (0.95 + 0.08 * math.sin((1.0 - frac) * math.pi)) * pop_scale)
            else:
                alpha_frac = frac
                scale = max(0.10, particle.size * 5.8 * (0.65 + frac))
        else:
            character = self.character_by_id(family)
            icon = self.generated_icon_surface(character, kind)
            alpha_frac = frac
            scale = max(0.12, particle.size * 5.8 * (0.65 + frac))
        img = pygame.transform.rotozoom(icon, math.degrees(particle.angle), scale)
        img.set_alpha(channel(particle.alpha * alpha_frac))
        self.screen.blit(img, img.get_rect(center=center))

    def fx_icon_surface(self, family, kind):
        key = ("fx_icon", family, kind)
        if key in self.icon_cache:
            return self.icon_cache[key]
        if family == "ceiling":
            surf = self.ceiling_seal_surface(kind)
            self.icon_cache[key] = surf
            return surf
        surf = pygame.Surface((GENERATED_ICON_SIZE, GENERATED_ICON_SIZE), pygame.SRCALPHA)
        w = h = GENERATED_ICON_SIZE
        if family == "fx":
            blue = (0, 160, 233)
            cyan = (83, 231, 255)
            navy = (5, 22, 52)
            red = (239, 47, 47)
            if kind == "qr":
                pygame.draw.rect(surf, rgba(navy, 230), (6, 6, w - 12, h - 12), border_radius=8)
                pygame.draw.rect(surf, rgba(blue, 245), (10, 10, w - 20, h - 20), border_radius=6)
                rng = random.Random(4242)
                cell = 5
                for gy in range(7, 56, cell):
                    for gx in range(7, 56, cell):
                        if rng.random() > 0.48:
                            pygame.draw.rect(surf, rgba(PALETTE["white"] if rng.random() > 0.25 else cyan, 235), (gx, gy, cell - 1, cell - 1))
                for x, y in ((11, 11), (43, 11), (11, 43)):
                    pygame.draw.rect(surf, navy, (x, y, 14, 14))
                    pygame.draw.rect(surf, PALETTE["white"], (x + 3, y + 3, 8, 8))
                    pygame.draw.rect(surf, blue, (x + 5, y + 5, 4, 4))
            elif kind in ("yen", "yuan"):
                text = "\u00a5" if kind == "yen" else "CNY"
                pygame.draw.circle(surf, rgba(cyan, 230), (w // 2, h // 2), 26)
                pygame.draw.circle(surf, rgba(navy, 230), (w // 2, h // 2), 28, 4)
                label = self.big_font.render(text, True, PALETTE["white"])
                label = pygame.transform.smoothscale(label, (min(44, label.get_width()), min(32, label.get_height())))
                surf.blit(label, label.get_rect(center=(w // 2, h // 2)))
            elif kind == "receipt":
                pygame.draw.polygon(surf, rgba(PALETTE["white"], 235), [(18, 7), (50, 13), (44, 58), (11, 52)])
                for y in (18, 28, 38, 48):
                    pygame.draw.line(surf, blue, (20, y), (42, y + 3), 3)
            elif kind == "red_packet":
                pygame.draw.rect(surf, rgba(red, 240), (15, 12, 36, 44), border_radius=6)
                pygame.draw.circle(surf, rgba((255, 220, 90), 245), (33, 34), 12)
                glyph = self.small_font.render("YEN", True, navy)
                surf.blit(glyph, glyph.get_rect(center=(33, 34)))
            elif kind == "check":
                pygame.draw.rect(surf, rgba(blue, 230), (10, 14, 44, 36), border_radius=10)
                pygame.draw.line(surf, PALETTE["white"], (20, 34), (29, 43), 7)
                pygame.draw.line(surf, PALETTE["white"], (29, 43), (46, 22), 7)
            else:
                self.draw_bracket_icon(surf, blue, cyan)
        elif family == "yt":
            red = (255, 0, 0)
            dark = (18, 18, 18)
            if kind in ("play", "triangle"):
                if kind == "play":
                    pygame.draw.rect(surf, rgba(red, 245), (8, 16, 48, 32), border_radius=10)
                    triangle = [(29, 24), (29, 40), (43, 32)]
                else:
                    triangle = [(17, 14), (17, 50), (51, 32)]
                pygame.draw.polygon(surf, PALETTE["white"], triangle)
                pygame.draw.rect(surf, rgba(dark, 110), (8, 16, 48, 32), 3, border_radius=10)
            elif kind == "like":
                pygame.draw.polygon(surf, rgba((54, 143, 255), 245), [(22, 31), (30, 18), (38, 20), (36, 29), (50, 29), (46, 51), (22, 51)])
                pygame.draw.rect(surf, PALETTE["white"], (13, 32, 9, 20), border_radius=3)
            elif kind == "subscribe":
                pygame.draw.rect(surf, rgba(red, 245), (5, 19, 54, 26), border_radius=13)
                label = self.small_font.render("SUB", True, PALETTE["white"])
                surf.blit(label, label.get_rect(center=(32, 32)))
            elif kind == "comment":
                pygame.draw.rect(surf, rgba(PALETTE["white"], 240), (10, 14, 44, 30), border_radius=7)
                pygame.draw.polygon(surf, rgba(PALETTE["white"], 240), [(25, 43), (32, 54), (36, 43)])
                for x in (22, 32, 42):
                    pygame.draw.circle(surf, red, (x, 29), 3)
            elif kind == "bell":
                pygame.draw.arc(surf, rgba((255, 218, 76), 245), (18, 14, 28, 32), math.pi, math.tau, 6)
                pygame.draw.line(surf, rgba((255, 218, 76), 245), (18, 31), (46, 31), 6)
                pygame.draw.circle(surf, PALETTE["white"], (32, 49), 5)
            else:
                pygame.draw.rect(surf, rgba(red, 240), (8, 28, 48, 8), border_radius=4)
                pygame.draw.circle(surf, PALETTE["white"], (42, 32), 7)
        self.icon_cache[key] = surf
        return surf

    def draw_bracket_icon(self, surf, color, accent):
        for x, sx in ((10, 1), (54, -1)):
            pygame.draw.line(surf, color, (x, 15), (x + sx * 13, 15), 5)
            pygame.draw.line(surf, color, (x, 49), (x + sx * 13, 49), 5)
            pygame.draw.line(surf, color, (x, 15), (x, 28), 5)
            pygame.draw.line(surf, color, (x, 49), (x, 36), 5)
        pygame.draw.line(surf, accent, (15, 32), (49, 32), 4)

    def ceiling_seal_surface(self, kind):
        try:
            if CEILING_SEAL_SPRITE.exists():
                surf = pygame.image.load(str(CEILING_SEAL_SPRITE)).convert_alpha()
                bounds = surf.get_bounding_rect(8)
                if bounds.width > 0 and bounds.height > 0:
                    surf = surf.subsurface(bounds).copy()
                target = (96, 64) if kind != "seal_face" else (70, 54)
                return pygame.transform.smoothscale(surf, target)
        except pygame.error as exc:
            self.log(f"seal art failed: {exc}")
        surf = pygame.Surface((96, 64), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (210, 215, 216), (6, 10, 82, 42))
        pygame.draw.ellipse(surf, (145, 152, 154), (18, 16, 42, 22), 3)
        pygame.draw.circle(surf, (20, 24, 26), (72, 27), 4)
        pygame.draw.circle(surf, (20, 24, 26), (84, 27), 4)
        pygame.draw.arc(surf, (40, 42, 42), (70, 30, 16, 12), 0.2, 2.8, 2)
        return surf

    def generated_icon_surface(self, character, kind):
        key = (character["id"], kind)
        if key in self.icon_cache:
            return self.icon_cache[key]
        surf = pygame.Surface((GENERATED_ICON_SIZE, GENERATED_ICON_SIZE), pygame.SRCALPHA)
        scale = GENERATED_ICON_SIZE / 64.0
        theme = character["theme"]
        dark = character["dark"]
        highlight = character["highlight"]
        accent = character["accent"]
        def s(point):
            return (int(point[0] * scale), int(point[1] * scale))
        pygame.draw.polygon(surf, dark, [s(p) for p in [(32, 4), (52, 14), (58, 38), (43, 58), (19, 58), (6, 37), (12, 13)]])
        if kind == "hit":
            pygame.draw.polygon(surf, theme, [s(p) for p in [(11, 33), (26, 18), (37, 25), (52, 12), (43, 34), (54, 50), (32, 43), (14, 55)]])
            pygame.draw.line(surf, highlight, s((16, 18)), s((50, 52)), max(1, int(5 * scale)))
            pygame.draw.line(surf, accent, s((47, 16)), s((18, 50)), max(1, int(4 * scale)))
        else:
            points = []
            for i in range(16):
                angle = i * math.tau / 16
                radius = 25 if i % 2 == 0 else 13
                points.append(s((32 + math.cos(angle) * radius, 32 + math.sin(angle) * radius)))
            pygame.draw.polygon(surf, theme, points)
            pygame.draw.circle(surf, accent, s((32, 32)), max(1, int(13 * scale)))
            pygame.draw.arc(surf, highlight, pygame.Rect(int(14 * scale), int(14 * scale), int(36 * scale), int(36 * scale)), 0.4, 5.6, max(1, int(4 * scale)))
        pygame.draw.rect(surf, highlight, pygame.Rect(int(30 * scale), int(9 * scale), max(1, int(5 * scale)), int(46 * scale)))
        self.icon_cache[key] = surf
        return surf

    def draw_beam(self, beam, offset):
        now = time.time()
        age = now - beam.created_at
        frac = clamp(1.0 - age / beam.duration, 0.0, 1.0)
        start = self.world_to_screen(*beam.start, offset)
        end_point = beam.hit_point if beam.hit_point else beam.end
        end = self.world_to_screen(*end_point, offset)
        player = self.players.get(beam.attacker_id) if beam.attacker_id else None
        character = self.character_for_player(player) if player else {
            "theme": beam.color, "secondary": beam.color, "dark": PALETTE["dark_brown"],
            "highlight": PALETTE["white"], "accent": PALETTE["soup"], "id": "fallback",
        }
        profile = ATTACK_PROFILES.get(beam.attack_type, ATTACK_PROFILES["razor"])
        shape = profile["beam_shape"]
        if shape == "jagged_ribbon":
            self.draw_razor_beam(start, end, character, beam, frac)
        elif shape == "particle_tunnel":
            self.draw_torrent_beam(start, end, character, beam, frac)
        elif shape == "emblem_path":
            self.draw_emblem_beam(start, end, character, beam, frac)
        elif shape == "lightning_chain":
            self.draw_chain_beam(start, end, character, beam, frac)
        elif shape == "pixel_fire":
            self.draw_pixel_fire_beam(start, end, character, beam, frac)
        elif shape == "spiral_ribbon":
            self.draw_spiral_beam(start, end, character, beam, frac)
        elif shape == "payment_scan":
            self.draw_payment_beam(start, end, character, beam, frac)
        elif shape == "youtube_feed":
            self.draw_youtube_beam(start, end, character, beam, frac)
        elif shape == "seal_avalanche":
            self.draw_ceiling_beam(start, end, character, beam, frac)
        else:
            self.draw_simple_beam(start, end, beam.color, frac)
        if beam.hit_point:
            self.draw_broken_ring(end, character["highlight"], 24 + int(14 * frac), frac, seed=int(beam.created_at * 1000), direction=beam.direction, attack_type=beam.attack_type)

    def beam_basis(self, start, end):
        sx, sy = start
        ex, ey = end
        vx = ex - sx
        vy = ey - sy
        length = max(1.0, math.hypot(vx, vy))
        dx = vx / length
        dy = vy / length
        return dx, dy, -dy, dx, length

    def beam_quad_points(self, start, end, nx, ny, width_start, width_end):
        return [
            (start[0] + nx * width_start, start[1] + ny * width_start),
            (end[0] + nx * width_end, end[1] + ny * width_end),
            (end[0] - nx * width_end, end[1] - ny * width_end),
            (start[0] - nx * width_start, start[1] - ny * width_start),
        ]

    def draw_simple_beam(self, start, end, color, frac):
        glow = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for width, alpha in ((34, 34), (22, 58), (12, 96)):
            pygame.draw.line(glow, rgba(color, alpha * frac), start, end, width)
        pygame.draw.line(glow, rgba(PALETTE["white"], 240 * frac), start, end, max(2, int(6 * frac)))
        self.screen.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)
        pygame.draw.circle(self.screen, PALETTE["white"], start, max(3, int(10 * frac)))

    def draw_razor_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        rng = random.Random(int(beam.created_at * 1000) + int((1 - frac) * 18))
        steps = 9
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        ribbon_layers = (
            (character["dark"], 30, 155, -0.05, 1.0),
            (character["theme"], 18, 210, 0.04, 0.72),
            (PALETTE["white"], 7, 235, 0.00, 0.32),
        )
        for color, base_width, alpha, phase, jitter_scale in ribbon_layers:
            left = []
            right = []
            for i in range(steps + 1):
                t = i / steps
                cx = start[0] + dx * length * t + nx * math.sin((t + phase) * math.tau * 2.0) * 4 * frac
                cy = start[1] + dy * length * t + ny * math.sin((t + phase) * math.tau * 2.0) * 4 * frac
                width = (base_width + base_width * 0.36 * math.sin(t * math.pi)) * frac
                jitter = rng.uniform(-13, 13) * jitter_scale * (0.35 + 0.65 * frac)
                left.append((cx + nx * (width + jitter), cy + ny * (width + jitter)))
                right.append((cx - nx * (width - jitter), cy - ny * (width - jitter)))
            pygame.draw.polygon(surf, rgba(color, alpha * frac), left + right[::-1])
        pygame.draw.line(surf, rgba(PALETTE["white"], 245 * frac), start, end, max(2, int(5 * frac)))
        for i in range(5):
            t = 0.12 + i * 0.16 + rng.uniform(-0.03, 0.03)
            if t > 0.92:
                continue
            side = rng.choice((-1, 1))
            cut_start = (
                start[0] + dx * length * (t - 0.06) + nx * side * rng.uniform(18, 46),
                start[1] + dy * length * (t - 0.06) + ny * side * rng.uniform(18, 46),
            )
            cut_end = (cut_start[0] + dx * rng.uniform(46, 95), cut_start[1] + dy * rng.uniform(46, 95))
            pygame.draw.line(surf, rgba(character["highlight"], 105 * frac), cut_start, cut_end, max(1, int(3 * frac)))
        for i in range(8):
            t = rng.random() * 0.82
            p1 = (start[0] + dx * length * t - dx * 32 + nx * rng.uniform(-46, 46), start[1] + dy * length * t - dy * 32 + ny * rng.uniform(-46, 46))
            p2 = (p1[0] - dx * rng.uniform(18, 52), p1[1] - dy * rng.uniform(18, 52))
            pygame.draw.line(surf, rgba(character["dark"], 70 * frac), p1, p2, 2)
        for i in range(12):
            t = rng.random()
            cx = start[0] + dx * length * t
            cy = start[1] + dy * length * t
            shard_len = rng.uniform(14, 44) * frac
            side = rng.choice((-1, 1))
            p1 = (cx + nx * side * rng.uniform(10, 28), cy + ny * side * rng.uniform(10, 28))
            p2 = (p1[0] + dx * shard_len + nx * side * 7, p1[1] + dy * shard_len + ny * side * 7)
            pygame.draw.line(surf, rgba(character["highlight"], 170 * frac), p1, p2, max(2, int(4 * frac)))
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)
        self.draw_slash_head(end, dx, dy, character["highlight"], frac)

    def draw_torrent_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        rng = random.Random(int(beam.created_at * 1000) + int((1 - frac) * 14))
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        colors = (character["dark"], character["theme"], character["secondary"], character["highlight"])
        phase = (time.time() - beam.created_at) * 8.0
        for i in range(94):
            t = rng.random()
            band = 0.72 + 0.48 * max(0.0, math.sin((t * 3.0 - phase) * math.tau))
            spread = (8 + t * 42) * band
            cx = start[0] + dx * length * t + nx * rng.uniform(-spread, spread)
            cy = start[1] + dy * length * t + ny * rng.uniform(-spread, spread)
            size = int(rng.uniform(3, 13) * (0.55 + frac))
            rect = pygame.Rect(0, 0, size, size)
            rect.center = (cx, cy)
            pygame.draw.rect(surf, rgba(rng.choice(colors), 170 * frac), rect)
        for i in range(6):
            t = (i + ((time.time() - beam.created_at) * 2.2 % 1.0)) / 6
            if t > 1:
                t -= 1
            cx = start[0] + dx * length * t
            cy = start[1] + dy * length * t
            width = 36 + 34 * t
            pygame.draw.line(surf, rgba(character["highlight"], 82 * frac), (cx - nx * width, cy - ny * width), (cx + nx * width, cy + ny * width), 3)
            arc_rect = pygame.Rect(0, 0, width * 1.55, width * 0.70)
            arc_rect.center = (cx, cy)
            pygame.draw.arc(surf, rgba(PALETTE["white"], 45 * frac), arc_rect, -0.4, math.pi + 0.4, 2)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw_emblem_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.line(surf, rgba(character["theme"], 70 * frac), start, end, 18)
        for i in range(9):
            t = i / 8
            p = (start[0] + dx * length * t, start[1] + dy * length * t)
            self.draw_pixel_diamond(p[0], p[1], 4 + (i % 3) * 2, rgba(character["accent"], 90 * frac))
        pygame.draw.line(surf, rgba(character["highlight"], 170 * frac), start, end, 4)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)
        icon = self.generated_icon_surface(character, "attack")
        for i in range(9):
            t = (i + ((time.time() - beam.created_at) * 8.0 % 1.0)) / 9
            if t > 1:
                t -= 1
            cx = start[0] + dx * length * t + nx * math.sin(t * math.tau * 2) * 16
            cy = start[1] + dy * length * t + ny * math.sin(t * math.tau * 2) * 16
            scale = 0.38 + 0.24 * math.sin(t * math.pi)
            angle = (time.time() * EMBLEM_SPIN_SPEED + i * 47) % 360
            ghost = pygame.transform.rotozoom(icon, angle - 18, scale * 1.06)
            ghost.set_alpha(channel(64 * frac))
            self.screen.blit(ghost, ghost.get_rect(center=(cx - dx * 10, cy - dy * 10)))
            img = pygame.transform.rotozoom(icon, angle, scale)
            img.set_alpha(channel(210 * frac))
            self.screen.blit(img, img.get_rect(center=(cx, cy)))

    def draw_chain_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        rng = random.Random(int(beam.created_at * 2000) + int(time.time() * LIGHTNING_REDRAW_RATE))
        points = [start]
        for i in range(1, 12):
            t = i / 12
            jitter = rng.uniform(-34, 34) * (0.4 + 0.6 * frac)
            points.append((start[0] + dx * length * t + nx * jitter, start[1] + dy * length * t + ny * jitter))
        points.append(end)
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.lines(surf, rgba(character["theme"], 125 * frac), False, points, 16)
        pygame.draw.lines(surf, rgba(character["highlight"], 230 * frac), False, points, 5)
        pygame.draw.lines(surf, rgba(PALETTE["white"], 245 * frac), False, points, 2)
        for point in points[2:-2:2]:
            branch_angle = math.atan2(dy, dx) + rng.choice((-1, 1)) * rng.uniform(0.8, 1.5)
            branch_len = rng.uniform(26, 74) * frac
            end_b = (point[0] + math.cos(branch_angle) * branch_len, point[1] + math.sin(branch_angle) * branch_len)
            pygame.draw.line(surf, rgba(character["secondary"], 155 * frac), point, end_b, 3)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw_pixel_fire_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        rng = random.Random(int(beam.created_at * 1000) + int(time.time() * FIRE_FLICKER_RATE))
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        colors = (character["dark"], character["theme"], character["accent"], character["highlight"], PALETTE["white"])
        for i in range(110):
            t = rng.random()
            heat = math.sin(t * math.pi)
            spread = 14 + heat * 34
            cx = start[0] + dx * length * t + nx * rng.uniform(-spread, spread)
            cy = start[1] + dy * length * t + ny * rng.uniform(-spread, spread) - rng.uniform(0, 24) * heat
            size = int(rng.uniform(4, 16) * (0.6 + heat * 0.7) * frac)
            rect = pygame.Rect(0, 0, max(2, size), max(2, size))
            rect.center = (cx, cy)
            pygame.draw.rect(surf, rgba(rng.choice(colors), 165 * frac), rect)
        for i in range(6):
            t = i / 5
            base = (start[0] + dx * length * t, start[1] + dy * length * t)
            tongue = [
                (base[0] - dx * 14 + nx * 18, base[1] - dy * 14 + ny * 18),
                (base[0] + dx * 28, base[1] + dy * 28 - 24 * math.sin(t * math.pi)),
                (base[0] - dx * 14 - nx * 18, base[1] - dy * 14 - ny * 18),
            ]
            pygame.draw.polygon(surf, rgba(character["highlight"], 42 * frac), tongue)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw_spiral_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        phase = (time.time() - beam.created_at) * 18.0
        for strand, color, width in ((0.0, character["theme"], 8), (math.pi * 0.72, character["secondary"], 7), (math.pi * 1.36, character["highlight"], 4)):
            points = []
            for i in range(28):
                t = i / 27
                amp = (26 + 5 * (width == 4)) * math.sin(t * math.pi) * frac
                wave = math.sin(t * math.tau * 3.2 + phase + strand) * amp
                points.append((start[0] + dx * length * t + nx * wave, start[1] + dy * length * t + ny * wave))
            pygame.draw.lines(surf, rgba(character["dark"], 110 * frac), False, points, width + 6)
            pygame.draw.lines(surf, rgba(color, 215 * frac), False, points, width)
            pygame.draw.lines(surf, rgba(character["highlight"], 175 * frac), False, points, 2)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw_payment_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        rng = random.Random(int(beam.created_at * 1000) + int(time.time() * 18))
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        navy = (5, 22, 52)
        blue = (0, 160, 233)
        cyan = (83, 231, 255)
        outer = self.beam_quad_points(start, end, nx, ny, 34 * frac, 54 * frac)
        inner = self.beam_quad_points(start, end, nx, ny, 19 * frac, 32 * frac)
        core = self.beam_quad_points(start, end, nx, ny, 5 * frac, 8 * frac)
        pygame.draw.polygon(surf, rgba(navy, 185 * frac), outer)
        pygame.draw.polygon(surf, rgba(blue, 150 * frac), inner)
        pygame.draw.polygon(surf, rgba(PALETTE["white"], 215 * frac), core)
        phase = (time.time() - beam.created_at) * 3.4
        for i in range(9):
            t = (i / 9 + phase) % 1.0
            cx = start[0] + dx * length * t
            cy = start[1] + dy * length * t
            half = lerp(22, 48, t) * frac
            pygame.draw.line(surf, rgba(cyan, 120 * frac), (cx - nx * half, cy - ny * half), (cx + nx * half, cy + ny * half), max(2, int(5 * frac)))
        for i in range(54):
            t = rng.random()
            half = lerp(16, 44, t)
            side = rng.uniform(-half, half)
            size = rng.randint(3, 9)
            cx = start[0] + dx * length * t + nx * side
            cy = start[1] + dy * length * t + ny * side
            color = PALETTE["white"] if rng.random() > 0.48 else cyan if rng.random() > 0.35 else blue
            pygame.draw.rect(surf, rgba(color, rng.randint(80, 190) * frac), (cx - size / 2, cy - size / 2, size, size))
        for t in (0.15, 0.42, 0.70):
            cx = start[0] + dx * length * t + nx * math.sin(time.time() * 11 + t) * 18
            cy = start[1] + dy * length * t + ny * math.sin(time.time() * 11 + t) * 18
            self.draw_scan_brackets_on(surf, (cx, cy), 18 + int(12 * frac), cyan, 96 * frac)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw_youtube_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        rng = random.Random(int(beam.created_at * 1000) + int(time.time() * 20))
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        red = (255, 0, 0)
        dark = (18, 18, 18)
        pygame.draw.polygon(surf, rgba(dark, 190 * frac), self.beam_quad_points(start, end, nx, ny, 30 * frac, 44 * frac))
        for i in range(5):
            side = (i - 2) * 13
            p1 = (start[0] + nx * side, start[1] + ny * side)
            p2 = (end[0] + nx * side * 1.25, end[1] + ny * side * 1.25)
            pygame.draw.line(surf, rgba(red if i != 2 else PALETTE["white"], (160 if i != 2 else 220) * frac), p1, p2, max(3, int((10 if i != 2 else 5) * frac)))
        phase = (time.time() - beam.created_at) * 5.5
        for i in range(8):
            t = (i / 8 + phase) % 1.0
            cx = start[0] + dx * length * t
            cy = start[1] + dy * length * t
            width = lerp(36, 70, t) * frac
            pygame.draw.line(surf, rgba(PALETTE["white"], 85 * frac), (cx - nx * width, cy - ny * width), (cx + nx * width, cy + ny * width), 3)
            pygame.draw.circle(surf, rgba(red, 145 * frac), (int(cx), int(cy)), max(3, int(6 * frac)))
        for i in range(16):
            t = rng.random()
            side = rng.uniform(-40, 40)
            cx = start[0] + dx * length * t + nx * side
            cy = start[1] + dy * length * t + ny * side
            rect = pygame.Rect(0, 0, rng.randint(18, 42), rng.randint(10, 22))
            rect.center = (cx, cy)
            pygame.draw.rect(surf, rgba(red if i % 2 else PALETTE["white"], 95 * frac), rect, border_radius=4)
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)
        icon = self.fx_icon_surface("yt", "play")
        for i in range(6):
            t = (i + ((time.time() - beam.created_at) * 4.8 % 1.0)) / 6
            if t > 1:
                t -= 1
            cx = start[0] + dx * length * t + nx * math.sin(t * math.tau * 2) * 22
            cy = start[1] + dy * length * t + ny * math.sin(t * math.tau * 2) * 22
            img = pygame.transform.rotozoom(icon, math.degrees(math.atan2(dy, dx)) + rng.uniform(-12, 12), 0.36 + 0.18 * math.sin(t * math.pi))
            img.set_alpha(channel(205 * frac))
            self.screen.blit(img, img.get_rect(center=(cx, cy)))

    def draw_ceiling_beam(self, start, end, character, beam, frac):
        dx, dy, nx, ny, length = self.beam_basis(start, end)
        rng = random.Random(int(beam.created_at * 1200) + int(time.time() * 10))
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        alpha_frac = max(0.45, frac)
        for i in range(24):
            t = rng.random()
            side = rng.uniform(-60, 60)
            p1 = (start[0] + dx * length * t + nx * side - dx * rng.uniform(28, 80), start[1] + dy * length * t + ny * side - dy * rng.uniform(28, 80))
            p2 = (p1[0] + dx * rng.uniform(58, 150), p1[1] + dy * rng.uniform(58, 150))
            pygame.draw.line(surf, rgba(character["dark"], 85 * alpha_frac), p1, p2, rng.randint(3, 9))
            pygame.draw.line(surf, rgba(PALETTE["white"], 60 * alpha_frac), p1, p2, 2)
        for i in range(30):
            t = rng.random()
            half = lerp(18, 55, t)
            cx = start[0] + dx * length * t + nx * rng.uniform(-half, half)
            cy = start[1] + dy * length * t + ny * rng.uniform(-half, half)
            pygame.draw.circle(surf, rgba((215, 205, 190), 58 * alpha_frac), (int(cx), int(cy)), rng.randint(6, 20))
        self.screen.blit(surf, (0, 0), special_flags=pygame.BLEND_ADD)
        seal = self.fx_icon_surface("ceiling", "seal")
        for i in range(26):
            t = (i / 26 + (time.time() - beam.created_at) * 1.8) % 1.0
            wave = math.sin(t * math.tau * 4.0 + i)
            side = wave * 48 + rng.uniform(-24, 24)
            cx = start[0] + dx * length * t + nx * side
            cy = start[1] + dy * length * t + ny * side
            scale = (0.42 + 0.48 * rng.random()) * (0.78 + 0.22 * frac)
            img = pygame.transform.rotozoom(seal, math.degrees(math.atan2(dy, dx)) + rng.uniform(-38, 38), scale)
            img.set_alpha(channel(240 * alpha_frac))
            self.screen.blit(img, img.get_rect(center=(cx, cy)))

    def draw_scan_brackets_on(self, surf, center, radius, color, alpha):
        cx, cy = center
        arm = radius * 0.48
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            x = cx + sx * radius
            y = cy + sy * radius
            pygame.draw.line(surf, rgba(color, alpha), (x, y), (x - sx * arm, y), 4)
            pygame.draw.line(surf, rgba(color, alpha), (x, y), (x, y - sy * arm), 4)

    def draw_slash_head(self, end, dx, dy, color, frac):
        nx, ny = -dy, dx
        length = 42 * frac
        width = 18 * frac
        points = [
            (end[0] + dx * length, end[1] + dy * length),
            (end[0] - dx * length * 0.25 + nx * width, end[1] - dy * length * 0.25 + ny * width),
            (end[0] - dx * length * 0.55, end[1] - dy * length * 0.55),
            (end[0] - dx * length * 0.25 - nx * width, end[1] - dy * length * 0.25 - ny * width),
        ]
        pygame.draw.polygon(self.screen, rgba(color, 220 * frac), points)

    def draw_broken_ring(self, center, color, radius, frac, seed, direction=None, attack_type="generic"):
        rng = random.Random(seed)
        if direction is None:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = self.screen_direction(direction)
        px, py = -uy, ux
        stretch_x = 1.0
        stretch_y = 1.0
        if attack_type == "razor":
            stretch_x, stretch_y = 1.45, 0.72
        elif attack_type == "torrent":
            stretch_x, stretch_y = 1.28, 0.90
        elif attack_type == "spiral":
            stretch_x, stretch_y = 1.08, 0.82
        elif attack_type == "shield":
            stretch_x, stretch_y = 1.12, 1.12
        segments = 11 if attack_type in ("chain", "fire") else 9
        for i in range(segments):
            start_angle = i * math.tau / segments + rng.uniform(-0.08, 0.08)
            end_angle = start_angle + rng.uniform(0.18, 0.50)
            if attack_type == "chain":
                end_angle += rng.uniform(-0.12, 0.10)
            points = []
            samples = 5
            for j in range(samples):
                t = j / max(1, samples - 1)
                angle = lerp(start_angle, end_angle, t)
                jitter = rng.uniform(-0.045, 0.045) if attack_type in ("razor", "chain") else 0.0
                local_x = math.cos(angle + jitter) * radius * stretch_x
                local_y = math.sin(angle + jitter) * radius * stretch_y
                points.append((center[0] + ux * local_x + px * local_y, center[1] + uy * local_x + py * local_y))
            width = max(2, int((5 if attack_type in ("razor", "shield") else 4) * frac))
            if len(points) >= 2:
                pygame.draw.lines(self.screen, rgba(color, 210 * frac), False, points, width)
                if attack_type in ("razor", "fire", "chain"):
                    for point in (points[0], points[-1]):
                        shard = max(3, int(radius * 0.055 * frac))
                        self.draw_pixel_diamond(point[0], point[1], shard, rgba(color, 170 * frac))

    def draw_bubble(self, player, offset):
        now = time.time()
        if not player.bubble_active(now):
            return
        character = self.character_for_player(player)
        left = max(0.0, player.bubble_until - now)
        frac = clamp(left / BUBBLE_DURATION, 0.0, 1.0)
        sx, sy = self.world_to_screen(player.x, player.y, offset)
        radius = self.meters_to_px(BUBBLE_RADIUS_M) * (1.0 + 0.08 * math.sin(now * 28))
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.circle(surf, rgba(PALETTE["bubble"], 26 + 32 * frac), (sx, sy), int(radius))
        pygame.draw.circle(surf, rgba(character["secondary"], 70 + 40 * frac), (sx, sy), int(radius * 0.72), 2)
        points = []
        for i in range(12):
            angle = now * 2.8 + i * math.tau / 12
            r = radius * (0.92 + 0.08 * (i % 2))
            points.append((sx + math.cos(angle) * r, sy + math.sin(angle) * r))
        pygame.draw.polygon(surf, rgba(PALETTE["bubble"], 165), points, 4)
        for i in range(6):
            angle = -now * 3.6 + i * math.tau / 6
            r1 = radius * 0.48
            r2 = radius * 1.06
            p1 = (sx + math.cos(angle) * r1, sy + math.sin(angle) * r1)
            p2 = (sx + math.cos(angle + 0.22) * r2, sy + math.sin(angle + 0.22) * r2)
            pygame.draw.line(surf, rgba(character["highlight"], 120 * frac), p1, p2, 3)
        self.draw_broken_ring((sx, sy), character["highlight"], int(radius), frac, int(player.player_id + now * 6))
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
        self.draw_aim_indicator(player, sx, sy, dx, dy, offset)

        rotated, rect = self.player_sprite_pose(player, offset)
        if not player.alive:
            ghost = rotated.copy()
            ghost.fill((90, 90, 90, 145), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(ghost, rect)
        else:
            self.screen.blit(rotated, rect)
        label = self.font.render(player.label, True, PALETTE["text"])
        self.screen.blit(label, (sx - label.get_width() // 2, rect.top - 24))

    def draw_aim_indicator(self, player, sx, sy, dx, dy, offset):
        character = self.character_for_player(player)
        aim_end = self.world_to_screen(player.x + dx * 0.58, player.y + dy * 0.58, offset)
        nx, ny = -dy, dx
        color = character["theme"]
        highlight = character["highlight"]
        pygame.draw.line(self.screen, rgba(color, 145), (sx, sy), aim_end, 4)
        pygame.draw.line(self.screen, rgba(highlight, 125), (sx, sy), aim_end, 1)
        now = time.time()
        for i in range(7):
            t = ((now * 0.85 + i * 0.173 + player.player_id * 0.011) % 1.0)
            drift = math.sin(now * 4.0 + i * 1.7 + player.player_id) * 4.0
            px = sx + (aim_end[0] - sx) * t + nx * drift
            py = sy + (aim_end[1] - sy) * t + ny * drift
            alpha = 80 + 55 * math.sin((t + now * 0.7) * math.tau)
            size = 2 if i % 3 else 3
            pygame.draw.rect(self.screen, rgba(highlight if i % 2 else color, alpha), (int(px) - size // 2, int(py) - size // 2, size, size))
        self.draw_iso_aim_marker(aim_end, color, highlight, character["dark"])

    def draw_iso_aim_marker(self, center, color, highlight, dark):
        x, y = center
        top = (x, y - 7)
        right = (x + 8, y + 2)
        bottom = (x + 1, y + 8)
        left = (x - 8, y + 3)
        shadow = [(px + 2, py + 3) for px, py in (top, right, bottom, left)]
        pygame.draw.polygon(self.screen, (0, 0, 0, 145), shadow)
        pygame.draw.polygon(self.screen, rgba(dark, 210), [left, bottom, right])
        pygame.draw.polygon(self.screen, rgba(color, 225), [top, right, bottom, left])
        pygame.draw.polygon(self.screen, rgba(highlight, 235), [top, right, (x, y + 1), left])
        pygame.draw.line(self.screen, rgba(PALETTE["white"], 160), top, (x, y + 1), 1)

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
            "FAKE: P1 WASD QE F/R     P2 ARROWS , .  / RSHIFT     ENTER RESET     Z RADAR DEBUG"
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
        self.refresh_local_magcal_statuses(now)
        visible = [status for status in self.mag_cal_status.values() if status.visible(now)]
        if not visible:
            return None
        active = [status for status in visible if status.active(now)]
        candidates = active or visible
        return max(candidates, key=lambda status: status.seen_at)

    def refresh_local_magcal_statuses(self, now):
        for status in self.mag_cal_status.values():
            if status.state != "RUNNING" or status.samples or status.quality or not (status.flags & 0x80):
                continue
            total_ms = max(status.elapsed_ms + status.remaining_ms, MAGCAL_COMMAND_MS)
            elapsed_ms = int(max(0.0, now - status.seen_at) * 1000)
            if elapsed_ms >= total_ms:
                status.state = "ERR"
                status.progress = 98
                status.quality = 0
                status.elapsed_ms = total_ms
                status.remaining_ms = 0
                status.seen_at = now
                self.log(f"P{status.player_id} no calibration packets received")
                self.sounds.play("invalid")
                continue
            status.elapsed_ms = min(elapsed_ms, total_ms)
            status.remaining_ms = max(0, total_ms - elapsed_ms)
            status.progress = clamp(int(100 * status.elapsed_ms / max(1, total_ms)), status.progress, 98)

    def format_seconds(self, ms):
        seconds = max(0, int(round(ms / 1000.0)))
        return f"{seconds}s"

    def magcal_instruction(self, status):
        if status.state == "REQUESTED":
            return "Waiting for controller. Keep it away from metal."
        if status.state == "RUNNING" and status.samples == 0:
            return "Command sent. Do figure-eights until the controller finishes."
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
        now = time.time()
        flash = clamp((self.hp_flash_until.get(player.player_id, 0.0) - now) / 0.52, 0.0, 1.0)
        character = self.character_for_player(player)
        self.draw_skew_panel(panel.move(0, 6), (0, 0, 0, 165), None, cut=16)
        self.draw_skew_panel(panel, rgba(PALETTE["panel_2"], 238), rgba(player.color, 215 + 40 * flash), cut=16, border_width=3)
        self.draw_slanted_strip(panel.left + 12, panel.top + 8, panel.width - 24, 7, -0.45, rgba(character["highlight"], 80 + 80 * flash))
        portrait = self.character_portrait(next((i for i, c in enumerate(CHARACTER_SLOTS) if c["id"] == player.character_id), 0))
        portrait_rect = pygame.Rect(panel.left + 10, panel.top + 10, 50, 50)
        self.blit_fit(portrait, portrait_rect, alpha=210)
        name = self.font.render(player.label.upper(), True, player.color)
        self.screen.blit(name, (x + 70, y + 10))
        hp_label = self.small_font.render("HP", True, PALETTE["muted"])
        self.screen.blit(hp_label, (x + 70, y + 42))
        for i in range(MAX_HP):
            bx = x + 104 + i * 36
            color = PALETTE["soup"] if i < player.hp else PALETTE["dark_brown"]
            if flash and i >= player.hp:
                color = PALETTE["bad"]
            pip = pygame.Rect(bx, y + 44 + int(math.sin(now * 50 + i) * 2 * flash), 28, 18)
            self.draw_skew_panel(pip, color, rgba(PALETTE["white"], 120 * flash), cut=4, border_width=1)
        score = self.small_font.render(f"ROUNDS {player.wins}/{WIN_ROUNDS}", True, PALETTE["text"])
        self.screen.blit(score, (panel.right - score.get_width() - 14, y + 45))

    def draw_messages(self):
        if self.match_state == "ready":
            text = self.big_font.render(self.round_message, True, PALETTE["beige"])
            rect = text.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2))
            bg = rect.inflate(56, 34)
            pygame.draw.rect(self.screen, (0, 0, 0), bg.move(0, 7), border_radius=14)
            pygame.draw.rect(self.screen, PALETTE["dark_brown"], bg, border_radius=14)
            pygame.draw.rect(self.screen, PALETTE["light_brown"], bg, 2, border_radius=14)
            self.screen.blit(text, rect)

    def draw_round_presentation(self):
        if self.match_state != "round_over" or self.round_winner_id is None:
            return
        winner = self.players.get(self.round_winner_id)
        if winner is None:
            return
        now = time.time()
        age = now - self.round_presentation_started_at
        t = ease_out_cubic(age / max(0.001, ROUND_WIN_PRESENTATION))
        w, h = self.screen.get_size()
        character = self.character_for_player(winner)
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, channel(80 * t)))
        self.screen.blit(overlay, (0, 0))
        sx, sy = self.world_to_screen(winner.x, winner.y)
        self.draw_starburst((sx, sy - 78), 120 + 40 * math.sin(now * 8), character["theme"], 120, seed=winner.player_id)
        self.draw_jagged_splash((sx, sy - 78), 150, character["secondary"], winner.player_id * 17, alpha=72, stretch=(1.35, 0.72))
        sprite, rect = self.player_sprite_pose(winner, target_pop=True)
        rect.centerx = sx
        rect.bottom = sy + 2
        glow = sprite.copy()
        glow.fill(rgba(character["highlight"], 150), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(glow, rect.move(0, -4))
        self.screen.blit(sprite, rect)

        banner = pygame.Rect(0, 0, min(820, w - 100), 96)
        banner.center = (w // 2, int(h * 0.52))
        slide = int((1.0 - t) * -w * 0.45)
        banner.move_ip(slide, 0)
        self.draw_skew_panel(banner.move(0, 8), (0, 0, 0, 185), None, cut=28)
        self.draw_skew_panel(banner, rgba(character["dark"], 236), rgba(character["highlight"], 240), cut=28, border_width=4)
        self.draw_slanted_strip(banner.left + 24, banner.top + 13, banner.width - 48, 9, -0.5, rgba(character["theme"], 155))
        label = f"{winner.label.upper()} TAKES THE ROUND"
        text = self.fit_text(self.big_font, label, banner.width - 58, character["highlight"])
        self.screen.blit(text, text.get_rect(center=banner.center))

    def draw_round_countdown_overlay(self):
        if self.match_state != "round_countdown":
            return
        labels = ("3", "2", "1", "FIGHT!")
        now = time.time()
        elapsed = max(0.0, now - self.round_countdown_started_at)
        step = min(3, int(elapsed / NEXT_ROUND_COUNTDOWN_STEP))
        local = (elapsed - step * NEXT_ROUND_COUNTDOWN_STEP) / NEXT_ROUND_COUNTDOWN_STEP
        w, h = self.screen.get_size()
        p1 = self.character_for_player(self.players[101])
        p2 = self.character_for_player(self.players[102])
        center = (w // 2, h // 2)
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(overlay, rgba(p1["theme"], 68), [(-50, h * 0.30), (w * 0.48, h * 0.42), (w * 0.44, h * 0.62), (-70, h * 0.76)])
        pygame.draw.polygon(overlay, rgba(p2["theme"], 68), [(w + 50, h * 0.26), (w * 0.52, h * 0.42), (w * 0.56, h * 0.64), (w + 70, h * 0.80)])
        self.screen.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)
        self.draw_starburst(center, 120 + step * 18, PALETTE["soup"] if step < 3 else PALETTE["white"], 180, seed=step + 80)
        label = labels[step]
        scale = 1.25 + 0.48 * (1.0 - ease_out_cubic(local))
        angle = math.sin(local * math.tau) * (8 if step < 3 else 3)
        text = self.title_font.render(label, True, (12, 10, 10) if step < 3 else PALETTE["white"])
        text = pygame.transform.rotozoom(text, angle, scale)
        rect = text.get_rect(center=center)
        shadow = text.copy()
        shadow.fill((0, 0, 0, 190), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(shadow, rect.move(7, 8))
        self.screen.blit(text, rect)

    def draw_match_win_screen(self):
        if self.match_state != "match_over" or not ENABLE_VICTORY_SCREEN or self.match_winner_id is None:
            return
        winner = self.players.get(self.match_winner_id)
        if winner is None:
            return
        now = time.time()
        age = now - self.match_win_started_at
        t = ease_out_cubic(min(1.0, age / 0.85))
        w, h = self.screen.get_size()
        character = self.character_for_player(winner)
        self.screen.fill(character["dark"])
        pygame.draw.polygon(self.screen, rgba(character["theme"], 210), [(-120, 0), (w * (0.54 + 0.12 * t), 0), (w * (0.42 + 0.10 * t), h), (-120, h)])
        pygame.draw.polygon(self.screen, rgba(character["secondary"], 190), [(w + 120, 0), (w * (0.52 - 0.10 * t), 0), (w * (0.62 - 0.12 * t), h), (w + 120, h)])
        self.draw_halftone_field((w * 0.20, h * 0.22), 210, character["highlight"], 0.52, now)
        self.draw_halftone_field((w * 0.82, h * 0.78), 230, character["accent"], 0.48, now + 1.1)
        for i in range(30):
            y = (i * 39 + now * 150) % (h + 100) - 50
            self.draw_slanted_strip(i * 67 % (w + 120) - 60, y, 170, 8 + i % 3 * 4, -0.45, rgba(PALETTE["white"], 36))

        art = self.creature_sprite(winner)
        art_h = int(h * (0.58 + 0.05 * math.sin(now * 3)))
        art_w = int(art_h * art.get_width() / max(1, art.get_height()))
        scaled = pygame.transform.smoothscale(art, (max(1, art_w), max(1, art_h)))
        art_rect = scaled.get_rect(center=(int(w * (0.30 + 0.04 * t)), int(h * 0.58)))
        glow = scaled.copy()
        glow.fill(rgba(character["highlight"], 150), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(glow, art_rect.move(8, -8))
        self.screen.blit(scaled, art_rect)

        title = f"{winner.label.upper()} WINS"
        title_surf = self.fit_text(self.title_font, title, int(w * 0.58), PALETTE["white"])
        title_rect = title_surf.get_rect(center=(int(w * 0.64), int(h * 0.34)))
        self.draw_starburst(title_rect.center, max(title_rect.width * 0.42, 180), character["accent"], 108, seed=winner.player_id + 44)
        self.screen.blit(title_surf, title_rect)
        subtitle = self.big_font.render("THE LAST BOWL", True, character["highlight"])
        subtitle_rect = subtitle.get_rect(center=(int(w * 0.64), int(h * 0.47)))
        self.draw_skew_panel(subtitle_rect.inflate(44, 22), rgba(character["dark"], 220), rgba(character["highlight"], 220), cut=18, border_width=3)
        self.screen.blit(subtitle, subtitle_rect)
        score = self.font.render(f"P{1 if winner.player_id == 101 else 2} VICTORY     ROUNDS {winner.wins}/2", True, PALETTE["beige"])
        self.screen.blit(score, score.get_rect(center=(int(w * 0.64), int(h * 0.58))))
        prompt = self.small_font.render("PRESS ENTER TO RETURN TO CHARACTER SELECT", True, PALETTE["light_brown"])
        self.screen.blit(prompt, prompt.get_rect(center=(int(w * 0.64), int(h * 0.72))))

    def draw_screen_flashes(self):
        if not self.screen_flashes:
            return
        now = time.time()
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for flash in self.screen_flashes:
            age = now - flash.created_at
            frac = clamp(1.0 - age / max(0.001, flash.duration), 0.0, 1.0)
            layer = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            layer.fill(rgba(flash.color, flash.alpha * frac))
            overlay.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)
        self.screen.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)

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
        contact_flash = frame_index < IMPACT_FRAME_FLASH_FRAMES
        inverted = frame_index >= IMPACT_FRAME_INVERT_FRAME
        bg = frame.color if contact_flash else (0, 0, 0) if inverted else PALETTE["white"]
        fg = PALETTE["white"] if inverted or contact_flash else (0, 0, 0)
        accent = PALETTE["soup"] if inverted else PALETTE["white"] if contact_flash else frame.color
        self.screen.fill(bg)
        smear_dx, smear_dy = self.screen_direction(frame.direction)
        for player in sorted(self.players.values(), key=lambda p: p.y, reverse=True):
            is_target = player.player_id == frame.target_id
            target_pop = is_target and frame_index < IMPACT_FRAME_INVERT_FRAME
            sprite, rect = self.player_sprite_pose(player, target_pop=target_pop)
            if target_pop:
                shove = IMPACT_FRAME_SHAKE if frame_index % 2 == 0 else -IMPACT_FRAME_SHAKE
                rect.move_ip(int(smear_dx * shove), int(smear_dy * shove))
            if is_target and frame_index < IMPACT_FRAME_REENTRY_FRAME:
                for i in range(1, 4):
                    alpha_color = accent if i % 2 else fg
                    smear = self.sprite_silhouette(sprite, rgba(alpha_color, 120 if i == 1 else 70))
                    offset = int(i * (7 if inverted else 5))
                    self.screen.blit(smear, rect.move(int(-smear_dx * offset), int(-smear_dy * offset)))
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
        dx, dy = self.screen_direction(frame.direction)
        nx, ny = -dy, dx
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
        attack_type = getattr(frame, "attack_type", "razor")
        profile = ATTACK_PROFILES.get(attack_type, ATTACK_PROFILES["razor"])
        for i in range(14):
            offset = (i - 6.5) * 32
            start = (hx - dx * 360 + nx * offset, hy - dy * 360 + ny * offset)
            end = (hx - dx * 74 + nx * offset * 0.22, hy - dy * 74 + ny * offset * 0.22)
            pygame.draw.line(self.screen, accent, start, end, 4 if i % 3 == 0 else 2)
        if HIT_TYPOGRAPHY and frame_index >= IMPACT_FRAME_FLASH_FRAMES:
            word = profile.get("hitWord", "HIT")
            text = self.big_font.render(word, True, accent)
            scale = 1.25 + 0.35 * frac
            text = pygame.transform.rotozoom(text, -8 + math.sin(frame_index) * 4, scale)
            text_rect = text.get_rect(center=(hx + nx * 120 - dx * 30, hy + ny * 74 - dy * 30))
            shadow = text.copy()
            shadow.fill(rgba(fg, 170), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(shadow, text_rect.move(5, 6))
            self.screen.blit(text, text_rect)
        if attack_type == "payment":
            self.draw_fake_qr_tile((hx, hy), 86 + 54 * frac, frame_index + 701, 1.0, angle=frame_index * 18)
            self.draw_scan_brackets((hx, hy), 124 + 42 * frac, accent, 230)
            for i, label in enumerate(("SCAN", "PAY", "YEN", "APPROVED")):
                stamp = self.small_font.render(label, True, accent if i % 2 else fg)
                stamp = pygame.transform.rotozoom(stamp, -18 + i * 11, 1.3)
                self.screen.blit(stamp, stamp.get_rect(center=(hx + nx * (90 + i * 18) - dx * (40 + i * 24), hy + ny * (58 - i * 22) - dy * (40 + i * 24))))
            for i in range(8):
                offset = (i - 3.5) * 46
                p1 = (hx - dx * 330 + nx * offset, hy - dy * 330 + ny * offset)
                p2 = (hx + dx * 260 + nx * offset * 0.12, hy + dy * 260 + ny * offset * 0.12)
                pygame.draw.line(self.screen, accent, p1, p2, 5 if i % 2 else 9)
                pygame.draw.line(self.screen, fg, p1, p2, 2)
        elif attack_type == "youtube":
            self.draw_youtube_play_splat((hx, hy), 132 + 52 * frac, 1.0, angle=-7 + frame_index * 4, alpha=255)
            pygame.draw.line(self.screen, accent, (hx - dx * 420 - nx * 180, hy - dy * 420 - ny * 180), (hx + dx * 420 + nx * 180, hy + dy * 420 + ny * 180), 18)
            pygame.draw.line(self.screen, fg, (hx - dx * 380 - nx * 160, hy - dy * 380 - ny * 160), (hx + dx * 380 + nx * 160, hy + dy * 380 + ny * 160), 6)
            for i, label in enumerate(("LIKE", "SUB", "BELL", "COMMENT")):
                stamp = self.small_font.render(label, True, fg if i % 2 else accent)
                stamp = pygame.transform.rotozoom(stamp, -14 + i * 8, 1.45)
                self.screen.blit(stamp, stamp.get_rect(center=(hx - nx * (130 - i * 78) + dx * (20 + i * 18), hy - ny * (78 - i * 36) + dy * (20 + i * 18))))
            for i in range(7):
                rect = pygame.Rect(0, 0, 82 + i * 8, 34 + (i % 2) * 12)
                rect.center = (hx + math.cos(i) * 180 * frac, hy + math.sin(i * 1.7) * 120 * frac)
                pygame.draw.rect(self.screen, accent if i % 2 else fg, rect, 4, border_radius=6)
        elif attack_type == "ceiling":
            self.draw_starburst((hx, hy), 150 + 56 * frac, accent, 230, seed=frame_index + 7)
            seal = self.fx_icon_surface("ceiling", "seal")
            giant = pygame.transform.rotozoom(seal, -12 + frame_index * 5, 2.2 + 0.45 * frac)
            giant.set_alpha(245)
            self.screen.blit(giant, giant.get_rect(center=(hx + dx * 42, hy + dy * 24)))
            for i in range(12):
                angle = i * math.tau / 12 + frame_index * 0.18
                pos = (hx + math.cos(angle) * (88 + 104 * frac), hy + math.sin(angle) * (58 + 76 * frac))
                baby = pygame.transform.rotozoom(seal, math.degrees(angle) + 90, 0.38 + 0.18 * (i % 3))
                baby.set_alpha(230)
                self.screen.blit(baby, baby.get_rect(center=pos))
            bonk = self.small_font.render("BONK", True, fg)
            bonk = pygame.transform.rotozoom(bonk, 10, 1.8)
            self.screen.blit(bonk, bonk.get_rect(center=(hx - nx * 108, hy - ny * 76)))
        elif attack_type == "chain":
            rng = random.Random(frame_index + 44)
            for _ in range(8):
                x1 = hx + rng.uniform(-120, 120)
                y1 = hy + rng.uniform(-90, 90)
                x2 = x1 + rng.uniform(-48, 48)
                y2 = y1 + rng.uniform(-48, 48)
                pygame.draw.line(self.screen, accent, (x1, y1), (x2, y2), 4)
                pygame.draw.line(self.screen, fg, (x1, y1), (x2, y2), 1)
        elif attack_type == "spiral":
            points = []
            for i in range(42):
                t = i / 41
                angle = t * math.tau * 2.4 + frame_index * 0.3
                r = 12 + t * 104 * frac
                points.append((hx + math.cos(angle) * r, hy + math.sin(angle) * r * 0.72))
            pygame.draw.lines(self.screen, accent, False, points, 5)
            pygame.draw.lines(self.screen, fg, False, points, 2)
        elif attack_type == "torrent":
            rng = random.Random(frame_index + 88)
            for _ in range(18):
                size = rng.randint(8, 24)
                x = hx + rng.uniform(-110, 110) * frac
                y = hy + rng.uniform(-80, 80) * frac
                pygame.draw.rect(self.screen, accent, (x, y, size, size))
                pygame.draw.rect(self.screen, fg, (x + 3, y + 3, max(2, size // 3), max(2, size // 3)))
        elif attack_type == "emblem":
            for i in range(5):
                angle = i * math.tau / 5 + frame_index * 0.24
                cx = hx + math.cos(angle) * 72 * frac
                cy = hy + math.sin(angle) * 52 * frac
                self.draw_starburst((cx, cy), 22, accent, 210, seed=i + frame_index)
        elif attack_type == "razor":
            for i in range(4):
                offset = (i - 1.5) * 70
                p1 = (hx - dx * 260 + nx * offset, hy - dy * 260 + ny * offset)
                p2 = (hx + dx * 280 - nx * offset * 0.20, hy + dy * 280 - ny * offset * 0.20)
                pygame.draw.line(self.screen, accent, p1, p2, 14 - i * 2)
                pygame.draw.line(self.screen, fg, p1, p2, 4)
        elif attack_type == "fire":
            rng = random.Random(frame_index + 184)
            for _ in range(24):
                size = rng.randint(10, 34)
                x = hx + rng.uniform(-170, 170) * frac
                y = hy + rng.uniform(-130, 130) * frac
                pygame.draw.rect(self.screen, accent, (x, y, size, size))
                inner = max(2, int(size * 0.35))
                pygame.draw.rect(self.screen, fg, (x + size * 0.25, y + size * 0.25, inner, inner))

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
