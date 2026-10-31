"""Draw the per-board pin maps used in docs/PINMAP.md (docs/images/pinmap_*.svg).

The CH552G (SOP-16) is drawn as seen from the top: pins 1-8 down the left
side, 16-9 down the right side, each with what it is wired to on the board.

Run from the repo root:  gui\\.venv\\Scripts\\python tools\\draw_pinmap.py
"""
from __future__ import annotations

from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"

# Kind of each connection -> (fill, stroke)
COLORS = {
    "key": ("#e3f2fd", "#1e88e5"),
    "boot": ("#fff3e0", "#fb8c00"),
    "knob": ("#e8f5e9", "#43a047"),
    "led": ("#fce4ec", "#d81b60"),
    "usb": ("#ede7f6", "#5e35b1"),
    "power": ("#f5f5f5", "#9e9e9e"),
    "none": ("#ffffff", "#bdbdbd"),
}

# pin -> (GPIO name, connection, kind); the same on both boards
PINS = {
    1: ("P3.2", "키 F · 슬롯 5", "key"),
    2: ("P1.4", "키 E · 슬롯 4", "key"),
    3: ("P1.5", "키 D · 슬롯 3 (부트로더 진입)", "boot"),
    4: ("P1.6", "키 C · 슬롯 2", "key"),
    5: ("P1.7", "키 B · 슬롯 1", "key"),
    6: ("RST", "연결 없음", "none"),
    7: ("P3.1", "노브 인코더 B", "knob"),
    8: ("P3.0", "노브 인코더 A", "knob"),
    9: ("P1.1", "키 A · 슬롯 0", "key"),
    10: ("P3.3", "노브 누르기 · 슬롯 8", "knob"),
    11: ("P3.4", "LED 데이터", "led"),
    12: ("P3.6", "USB D+", "usb"),
    13: ("P3.7", "USB D−", "usb"),
    14: ("GND", "GND", "power"),
    15: ("VCC", "5V (USB)", "power"),
    16: ("V33", "3.3V", "power"),
}

FONT = "Malgun Gothic, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
PITCH = 46                 # distance between pins
TOP = 90                   # first pin row
CHIP_X, CHIP_W = 300, 220  # chip body
BOX_W, BOX_H = 230, 32     # connection boxes
STUB = 18                  # pin length outside the body


def row_y(pin: int) -> int:
    """Pins 1-8 top to bottom on the left, 16-9 top to bottom on the right."""
    index = pin - 1 if pin <= 8 else 16 - pin
    return TOP + index * PITCH


def box(x: float, y: float, text: str, kind: str, w: float = BOX_W) -> str:
    fill, stroke = COLORS[kind]
    return (f'<rect x="{x}" y="{y - BOX_H / 2}" width="{w}" height="{BOX_H}" rx="6" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            f'<text x="{x + w / 2}" y="{y + 5}" text-anchor="middle" font-size="14">{escape(text)}</text>')


def draw(board: str, title: str, led_text: str, chain: list[str] | None) -> str:
    width = 1060 if chain else 820
    height = TOP + 8 * PITCH + 70
    chip_left, chip_right = CHIP_X, CHIP_X + CHIP_W
    chip_top, chip_bottom = TOP - 30, TOP + 7 * PITCH + 30
    left_box_x = chip_left - STUB - 40 - BOX_W
    right_box_x = chip_right + STUB + 40
    parts = [
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="32" text-anchor="middle" font-size="20" font-weight="bold">{escape(title)}</text>',
        # chip body with the pin 1 notch
        f'<rect x="{chip_left}" y="{chip_top}" width="{CHIP_W}" height="{chip_bottom - chip_top}" rx="8" '
        'fill="#37474f" stroke="#263238" stroke-width="2"/>',
        # notch at the top edge; pin 1 is the first pin left of it
        f'<path d="M {chip_left + CHIP_W / 2 - 16} {chip_top} a 16 16 0 0 0 32 0" fill="#ffffff"/>',
        f'<text x="{chip_left + CHIP_W / 2}" y="{(chip_top + chip_bottom) / 2 - 6}" text-anchor="middle" '
        'font-size="22" font-weight="bold" fill="#ffffff">CH552G</text>',
        f'<text x="{chip_left + CHIP_W / 2}" y="{(chip_top + chip_bottom) / 2 + 18}" text-anchor="middle" '
        'font-size="13" fill="#cfd8dc">SOP-16 · 윗면</text>',
    ]
    for pin, (gpio, text, kind) in PINS.items():
        y = row_y(pin)
        left = pin <= 8
        if pin == 11:
            text = led_text
        pin_x = chip_left - STUB if left else chip_right
        parts.append(f'<rect x="{pin_x}" y="{y - 6}" width="{STUB}" height="12" fill="#b0bec5" stroke="#78909c"/>')
        # pin number and name inside the body
        if left:
            parts.append(f'<text x="{chip_left + 10}" y="{y + 5}" font-size="14" fill="#ffffff">'
                         f'<tspan font-weight="bold">{pin}</tspan>  {gpio}</text>')
            line_from, line_to = left_box_x + BOX_W, chip_left - STUB
        else:
            parts.append(f'<text x="{chip_right - 10}" y="{y + 5}" text-anchor="end" font-size="14" fill="#ffffff">'
                         f'{gpio}  <tspan font-weight="bold">{pin}</tspan></text>')
            line_from, line_to = chip_right + STUB, right_box_x
        dash = ' stroke-dasharray="4 4"' if kind == "none" else ""
        parts.append(f'<line x1="{line_from}" y1="{y}" x2="{line_to}" y2="{y}" stroke="{COLORS[kind][1]}" '
                     f'stroke-width="2"{dash}/>')
        parts.append(box(left_box_x if left else right_box_x, y, text, kind))

    if chain:
        # the WS2812 chain, fed from pin 11, one LED per key
        x = right_box_x + BOX_W + 50
        w = 150
        ys = [row_y(16) + i * PITCH for i in range(len(chain))]
        start_y = row_y(11)
        parts.append(f'<path d="M {right_box_x + BOX_W} {start_y} H {x - 25} V {ys[0]} H {x}" fill="none" '
                     f'stroke="{COLORS["led"][1]}" stroke-width="2" marker-end="url(#arrow)"/>')
        for i, (y, text) in enumerate(zip(ys, chain)):
            parts.append(box(x, y, text, "led", w))
            if i:
                parts.append(f'<line x1="{x + w / 2}" y1="{ys[i - 1] + BOX_H / 2}" x2="{x + w / 2}" '
                             f'y2="{y - BOX_H / 2}" stroke="{COLORS["led"][1]}" stroke-width="2" '
                             'marker-end="url(#arrow)"/>')
        parts.append(f'<text x="{x + w / 2}" y="{ys[-1] + 40}" text-anchor="middle" font-size="12" '
                     f'fill="#616161">데이터 순서: 0 → 5</text>')

    legend = [("key", "키"), ("boot", "키 + 부트로더 진입"), ("knob", "노브"), ("led", "LED"),
              ("usb", "USB"), ("power", "전원")]
    lx = 20
    for kind, label in legend:
        fill, stroke = COLORS[kind]
        parts.append(f'<rect x="{lx}" y="{height - 30}" width="16" height="16" rx="3" fill="{fill}" stroke="{stroke}"/>')
        parts.append(f'<text x="{lx + 22}" y="{height - 17}" font-size="13">{label}</text>')
        lx += 46 + sum(14 if ord(c) > 127 else 8 for c in label)   # Hangul is about twice as wide
    parts.append(f'<text x="{width - 20}" y="{height - 17}" text-anchor="end" font-size="12" fill="#757575">'
                 f'{board} · tools/draw_pinmap.py</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="{FONT}" fill="#212121">'
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{COLORS["led"][1]}"/></marker></defs>'
            + "".join(parts) + "</svg>\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "pinmap_mk6k1n.svg": draw("MK6K1N", "MK6K1N 핀 배치 (6키 + 노브, LED 1개)",
                                  "WS2812 LED 1개 (GRB)", None),
        "pinmap_mk6k1nl.svg": draw("MK6K1NL", "MK6K1NL 핀 배치 (6키 + 노브, 키마다 LED)",
                                   "LED 체인 데이터 (GRB) →",
                                   [f"LED {i} · 키 {k} 아래" for i, k in enumerate("ABCDEF")]),
    }
    for name, svg in files.items():
        (OUT / name).write_text(svg, encoding="utf-8")
        print(name)


if __name__ == "__main__":
    main()
