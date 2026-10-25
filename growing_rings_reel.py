"""
Growing Bouncing Rings Simulation
=================================
A self-contained 9:16 vertical physics simulation built with Pygame and NumPy.
Recreates the viral Instagram Reel / TikTok visual where a glowing neon ring
bounces inside a circular arena, grows on every wall impact, and locks concentric
rainbow ring layers until the entire circle is filled.

Features:
    - Interactive Options Setup Menu at startup (custom text, ball size, layer thickness,
      color palette / gradient mode, gravity, ball growth rate, and bounciness).
    - Multi-pass neon bloom, motion trails, and spark particles.
    - Zero-dependency synthesized pentatonic chime audio and celebration chord.
    - Anti-tunneling and anti-sliding physics with inward rebound impulses.
    - Video frame recorder for exporting MP4 reels.

Controls:
    [Menu Mode]
        Mouse Click  : Click cards, arrows, text box, or START button
        UP / DOWN    : Navigate between options
        LEFT / RIGHT : Change setting value
        ENTER / SPACE: Start simulation (or confirm custom text edit)
    [Simulation Mode]
        O / ESC      : Open Options Menu to tweak settings
        SPACE        : Pause / Resume simulation
        R            : Reset simulation (randomizes launch angle)
        UP / DOWN    : Fine-tune gravity in real time
        M            : Toggle audio mute / unmute
        V            : Toggle video frame recording (saved to ./output_frames)
        Q            : Quit application
"""

import colorsys
import math
import os
import random
import sys
import numpy as np
import pygame

# ---------------------------------------------------------------------------
# Global Window & Canvas Specifications
# ---------------------------------------------------------------------------
BASE_WIDTH = 540
BASE_HEIGHT = 960
SCALE_FACTOR = 1   # Set to 2 for crisp 1080x1920 Full HD rendering / recording
TARGET_FPS = 60

# Arena Geometry
CENTER_X = BASE_WIDTH // 2          # 270
CENTER_Y = BASE_HEIGHT // 2 + 20     # 500
OUTER_RADIUS = 225

# Color Palette Definitions
COLOR_BG = (8, 9, 15)           # Deep space-black #08090F
COLOR_BORDER = (60, 70, 95)     # Crisp neutral arena border #3C465F
COLOR_ARENA_FILL = (12, 14, 22) # Subtle deep backdrop inside arena
COLOR_WHITE = (255, 255, 255)
COLOR_TEXT_MUTED = (110, 120, 145)
COLOR_TEXT_HINT = (85, 95, 120)
COLOR_ACCENT = (165, 180, 252)
COLOR_CYAN = (0, 240, 255)
COLOR_CARD_BG = (16, 20, 32)
COLOR_CARD_BORDER = (38, 46, 68)
COLOR_CARD_ACTIVE = (30, 40, 68)
COLOR_CARD_ACTIVE_BORDER = (99, 102, 241)

# Audio Pentatonic Scale (Hz)
PENTATONIC_FREQS = [
    261.63, 293.66, 329.63, 392.00, 440.00,
    523.25, 587.33, 659.25, 783.99, 880.00
]


# ---------------------------------------------------------------------------
# Audio Synthesis (pygame.sndarray + numpy)
# ---------------------------------------------------------------------------
def synthesize_chimes(sample_rate: int = 44100):
    """
    Programmatically synthesizes clean chime notes with exponential decay
    envelopes across the 10-note pentatonic scale using NumPy.
    """
    duration = 0.35
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    chimes = []

    for freq in PENTATONIC_FREQS:
        # Multi-harmonic warm bell tone
        wave = (
            0.72 * np.sin(2 * np.pi * freq * t) +
            0.20 * np.sin(4 * np.pi * freq * t) +
            0.08 * np.sin(6 * np.pi * freq * t)
        )
        envelope = np.exp(-t * 11.5)
        audio = (wave * envelope * 0.75 * 32767).astype(np.int16)
        stereo = np.column_stack((audio, audio))
        chimes.append(pygame.sndarray.make_sound(stereo))

    # Celebratory C-Major harmonic chord for the completion fanfare
    chord_duration = 2.4
    tc = np.linspace(0, chord_duration, int(sample_rate * chord_duration), False)
    chord_wave = np.zeros_like(tc)
    chord_notes = [523.25, 659.25, 783.99, 1046.50]  # C5, E5, G5, C6
    for f in chord_notes:
        chord_wave += 0.25 * np.sin(2 * np.pi * f * tc)
        chord_wave += 0.05 * np.sin(4 * np.pi * f * tc)

    chord_envelope = np.exp(-tc * 2.0)
    chord_audio = (chord_wave * chord_envelope * 0.85 * 32767).astype(np.int16)
    chord_stereo = np.column_stack((chord_audio, chord_audio))
    chord_sound = pygame.sndarray.make_sound(chord_stereo)

    return chimes, chord_sound


# ---------------------------------------------------------------------------
# Radial Vignette
# ---------------------------------------------------------------------------
def create_radial_vignette(width: int, height: int) -> pygame.Surface:
    """Precomputes a soft radial vignette surface for cinematic depth."""
    y, x = np.ogrid[:height, :width]
    dist_from_center = np.hypot(x - width / 2.0, y - height / 2.0)
    max_dist = np.hypot(width / 2.0, height / 2.0)

    vignette_curve = np.clip(((dist_from_center / max_dist) ** 2.2) * 215, 0, 255)
    vignette_alpha = vignette_curve.astype(np.uint8)

    vignette_rgba = np.zeros((height, width, 4), dtype=np.uint8)
    vignette_rgba[..., 3] = vignette_alpha
    return pygame.image.frombuffer(vignette_rgba.tobytes(), (width, height), "RGBA")


# ---------------------------------------------------------------------------
# Simulation Configuration & Options
# ---------------------------------------------------------------------------
class SimulationConfig:
    """Holds all customizable options selected by the user in the start menu."""

    TEXT_PRESETS = [
        "Will it fill the whole circle?",
        "Oddly Satisfying Rainbow Rings",
        "Wait till the very end...",
        "Can you guess the final color?",
        "[Custom Text]"
    ]

    SHOW_STATS_OPTIONS = [
        (True, "Enabled (Show Fill % & Layers)"),
        (False, "Disabled (Hidden / Clean Video)")
    ]

    COLOR_STYLE_OPTIONS = [
        ("Normal", "Normal Colors (Distinct Solid Per Layer)"),
        ("Gradient", "Gradient Palette (Continuous Spectrum)")
    ]

    PALETTE_OPTIONS = [
        ("Rainbow", "Rainbow Gradient (360° Continuous HSV)"),
        ("Cyberpunk", "Cyberpunk Neon (Cyan ↔ Pink ↔ Violet)"),
        ("Sunset Fire", "Sunset Fire (Gold ↔ Orange ↔ Crimson ↔ Plum)"),
        ("Electric Blue", "Electric Blue (Ice Cyan ↔ Cobalt ↔ Violet)"),
        ("Emerald Mint", "Emerald Mint (Lime ↔ Seafoam ↔ Aquamarine)"),
        ("Cotton Candy", "Pastel Bubblegum (Baby Pink ↔ Sky Blue ↔ Lilac)"),
        ("Dark Synthwave", "80s Synthwave (Magenta ↔ Violet ↔ Amber)"),
        ("Toxic Matrix", "Toxic Venom (Acid Lime ↔ Green ↔ Yellow)"),
        ("Golden Luxury", "Imperial Gold (Champagne ↔ Amber ↔ Pearl)"),
        ("Sakura Bloom", "Cherry Blossom (Pearl White ↔ Coral ↔ Deep Rose)"),
        ("Ocean Abyss", "Deep Abyss (Aqua ↔ Marine Cobalt ↔ Seafoam)"),
        ("Magma Lava", "Lava Lamp (Solar Yellow ↔ Orange ↔ Dark Wine)"),
        ("Neon Violet", "Violet Haze (Soft Lilac ↔ Purple ↔ Indigo)"),
        ("Peachy Coral", "Peachy Sunrise (Pastel Peach ↔ Tangerine ↔ Pink)"),
        ("Silver Minimal", "Chrome Minimal (Pure White ↔ Silver ↔ Slate)"),
        ("Solid Cyan", "Solid Neon Cyan (Crisp Monochrome)")
    ]

    PALETTE_STOPS = {
        "Cyberpunk": [(0, 245, 255), (255, 10, 140), (160, 40, 255), (0, 245, 255)],
        "Sunset Fire": [(255, 220, 50), (255, 95, 20), (230, 20, 80), (140, 10, 120), (255, 220, 50)],
        "Electric Blue": [(120, 240, 255), (30, 140, 255), (70, 70, 255), (150, 100, 255), (120, 240, 255)],
        "Emerald Mint": [(120, 255, 100), (40, 255, 180), (0, 215, 215), (60, 180, 255), (120, 255, 100)],
        "Cotton Candy": [(255, 150, 200), (160, 210, 255), (210, 160, 255), (255, 200, 180), (255, 150, 200)],
        "Dark Synthwave": [(255, 0, 128), (140, 0, 255), (0, 230, 255), (255, 120, 0), (255, 0, 128)],
        "Toxic Matrix": [(180, 255, 20), (0, 255, 100), (0, 180, 80), (220, 255, 50), (180, 255, 20)],
        "Golden Luxury": [(255, 240, 180), (245, 180, 50), (200, 120, 20), (255, 255, 230), (255, 240, 180)],
        "Sakura Bloom": [(255, 245, 250), (255, 140, 180), (240, 60, 130), (255, 190, 210), (255, 245, 250)],
        "Ocean Abyss": [(0, 255, 210), (0, 140, 230), (10, 40, 160), (40, 220, 180), (0, 255, 210)],
        "Magma Lava": [(255, 230, 40), (255, 90, 0), (200, 10, 40), (90, 5, 50), (255, 230, 40)],
        "Neon Violet": [(210, 120, 255), (140, 40, 255), (80, 10, 200), (180, 90, 255), (210, 120, 255)],
        "Peachy Coral": [(255, 180, 140), (255, 110, 110), (255, 70, 130), (255, 200, 160), (255, 180, 140)],
        "Silver Minimal": [(255, 255, 255), (180, 195, 210), (110, 125, 145), (220, 230, 245), (255, 255, 255)],
        "Solid Cyan": [(0, 240, 255)]
    }

    THICKNESS_PLAN_OPTIONS = [
        ("Same: 25 px", "Same Thickness (25 px • ~9 Layers)", 25.0, 1.0),
        ("Same: 15 px", "Same Thickness (15 px • ~15 Layers)", 15.0, 1.0),
        ("Same: 35 px", "Same Thickness (35 px • ~7 Layers)", 35.0, 1.0),
        ("50% Halving", "50% of Previous (Halving • 105px → 52px → 26px...)", 105.0, 0.5),
        ("65% Decay", "65% of Previous (Decaying • 72px → 47px → 30px...)", 72.0, 0.65),
        ("80% Decay", "80% of Previous (Smooth • 44px → 35px → 28px...)", 44.0, 0.8),
        ("130% Growth", "130% Growing Inward (12px → 16px → 21px → 27px...)", 12.0, 1.3),
    ]

    BOUNCES_PER_LAYER_OPTIONS = [
        (4, "4 Bounces (Fast & Punchy Growth)"),
        (6, "6 Bounces (Standard Balanced)"),
        (8, "8 Bounces (Satisfying Progression)"),
        (12, "12 Bounces (Extended Progression)"),
        (1, "1 Bounce (Instant 1-Hit Layer Lock)")
    ]

    SIZE_OPTIONS = [
        (10.0, "10 px (Small Starting Ball)"),
        (14.0, "14 px (Standard Starting Ball)"),
        (18.0, "18 px (Large Starting Ball)"),
        (24.0, "24 px (Chonky Starting Ball)")
    ]

    GRAVITY_OPTIONS = [
        (0.00, "0.00 (Zero-Gravity Float)"),
        (0.14, "0.14 (Low Float Gravity)"),
        (0.26, "0.26 (Default Balanced)"),
        (0.40, "0.40 (Heavy Bounce)"),
        (0.60, "0.60 (High Kinetic)")
    ]

    BOUNCINESS_OPTIONS = [
        ({"min_speed": 4.5, "restitution": 1.01}, "Mellow (Speed 4.5, Rest 1.01)"),
        ({"min_speed": 5.5, "restitution": 1.02}, "Energetic (Speed 5.5, Rest 1.02)"),
        ({"min_speed": 7.0, "restitution": 1.04}, "Hyper Kinetic (Speed 7.0, Rest 1.04)")
    ]

    def __init__(self):
        self.text_idx = 0
        self.custom_text = "Will it fill the whole circle?"
        self.is_editing_custom = False

        self.show_stats_idx = 0         # Enabled by default
        self.color_style_idx = 0        # Normal Colors (Solid per layer)
        self.palette_idx = 0            # Rainbow
        self.thickness_plan_idx = 0     # Same 25 px
        self.bounces_per_layer_idx = 1  # 6 bounces
        self.size_idx = 1               # 14.0 px
        self.gravity_idx = 2            # 0.26
        self.bounciness_idx = 1         # Energetic

    def get_hook_text(self) -> str:
        if self.text_idx == len(self.TEXT_PRESETS) - 1:
            return self.custom_text if self.custom_text.strip() else "Will it fill the whole circle?"
        return self.TEXT_PRESETS[self.text_idx]

    def is_stats_enabled(self) -> bool:
        return self.SHOW_STATS_OPTIONS[self.show_stats_idx][0]

    def get_initial_radius(self) -> float:
        return self.SIZE_OPTIONS[self.size_idx][0]

    def get_bounces_per_layer(self) -> int:
        return self.BOUNCES_PER_LAYER_OPTIONS[self.bounces_per_layer_idx][0]

    def get_palette_name(self) -> str:
        return self.PALETTE_OPTIONS[self.palette_idx][0]

    def get_gravity(self) -> float:
        return self.GRAVITY_OPTIONS[self.gravity_idx][0]

    def get_bounciness(self) -> tuple:
        cfg = self.BOUNCINESS_OPTIONS[self.bounciness_idx][0]
        return cfg["restitution"], cfg["min_speed"]

    def generate_layer_plan(self) -> list:
        """Precomputes the radii, thicknesses, and colors for all concentric layers."""
        base_t = self.THICKNESS_PLAN_OPTIONS[self.thickness_plan_idx][2]
        ratio = self.THICKNESS_PLAN_OPTIONS[self.thickness_plan_idx][3]
        min_r = 10.0
        cur_r = float(OUTER_RADIUS)
        plan = []
        cur_t = base_t

        while cur_r - cur_t >= min_r + 5.0:
            plan.append({
                "outer_r": cur_r,
                "inner_r": cur_r - cur_t,
                "thickness": cur_t
            })
            cur_r -= cur_t
            if ratio != 1.0:
                cur_t = max(7.0, cur_t * ratio)

        if cur_r > min_r:
            plan.append({
                "outer_r": cur_r,
                "inner_r": min_r,
                "thickness": cur_r - min_r
            })

        num_layers = len(plan)
        palette = self.get_palette_name()
        color_style = self.COLOR_STYLE_OPTIONS[self.color_style_idx][0]

        for i, lyr in enumerate(plan):
            if color_style == "Gradient":
                t = i / max(1, num_layers - 1)
            else:
                t = (i * 0.38) % 1.0

            if palette == "Rainbow":
                r, g, b = colorsys.hsv_to_rgb(t, 0.85, 1.0)
                col = (int(r * 255), int(g * 255), int(b * 255))
            else:
                stops = self.PALETTE_STOPS.get(palette, [(255, 255, 255)])
                if len(stops) == 1:
                    col = stops[0]
                else:
                    pos = (t % 1.0) * (len(stops) - 1)
                    idx = int(pos)
                    frac = pos - idx
                    c1 = stops[idx]
                    c2 = stops[min(idx + 1, len(stops) - 1)]
                    col = (
                        int(c1[0] + (c2[0] - c1[0]) * frac),
                        int(c1[1] + (c2[1] - c1[1]) * frac),
                        int(c1[2] + (c2[2] - c1[2]) * frac)
                    )
            lyr["color"] = col

        return plan

    def evaluate_color(self, step_idx: int, total_steps: int = 42) -> tuple:
        """Computes RGB color based on the selected palette and step index (used for swatches)."""
        palette = self.get_palette_name()
        if palette == "Rainbow":
            h = (step_idx * 0.038) % 1.0
            r, g, b = colorsys.hsv_to_rgb(h, 0.85, 1.0)
            return (int(r * 255), int(g * 255), int(b * 255))

        colors = self.PALETTE_STOPS.get(palette, [(255, 255, 255)])
        if len(colors) == 1:
            return colors[0]

        t = (step_idx / max(1, total_steps)) % 1.0
        pos = t * (len(colors) - 1)
        idx = int(pos)
        frac = pos - idx
        c1 = colors[idx]
        c2 = colors[min(idx + 1, len(colors) - 1)]
        return (
            int(c1[0] + (c2[0] - c1[0]) * frac),
            int(c1[1] + (c2[1] - c1[1]) * frac),
            int(c1[2] + (c2[2] - c1[2]) * frac)
        )


# ---------------------------------------------------------------------------
# Particle Sparks System
# ---------------------------------------------------------------------------
class SparkParticle:
    """A glowing spark particle emitted at collision points."""

    def __init__(self, x: float, y: float, inward_nx: float, inward_ny: float, color: tuple):
        self.x = x
        self.y = y
        self.color = color
        self.max_life = 25
        self.life = self.max_life

        base_angle = math.atan2(inward_ny, inward_nx)
        spread_angle = base_angle + random.uniform(-0.85, 0.85)
        speed = random.uniform(2.2, 6.8)

        self.vx = math.cos(spread_angle) * speed
        self.vy = math.sin(spread_angle) * speed
        self.radius = random.uniform(1.8, 3.6)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.93
        self.vy *= 0.93
        self.life -= 1

    def draw(self, surface: pygame.Surface):
        if self.life <= 0:
            return
        alpha = int(255 * (self.life / self.max_life))
        color_with_alpha = (*self.color, alpha)

        s_radius = max(1, int(self.radius * (self.life / self.max_life)))
        s_size = s_radius * 2 + 4
        p_surf = pygame.Surface((s_size, s_size), pygame.SRCALPHA)
        pygame.draw.circle(p_surf, color_with_alpha, (s_size // 2, s_size // 2), s_radius)
        pygame.draw.circle(p_surf, (255, 255, 255, alpha), (s_size // 2, s_size // 2), max(1, s_radius // 2))
        surface.blit(p_surf, (int(self.x - s_size // 2), int(self.y - s_size // 2)))


class LayerShockwave:
    """A radiant expanding shockwave across a newly locked ring."""

    def __init__(self, radius: float, thickness: float, color: tuple):
        self.radius = radius
        self.thickness = thickness
        self.color = color
        self.life = 22
        self.max_life = 22

    def update(self):
        self.life -= 1

    def draw(self, surface: pygame.Surface):
        if self.life <= 0:
            return
        progress = self.life / self.max_life
        alpha = int(220 * progress)
        w = max(2, int(self.thickness * progress))
        surf = pygame.Surface((BASE_WIDTH, BASE_HEIGHT), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*self.color, alpha), (CENTER_X, CENTER_Y), int(round(self.radius)), width=w)
        pygame.draw.circle(surf, (255, 255, 255, alpha), (CENTER_X, CENTER_Y), int(round(self.radius)), width=2)
        surface.blit(surf, (0, 0))


class SpawnBurst:
    """A glowing expanding ripple at the location where a new ball spawns."""

    def __init__(self, x: float, y: float, color: tuple):
        self.x = x
        self.y = y
        self.color = color
        self.life = 18
        self.max_life = 18

    def update(self):
        self.life -= 1

    def draw(self, surface: pygame.Surface):
        if self.life <= 0:
            return
        progress = 1.0 - (self.life / self.max_life)
        alpha = int(230 * (self.life / self.max_life))
        radius = int(8 + progress * 24)
        s_size = radius * 2 + 10
        b_surf = pygame.Surface((s_size, s_size), pygame.SRCALPHA)
        center = (s_size // 2, s_size // 2)
        pygame.draw.circle(b_surf, (*self.color, alpha), center, radius, width=2)
        pygame.draw.circle(b_surf, (255, 255, 255, alpha), center, max(1, radius - 2), width=1)
        surface.blit(b_surf, (int(self.x - center[0]), int(self.y - center[1])))


# ---------------------------------------------------------------------------
# Simulation Engine
# ---------------------------------------------------------------------------
class GrowingRingsSimulation:
    """Manages progressive ball growth, layer filling, random ball respawns, and physics."""

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.muted = False
        self.paused = False

        try:
            self.chimes, self.chord_sound = synthesize_chimes()
            self.audio_available = True
        except Exception as e:
            print(f"[Warning] Audio synthesis unavailable: {e}")
            self.chimes = []
            self.chord_sound = None
            self.audio_available = False

        self.current_chime_idx = 0
        self.reset()

    def reset(self, random_angle: bool = False):
        """Resets the simulation using current configuration options."""
        self.layers = self.config.generate_layer_plan()
        self.current_layer_idx = 0
        self.locked_layers = []

        self.particles = []
        self.shockwaves = []
        self.spawn_bursts = []
        self.trail = []

        self.gravity = self.config.get_gravity()
        self.restitution, self.min_speed = self.config.get_bounciness()

        self.is_completed = False
        self.pulse_phase = 0.0
        self.screen_shake = 0.0
        self.bounce_cooldown = 0

        self.spawn_new_ball_for_layer(random_angle=random_angle)

    def spawn_new_ball_for_layer(self, random_angle: bool = False):
        """Spawns a new ball in a random location inside the current layer's inner radius."""
        if self.current_layer_idx >= len(self.layers):
            return

        lyr = self.layers[self.current_layer_idx]
        outer_r = lyr["outer_r"]
        inner_r = lyr["inner_r"]
        thickness = lyr["thickness"]

        base_init = float(self.config.get_initial_radius())
        max_start = max(4.0, min(base_init, thickness * 0.45, (outer_r - 8.0) * 0.4))
        self.ball_radius = max(4.0, min(base_init, max_start))
        self.bounces_in_layer = 0
        self.target_bounces = self.config.get_bounces_per_layer()

        # Growth per bounce: by target bounce, ball size fills the layer thickness
        target_r = max(self.ball_radius + 4.0, min(thickness * 0.95, outer_r - 4.0))
        self.growth_per_bounce = (target_r - self.ball_radius) / max(1, self.target_bounces)

        # Safe spawn radius strictly within the remaining arena
        max_spawn_r = max(0.0, outer_r - self.ball_radius - 12.0)
        spawn_r = random.uniform(0.0, max_spawn_r) if max_spawn_r > 0 else 0.0
        spawn_theta = random.uniform(0.0, 2.0 * math.pi)

        self.x = float(CENTER_X + spawn_r * math.cos(spawn_theta))
        self.y = float(CENTER_Y + spawn_r * math.sin(spawn_theta))

        # Launch in a completely random 360-degree direction and randomized speed on every spawn / respawn
        launch_angle = random.uniform(0.0, 2.0 * math.pi)
        # Avoid degenerate near-vertical trajectory (1D traps)
        if abs(math.cos(launch_angle)) < 0.25:
            launch_angle += 0.45 if math.sin(launch_angle) >= 0 else -0.45

        # Random speed scaled to bounciness setting
        min_s = max(5.0, self.min_speed)
        max_s = min_s * 1.5 + 3.0
        launch_speed = random.uniform(min_s, max_s)

        self.vx = math.cos(launch_angle) * launch_speed
        self.vy = math.sin(launch_angle) * launch_speed

        self.trail = []
        self.bounce_cooldown = 10

        # Spawn visual burst
        self.spawn_bursts.append(SpawnBurst(self.x, self.y, lyr["color"]))

    def get_current_color(self) -> tuple:
        if self.current_layer_idx < len(self.layers):
            return self.layers[self.current_layer_idx]["color"]
        return (255, 255, 255)

    def play_chime(self):
        if not self.muted and self.audio_available and self.chimes:
            self.chimes[self.current_chime_idx].play()
            self.current_chime_idx = (self.current_chime_idx + 1) % len(self.chimes)

    def play_celebration(self):
        if not self.muted and self.audio_available and self.chord_sound:
            self.chord_sound.play()

    def update(self):
        """Advances physics and collision resolution by one frame."""
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.life > 0]

        for s in self.shockwaves:
            s.update()
        self.shockwaves = [s for s in self.shockwaves if s.life > 0]

        for b in self.spawn_bursts:
            b.update()
        self.spawn_bursts = [b for b in self.spawn_bursts if b.life > 0]

        if self.screen_shake > 0:
            self.screen_shake = max(0.0, self.screen_shake - 0.5)

        if self.is_completed:
            self.pulse_phase += 0.12
            return

        if self.current_layer_idx >= len(self.layers):
            self.is_completed = True
            self.play_celebration()
            return

        current_lyr = self.layers[self.current_layer_idx]
        current_boundary = current_lyr["outer_r"]
        current_color = current_lyr["color"]

        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy

        self.trail.append((self.x, self.y, self.ball_radius, current_color))
        if len(self.trail) > 18:
            self.trail.pop(0)

        dx = self.x - CENTER_X
        dy = self.y - CENTER_Y
        dist = math.hypot(dx, dy)

        if self.bounce_cooldown > 0:
            self.bounce_cooldown -= 1

        # Check boundary collision against current layer's outer_r
        if dist + self.ball_radius >= current_boundary and self.bounce_cooldown == 0:
            if dist > 0.0001:
                nx = dx / dist
                ny = dy / dist
            else:
                nx = 0.0
                ny = -1.0

            dot = self.vx * nx + self.vy * ny
            # Pure specular reflection: v - 2(v . n)n
            rx = self.vx - 2.0 * dot * nx
            ry = self.vy - 2.0 * dot * ny

            # Micro-chaos angular jitter (+/- 0.14 rad) breaks 1D trapped loops
            jitter = random.uniform(-0.14, 0.14)
            cos_j = math.cos(jitter)
            sin_j = math.sin(jitter)
            rx, ry = rx * cos_j - ry * sin_j, rx * sin_j + ry * cos_j

            # When bouncing off top or bottom, add lateral kick away from vertical axis
            if abs(ny) > 0.45:
                kick_dir = math.copysign(1.0, rx) if abs(rx) > 0.2 else (-1.0 if nx > 0 else 1.0)
                rx += kick_dir * 1.5

            speed = math.hypot(rx, ry) * self.restitution
            speed = max(self.min_speed, min(13.5, speed))

            # Lateral velocity guarantee for 360 wall coverage
            min_lateral = max(3.5, speed * 0.38)
            if abs(rx) < min_lateral:
                sign_x = math.copysign(1.0, rx) if abs(rx) > 0.05 else (-1.0 if nx > 0 else 1.0)
                rx = sign_x * min_lateral
                rem_sq = max(1.0, speed * speed - rx * rx)
                ry = math.copysign(math.sqrt(rem_sq), ry)
            else:
                cur_s = math.hypot(rx, ry)
                if cur_s > 0:
                    rx = (rx / cur_s) * speed
                    ry = (ry / cur_s) * speed

            # Upward assist for lower basin under gravity
            if self.gravity > 0.05 and ny > 0.65:
                ry -= min(2.0, self.gravity * 6.5)

            self.vx = rx
            self.vy = ry

            # Ball size increases on bounce!
            self.ball_radius = min(
                self.ball_radius + self.growth_per_bounce,
                current_boundary - 4.0
            )
            self.bounces_in_layer += 1
            self.bounce_cooldown = 8

            # Push back inside boundary to prevent sticking
            overlap = (dist + self.ball_radius) - current_boundary
            if overlap > 0:
                self.x -= nx * (overlap + 2.0)
                self.y -= ny * (overlap + 2.0)

            # Spawn impact sparks
            contact_x = CENTER_X + nx * current_boundary
            contact_y = CENTER_Y + ny * current_boundary
            for _ in range(12):
                self.particles.append(
                    SparkParticle(contact_x, contact_y, -nx, -ny, current_color)
                )

            self.play_chime()
            self.screen_shake = 2.5

            # CHECK IF BALL HAS FILLED THIS LAYER:
            if self.bounces_in_layer >= self.target_bounces:
                # Lock layer!
                self.locked_layers.append((
                    current_lyr["outer_r"],
                    current_lyr["inner_r"],
                    current_lyr["thickness"],
                    current_lyr["color"]
                ))
                # Add expanding shockwave on the newly locked layer
                self.shockwaves.append(
                    LayerShockwave(current_lyr["outer_r"], current_lyr["thickness"], current_color)
                )

                self.current_layer_idx += 1
                self.screen_shake = 5.0

                if self.current_layer_idx >= len(self.layers) or current_lyr["inner_r"] <= 12.0:
                    self.is_completed = True
                    self.x = float(CENTER_X)
                    self.y = float(CENTER_Y)
                    self.vx = 0.0
                    self.vy = 0.0
                    self.play_celebration()
                else:
                    # Spawn new ball in a random place inside the remaining circle!
                    self.spawn_new_ball_for_layer()

    def draw_locked_rings(self, surface: pygame.Surface):
        """Renders concentric locked layers."""
        for i, (outer_r, inner_r, thickness, base_color) in enumerate(self.locked_layers):
            color = base_color
            if self.is_completed:
                wave = math.sin(self.pulse_phase - i * 0.35)
                brightness = 0.5 + 0.5 * wave
                r_c = min(255, int(base_color[0] + (255 - base_color[0]) * brightness * 0.6))
                g_c = min(255, int(base_color[1] + (255 - base_color[1]) * brightness * 0.6))
                b_c = min(255, int(base_color[2] + (255 - base_color[2]) * brightness * 0.6))
                color = (r_c, g_c, b_c)

            if inner_r <= 12.0:
                pygame.draw.circle(surface, color, (CENTER_X, CENTER_Y), int(round(outer_r)))
            else:
                stroke_w = int(math.ceil(thickness)) + 1
                pygame.draw.circle(surface, color, (CENTER_X, CENTER_Y), int(round(outer_r)), width=stroke_w)

            # Elegant layer border seams
            if inner_r > 12.0:
                pygame.draw.circle(surface, (12, 16, 26), (CENTER_X, CENTER_Y), int(round(inner_r)), width=1)
            pygame.draw.circle(surface, (255, 255, 255, 30), (CENTER_X, CENTER_Y), int(round(outer_r)), width=1)

    def draw_motion_trail(self, surface: pygame.Surface):
        """Renders decaying motion trails for the active ring."""
        if not self.trail or self.is_completed:
            return

        trail_surf = pygame.Surface((BASE_WIDTH, BASE_HEIGHT), pygame.SRCALPHA)
        trail_len = len(self.trail)

        for idx, (tx, ty, tr, color) in enumerate(self.trail):
            decay = (idx + 1) / trail_len
            alpha = int(105 * (decay ** 1.8))
            r_int = max(1, int(tr))
            pygame.draw.circle(trail_surf, (*color, alpha), (int(tx), int(ty)), r_int, width=2)

        surface.blit(trail_surf, (0, 0))

    def draw_active_ring(self, surface: pygame.Surface):
        """Renders the bouncing ring with multi-pass neon bloom and white core."""
        r = int(round(self.ball_radius))
        if r <= 0:
            return

        color = self.get_current_color()

        if self.is_completed:
            fill_r = int(round(self.layers[-1]["outer_r"])) + 2
            core_surf = pygame.Surface((fill_r * 2 + 40, fill_r * 2 + 40), pygame.SRCALPHA)
            c_center = (fill_r + 20, fill_r + 20)

            pulse_wave = (math.sin(self.pulse_phase) + 1.0) * 0.5
            core_r = min(255, int(color[0] + (255 - color[0]) * pulse_wave * 0.5))
            core_g = min(255, int(color[1] + (255 - color[1]) * pulse_wave * 0.5))
            core_b = min(255, int(color[2] + (255 - color[2]) * pulse_wave * 0.5))
            pulsed_color = (core_r, core_g, core_b)

            pygame.draw.circle(core_surf, pulsed_color, c_center, fill_r)
            inner_r = max(2, int(fill_r * 0.55))
            pygame.draw.circle(core_surf, (255, 255, 255, 160), c_center, inner_r, width=3)
            pygame.draw.circle(core_surf, (255, 255, 255, 255), c_center, max(2, int(fill_r * 0.28)))
            surface.blit(core_surf, (int(self.x - c_center[0]), int(self.y - c_center[1])))
            return

        glow_pad = 20
        box_size = (r + glow_pad) * 2
        glow_surf = pygame.Surface((box_size, box_size), pygame.SRCALPHA)
        center = (box_size // 2, box_size // 2)

        pygame.draw.circle(glow_surf, (*color, 22), center, max(1, r - 3))
        pygame.draw.circle(glow_surf, (*color, 40), center, r, width=8)
        pygame.draw.circle(glow_surf, (*color, 95), center, r, width=5)
        pygame.draw.circle(glow_surf, (*color, 195), center, r, width=3)
        pygame.draw.circle(glow_surf, (255, 255, 255, 250), center, r, width=1)

        surface.blit(glow_surf, (int(self.x - center[0]), int(self.y - center[1])))


# ---------------------------------------------------------------------------
# Options Menu UI System
# ---------------------------------------------------------------------------
class OptionsMenu:
    """Renders the sleek interactive setup dashboard at startup."""

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.selected_idx = 0
        self.num_options = 9  # 9 customizable parameters

        self.font_title = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 24, bold=True)
        self.font_sub = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 13)
        self.font_label = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 11, bold=True)
        self.font_val = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 13, bold=True)
        self.font_btn = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 19, bold=True)
        self.font_hint = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 12)

        self.start_btn_rect = pygame.Rect(70, 755, 400, 50)
        self.card_rects = []
        self.left_btn_rects = []
        self.right_btn_rects = []
        self.cursor_blink = 0

    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        Handles mouse and keyboard input for the options menu.
        Returns True when the user clicks or presses START.
        """
        # Custom text typing mode
        if self.config.is_editing_custom:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                    self.config.is_editing_custom = False
                elif event.key == pygame.K_BACKSPACE:
                    self.config.custom_text = self.config.custom_text[:-1]
                else:
                    if event.unicode and len(self.config.custom_text) < 38:
                        self.config.custom_text += event.unicode
                return False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.config.is_editing_custom = False
                return False

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.selected_idx == 0 and self.config.text_idx == len(self.config.TEXT_PRESETS) - 1:
                    self.config.is_editing_custom = True
                    return False
                return True  # Start simulation

            elif event.key == pygame.K_UP:
                self.selected_idx = (self.selected_idx - 1) % self.num_options

            elif event.key == pygame.K_DOWN:
                self.selected_idx = (self.selected_idx + 1) % self.num_options

            elif event.key == pygame.K_LEFT:
                self.adjust_option(self.selected_idx, -1)

            elif event.key == pygame.K_RIGHT:
                self.adjust_option(self.selected_idx, 1)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            # Account for scale factor
            mx = int(mx / SCALE_FACTOR)
            my = int(my / SCALE_FACTOR)

            # Check Start Button
            if self.start_btn_rect.collidepoint(mx, my):
                return True

            # Check Arrow Buttons & Card Clicks
            for idx in range(self.num_options):
                if idx < len(self.left_btn_rects) and self.left_btn_rects[idx].collidepoint(mx, my):
                    self.selected_idx = idx
                    self.adjust_option(idx, -1)
                    return False
                elif idx < len(self.right_btn_rects) and self.right_btn_rects[idx].collidepoint(mx, my):
                    self.selected_idx = idx
                    self.adjust_option(idx, 1)
                    return False
                elif idx < len(self.card_rects) and self.card_rects[idx].collidepoint(mx, my):
                    self.selected_idx = idx
                    # If clicking custom text option, toggle editing
                    if idx == 0 and self.config.text_idx == len(self.config.TEXT_PRESETS) - 1:
                        self.config.is_editing_custom = True
                    else:
                        self.adjust_option(idx, 1)
                    return False

        return False

    def adjust_option(self, option_idx: int, direction: int):
        """Cycles settings values forwards (+1) or backwards (-1)."""
        if option_idx == 0:
            self.config.text_idx = (self.config.text_idx + direction) % len(self.config.TEXT_PRESETS)
            if self.config.text_idx == len(self.config.TEXT_PRESETS) - 1:
                self.config.is_editing_custom = True

        elif option_idx == 1:
            self.config.show_stats_idx = (self.config.show_stats_idx + direction) % len(self.config.SHOW_STATS_OPTIONS)

        elif option_idx == 2:
            self.config.color_style_idx = (self.config.color_style_idx + direction) % len(self.config.COLOR_STYLE_OPTIONS)

        elif option_idx == 3:
            self.config.palette_idx = (self.config.palette_idx + direction) % len(self.config.PALETTE_OPTIONS)

        elif option_idx == 4:
            self.config.thickness_plan_idx = (self.config.thickness_plan_idx + direction) % len(self.config.THICKNESS_PLAN_OPTIONS)

        elif option_idx == 5:
            self.config.bounces_per_layer_idx = (self.config.bounces_per_layer_idx + direction) % len(self.config.BOUNCES_PER_LAYER_OPTIONS)

        elif option_idx == 6:
            self.config.size_idx = (self.config.size_idx + direction) % len(self.config.SIZE_OPTIONS)

        elif option_idx == 7:
            self.config.gravity_idx = (self.config.gravity_idx + direction) % len(self.config.GRAVITY_OPTIONS)

        elif option_idx == 8:
            self.config.bounciness_idx = (self.config.bounciness_idx + direction) % len(self.config.BOUNCINESS_OPTIONS)

    def draw(self, surface: pygame.Surface, mouse_pos: tuple):
        """Renders the options dashboard onto the base surface."""
        surface.fill(COLOR_BG)
        self.cursor_blink += 1

        # Header Badge & Title
        title_surf = self.font_title.render("SIMULATION SETUP", True, COLOR_WHITE)
        title_rect = title_surf.get_rect(center=(BASE_WIDTH // 2, 44))
        surface.blit(title_surf, title_rect)

        sub_surf = self.font_sub.render("Configure physics, visuals & text before launch", True, COLOR_TEXT_MUTED)
        sub_rect = sub_surf.get_rect(center=(BASE_WIDTH // 2, 70))
        surface.blit(sub_surf, sub_rect)

        # Thin glowing divider
        pygame.draw.line(surface, COLOR_CARD_BORDER, (40, 88), (BASE_WIDTH - 40, 88), 1)

        # Build options definitions
        labels_and_values = [
            ("TOP HOOK CAPTION", self.get_display_text_value()),
            ("FILL & LAYERS COUNTER", self.config.SHOW_STATS_OPTIONS[self.config.show_stats_idx][1]),
            ("COLOR STYLE", self.config.COLOR_STYLE_OPTIONS[self.config.color_style_idx][1]),
            ("COLOR PALETTE / THEME", self.config.PALETTE_OPTIONS[self.config.palette_idx][1]),
            ("LAYER THICKNESS & SCALING", self.config.THICKNESS_PLAN_OPTIONS[self.config.thickness_plan_idx][1]),
            ("BOUNCES TO FILL LAYER", self.config.BOUNCES_PER_LAYER_OPTIONS[self.config.bounces_per_layer_idx][1]),
            ("STARTING BALL SIZE", self.config.SIZE_OPTIONS[self.config.size_idx][1]),
            ("GRAVITY STRENGTH", self.config.GRAVITY_OPTIONS[self.config.gravity_idx][1]),
            ("BOUNCINESS & SPEED", self.config.BOUNCINESS_OPTIONS[self.config.bounciness_idx][1])
        ]

        start_y = 96
        card_h = 60
        spacing = 7
        card_w = 460
        card_x = (BASE_WIDTH - card_w) // 2

        self.card_rects = []
        self.left_btn_rects = []
        self.right_btn_rects = []

        mx, my = mouse_pos
        mx = int(mx / SCALE_FACTOR)
        my = int(my / SCALE_FACTOR)

        for i, (label, val_str) in enumerate(labels_and_values):
            cy = start_y + i * (card_h + spacing)
            card_rect = pygame.Rect(card_x, cy, card_w, card_h)
            self.card_rects.append(card_rect)

            is_selected = (i == self.selected_idx)
            is_hovered = card_rect.collidepoint(mx, my)

            # Card background & border
            bg_color = COLOR_CARD_ACTIVE if (is_selected or is_hovered) else COLOR_CARD_BG
            border_color = COLOR_CARD_ACTIVE_BORDER if is_selected else (
                COLOR_ACCENT if is_hovered else COLOR_CARD_BORDER
            )
            pygame.draw.rect(surface, bg_color, card_rect, border_radius=10)
            pygame.draw.rect(surface, border_color, card_rect, width=2 if is_selected else 1, border_radius=10)

            # Option Label
            lbl_color = COLOR_CYAN if is_selected else COLOR_TEXT_MUTED
            lbl_surf = self.font_label.render(label, True, lbl_color)
            surface.blit(lbl_surf, (card_x + 16, cy + 8))

            # Left/Right Arrow Steppers
            btn_w, btn_h = 24, 24
            left_rect = pygame.Rect(card_x + 12, cy + 28, btn_w, btn_h)
            right_rect = pygame.Rect(card_x + card_w - 36, cy + 28, btn_w, btn_h)
            self.left_btn_rects.append(left_rect)
            self.right_btn_rects.append(right_rect)

            l_color = COLOR_WHITE if left_rect.collidepoint(mx, my) else COLOR_TEXT_MUTED
            r_color = COLOR_WHITE if right_rect.collidepoint(mx, my) else COLOR_TEXT_MUTED

            pygame.draw.rect(surface, (28, 36, 56), left_rect, border_radius=4)
            pygame.draw.rect(surface, (28, 36, 56), right_rect, border_radius=4)

            # Crisp vector polygon arrows (avoids font glyph missing boxes)
            lcx, lcy = left_rect.center
            pygame.draw.polygon(surface, l_color, [(lcx + 4, lcy - 6), (lcx - 4, lcy), (lcx + 4, lcy + 6)])

            rcx, rcy = right_rect.center
            pygame.draw.polygon(surface, r_color, [(rcx - 4, rcy - 6), (rcx + 4, rcy), (rcx - 4, rcy + 6)])

            # Value text display
            val_color = COLOR_WHITE if is_selected else (220, 225, 240)
            val_surf = self.font_val.render(val_str, True, val_color)
            val_rect = val_surf.get_rect(midleft=(card_x + 44, cy + 39))
            surface.blit(val_surf, val_rect)

            # Special Mini Preview Swatch for Color Palette (at index 3)
            if i == 3:
                swatch_x = card_x + card_w - 110
                swatch_y = cy + 10
                self.draw_palette_swatch(surface, swatch_x, swatch_y, 70, 11)

        # Start Simulation Button
        btn_hovered = self.start_btn_rect.collidepoint(mx, my)
        btn_bg = (79, 70, 229) if btn_hovered else (67, 56, 202)
        pygame.draw.rect(surface, btn_bg, self.start_btn_rect, border_radius=12)
        pygame.draw.rect(surface, COLOR_CYAN if btn_hovered else COLOR_ACCENT, self.start_btn_rect, width=2, border_radius=12)

        bcx, bcy = self.start_btn_rect.center
        btn_text = "START SIMULATION"
        btn_surf = self.font_btn.render(btn_text, True, COLOR_WHITE)
        btn_rect = btn_surf.get_rect(center=(bcx + 10, bcy))
        surface.blit(btn_surf, btn_rect)

        # Play icon vector triangle
        play_icon_x = btn_rect.left - 18
        icon_color = COLOR_CYAN if btn_hovered else COLOR_WHITE
        pygame.draw.polygon(surface, icon_color, [(play_icon_x - 5, bcy - 7), (play_icon_x + 6, bcy), (play_icon_x - 5, bcy + 7)])

        # Bottom Hints
        hint_text = "Click arrows • ↑ / ↓ to select • ← / → to change • ENTER to start"
        hint_surf = self.font_hint.render(hint_text, True, COLOR_TEXT_HINT)
        surface.blit(hint_surf, hint_surf.get_rect(center=(BASE_WIDTH // 2, 835)))

        hint_sim = "In Simulation: [O] Options • [H] Toggle Stats • [SPACE] Pause • [R] Reset"
        hint_sim_surf = self.font_hint.render(hint_sim, True, COLOR_TEXT_MUTED)
        surface.blit(hint_sim_surf, hint_sim_surf.get_rect(center=(BASE_WIDTH // 2, 862)))

    def get_display_text_value(self) -> str:
        """Returns the formatted hook text display string with cursor if editing."""
        if self.config.text_idx == len(self.config.TEXT_PRESETS) - 1:
            cursor = "|" if (self.config.is_editing_custom and (self.cursor_blink // 20) % 2 == 0) else ""
            return f"Custom: \"{self.config.custom_text}{cursor}\""
        return f"\"{self.config.get_hook_text()}\""

    def draw_palette_swatch(self, surface: pygame.Surface, x: int, y: int, w: int, h: int):
        """Renders a small continuous color gradient bar as a visual preview."""
        palette = self.config.get_palette_name()
        for px in range(w):
            step = int((px / w) * 40)
            col = self.config.evaluate_color(step, 40)
            pygame.draw.line(surface, col, (x + px, y), (x + px, y + h))
        pygame.draw.rect(surface, COLOR_CARD_BORDER, (x, y, w, h), width=1)


# ---------------------------------------------------------------------------
# Main Application Loop
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    pygame.mixer.init(frequency=44100, size=-16, channels=2)
    pygame.display.set_caption("Viral Growing Bouncing Rings")

    window_width = BASE_WIDTH * SCALE_FACTOR
    window_height = BASE_HEIGHT * SCALE_FACTOR
    window = pygame.display.set_mode((window_width, window_height))

    base_surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
    vignette_surface = create_radial_vignette(BASE_WIDTH, BASE_HEIGHT)

    clock = pygame.time.Clock()

    # Fonts
    font_hook = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 24, bold=True)
    font_stats = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 18, bold=True)
    font_watermark = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 16)
    font_hints = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 13)
    font_banner = pygame.font.SysFont(["Arial", "Helvetica", "sans-serif"], 28, bold=True)

    config = SimulationConfig()
    menu = OptionsMenu(config)
    sim = GrowingRingsSimulation(config)

    # State: "MENU" or "SIMULATION"
    app_state = "MENU"

    # Video Recorder State
    recording = False
    record_frame_count = 0
    record_dir = "output_frames"

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        # Event Processing
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif app_state == "MENU":
                should_start = menu.handle_event(event)
                if should_start:
                    sim.reset()
                    app_state = "SIMULATION"

            elif app_state == "SIMULATION":
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        running = False

                    # Return to Options Menu
                    elif event.key in (pygame.K_ESCAPE, pygame.K_o):
                        app_state = "MENU"

                    # Toggle Fill % & Layers display
                    elif event.key == pygame.K_h:
                        config.show_stats_idx = 1 - config.show_stats_idx

                    elif event.key == pygame.K_SPACE:
                        sim.paused = not sim.paused

                    elif event.key == pygame.K_r:
                        sim.reset(random_angle=True)

                    elif event.key == pygame.K_m:
                        sim.muted = not sim.muted

                    elif event.key == pygame.K_UP:
                        sim.gravity = round(min(1.2, sim.gravity + 0.04), 2)

                    elif event.key == pygame.K_DOWN:
                        sim.gravity = round(max(0.00, sim.gravity - 0.04), 2)

                    elif event.key == pygame.K_v:
                        recording = not recording
                        if recording:
                            os.makedirs(record_dir, exist_ok=True)
                            print(f"[Recorder] Recording started -> saving PNG frames to ./{record_dir}")
                        else:
                            print(f"[Recorder] Recording stopped ({record_frame_count} frames saved).")

        # -------------------------------------------------------------------
        # Update & Render
        # -------------------------------------------------------------------
        if app_state == "MENU":
            menu.draw(base_surface, mouse_pos)

        elif app_state == "SIMULATION":
            if not sim.paused:
                sim.update()

            base_surface.fill(COLOR_BG)

            # 1. Arena Interior & Border
            pygame.draw.circle(base_surface, COLOR_ARENA_FILL, (CENTER_X, CENTER_Y), OUTER_RADIUS)
            pygame.draw.circle(base_surface, COLOR_BORDER, (CENTER_X, CENTER_Y), OUTER_RADIUS, width=3)

            # 2. Concentric Locked Layers
            sim.draw_locked_rings(base_surface)

            # Shockwaves on newly locked layers
            for s in sim.shockwaves:
                s.draw(base_surface)

            # 3. Motion Trail
            sim.draw_motion_trail(base_surface)

            # 4. Impact Sparks
            for p in sim.particles:
                p.draw(base_surface)

            # 4b. Spawn Bursts
            for b in sim.spawn_bursts:
                b.draw(base_surface)

            # 5. Active Neon Bouncing Ring / Ball
            sim.draw_active_ring(base_surface)

            # 6. Radial Vignette Overlay
            base_surface.blit(vignette_surface, (0, 0))

            # ---------------------------------------------------------------
            # Typography & HUD
            # ---------------------------------------------------------------
            # Configurable Hook Text at Top (y = 95)
            hook_text = config.get_hook_text()
            hook_shadow = font_hook.render(hook_text, True, (0, 0, 0))
            hook_surf = font_hook.render(hook_text, True, COLOR_WHITE)
            hook_rect = hook_surf.get_rect(center=(BASE_WIDTH // 2, 95))
            base_surface.blit(hook_shadow, (hook_rect.x + 2, hook_rect.y + 2))
            base_surface.blit(hook_surf, hook_rect)

            # Live Fill Percentage & Layers Counter (y = 136, Disabable)
            if config.is_stats_enabled():
                total_layers = len(sim.layers)
                completed = len(sim.locked_layers)
                fill_pct = 100.0 if sim.is_completed else min(99.9, (completed / max(1, total_layers)) * 100.0)

                if not sim.is_completed and sim.current_layer_idx < total_layers:
                    counter_text = f"Layer: {completed + 1}/{total_layers}   •   Fill: {fill_pct:4.1f}%   •   Bounce: {sim.bounces_in_layer}/{sim.target_bounces}"
                else:
                    counter_text = f"Layers: {completed}/{total_layers}   •   Fill: 100.0%"

                counter_shadow = font_stats.render(counter_text, True, (0, 0, 0))
                counter_surf = font_stats.render(counter_text, True, COLOR_ACCENT)
                counter_rect = counter_surf.get_rect(center=(BASE_WIDTH // 2, 136))
                base_surface.blit(counter_shadow, (counter_rect.x + 1, counter_rect.y + 1))
                base_surface.blit(counter_surf, counter_rect)

            # Completion Banner
            if sim.is_completed:
                pulse_val = (math.sin(sim.pulse_phase * 2.0) + 1.0) * 0.5
                banner_color = (
                    int(220 + 35 * pulse_val),
                    int(230 + 25 * pulse_val),
                    255
                )
                banner_surf = font_banner.render("CIRCLE COMPLETED!", True, banner_color)
                banner_rect = banner_surf.get_rect(center=(BASE_WIDTH // 2, CENTER_Y - OUTER_RADIUS - 30))
                base_surface.blit(banner_surf, banner_rect)

            # Paused Overlay
            if sim.paused:
                pause_surf = font_banner.render("PAUSED", True, (255, 230, 100))
                pause_rect = pause_surf.get_rect(center=(BASE_WIDTH // 2, CENTER_Y))
                base_surface.blit(pause_surf, pause_rect)

            # Watermark (@satisfylab_fx at y = HEIGHT - 80)
            wm_text = "@satisfylab_fx"
            wm_surf = font_watermark.render(wm_text, True, COLOR_TEXT_MUTED)
            wm_rect = wm_surf.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 80))
            base_surface.blit(wm_surf, wm_rect)

            # Keyboard Controls Hint (y = HEIGHT - 45)
            stats_status = "Stats ON" if config.is_stats_enabled() else "Stats OFF"
            status_audio = "Muted" if sim.muted else "Audio ON"
            hint_text = f"O: Options | H: {stats_status} | SPACE: Pause | R: Reset | G: {sim.gravity:.2f} | M: {status_audio}"
            hint_surf = font_hints.render(hint_text, True, COLOR_TEXT_HINT)
            hint_rect = hint_surf.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 45))
            base_surface.blit(hint_surf, hint_rect)

            # Video Recording Indicator
            if recording:
                rec_text = "● REC"
                rec_surf = font_stats.render(rec_text, True, (255, 60, 60))
                base_surface.blit(rec_surf, (BASE_WIDTH - 85, 25))

        # -------------------------------------------------------------------
        # Screen Shake & Blit to Window
        # -------------------------------------------------------------------
        shake_x = 0
        shake_y = 0
        if app_state == "SIMULATION" and sim.screen_shake > 0:
            shake_x = int(random.uniform(-sim.screen_shake, sim.screen_shake) * SCALE_FACTOR)
            shake_y = int(random.uniform(-sim.screen_shake, sim.screen_shake) * SCALE_FACTOR)

        if SCALE_FACTOR == 1:
            window.fill(COLOR_BG)
            window.blit(base_surface, (shake_x, shake_y))
        else:
            scaled_surf = pygame.transform.smoothscale(base_surface, (window_width, window_height))
            window.fill(COLOR_BG)
            window.blit(scaled_surf, (shake_x, shake_y))

        # Frame recording
        if recording and app_state == "SIMULATION":
            frame_path = os.path.join(record_dir, f"frame_{record_frame_count:05d}.png")
            pygame.image.save(window, frame_path)
            record_frame_count += 1

        pygame.display.flip()
        clock.tick(TARGET_FPS)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
