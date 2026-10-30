# -*- coding: utf-8 -*-
"""
ChatWindow —— 聊天窗（对应 Mac 版 ChatPanel + ChatPanelView）

全应用唯一"正常"的窗口：带系统标题栏、能拿键盘焦点。
历史就是 engine.messages（长期记忆的可视化渲染），只读显示，
输入框回车/点发送 → engine.send_chat()，回复到达后 chat_changed
信号触发重载。
"""

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QTextBrowser, QVBoxLayout, QWidget)


class ChatWindow(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("和奶龙聊天 🐲")
        self.setWindowFlag(Qt.Tool)          # 不进任务栏（但保留标题栏和焦点能力）
        self.resize(400, 480)

        lay = QVBoxLayout(self)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        lay.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("跟奶龙说点什么…（回车发送）")
        self.input.returnPressed.connect(self._send)
        self.btn = QPushButton("发送")
        self.btn.clicked.connect(self._send)
        row.addWidget(self.input, 1)
        row.addWidget(self.btn)
        lay.addLayout(row)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#888; font-size:11px;")
        lay.addWidget(self.status)

        # 引擎 → 视图：数据变了就重画（≈ SwiftUI 的 @Published 自动刷新）
        self.engine.chat_changed.connect(self.reload)
        self.engine.busy_changed.connect(self._set_busy)
        self.reload()

    def reload(self):
        parts = []
        for m in self.engine.messages:
            who = "🧑 你" if m["role"] == "user" else "🐲 奶龙"
            text = html.escape(m["content"]).replace("\n", "<br>")
            color = "#0a6cff" if m["role"] == "user" else "#b35900"
            parts.append(
                f'<p style="margin:2px 0;"><b style="color:{color}">{who}：</b>'
                f'<span style="color:#222">{text}</span></p>')
        self.view.setHtml("".join(parts) or
                          '<p style="color:#999;">（聊过天之后，这里会显示历史记录；'
                          '奶龙重启也不会忘记你。）</p>')
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())            # 自动滚到最新一条

    def _set_busy(self, busy: bool):
        self.input.setEnabled(not busy)
        self.btn.setEnabled(not busy)
        self.status.setText("奶龙正在输入…" if busy else "")
        if busy:
            self.btn.setText("…")
        else:
            self.btn.setText("发送")

    def _send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.engine.send_chat(text)
        self.raise_()    # 回复到达前保持在前台，别被盖住

    def open(self):
        self.show()
        self.raise_()
        self.activateWindow()    # 聊天窗就是要焦点的那个窗口
        self.input.setFocus()
