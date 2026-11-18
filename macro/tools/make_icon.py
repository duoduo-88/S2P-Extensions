"""Build the S2P-Joystick-Macro icon set from the 32 px pixel-art source.

Sizes that are whole multiples of 32 are nearest-neighbour enlargements, so
they match the artwork exactly.  Smaller and in-between sizes are plain
area-averaged shrinks of the same artwork (soft, but never redrawn).
Transparent pixels are cleared first and alpha is premultiplied while
shrinking, so no hidden colour bleeds into the corners as a dark dot.

    python macro/tools/make_icon.py
"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "s2p_macro" / "assets"


def load_source():
    source = Image.open(ASSETS / "icon.png").convert("RGBA")
    if source.size != (32, 32):
        raise SystemExit("icon.png must be the 32 px source artwork")
    data = source.load()
    for y in range(32):
        for x in range(32):
            if data[x, y][3] == 0:
                data[x, y] = (0, 0, 0, 0)
    return source


def shrink(source, size):
    return source.convert("RGBa").resize((size, size), Image.Resampling.BOX).convert("RGBA")


def main():
    source = load_source()
    frames = {size: shrink(source, size) for size in (16, 20, 24, 40, 48)}
    for size in (32, 64, 128, 256):
        frames[size] = source.resize((size, size), Image.Resampling.NEAREST)
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
