# 图片转换助手 (Photo Converter)

一个现代化的 Windows 桌面小工具：批量把 PNG 转成 JPG、自动裁剪为 3:2 比例、可选批量重命名。

![screenshot](docs/screenshot.png)

## ✨ 功能

- **PNG → JPG**：支持 PNG / JPG / JPEG 输入，统一输出 JPG（画质 60–100 可调，默认 95）
- **3:2 比例整理**：非 3:2 的照片自动居中裁剪（横图裁左右、竖图裁上下），已是 3:2 的保持原样
- **批量重命名（可选）**：默认按 `DSC03500、DSC03501…` 依次编号，前缀 / 起始序号 / 位数可自定义；关闭开关则保留原文件名
- **安全无忧**：输出保存到源文件夹的 `JPG输出` 子文件夹，**原图永远不会被修改**；重复转换自动加后缀，绝不覆盖
- **细节处理**：透明 PNG 自动垫白底、手机竖拍照片按 EXIF 摆正方向、自然排序（IMG2 排在 IMG10 前面）
- **现代界面**：深色主题、无边框圆角窗口、拖拽添加、缩略图与转换后文件名实时预览、后台转换不卡界面

## 🚀 使用

从 [Releases](../../releases) 下载解压后双击 `图片转换助手.exe`（无需安装 Python）。

也可以从源码运行：

```bash
pip install PyQt6 Pillow
python main.py
```

## 🛠️ 从源码打包 exe

双击 `build.bat`（自动安装 PyInstaller 并生成 `dist/图片转换助手/图片转换助手.exe`）。

## 📁 项目结构

```
main.py             # PyQt6 界面
converter.py        # 转换核心逻辑（裁剪 / 格式转换 / 重命名）
make_icon.py        # 生成程序图标
test_converter.py   # 核心逻辑自动化测试（28 项）
test_ui_toggle.py   # 重命名开关无头 UI 测试（17 项）
build.bat           # 一键打包脚本
```

## 🧪 运行测试

```bash
python test_converter.py
python test_ui_toggle.py
```

## 技术栈

Python 3.11 · PyQt6 · Pillow · PyInstaller
