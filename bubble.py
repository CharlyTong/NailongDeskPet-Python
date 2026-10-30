# -*- coding: utf-8 -*-
"""
Bubble —— 头顶气泡（对应 Mac 版 BubblePanel + BubbleView）

Mac 版在这个窗口上踩过的两个大坑，Qt 里的对应解法：
  1. "幽灵窗口"：NSPanel 默认 hidesOnDeactivate，App 不活跃就藏面板。
     Qt 窗口没有这个默认行为，天然免疫。
  2. 点击穿透：WA_TransparentForMouseEvents 一个属性搞定
     （≈ NSWindow 的 ignoreMouseEvents）。
  3. 文字颜色：显式画黑色。别依赖系统主题默认色——
     "背景写死白色 + 文字跟随主题"在深色模式 = 白字白底（Mac 版的第 4 个坑）。
"""

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from pet_engine import BUBBLE_W, BUBBLE_H, PET_SIZE


class Bubble(QWidget):
    """漫画式白气泡 + 指向头顶的小尾巴 + 淡入动画"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)          # 不抢焦点
        self.setAttribute(Qt.WA_TransparentForMouseEvents)     # 整窗点击穿透
        self.setFixedSize(BUBBLE_W, BUBBLE_H)
        self._text = ""
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(180)                             # 淡入，别太拖沓
        self._anim.setStartValue(0.0)
        self._end_value = 1.0
        self._anim.setEndValue(self._end_value)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def show_text(self, text: str):
        self._text = text
        self.setGeometry(self.x(), self.y(), BUBBLE_W, BUBBLE_H)
        self.show()
        self.raise_()
        self._anim.start()
        self.update()

    def position_above(self, px: int, py: int):
        """定位到桌宠头顶居中（px/py = 桌宠窗口左上角，Qt 坐标 y 向下）"""
        r = QApplication.primaryScreen().availableGeometry()
        x = px + PET_SIZE / 2 - BUBBLE_W / 2
        x = min(max(x, r.left()), r.right() + 1 - BUBBLE_W)   # 水平夹在屏幕内
        y = py - BUBBLE_H - 8                                  # 头顶上方 8px
        self.move(int(x), int(y))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 气泡身体（圆角矩形）+ 尾巴（三角，指向下方桌宠的头顶）
        body = QPainterPath()
        body.addRoundedRect(4, 4, w - 8, h - 26, 14, 14)
        tail = QPainterPath()
        cx = w / 2
        tail.moveTo(cx - 11, h - 23)
        tail.lineTo(cx + 11, h - 23)
        tail.lineTo(cx - 4, h - 3)     # 尾巴略偏，指向"说话者"
        tail.closeSubpath()
        balloon = body.united(tail)    # 并集：尾巴和身体自动无缝焊接
        p.setPen(QPen(QColor(0, 0, 0, 40), 1.5))
        p.setBrush(QColor(255, 255, 255, 242))
        p.drawPath(balloon)

        # 文字：黑色、最多 2 行、超出省略（防 AI 长回复撑爆气泡）
        p.setPen(QColor(20, 20, 20))
        f = QFont()
        f.setPointSize(13)
        p.setFont(f)
        fm = QFontMetrics(f)
        rect_w = w - 36
        words = self._text
        lines = []
        while words and len(lines) < 2:
            line = fm.elidedText(words, Qt.ElideRight, rect_w)
            if fm.horizontalAdvance(line) < rect_w:      # 没被省略 = 全装下了
                lines.append(line)
                words = ""
            else:                                        # 先截一行，剩余进下一行
                cut = len(words)
                while cut > 1 and fm.horizontalAdvance(words[:cut]) > rect_w:
                    cut -= 1
                lines.append(words[:cut])
                words = words[cut:]
        if words:                                        # 两行还装不下：第二行加省略号
            lines[1] = fm.elidedText(lines[1] + words, Qt.ElideRight, rect_w)
        p.drawText(18, 4, rect_w, h - 26,
                   Qt.AlignCenter | Qt.TextWordWrap, "\n".join(lines))
