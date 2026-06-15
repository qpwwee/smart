#!/usr/bin/env python3
"""Generate a PNG icon for Smart Greenhouse Monitoring System."""

from PIL import Image, ImageDraw
import math

SIZE = 512
BG_COLOR = (13, 17, 23)        # #0d1117
GREEN = (63, 185, 80)          # #3fb950
BLUE = (88, 166, 255)          # #58a6ff
CORNER_RADIUS = 96

def rounded_rect_mask(size, radius):
    """Create a rounded rectangle alpha mask."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (size[0]-1, size[1]-1)], radius=radius, fill=255)
    return mask

def draw_leaf(draw, cx, cy, scale=1.0):
    """Draw a stylized leaf shape using ellipses and lines."""
    # Main leaf body - an ellipse rotated conceptually
    # We'll approximate with a polygon for a leaf shape
    s = scale

    # Leaf outline as a polygon (pointed at top and bottom)
    points = []
    num_pts = 64
    for i in range(num_pts):
        t = 2 * math.pi * i / num_pts
        # Parametric leaf shape
        x = 40 * s * math.sin(t)
        y = -70 * s * math.cos(t) + 20 * s * math.cos(2 * t)
        points.append((cx + x, cy + y))

    draw.polygon(points, fill=GREEN)

    # Leaf vein (center line)
    draw.line([(cx, cy - 80 * s), (cx, cy + 50 * s)], fill=(30, 120, 50), width=max(1, int(3 * s)))

    # Side veins
    for offset in [-40, -20, 0, 20]:
        vy = cy + offset * s
        # Left vein
        draw.line([(cx, vy), (cx - 20 * s, vy - 15 * s)], fill=(30, 120, 50), width=max(1, int(2 * s)))
        # Right vein
        draw.line([(cx, vy), (cx + 20 * s, vy - 15 * s)], fill=(30, 120, 50), width=max(1, int(2 * s)))

def draw_stem(draw, cx, cy, scale=1.0):
    """Draw a simple stem below the leaf."""
    s = scale
    # Stem
    draw.line([(cx, cy + 50 * s), (cx, cy + 110 * s)], fill=GREEN, width=max(1, int(6 * s)))
    # Small side leaves at the base
    # Left small leaf
    pts_l = [
        (cx, cy + 90 * s),
        (cx - 25 * s, cy + 75 * s),
        (cx - 20 * s, cy + 95 * s),
    ]
    draw.polygon(pts_l, fill=GREEN)
    # Right small leaf
    pts_r = [
        (cx, cy + 90 * s),
        (cx + 25 * s, cy + 75 * s),
        (cx + 20 * s, cy + 95 * s),
    ]
    draw.polygon(pts_r, fill=GREEN)

def draw_signal_arcs(draw, cx, cy, radius, color, width, num_arcs=3, arc_span=60):
    """Draw concentric arc segments (signal waves) around the center."""
    for i in range(num_arcs):
        r = radius + i * 28
        # Draw arc on top-right and top-left (like WiFi signal)
        # We'll draw arcs at top-left and top-right
        bbox = [cx - r, cy - r, cx + r, cy + r]

        # Top-left arc (from 200 to 250 degrees roughly)
        start1 = 200 + i * 5
        end1 = 250 - i * 5
        draw.arc(bbox, start=start1, end=end1, fill=color, width=width)

        # Top-right arc (from 290 to 340 degrees roughly)
        start2 = 290 + i * 5
        end2 = 340 - i * 5
        draw.arc(bbox, start=start2, end=end2, fill=color, width=width)

def main():
    # Create RGBA image
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Draw background with rounded corners
    bg = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    bg_draw.rounded_rectangle([(0, 0), (SIZE-1, SIZE-1)], radius=CORNER_RADIUS, fill=BG_COLOR + (255,))

    img = bg.copy()
    draw = ImageDraw.Draw(img)

    center_x = SIZE // 2
    center_y = SIZE // 2 + 10  # slightly below center for visual balance

    # Draw signal arcs (Zigbee/wireless waves) behind the plant
    # Top arcs
    arc_radius = 140
    for i in range(3):
        r = arc_radius + i * 32
        bbox = [center_x - r, center_y - 30 - r, center_x + r, center_y - 30 + r]
        # Left arc
        draw.arc(bbox, start=200, end=260, fill=BLUE, width=5)
        # Right arc
        draw.arc(bbox, start=280, end=340, fill=BLUE, width=5)

    # Draw the plant (leaf + stem)
    draw_leaf(draw, center_x, center_y - 30, scale=1.3)
    draw_stem(draw, center_x, center_y - 30, scale=1.3)

    # Apply rounded corner mask
    mask = rounded_rect_mask((SIZE, SIZE), CORNER_RADIUS)
    img.putalpha(mask)

    output_path = "/Users/pon/Desktop/ject/SmartGreenhouse_已修复/icon.png"
    img.save(output_path, "PNG")
    print(f"Icon saved to: {output_path}")
    print(f"Size: {img.size}")

if __name__ == "__main__":
    main()
