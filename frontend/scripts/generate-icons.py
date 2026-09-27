#!/usr/bin/env python3
"""アプリアイコンを1枚の元画像から全サイズ生成する。

    python3 frontend/scripts/generate-icons.py [元画像]

元画像は既定で frontend/assets/icon-only.png（1024x1024）。差し替えたら
これを流せば、PWA・ホーム画面・ブラウザのタブ・iOS のアプリアイコンが
まとめて更新される。

Pillow が要る。バックエンドの仮想環境に入っているのでそれを使うとよい:

    backend/.venv/bin/python frontend/scripts/generate-icons.py
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "assets" / "icon-only.png"

# マスカブルアイコンは端末側で円などに切り抜かれる。中央のこの割合（安全領域）
# に絵を収め、外側は地色で埋める。
MASKABLE_SAFE_RATIO = 0.8

# 角丸込みの絵をそのまま縮小して置くもの。
PLAIN = [
    (192, ROOT / "public" / "icons" / "icon-192.png"),
    (512, ROOT / "public" / "icons" / "icon-512.png"),
    (180, ROOT / "public" / "icons" / "apple-touch-icon.png"),
    (48, ROOT / "public" / "favicon-48.png"),
    (32, ROOT / "public" / "favicon-32.png"),
]

MASKABLE = (512, ROOT / "public" / "icons" / "icon-maskable-512.png")

# iOS のアプリアイコンは透過不可。角丸は OS 側が付けるので元画像のまま。
IOS_ICON = (
    1024,
    ROOT / "ios" / "App" / "App" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-512@2x.png",
)


def main(argv):
    source_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE
    if not source_path.exists():
        raise SystemExit(f"元画像が見つかりません: {source_path}")

    source = Image.open(source_path).convert("RGB")
    if source.width != source.height:
        raise SystemExit(f"元画像は正方形にしてください（いまは {source.size}）")

    for size, path in PLAIN:
        path.parent.mkdir(parents=True, exist_ok=True)
        source.resize((size, size), Image.LANCZOS).convert("RGBA").save(path, "PNG")
        print(f"{path.relative_to(ROOT)}  {size}x{size}")

    size, path = MASKABLE
    background = source.getpixel((6, 6))  # 角の色＝アイコンの地色
    canvas = Image.new("RGB", (size, size), background)
    inner = source.resize(
        (int(size * MASKABLE_SAFE_RATIO), int(size * MASKABLE_SAFE_RATIO)), Image.LANCZOS
    )
    canvas.paste(inner, ((size - inner.width) // 2, (size - inner.height) // 2))
    canvas.convert("RGBA").save(path, "PNG")
    print(f"{path.relative_to(ROOT)}  {size}x{size} (maskable)")

    size, path = IOS_ICON
    path.parent.mkdir(parents=True, exist_ok=True)
    source.resize((size, size), Image.LANCZOS).save(path, "PNG")
    print(f"{path.relative_to(ROOT)}  {size}x{size} (不透明)")


if __name__ == "__main__":
    main(sys.argv)
