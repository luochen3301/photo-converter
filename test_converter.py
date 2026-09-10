# -*- coding: utf-8 -*-
"""converter.py 自动化测试：生成各类测试图片并验证转换行为。

运行：python test_converter.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

import converter
from converter import (crop_to_target_ratio, flatten_alpha, is_target_ratio,
                       natural_key, plan_rename, scan_folder, unique_path,
                       convert_one)

TMP = Path(tempfile.mkdtemp(prefix="imgconv_test_"))
PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [通过] {name}")
    else:
        FAIL += 1
        print(f"  [失败] {name}  {detail}")


def make_png(path, w, h, mode="RGB", color="red"):
    img = Image.new(mode, (w, h), color)
    img.save(path, "PNG")
    return path


print("== 1. 比例判断 ==")
check("6000x4000 是 3:2", is_target_ratio(6000, 4000))
check("4000x6000 竖版是 3:2", is_target_ratio(4000, 6000))
check("4:3 不是 3:2", not is_target_ratio(4000, 3000))
check("16:9 不是 3:2", not is_target_ratio(1920, 1080))
check("1:1 不是 3:2", not is_target_ratio(3000, 3000))

print("== 2. 居中裁剪 ==")
img = Image.new("RGB", (4000, 3000))            # 4:3 横图
out = crop_to_target_ratio(img)
check("4:3 横图 → 3:2", out.size == (4000, 2667), f"got {out.size}")
img = Image.new("RGB", (3000, 4000))            # 4:3 竖图
out = crop_to_target_ratio(img)
check("4:3 竖图 → 2:3", out.size == (2667, 4000), f"got {out.size}")
img = Image.new("RGB", (1920, 1080))            # 16:9
out = crop_to_target_ratio(img)
check("16:9 → 3:2", out.size == (1620, 1080), f"got {out.size}")
img = Image.new("RGB", (6000, 4000))            # 已是 3:2
out = crop_to_target_ratio(img)
check("3:2 原样保留", out.size == (6000, 4000), f"got {out.size}")
img = Image.new("RGB", (3000, 3000))            # 方图
out = crop_to_target_ratio(img)
check("方图 → 3:2 横版", out.size == (3000, 2000), f"got {out.size}")

print("== 3. 自然排序与重命名 ==")
check("IMG2 < IMG10", natural_key("IMG2.jpg") < natural_key("IMG10.jpg"))
files = [TMP / "IMG10.png", TMP / "IMG2.png", TMP / "b1.jpg"]
plan = plan_rename(files, "DSC", 3500, 5)
names = [n for _, n in plan]
check("按自然排序编号", names == ["DSC03500.jpg", "DSC03501.jpg", "DSC03502.jpg"],
      f"got {names}")
plan2 = plan_rename([TMP / "a.png"], "IMG", 42, 4)
check("自定义位数补零", plan2[0][1] == "IMG0042.jpg", f"got {plan2[0][1]}")

print("== 4. 透明垫白 ==")
rgba = Image.new("RGBA", (300, 200), (255, 0, 0, 0))   # 全透明
flat = flatten_alpha(rgba)
check("RGBA 转 RGB", flat.mode == "RGB")
check("透明区垫白", flat.getpixel((0, 0)) == (255, 255, 255))

print("== 5. 文件名防覆盖 ==")
target = TMP / "dup.jpg"
target.write_bytes(b"x")
u = unique_path(target)
check("重名追加后缀", u.name == "dup_1.jpg", f"got {u.name}")
check("不重名原样返回", unique_path(TMP / "ok.jpg").name == "ok.jpg")

print("== 6. 单张转换（端到端）==")
make_png(TMP / "photo1.png", 4000, 3000)                       # 4:3 RGB PNG
r = convert_one(TMP / "photo1.png", "JPG输出", "DSC03500.jpg", 95)
check("转换成功", r.ok, r.error)
check("输出为 JPG", r.dst.suffix.lower() == ".jpg" and r.dst.exists())
with Image.open(r.dst) as im:
    check("输出尺寸 3:2", is_target_ratio(*im.size), f"got {im.size}")
    check("输出格式 JPEG", im.format == "JPEG")
check("输出在子文件夹", r.dst.parent.name == "JPG输出")

# 透明 PNG
tp = Image.new("RGBA", (1500, 3000), (200, 30, 30, 128))
tp.save(TMP / "alpha.png", "PNG")
r = convert_one(TMP / "alpha.png", "JPG输出", "DSC03501.jpg", 95)
with Image.open(r.dst) as im:
    check("透明 PNG 输出 RGB", im.mode == "RGB" and is_target_ratio(*im.size))

# 已是 3:2 的 JPG 输入，尺寸不变
make_png(TMP / "ready.jpg", 6000, 4000)  # Pillow 按后缀存成 JPEG
r = convert_one(TMP / "ready.jpg", "JPG输出", "DSC03502.jpg", 95)
with Image.open(r.dst) as im:
    check("3:2 JPG 尺寸不变", im.size == (6000, 4000), f"got {im.size}")

# EXIF 方向：orientation=6（顺时针 90°），4000x3000 应摆正为竖版再裁剪
exif_img = Image.new("RGB", (4000, 3000), "blue")
exif = Image.Exif()
exif[274] = 6
exif_img.save(TMP / "rotated.jpg", exif=exif)
r = convert_one(TMP / "rotated.jpg", "JPG输出", "DSC03503.jpg", 95)
with Image.open(r.dst) as im:
    check("EXIF 摆正后为竖版 3:2",
          im.size[1] > im.size[0] and is_target_ratio(*im.size), f"got {im.size}")

# 重复运行同名 → 自动 _1，不覆盖
r1 = convert_one(TMP / "photo1.png", "JPG输出", "DSC03600.jpg", 95)
r2 = convert_one(TMP / "photo1.png", "JPG输出", "DSC03600.jpg", 95)
check("重复转换不覆盖", r1.dst.exists() and r2.dst.exists() and r1.dst != r2.dst,
      f"{r1.dst.name} / {r2.dst.name}")

# 损坏文件 → 报错但不抛异常
(TMP / "bad.png").write_bytes(b"not an image")
r = convert_one(TMP / "bad.png", "JPG输出", "DSC09999.jpg", 95)
check("损坏文件返回失败", not r.ok and r.error)

print("== 7. 文件夹扫描 ==")
check("扫描到 6 个图片（不含损坏与输出）",
      len(scan_folder(TMP)) == 6, f"got {len(scan_folder(TMP))}")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n结果：{PASS} 通过，{FAIL} 失败")
sys.exit(1 if FAIL else 0)
