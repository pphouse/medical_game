#!/usr/bin/env python3
"""アプリアイコンからキャラクター（フクロウ）だけを切り出す。

    backend/.venv/bin/python frontend/scripts/extract-character.py

元画像は frontend/assets/icon-only.png。背景の青いカードと影を透過に
落とし、frontend/assets/character.png（原寸）と
frontend/src/assets/character.png（アプリで使う縮小版）を書き出す。

アイコンを差し替えたらこれを流し直す。手作業で切り抜くと、次に
アイコンを描き直したときに同じ手順を再現できない。

Pillow が要る。バックエンドの仮想環境に入っているのでそれを使う。
"""

import sys
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets/icon-only.png"
FULL_OUT = ROOT / "assets/character.png"
APP_OUT = ROOT / "src/assets/character.png"
# アプリでは最大でも 130px 角ほどでしか出さない。高解像度の端末を考えて
# 3倍の幅までにしておく（原寸のままだと 500KB を超える）。
APP_WIDTH = 400

# 隣り合う画素の色差がこれを超えたら、背景は続いていないとみなす。
# グラデーションのかかった背景を追うために、絶対値ではなく差で見る。
TOLERANCE = 60


def is_background(p):
    """背景（青いカードとその縁・影、カードの外の白）かどうか。

    フクロウの輪郭線も青みがかった暗色だが、そちらは緑成分が青成分に近い
    （b-g が小さい）ので、この条件には当たらない。
    """
    r, g, b = p[0], p[1], p[2]
    if b - r > 55 and b - g > 35:
        return True
    return r > 235 and g > 235 and b > 235


def flood_from_border(px, w, h):
    """画像の縁から背景をたどって塗りつぶし、その印を返す。"""
    bg = bytearray(w * h)
    queue = deque()

    def seed(x, y):
        i = y * w + x
        if not bg[i] and is_background(px[x, y]):
            bg[i] = 1
            queue.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while queue:
        x, y = queue.popleft()
        c = px[x, y]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            i = ny * w + nx
            if bg[i]:
                continue
            n = px[nx, ny]
            if not is_background(n):
                continue
            if abs(n[0] - c[0]) + abs(n[1] - c[1]) + abs(n[2] - c[2]) > TOLERANCE:
                continue
            bg[i] = 1
            queue.append((nx, ny))
    return bg


def largest_blob(bg, w, h):
    """背景でない画素のうち、いちばん大きいひと塊を返す。

    カードの角のアンチエイリアスが縁の塗りつぶしから取り残されて、
    切れ端として残る。キャラクターは1つながりなので、最大の塊だけを採る。
    """
    seen = bytearray(w * h)
    best = []
    for sy in range(h):
        for sx in range(w):
            if bg[sy * w + sx] or seen[sy * w + sx]:
                continue
            blob = []
            queue = deque([(sx, sy)])
            seen[sy * w + sx] = 1
            while queue:
                x, y = queue.popleft()
                blob.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < w and 0 <= ny < h):
                        continue
                    i = ny * w + nx
                    if bg[i] or seen[i]:
                        continue
                    seen[i] = 1
                    queue.append((nx, ny))
            if len(blob) > len(best):
                best = blob
    return best


def main(argv):
    source = Path(argv[1]) if len(argv) > 1 else SOURCE
    image = Image.open(source).convert("RGBA")
    w, h = image.size
    px = image.load()

    bg = flood_from_border(px, w, h)
    keep = bytearray(w * h)
    for x, y in largest_blob(bg, w, h):
        keep[y * w + x] = 1

    out = image.copy()
    opx = out.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            if not keep[row + x]:
                opx[x, y] = (0, 0, 0, 0)

    cropped = out.crop(out.getbbox())
    FULL_OUT.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(FULL_OUT)

    scale = APP_WIDTH / cropped.width
    small = cropped.resize(
        (APP_WIDTH, round(cropped.height * scale)), Image.LANCZOS
    )
    # 色数を絞ってからPNGにする。フルカラーのままだと 500KB を超え、
    # 初回表示のために毎回それだけ落とすことになる。
    small = small.quantize(colors=128, method=Image.FASTOCTREE).convert("RGBA")
    APP_OUT.parent.mkdir(parents=True, exist_ok=True)
    small.save(APP_OUT, optimize=True)

    print(f"{FULL_OUT.relative_to(ROOT.parent)}  {cropped.width}x{cropped.height}")
    print(f"{APP_OUT.relative_to(ROOT.parent)}  {small.width}x{small.height}")


if __name__ == "__main__":
    main(sys.argv)
