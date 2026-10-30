# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置（跨平台：同一份 spec 在 Windows/mac/Linux 都能用）
#   Windows 打包：双击 build.bat，或 python -m PyInstaller NailongDeskPet.spec
#   产物：dist/NailongDeskPet.exe（单文件，无需安装 Python）
#
# datas 把 sprites/ 打进包里 —— 运行时解包到 sys._MEIPASS（见 paths.py）

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('sprites', 'sprites')],   # 帧动画素材随包携带
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,          # 下面三项进 EXE = 单文件模式（onefile）
    a.datas,
    name='NailongDeskPet',
    debug=False,
    console=False,       # GUI 程序：不弹黑色控制台窗口
    icon=None,           # 想换图标：放一个 .ico 在目录里，改成 icon='nailong.ico'
)

# macOS 专属：Qt 的 GUI 程序需要正经 .app 包结构（Info.plist +
# NSApplication 生命周期），裸二进制跑 console=False 会静默不出窗。
# Windows 上这段自动跳过，产物就是独立的 NailongDeskPet.exe。
import sys
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='NailongDeskPet.app',
        bundle_identifier='com.charlytong.nailongdeskpet',
        info_plist={'LSUIElement': True},   # 不在 Dock 显示图标（桌宠礼仪）
    )
