# -*- coding: utf-8 -*-
"""
main —— 装配入口（对应 Mac 版 main.swift + AppDelegate）

职责只有三件事：创建部件、连线（信号 → 槽）、启动。
所有"逻辑"都在 pet_engine，所有"画面"都在 *_window。
"""

import sys

from PySide6.QtWidgets import QApplication

from ai_client import ChatConfig, ChatService
from bubble import Bubble
from chat_window import ChatWindow
from pet_engine import PET_SIZE, PetEngine
from pet_window import PetWindow


def main():
    # 仅用 QT_MAC_WANTS_LAYER 之类平台参数时才动这里；默认即可
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 关掉聊天窗 ≠ 退出（桌宠本体还在）

    # ---- 创建部件 ----
    config = ChatConfig.load()
    ai = ChatService(config)
    engine = PetEngine(ai)
    pet = PetWindow(engine)
    bubble = Bubble()
    chat = ChatWindow(engine)

    # ---- 连线：引擎的信号 → 窗口的动作（≈ SwiftUI 的数据驱动）----
    engine.moved.connect(pet.move)
    engine.moved.connect(bubble.position_above)      # 气泡跟随桌宠
    engine.tick_done.connect(pet.update)             # 每帧重画
    engine.bubble_show.connect(bubble.show_text)
    engine.bubble_hide.connect(bubble.hide)

    # 窗口 → 引擎的注入点（不让窗口互相认识，都走 main 中转）
    pet.chat_opener = chat.open
    pet.quitter = app.quit

    # 分辨率 / 任务栏(Dock) 变化：把桌宠夹回可见区
    screen = QApplication.primaryScreen()
    screen.availableGeometryChanged.connect(lambda *_: engine.clamp_to_screen())

    # ---- 初始位置：屏幕底部居中，摆好后交给引擎接管 ----
    r = screen.availableGeometry()
    start_x = r.left() + (r.width() - PET_SIZE) / 2
    start_y = r.bottom() + 1 - PET_SIZE
    pet.move(int(start_x), int(start_y))
    pet.show()
    bubble.position_above(int(start_x), int(start_y))
    engine.start(start_x, start_y)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
