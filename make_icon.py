# -*- coding: utf-8 -*-
"""生成程序图标 assets/icon.ico：紫蓝渐变圆角方块 + "3:2" 字样。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "assets" / "icon.ico"


def rounded_gradient(size: int) -> Image.Image:
    """画一个圆角渐变方块（紫→蓝，左上到右下）。"""
    scale = 4  # 超采样，缩回后边缘平滑
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 逐行插值生成渐变
    grad = Image.new("RGBA", (s, s))
    c1, c2 = (123, 92, 255), (62, 139, 255)
    px = grad.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * s - 2)
            px[x, y] = (round(c1[0] + (c2[0] - c1[0]) * t),
                        round(c1[1] + (c2[1] - c1[1]) * t),
                        round(c1[2] + (c2[2] - c1[2]) * t), 255)

    mask = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask)
    radius = round(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # 顶部内侧高光，增加质感
    hi = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dh = ImageDraw.Draw(hi)
    dh.rounded_rectangle([s * 0.08, s * 0.05, s * 0.92, s * 0.5],
                         radius=round(s * 0.10), fill=(255, 255, 255, 36))
    img = Image.alpha_composite(img, hi)
    return img.resize((size, size), Image.LANCZOS)


def add_text(img: Image.Image, size: int) -> Image.Image:
    d = ImageDraw.Draw(img)
    text = "3:2"
    font = None
    for name in ("segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(f"C:/Windows/Fonts/{name}",
                                      round(size * 0.42))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1] - size * 0.02),
           text, font=font, fill=(255, 255, 255, 255))
    return img


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = []
    for s in sizes:
        img = rounded_gradient(s)
        if s >= 32:
            img = add_text(img, s)
        imgs.append(img)
    imgs[-1].save(OUT, format="ICO", sizes=[(s, s) for s in sizes],
                  append_images=imgs[:-1])
    print(f"图标已生成: {OUT}")


if __name__ == "__main__":
    main()
