# -*- coding: utf-8 -*-
"""图片转换核心逻辑：PNG→JPG、3:2 居中裁剪、批量重命名。

本模块不依赖任何界面代码，可单独导入和测试。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

# 支持的输入格式（统一输出 JPG）
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}

# 目标比例：长边:短边 = 3:2（横图 3:2、竖图 2:3）
TARGET_RATIO = 3.0 / 2.0
# 相对容差：偏差 1% 以内视为已符合 3:2，不再裁剪
RATIO_TOLERANCE = 0.01


@dataclass
class ConvertResult:
    """单张图片的转换结果。"""
    ok: bool
    src: Path
    dst: Path | None = None
    error: str = ""


def natural_key(name: str) -> list:
    """自然排序键，保证 IMG2 排在 IMG10 前面。"""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def scan_folder(folder: str | Path) -> list[Path]:
    """列出文件夹（不含子文件夹）内所有受支持的图片，按自然排序。"""
    folder = Path(folder)
    return sorted(
        (p for p in folder.iterdir()
         if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS),
        key=lambda p: natural_key(p.name),
    )


def is_target_ratio(w: int, h: int) -> bool:
    """判断尺寸是否已符合 3:2（自动适配横图/竖图）。"""
    if w <= 0 or h <= 0:
        return False
    ratio = max(w, h) / min(w, h)
    return abs(ratio - TARGET_RATIO) / TARGET_RATIO < RATIO_TOLERANCE


def crop_to_target_ratio(img: Image.Image) -> Image.Image:
    """居中裁剪到 3:2：横图裁左右、竖图裁上下。已符合则原样返回。"""
    w, h = img.size
    if is_target_ratio(w, h):
        return img
    if w >= h:
        # 横图/方图 → 目标 w:h = 3:2
        target_w, target_h = w, round(w * 2 / 3)
        if target_h > h:  # 高度不足，改为裁宽度
            target_h, target_w = h, round(h * 3 / 2)
    else:
        # 竖图 → 目标 w:h = 2:3
        target_w, target_h = w, round(w * 3 / 2)
        if target_h > h:  # 宽度不足，改为裁高度
            target_h, target_w = h, round(h * 2 / 3)
    left = (w - target_w) // 2
    top = (h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def flatten_alpha(img: Image.Image) -> Image.Image:
    """透明 PNG 垫白底转 RGB（JPG 不支持透明通道）。"""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def unique_path(path: Path) -> Path:
    """目标文件已存在时追加 _1/_2 后缀，绝不覆盖任何文件。"""
    if not path.exists():
        return path
    for i in range(1, 10000):
        cand = path.parent / f"{path.stem}_{i}{path.suffix}"
        if not cand.exists():
            return cand
    raise RuntimeError(f"无法为 {path.name} 生成不重名的文件名")


def plan_rename(files, prefix: str = "DSC", start: int = 3500, digits: int = 5):
    """按自然排序为文件分配新名字。

    返回 [(源文件, 新文件名), ...]，例如 DSC03500.jpg、DSC03501.jpg …
    """
    ordered = sorted(files, key=lambda p: natural_key(p.name))
    return [(p, f"{prefix}{start + i:0{digits}d}.jpg") for i, p in enumerate(ordered)]


def convert_one(src, subfolder: str = "JPG输出", new_name: str | None = None,
                quality: int = 95) -> ConvertResult:
    """转换单张图片：EXIF 摆正 → 3:2 居中裁剪 → 透明垫白 → 保存 JPG。

    输出到源文件所在文件夹的 subfolder 子文件夹内。
    单张失败抛出的异常会被捕获，不影响整批任务。
    """
    src = Path(src)
    try:
        out_dir = src.parent / subfolder
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = unique_path(out_dir / (new_name or (src.stem + ".jpg")))
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            im = crop_to_target_ratio(im)
            im = flatten_alpha(im)
            im.save(dst, "JPEG", quality=quality, optimize=True,
                    icc_profile=im.info.get("icc_profile"))
        return ConvertResult(True, src, dst)
    except Exception as e:  # noqa: BLE001 - 单张失败需整批继续
        return ConvertResult(False, src, error=str(e))
