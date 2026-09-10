# -*- coding: utf-8 -*-
"""无头 UI 测试：验证「批量重命名」开关的两种模式端到端行为。

运行：python test_ui_toggle.py（无需显示环境）
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PIL import Image  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import main as appmod  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="ui_toggle_test_"))
FAILED = []


def check(name, cond, detail=""):
    print(f"  [{'通过' if cond else '失败'}] {name}" + ("" if cond else f"  {detail}"))
    if not cond:
        FAILED.append(name)


# 造测试图：一张需裁剪的 PNG、一张已是 3:2 的 JPG
Image.new("RGB", (1600, 1200), "tomato").save(TMP / "alpha.png", "PNG")
Image.new("RGB", (3000, 2000), "steelblue").save(TMP / "beta.jpg", "JPEG")

app = QApplication(sys.argv)
win = appmod.MainWindow()
win.add_paths([str(TMP / "alpha.png"), str(TMP / "beta.jpg")])

print("== 模式一：开启批量重命名（默认） ==")
check("开关默认开启", win.chk_rename.isChecked())
check("预览列显示 DSC 名", win.table.item(0, 4).text() == "→ DSC03500.jpg",
      win.table.item(0, 4).text())
check("前缀框可用", win.ed_prefix.isEnabled())

print("== 模式二：关闭批量重命名 ==")
win.chk_rename.setChecked(False)
check("前缀框被置灰", not win.ed_prefix.isEnabled())
check("起始序号被置灰", not win.sp_start.isEnabled())
check("位数被置灰", not win.sp_digits.isEnabled())
check("预览列显示原名", win.table.item(0, 4).text() == "→ alpha.jpg",
      win.table.item(0, 4).text())
check("提示文字已切换", "保留原文件名" in win.lb_tip.text())


def run_convert(timeout=30):
    win.start_convert()
    deadline = time.time() + timeout
    while win.converting and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    return not win.converting


check("转换完成", run_convert())
out = TMP / "JPG输出"
names = sorted(p.name for p in out.glob("*.jpg"))
check("输出保留原名", names == ["alpha.jpg", "beta.jpg"], str(names))

print("== 转回开启模式再次转换 ==")
win.chk_rename.setChecked(True)
check("前缀框恢复可用", win.ed_prefix.isEnabled())
check("预览列恢复 DSC 名", win.table.item(0, 4).text() == "→ DSC03500.jpg")
check("第二次转换完成", run_convert())
names = sorted(p.name for p in out.glob("*.jpg"))
check("DSC 与原名文件共存不覆盖",
      names == ["DSC03500.jpg", "DSC03501.jpg", "alpha.jpg", "beta.jpg"],
      str(names))
check("状态列显示成功", win.table.item(0, 5).text().startswith("✓"))

# 关闭重命名时改名框改动不影响方案
win.chk_rename.setChecked(False)
win.ed_prefix.setText("XYZ")  # 已置灰，不应生效
plan = win.current_plan()
check("置灰状态下方案仍用原名", plan[0][1] == "alpha.jpg", plan[0][1])

win.close()
print(f"\n结果：{'全部通过' if not FAILED else '失败项: ' + ', '.join(FAILED)}")
sys.exit(1 if FAILED else 0)
