# -*- coding: utf-8 -*-
"""
PetWindow —— 桌宠本体窗口（对应 Mac 版 PetPanel + PetView 合体）

窗口四条灵魂属性（跨平台版，每条都有故事）：
  FramelessWindowHint     无边框（不然顶着系统标题栏的宠物像贴膏药）
  WindowStaysOnTopHint    永远置顶（对应 NSPanel 的 floating 层）
  WA_TranslucentBackground 透明底（PNG 的 alpha 通道才透得出来）
  Tool + WA_ShowWithoutActivating
                         不进任务栏 + 点击不抢键盘焦点
                         ——你打字时点它一下，输入法不会断（Mac 版踩过的
                         "不抢焦点"坑，Qt 里用这两个属性一步到位）
"""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget, QMenu

from pet_engine import PET_SIZE
from paths import resource_dir

SPRITES_DIR = os.path.join(resource_dir(), "sprites")


def mac_join_all_spaces(widget):
    """macOS 专属：让窗口【永远出现在用户面前】的两个必要条件：
    1. CanJoinAllSpaces —— 跟随所有普通桌面空间（多桌面切换不掉队）
    2. 提到状态栏层级（level 25）—— 只有 ≥ 这个层级的窗口才能浮在
       全屏应用之上（Spotlight 就是这么做的）。floating 层(3~8)进不了
       全屏空间：进程活着、会走路、用户就是看不见——本次排查的主案。
    Qt 没暴露这两个 API，走 pyobjc 直改 NSWindow。
    Windows 不需要也装不上 pyobjc，静默跳过。"""
    if sys.platform != "darwin":
        return
    try:
        import objc
        from AppKit import (NSWindowCollectionBehaviorCanJoinAllSpaces,
                            NSStatusWindowLevel)
        # winId() 返回 NSView 指针 → .window() 拿到 NSWindow → 改行为
        win = objc.objc_object(c_void_p=int(widget.winId())).window()
        win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
        win.setLevel_(NSStatusWindowLevel)
        # ⚠️ Qt.Tool 在 mac 底层是 NSPanel，默认 hidesOnDeactivate=True：
        # 用户一点别的应用（我们的 App 永远非激活），窗口就自动消失——
        # 症状是"启动时好好的，过一会儿神秘失踪"。Swift 版同款坑同款修法。
        win.setHidesOnDeactivate_(False)
    except Exception as e:
        print("⚠️ 窗口常驻设置失败（Windows 上正常，mac 上需要 pyobjc）:", e)


class PetWindow(QWidget):
    """透明的 96×96 窗口：左边是鼠标交互（戳/拖/右键菜单），右边只会画图"""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)       # 透明底
        self.setAttribute(Qt.WA_ShowWithoutActivating)       # 不抢焦点
        self.setFixedSize(PET_SIZE, PET_SIZE)
        self._cache = {}          # "动作_帧号" → QPixmap（懒加载缓存 ≈ SpriteStore）
        self._dragging = False    # 鼠标按住中

    def showEvent(self, ev):
        super().showEvent(ev)
        mac_join_all_spaces(self)   # 窗口真正创建后才能拿到 NSView（winId）

    # ---------- 绘制：只读引擎数据，从不改逻辑 ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        pm = self._frame_pixmap(self.engine.state, self.engine.frame_index)
        if pm is None:
            return   # 素材缺失就不画（窗口全透明，等于隐身，不画占位块）
        if self.engine.facing_left:
            pm = pm.transformed(QTransform().scale(-1, 1))   # 镜像：左右共用素材
        # 等比缩放：素材是竖长条（如 147x198），硬塞进 96x96 会横向拉胖。
        # KeepAspectRatio 保比例、以高度为准缩到 96，底部居中（脚踩地面）。
        fitted = pm.scaled(PET_SIZE, PET_SIZE,
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap((PET_SIZE - fitted.width()) // 2,   # 水平居中
                     PET_SIZE - fitted.height(),          # 贴底
                     fitted)

    def _frame_pixmap(self, action, frame):
        key = f"{action}_{frame}"
        if key in self._cache:
            return self._cache[key]
        path = os.path.join(SPRITES_DIR, f"{key}.png")
        pm = QPixmap(path) if os.path.exists(path) else None
        self._cache[key] = pm
        return pm

    # ---------- 鼠标交互：全部翻译成引擎调用 ----------
    def mousePressEvent(self, ev):
        # 右键菜单：直接在这里处理，不用 contextMenuEvent——
        # 那个事件由平台"合成"，mac 上对常驻非激活窗口经常不触发（实测踩坑）。
        if ev.button() == Qt.RightButton:
            m = QMenu(self)
            m.addAction("和我聊天", self._open_chat)
            m.addAction("测试 API", self.engine.test_api)
            m.addAction("回到屏幕底部", self.engine.reset_to_ground)
            m.addSeparator()
            m.addAction("退出", self._quit)
            m.exec(ev.globalPosition().toPoint())
            return
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            # 拖拽起点交给引擎记录（它用全局光标坐标算位移，见 pet_engine 注释）
            g = ev.globalPosition().toPoint()
            self.engine.drag_started(g.x(), g.y())

    def mouseMoveEvent(self, ev):
        if self._dragging:
            g = ev.globalPosition().toPoint()
            self.engine.drag_moved(g.x(), g.y())

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            g = ev.globalPosition().toPoint()
            self.engine.drag_ended(g.x(), g.y())

    # 这两个引用由 main.py 注入（引擎不该认识窗口，窗口之间也不该认识）
    chat_opener = None
    quitter = None

    def _open_chat(self):
        if self.chat_opener:
            self.chat_opener()

    def _quit(self):
        if self.quitter:
            self.quitter()
