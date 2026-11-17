"""Deterministic scan simulation: rasterise a PDF page and degrade it like an office scan.

Rotation, blur, low contrast, sensor noise, speckle and JPEG artefacts, all seeded.
Needs the ``synthetic`` extra (pypdfium2, pillow, numpy).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScanNoise:
    dpi: int
    max_angle: float  # degrees, uniform in [-max, max]
    blur: float  # Gaussian blur radius in pixels
    contrast: float  # 1.0 = black ink stays black
    sigma: float  # Gaussian sensor noise (grey levels)
    speckle: float  # share of pixels flipped to black or white
    jpeg_quality: int


NOISE_LEVELS: dict[str, ScanNoise] = {
    "light": ScanNoise(
        dpi=200, max_angle=0.8, blur=0.5, contrast=0.92, sigma=8, speckle=0, jpeg_quality=70
    ),
    "heavy": ScanNoise(
        dpi=150, max_angle=2.0, blur=0.9, contrast=0.72, sigma=22, speckle=0.004, jpeg_quality=35
    ),
}


def simulate_scan(page: Any, noise: ScanNoise, seed: int) -> bytes:
    """Rasterise a PDF page and degrade it like a cheap office scan; returns JPEG bytes."""
    import numpy as np
    from PIL import Image, ImageFilter

    rng = np.random.default_rng(seed)
    image = page.render(scale=noise.dpi / 72, grayscale=True).to_pil().convert("L")
    angle = float(rng.uniform(-noise.max_angle, noise.max_angle))
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
    if noise.blur:
        image = image.filter(ImageFilter.GaussianBlur(noise.blur))
    pixels = np.asarray(image, dtype=np.float32)
    pixels = 245 - (245 - pixels) * noise.contrast  # grey ink on slightly grey paper
    pixels += rng.normal(0.0, noise.sigma, pixels.shape)
    if noise.speckle:
        mask = rng.random(pixels.shape) < noise.speckle
        pixels[mask] = rng.choice(np.array([0.0, 255.0], dtype=np.float32), size=int(mask.sum()))
    out = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), mode="L")
    buffer = io.BytesIO()
    out.save(buffer, format="JPEG", quality=noise.jpeg_quality)
    return buffer.getvalue()
