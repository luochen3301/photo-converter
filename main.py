# -*- coding: utf-8 -*-
"""图片转换助手 —— PNG 转 JPG · 3:2 裁剪 · 批量重命名

现代深色界面（PyQt6）。核心逻辑见 converter.py。
"""
from __future__ import annotations

import os
import queue
import sys
from pathlib import Path

from PIL import Image, ImageOps
from PyQt6.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QIcon, QImage, QMouseEvent, QPixmap)
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                             QFileDialog, QFrame, QGraphicsDropShadowEffect,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMenu, QProgressBar, QPushButton, QSlider,
                             QSpinBox, QTableWidget, QTableWidgetItem,
                             QToolButton, QVBoxLayout, QWidget)

import converter
from converter import natural_key, plan_rename, scan_folder

# ---------------- 主题色 ----------------
BG = "#14161d"          # 窗口背景
CARD = "#1c1f29"        # 卡片背景
CARD2 = "#222633"       # 卡片内元素
BORDER = "#2c313f"      # 边框
TEXT = "#e9ebf2"        # 主文字
TEXT2 = "#8d93a6"       # 次要文字
ACCENT1 = "#7b5cff"     # 渐变起点（紫）
ACCENT2 = "#3e8bff"     # 渐变终点（蓝）
GREEN = "#3ecf8e"
AMBER = "#f5b54a"
RED = "#ff6b6b"

COL_COUNT = 6
COL_W = [64, 250, 105, 118, 185, 190]


def resource_path(rel: str) -> Path:
    """兼容开发环境与 PyInstaller 打包后的资源路径。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "")) / rel
    return Path(__file__).parent / rel


def _to_qimage(im: Image.Image) -> QImage:
    """PIL Image → QImage（深拷贝，线程安全）。"""
    im = im.convert("RGB")
    data = im.tobytes()
    return QImage(data, im.width, im.height, im.width * 3,
                  QImage.Format.Format_RGB888).copy()


# ---------------- 顶栏 ----------------
class TitleBar(QFrame):
    """无边框窗口的自定义标题栏：图标 + 标题 + 最小化/关闭。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(52)
        self._press_pos = None

        icon_lbl = QLabel()
        ico = resource_path("assets/icon.ico")
        if ico.exists():
            icon_lbl.setPixmap(QIcon(str(ico)).pixmap(QSize(28, 28)))
        else:  # 无图标文件时的占位圆点
            icon_lbl.setText("●")
            icon_lbl.setStyleSheet(f"color:{ACCENT1}; font-size:18px;")

        title = QLabel("图片转换助手")
        title.setStyleSheet(f"color:{TEXT}; font-size:15px; font-weight:600;")
        sub = QLabel("PNG → JPG · 3:2 · 批量改名")
        sub.setStyleSheet(f"color:{TEXT2}; font-size:11px;")

        self.btn_min = QToolButton()
        self.btn_min.setText("—")
        self.btn_close = QToolButton()
        self.btn_close.setText("✕")
        for b, hover in ((self.btn_min, "#2a2e3a"), (self.btn_close, "#e81123")):
            b.setFixedSize(40, 32)
            b.setStyleSheet(
                f"QToolButton{{border:none;border-radius:8px;color:{TEXT2};"
                f"font-size:{'11px' if b is self.btn_min else '10px'};}}"
                f"QToolButton:hover{{background:{hover};color:{TEXT};}}")
        self.btn_min.clicked.connect(self.window().showMinimized)
        self.btn_close.clicked.connect(self.window().close)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 8, 8)
        lay.setSpacing(10)
        lay.addWidget(icon_lbl)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addStretch(1)
        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_close)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._press_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._press_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(e)


# ---------------- 拖拽区 ----------------
class DropZone(QFrame):
    """拖入文件/文件夹，或点按钮选择。"""

    filesDropped = pyqtSignal(list)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(92)

        icon = QLabel("🖼")
        icon.setStyleSheet("font-size:26px; background:transparent; border:none;")
        center = QVBoxLayout()
        center.setSpacing(2)
        l1 = QLabel("拖拽图片或整个文件夹到此处")
        l1.setStyleSheet(f"color:{TEXT}; font-size:14px; font-weight:600; border:none;")
        l2 = QLabel("支持 PNG / JPG / JPEG，自动转为 JPG 并整理为 3:2")
        l2.setStyleSheet(f"color:{TEXT2}; font-size:11px; border:none;")
        center.addWidget(l1)
        center.addWidget(l2)

        self.btn_files = QPushButton("选择图片")
        self.btn_folder = QPushButton("选择文件夹")
        for b in (self.btn_files, self.btn_folder):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(38)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 12, 24, 12)
        lay.setSpacing(16)
        lay.addWidget(icon)
        lay.addLayout(center)
        lay.addStretch(1)
        lay.addWidget(self.btn_files)
        lay.addWidget(self.btn_folder)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setStyleSheet(self.styleSheet().replace(BORDER, ACCENT1))

    def dragLeaveEvent(self, e) -> None:
        self._reset_style()

    def dropEvent(self, e) -> None:
        self._reset_style()
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)

    def _reset_style(self) -> None:
        self.setStyleSheet("")  # 恢复全局 QSS 定义的样式


# ---------------- 信息加载线程（尺寸 + 缩略图） ----------------
class InfoWorker(QThread):
    """后台读取图片尺寸/比例/缩略图，避免大量文件时卡界面。"""

    infoReady = pyqtSignal(int, int, int, QImage)  # row, w, h, thumb

    def __init__(self):
        super().__init__()
        self._jobs: "queue.Queue[tuple[int, Path] | None]" = queue.Queue()

    def submit(self, row: int, path: Path) -> None:
        self._jobs.put((row, path))

    def stop(self) -> None:
        self._jobs.put(None)

    def run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            row, path = job
            try:
                with Image.open(path) as im:
                    # 先取缩略图再摆正方向，代价最小
                    thumb = im.copy()
                    thumb.thumbnail((120, 120))
                    thumb = ImageOps.exif_transpose(thumb)
                    w, h = im.size
                    if im.getexif().get(274) in (5, 6, 7, 8):
                        w, h = h, w  # EXIF 旋转后实际显示为竖版
                self.infoReady.emit(row, w, h, _to_qimage(thumb))
            except Exception:  # noqa: BLE001
                self.infoReady.emit(row, 0, 0, QImage())


# ---------------- 转换线程 ----------------
class ConvertWorker(QThread):
    itemDone = pyqtSignal(int, bool, str, str)  # row, ok, dst_name, error
    allDone = pyqtSignal(int, int, list)        # 成功数, 失败数, 输出文件夹列表

    def __init__(self, jobs: list[tuple[int, Path, str, int, str]]):
        super().__init__()
        self._jobs = jobs  # [(row, src, new_name, quality, subfolder)]

    def run(self) -> None:
        ok = fail = 0
        out_dirs: list[str] = []
        for row, src, name, quality, subfolder in self._jobs:
            r = converter.convert_one(src, subfolder, name, quality)
            if r.ok:
                ok += 1
                if str(r.dst.parent) not in out_dirs:
                    out_dirs.append(str(r.dst.parent))
                self.itemDone.emit(row, True, r.dst.name, "")
            else:
                fail += 1
                self.itemDone.emit(row, False, "", r.error)
        self.allDone.emit(ok, fail, out_dirs)


# ---------------- 主窗口 ----------------
class MainWindow(QFrame):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片转换助手")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(1010, 730)

        self.files: list[Path] = []
        self.converting = False
        self.out_dirs: list[str] = []

        # ---- 外层容器（圆角 + 阴影） ----
        container = QFrame()
        container.setObjectName("container")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 170))
        container.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 12, 18, 18)
        root.addWidget(container)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(16, 10, 16, 16)
        lay.setSpacing(12)

        self.title_bar = TitleBar(self)
        self.drop_zone = DropZone(self)
        lay.addWidget(self.title_bar)
        lay.addWidget(self.drop_zone)

        # ---- 文件列表卡片 ----
        list_card = QFrame()
        list_card.setObjectName("card")
        lv = QVBoxLayout(list_card)
        lv.setContentsMargins(14, 10, 14, 12)
        lv.setSpacing(6)

        head = QHBoxLayout()
        self.list_title = QLabel("文件列表")
        self.list_title.setStyleSheet(
            f"color:{TEXT}; font-size:13px; font-weight:600; border:none;")
        self.list_info = QLabel("尚未添加图片")
        self.list_info.setStyleSheet(f"color:{TEXT2}; font-size:11px; border:none;")
        self.btn_clear = QPushButton("全部清空")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setObjectName("ghostBtn")
        head.addWidget(self.list_title)
        head.addSpacing(8)
        head.addWidget(self.list_info)
        head.addStretch(1)
        head.addWidget(self.btn_clear)
        lv.addLayout(head)

        self.table = QTableWidget(0, COL_COUNT)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setIconSize(QSize(52, 40))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i, w in enumerate(COL_W):
            self.table.setColumnWidth(i, w)
        self.table.verticalHeader().setDefaultSectionSize(50)
        lv.addWidget(self.table, 1)
        lay.addWidget(list_card, 1)

        # ---- 设置卡片 ----
        set_card = QFrame()
        set_card.setObjectName("card")
        sv = QHBoxLayout(set_card)
        sv.setContentsMargins(16, 9, 16, 9)
        sv.setSpacing(14)

        def field(caption: str, widget: QWidget) -> QFrame:
            f = QFrame()
            f.setStyleSheet("border:none;")
            box = QVBoxLayout(f)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(2)
            cap = QLabel(caption)
            cap.setStyleSheet(f"color:{TEXT2}; font-size:10px; border:none;")
            box.addWidget(cap)
            box.addWidget(widget)
            return f

        self.chk_rename = QCheckBox("启用")
        self.chk_rename.setChecked(True)
        self.chk_rename.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_rename.setToolTip("关闭后保留原文件名，仅转换格式并裁剪为 3:2")
        self.ed_prefix = QLineEdit("DSC")
        self.ed_prefix.setFixedWidth(84)
        self.ed_prefix.setMaxLength(12)
        self.sp_start = QSpinBox()
        self.sp_start.setRange(0, 9_999_999)
        self.sp_start.setValue(3500)
        self.sp_start.setFixedWidth(96)
        self.sp_digits = QSpinBox()
        self.sp_digits.setRange(3, 8)
        self.sp_digits.setValue(5)
        self.sp_digits.setFixedWidth(62)
        self.sl_quality = QSlider(Qt.Orientation.Horizontal)
        self.sl_quality.setRange(60, 100)
        self.sl_quality.setValue(95)
        self.sl_quality.setFixedWidth(130)
        self.lb_quality = QLabel("95")
        self.lb_quality.setStyleSheet(
            f"color:{ACCENT2}; font-size:13px; font-weight:600; border:none;")
        self.lb_quality.setFixedWidth(26)
        self.ed_subfolder = QLineEdit("JPG输出")
        self.ed_subfolder.setFixedWidth(120)
        self.ed_subfolder.setMaxLength(40)

        sv.addWidget(field("批量重命名", self.chk_rename))
        sv.addWidget(field("文件名前缀", self.ed_prefix))
        sv.addWidget(field("起始序号", self.sp_start))
        sv.addWidget(field("序号位数", self.sp_digits))
        sep1 = QLabel()
        sep1.setFixedSize(1, 40)
        sep1.setStyleSheet(f"background:{BORDER}; border:none;")
        sv.addWidget(sep1)
        sv.addWidget(field("JPG 画质", self.sl_quality))
        sv.addWidget(self.lb_quality)
        self.lb_quality.setAlignment(Qt.AlignmentFlag.AlignBottom |
                                     Qt.AlignmentFlag.AlignHCenter)
        sep2 = QLabel()
        sep2.setFixedSize(1, 40)
        sep2.setStyleSheet(f"background:{BORDER}; border:none;")
        sv.addWidget(sep2)
        sv.addWidget(field("保存到子文件夹", self.ed_subfolder))
        sv.addStretch(1)
        self.lb_tip = QLabel("序号按文件名排序依次递增\n转换绝不修改原图")
        self.lb_tip.setStyleSheet(f"color:{TEXT2}; font-size:10px; border:none;")
        self.lb_tip.setAlignment(Qt.AlignmentFlag.AlignRight |
                                 Qt.AlignmentFlag.AlignVCenter)
        sv.addWidget(self.lb_tip)
        lay.addWidget(set_card)

        # ---- 底部操作行 ----
        action = QHBoxLayout()
        action.setSpacing(12)
        self.btn_convert = QPushButton("开始转换")
        self.btn_convert.setObjectName("primaryBtn")
        self.btn_convert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_convert.setFixedSize(220, 50)
        self.btn_convert.setEnabled(False)

        prog_col = QVBoxLayout()
        prog_col.setSpacing(4)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.lb_progress = QLabel("准备就绪")
        self.lb_progress.setStyleSheet(f"color:{TEXT2}; font-size:11px; border:none;")
        prog_col.addWidget(self.progress)
        prog_col.addWidget(self.lb_progress)

        self.btn_open = QPushButton("打开输出文件夹")
        self.btn_open.setObjectName("ghostBtn")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setFixedSize(140, 50)
        self.btn_open.setEnabled(False)

        action.addWidget(self.btn_convert)
        action.addLayout(prog_col, 1)
        action.addWidget(self.btn_open)
        lay.addLayout(action)

        # ---- 信号连接 ----
        self.drop_zone.filesDropped.connect(self.add_paths)
        self.drop_zone.btn_files.clicked.connect(self.pick_files)
        self.drop_zone.btn_folder.clicked.connect(self.pick_folder)
        self.btn_clear.clicked.connect(self.clear_files)
        self.btn_convert.clicked.connect(self.start_convert)
        self.btn_open.clicked.connect(self.open_output)
        self.table.customContextMenuRequested.connect(self.table_menu)
        self.ed_prefix.textChanged.connect(self.refresh_names)
        self.sp_start.valueChanged.connect(self.refresh_names)
        self.sp_digits.valueChanged.connect(self.refresh_names)
        self.chk_rename.toggled.connect(self.on_rename_toggled)
        self.sl_quality.valueChanged.connect(
            lambda v: self.lb_quality.setText(str(v)))

        # 后台信息线程
        self.info_worker = InfoWorker()
        self.info_worker.infoReady.connect(self.on_info_ready)
        self.info_worker.start()

        self.rebuild_table()

    # ---------------- 文件管理 ----------------
    def add_paths(self, raw_paths: list[str]) -> None:
        if self.converting:
            return
        added, skipped = 0, 0
        existing = {f.resolve() for f in self.files}
        for raw in raw_paths:
            p = Path(raw)
            if p.is_dir():
                for img in scan_folder(p):
                    rp = img.resolve()
                    if rp not in existing:
                        existing.add(rp)
                        self.files.append(img)
                        added += 1
            elif p.is_file() and p.suffix.lower() in converter.SUPPORTED_EXTS:
                rp = p.resolve()
                if rp not in existing:
                    existing.add(rp)
                    self.files.append(p)
                    added += 1
            else:
                skipped += 1
        self.files.sort(key=lambda f: natural_key(f.name))
        self.rebuild_table()
        if added or skipped:
            msg = []
            if added:
                msg.append(f"新增 {added} 张")
            if skipped:
                msg.append(f"忽略 {skipped} 个不支持的文件")
            self.list_info.setText("，".join(msg))

    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", "",
                                                "图片 (*.png *.jpg *.jpeg)")
        if files:
            self.add_paths(files)

    def pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.add_paths([folder])

    def clear_files(self) -> None:
        if self.converting:
            return
        self.files.clear()
        self.out_dirs.clear()
        self.btn_open.setEnabled(False)
        self.rebuild_table()

    def remove_selected(self) -> None:
        if self.converting:
            return
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.files[r]
        self.rebuild_table()

    def table_menu(self, pos) -> None:
        if self.converting or not self.files:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{CARD2}; color:{TEXT}; border:1px solid {BORDER};"
            "border-radius:8px; padding:6px 2px;}"
            f"QMenu::item{{padding:6px 22px; border-radius:6px;}}"
            f"QMenu::item:selected{{background:{ACCENT1};}}")
        a1 = menu.addAction("移除所选（Delete）")
        a2 = menu.addAction("清空全部")
        act = menu.exec(self.table.viewport().mapToGlobal(pos))
        if act == a1:
            self.remove_selected()
        elif act == a2:
            self.clear_files()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_selected()
        super().keyPressEvent(e)

    # ---------------- 表格 ----------------
    def rebuild_table(self) -> None:
        self.table.setRowCount(len(self.files))
        need_crop = 0
        for row, f in enumerate(self.files):
            name = QTableWidgetItem(f.name)
            name.setForeground(QColor(TEXT))
            self.table.setItem(row, 0, QTableWidgetItem())  # 缩略图占位
            self.table.item(row, 0).setIcon(self._placeholder_icon())
            self.table.setItem(row, 1, name)
            dims = QTableWidgetItem("读取中…")
            dims.setForeground(QColor(TEXT2))
            self.table.setItem(row, 2, dims)
            ratio = QTableWidgetItem("…")
            ratio.setForeground(QColor(TEXT2))
            self.table.setItem(row, 3, ratio)
            self.table.setItem(row, 4, QTableWidgetItem())
            status = QTableWidgetItem("—")
            status.setForeground(QColor(TEXT2))
            self.table.setItem(row, 5, status)
            self.info_worker.submit(row, f)
        n = len(self.files)
        self.list_title.setText(f"文件列表（{n}）")
        if n == 0:
            self.list_info.setText("尚未添加图片")
        self.btn_convert.setEnabled(n > 0 and not self.converting)
        self.btn_convert.setText("开始转换" if n == 0 else f"开始转换（{n} 张）")
        self.refresh_names()

    def _placeholder_icon(self) -> QIcon:
        pm = QPixmap(52, 40)
        pm.fill(QColor(CARD2))
        return QIcon(pm)

    def on_info_ready(self, row: int, w: int, h: int, thumb: QImage) -> None:
        if row >= self.table.rowCount():
            return  # 行已删除
        src_name = self.files[row].name if row < len(self.files) else ""
        if self.table.item(row, 1) and self.table.item(row, 1).text() != src_name:
            return  # 行已刷新为其他文件
        if w == 0:
            self.table.item(row, 2).setText("无法读取")
            self.table.item(row, 2).setForeground(QColor(RED))
            return
        self.table.item(row, 0).setIcon(QIcon(QPixmap.fromImage(thumb)))
        self.table.item(row, 2).setText(f"{w} × {h}")
        item = self.table.item(row, 3)
        if converter.is_target_ratio(w, h):
            item.setText("✓ 已是 3:2")
            item.setForeground(QColor(GREEN))
        else:
            item.setText("⟳ 将裁剪为 3:2")
            item.setForeground(QColor(AMBER))

    def current_plan(self) -> list[tuple[Path, str]]:
        """当前设置下的转换方案：[(源文件, 新文件名), ...]。"""
        if self.chk_rename.isChecked():
            prefix = self.ed_prefix.text().strip() or "IMG"
            return plan_rename(self.files, prefix,
                               self.sp_start.value(), self.sp_digits.value())
        # 关闭重命名：保留原文件名，仅换 .jpg 后缀
        return [(f, f"{f.stem}.jpg") for f in self.files]

    def on_rename_toggled(self, on: bool) -> None:
        """开关批量重命名：联动置灰相关输入框并刷新预览。"""
        for w in (self.ed_prefix, self.sp_start, self.sp_digits):
            w.setEnabled(on)
        self.lb_tip.setText(
            "序号按文件名排序依次递增\n转换绝不修改原图" if on
            else "保留原文件名，仅转 JPG 与 3:2\n转换绝不修改原图")
        self.refresh_names()

    def refresh_names(self, *_a) -> None:
        """设置变化时实时刷新「转换后文件名」预览列。"""
        if self.converting:
            return
        plan = self.current_plan()
        for row, (_, new_name) in enumerate(plan):
            item = self.table.item(row, 4)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, 4, item)
            item.setText(f"→ {new_name}")
            item.setForeground(QColor(ACCENT2))

    # ---------------- 转换 ----------------
    def start_convert(self) -> None:
        if self.converting or not self.files:
            return
        self.converting = True
        self.btn_convert.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.drop_zone.setEnabled(False)
        self.chk_rename.setEnabled(False)
        quality = self.sl_quality.value()
        subfolder = self.ed_subfolder.text().strip() or "JPG输出"
        plan = self.current_plan()
        jobs = []
        for row, (src, new_name) in enumerate(plan):
            st = self.table.item(row, 5)
            st.setText("排队中…")
            st.setForeground(QColor(TEXT2))
            jobs.append((row, src, new_name, quality, subfolder))
        self.progress.setValue(0)
        self.lb_progress.setText("正在转换…")
        self.worker = ConvertWorker(jobs)
        self.worker.itemDone.connect(self.on_item_done)
        self.worker.allDone.connect(self.on_all_done)
        self.worker.start()

    def on_item_done(self, row: int, ok: bool, dst_name: str, error: str) -> None:
        item = self.table.item(row, 5)
        if item is None:
            return
        if ok:
            item.setText(f"✓ {dst_name}")
            item.setForeground(QColor(GREEN))
        else:
            item.setText(f"✗ 失败：{error[:20]}")
            item.setForeground(QColor(RED))
        done = sum(1 for r in range(self.table.rowCount())
                   if self.table.item(r, 5)
                   and (self.table.item(r, 5).text().startswith("✓")
                        or self.table.item(r, 5).text().startswith("✗")))
        total = self.table.rowCount()
        self.progress.setValue(int(done / total * 100))
        self.lb_progress.setText(f"正在转换… {done}/{total}")

    def on_all_done(self, ok: int, fail: int, out_dirs: list[str]) -> None:
        self.converting = False
        self.out_dirs = out_dirs
        self.btn_convert.setEnabled(True)
        self.btn_clear.setEnabled(True)
        self.drop_zone.setEnabled(True)
        self.chk_rename.setEnabled(True)
        self.btn_open.setEnabled(bool(out_dirs))
        self.progress.setValue(100)
        if fail == 0:
            self.lb_progress.setText(f"完成！成功转换 {ok} 张 🎉")
        else:
            self.lb_progress.setText(f"完成：成功 {ok} 张，失败 {fail} 张")

    def open_output(self) -> None:
        for d in self.out_dirs[:1]:
            try:
                os.startfile(d)  # noqa: S606 - Windows 打开资源管理器
            except OSError:
                pass

    def closeEvent(self, e) -> None:
        self.info_worker.stop()
        self.info_worker.wait(2000)
        super().closeEvent(e)


# ---------------- 全局样式 ----------------
STYLE = f"""
QFrame#container {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QFrame#titleBar {{ background: transparent; border: none; }}
QFrame#dropZone {{
    background: {CARD};
    border: 1.5px dashed {BORDER};
    border-radius: 14px;
}}
QFrame#card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QPushButton#primaryBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {ACCENT1}, stop:1 {ACCENT2});
    color: white; font-size: 15px; font-weight: 600;
    border: none; border-radius: 12px;
}}
QPushButton#primaryBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #8d70ff, stop:1 #5b9dff);
}}
QPushButton#primaryBtn:disabled {{ background: {CARD2}; color: {TEXT2}; }}
QPushButton#ghostBtn, DropZone QPushButton {{
    background: {CARD2}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 10px;
    font-size: 12px; padding: 0 16px;
}}
QPushButton#ghostBtn:hover, DropZone QPushButton:hover {{
    border-color: {ACCENT1}; color: white;
}}
DropZone QPushButton {{ font-size: 13px; font-weight: 600; }}
QLineEdit, QSpinBox {{
    background: {CARD2}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 8px;
    padding: 5px 8px; font-size: 12px;
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT1}; }}
QCheckBox {{
    spacing: 6px; color: {TEXT}; font-size: 12px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 6px;
    border: 1.5px solid {BORDER}; background: {CARD2};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT1}; }}
QCheckBox::indicator:checked {{
    border-color: {ACCENT1};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {ACCENT1}, stop:1 {ACCENT2});
}}
QCheckBox:disabled {{ color: {TEXT2}; }}
QLineEdit:disabled, QSpinBox:disabled {{
    color: #5c6170; background: #171a21; border-color: #242835;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; }}
QSlider::groove:horizontal {{
    height: 4px; border-radius: 2px; background: {BORDER};
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
    background: {ACCENT2};
}}
QSlider::sub-page:horizontal {{
    border-radius: 2px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {ACCENT1}, stop:1 {ACCENT2});
}}
QTableWidget {{
    background: transparent; border: none; font-size: 12px;
}}
QTableWidget::item {{ padding: 2px 6px; }}
QTableWidget::item:selected {{ background: {ACCENT1}33; border-radius: 6px; }}
QProgressBar {{
    background: {CARD2}; border: none; border-radius: 4px;
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {ACCENT1}, stop:1 {ACCENT2});
}}
QToolTip {{
    background: {CARD2}; color: {TEXT}; border: 1px solid {BORDER};
}}
"""


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
