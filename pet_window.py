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

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget, QMenu

from pet_engine import PET_SIZE, HERE

SPRITES_DIR = os.path.join(HERE, "sprites")


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

    # ---------- 绘制：只读引擎数据，从不改逻辑 ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        pm = self._frame_pixmap(self.engine.state, self.engine.frame_index)
        if pm is None:
            return   # 素材缺失就不画（窗口全透明，等于隐身，不画占位块）
        if self.engine.facing_left:
            pm = pm.transformed(QTransform().scale(-1, 1))   # 镜像：左右共用素材
        p.drawPixmap(0, 0, PET_SIZE, PET_SIZE, pm)

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

    def contextMenuEvent(self, ev):
        """右键菜单（对应 Mac 版 AppDelegate 里的 menu）"""
        m = QMenu(self)
        m.addAction("和我聊天", self._open_chat)
        m.addAction("测试 API", self.engine.test_api)
        m.addAction("回到屏幕底部", self.engine.reset_to_ground)
        m.addSeparator()
        m.addAction("退出", self._quit)
        m.exec(ev.globalPos().toPoint())

    # 这两个引用由 main.py 注入（引擎不该认识窗口，窗口之间也不该认识）
    chat_opener = None
    quitter = None

    def _open_chat(self):
        if self.chat_opener:
            self.chat_opener()

    def _quit(self):
        if self.quitter:
            self.quitter()
