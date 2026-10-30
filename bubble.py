# -*- coding: utf-8 -*-
"""
Bubble —— 头顶气泡（对应 Mac 版 BubblePanel + BubbleView）

Mac 版在这个窗口上踩过的两个大坑，Qt 里的对应解法：
  1. "幽灵窗口"：NSPanel 默认 hidesOnDeactivate，App 不活跃就藏面板。
     （后来发现 Qt.Tool 在 mac 底层同样是 NSPanel，同样中招——
      见 pet_window.mac_join_all_spaces 里的三连修）
  2. 点击穿透：WA_TransparentForMouseEvents 一个属性搞定
     （≈ NSWindow 的 ignoreMouseEvents）。
  3. 文字颜色：显式画黑色。别依赖系统主题默认色——
     "背景写死白色 + 文字跟随主题"在深色模式 = 白字白底（Mac 版的第 4 个坑）。

尺寸自适应：气泡大小随文字长度浮动——
show_text 时用 QFontMetrics 实测文本宽度并折行，
按"最宽行 + 内边距"定宽、"行数 × 行高 + 尾巴区"定高。
短句（"牛来！"）≈ 76×57，长回复最多 240×130。
"""

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from pet_engine import PET_SIZE
from pet_window import mac_join_all_spaces

FONT_PT = 11          # 字号
MAX_TEXT_W = 200      # 文字区最大宽度（再宽就折行）
PAD_X = 20            # 文字左右内边距
TAIL_H = 24           # 底部尾巴区高度
MAX_LINES = 5         # 最多行数（超出末行省略——防长回复撑成大楼）


class Bubble(QWidget):
    """漫画式白气泡 + 指向头顶的小尾巴 + 淡入动画，尺寸随内容浮动"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)          # 不抢焦点
        self.setAttribute(Qt.WA_TransparentForMouseEvents)     # 整窗点击穿透
        self._font = QFont()
        self._font.setPointSize(FONT_PT)
        self._text = ""
        self._lines = []      # 折行结果（show_text 里算好，paintEvent 直接用）
        self._last_pet = None # 桌宠上次位置：resize 后据此重新居中
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(180)                             # 淡入，别太拖沓
        self._anim.setStartValue(0.0)
        self._end_value = 1.0
        self._anim.setEndValue(self._end_value)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ---------- 尺寸计算：实测文本 → 折行 → (宽, 高) ----------
    def _layout(self, text: str):
        fm = QFontMetrics(self._font)
        line_h = fm.height()
        # 贪心折行：每行装到装不下为止（CJK 可任意位置断行）
        lines, remaining = [], text
        while remaining and len(lines) < MAX_LINES:
            cut = len(remaining)
            while cut > 0 and fm.horizontalAdvance(remaining[:cut]) > MAX_TEXT_W:
                cut -= 1
            if cut == 0:
                cut = 1
            lines.append(remaining[:cut])
            remaining = remaining[cut:]
        if remaining:                                  # 超过行数上限：末行省略
            lines[-1] = fm.elidedText(lines[-1] + remaining,
                                      Qt.ElideRight, MAX_TEXT_W)
        text_w = max(fm.horizontalAdvance(l) for l in lines)
        w = max(70, text_w + PAD_X * 2)                # 短句也留出最小宽度
        h = max(48, len(lines) * line_h + 14 + TAIL_H)
        return lines, w, h

    def show_text(self, text: str):
        self._text = text
        self._lines, w, h = self._layout(text)
        self.resize(int(w), int(h))
        if self._last_pet:
            # resize 改变了宽高，必须按新尺寸重新居中——否则"……"换成
            # 长回复时，气泡会以左上角为锚点向右长歪（奶龙发呆不动时
            # moved 信号不来，没人帮它重新摆位）
            self.position_above(*self._last_pet)
        self.show()
        mac_join_all_spaces(self)   # 每次显示都确保加入所有空间（首次 show 后 winId 才有效）
        self.raise_()
        self._anim.start()
        self.update()

    def position_above(self, px: int, py: int):
        """定位到桌宠头顶居中（px/py = 桌宠窗口左上角，Qt 坐标 y 向下）。
        宽高用当前实际尺寸——气泡已随内容自适应大小。"""
        self._last_pet = (px, py)
        r = QApplication.primaryScreen().availableGeometry()
        w, h = self.width(), self.height()
        x = px + PET_SIZE / 2 - w / 2
        x = min(max(x, r.left()), r.right() + 1 - w)    # 水平夹在屏幕内
        y = py - h - 8                                  # 头顶上方 8px
        self.move(int(x), int(y))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 气泡身体（圆角矩形）+ 尾巴（三角，指向下方桌宠的头顶）
        body = QPainterPath()
        body.addRoundedRect(4, 4, w - 8, h - 8 - TAIL_H, 12, 12)
        tail = QPainterPath()
        cx = w / 2
        tail.moveTo(cx - 11, h - TAIL_H - 1)
        tail.lineTo(cx + 11, h - TAIL_H - 1)
        tail.lineTo(cx - 4, h - 3)     # 尾巴略偏，指向"说话者"
        tail.closeSubpath()
        balloon = body.united(tail)    # 并集：尾巴和身体自动无缝焊接
        p.setPen(QPen(QColor(0, 0, 0, 40), 1.5))
        p.setBrush(QColor(255, 255, 255, 242))
        p.drawPath(balloon)

        # 文字：折行结果在 show_text 里已算好，这里只管居中画出来
        p.setPen(QColor(20, 20, 20))
        p.setFont(self._font)
        p.drawText(QRect(PAD_X, 4, w - PAD_X * 2, h - 8 - TAIL_H),
                   Qt.AlignVCenter | Qt.AlignHCenter,
                   "\n".join(self._lines))
