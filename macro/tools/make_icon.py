"""Build the S2P-Joystick-Macro icon set from the 32 px pixel-art source.

Shrinking pixel art blurs it (the red dot loses its shape and the dark corner
outline collapses into a black dot), so small sizes are redrawn pixel by pixel
in the same style.  Sizes that are whole multiples of 32 are enlarged with
nearest-neighbour scaling and stay identical to the original artwork.

    python macro/tools/make_icon.py
"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "s2p_macro" / "assets"
OUTLINE = (63, 53, 47, 255)
HIGHLIGHT = (249, 248, 248, 255)
BODY = (208, 207, 208, 255)
SHADE = (161, 162, 163, 255)
RED_RIM = (150, 0, 0, 255)
RED = (240, 20, 20, 255)
RED_LIGHT = (255, 120, 110, 255)


def draw(size):
    """Redraw the button at ``size`` px: rounded frame plus a centred red dot."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    margin = max(0, round(size / 16) - 1)
    low, high = margin, size - 1 - margin
    cut = max(1, round(size / 10))  # diagonal corner cut, like the original

    def inside(x, y):
        if not (low <= x <= high and low <= y <= high):
            return False
        dx = min(x - low, high - x)
        dy = min(y - low, high - y)
        return dx + dy >= cut

    for y in range(size):
        for x in range(size):
            if not inside(x, y):
                continue
            edge = not all(inside(x + ox, y + oy) for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if edge:
                pixels[x, y] = OUTLINE
            elif not inside(x - 2, y) or not inside(x, y - 2):
                pixels[x, y] = HIGHLIGHT
            elif not inside(x + 2, y) or not inside(x, y + 2):
                pixels[x, y] = SHADE
            else:
                pixels[x, y] = BODY

    centre = (size - 1) / 2.0
    radius = size * 0.24
    for y in range(size):
        for x in range(size):
            distance = ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5
            if distance <= radius + 0.25:
                rim = distance > radius - 0.9
                pixels[x, y] = RED_RIM if rim else RED
    if size >= 24:  # small highlight towards the lower right, as in the original
        spot = round(centre + radius * 0.45)
        for dx, dy in ((0, 0), (-1, 0), (0, -1)):
            pixels[spot + dx, spot + dy] = RED_LIGHT
    return image


def main():
    source = Image.open(ASSETS / "icon.png").convert("RGBA")
    if source.size != (32, 32):
        raise SystemExit("icon.png must be the 32 px source artwork")
    clean = source.copy()
    data = clean.load()
    for y in range(32):
        for x in range(32):
            if data[x, y][3] == 0:
                data[x, y] = (0, 0, 0, 0)  # no hidden colour that could bleed

    frames = {size: draw(size) for size in (16, 20, 24, 40, 48)}
    for size in (32, 64, 128, 256):
        frames[size] = clean.resize((size, size), Image.Resampling.NEAREST)
    order = sorted(frames)
    frames[256].save(
        ASSETS / "icon.ico",
        sizes=[(size, size) for size in order],
        append_images=[frames[size] for size in order if size != 256],
    )
    for size in (16, 32, 64):
        frames[size].save(ASSETS / f"icon{size}.png")
    print("wrote", ", ".join(f"{size}px" for size in order))


if __name__ == "__main__":
    main()
