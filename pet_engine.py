# -*- coding: utf-8 -*-
"""
PetEngine —— 桌宠的"大脑"（对应 Mac 版 PetEngine.swift）

架构：一个 33ms 的 QTimer 主循环（= pygame 的 main loop），
每次 tick 干三件事：
  1. 推进动画帧号（时间累加器，Timer 抖动不影响节奏）
  2. 按状态机执行行为（走动 / 重力下落 / 到点换状态）
  3. 气泡跟随 + 到点隐藏

与 Mac 版的两个关键差异（移植时踩过的坑，别再踩）：
  ⚠️ 坐标系：Qt 原点在【左上角、y 向下】；AppKit 原点在左下、y 向上。
     所以"重力下落"是 y 增大，"头顶"是 y 减小——全部反过来。
  ⚠️ 线程模型：Swift 用 async/await + @MainActor；PySide6 里我们用
     threading.Thread 发 HTTP，结果通过 Qt 信号送回主线程
     （信号跨线程自动变成"排队投递"，天然安全）。

分层规则：本类不持有任何窗口引用，只发信号（≈ Swift 的 @Published），
视图层"看数据画图"。想改桌宠性格，读这个文件就够。
"""

import json
import os
import random
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from ai_client import ChatService

# ============================================================
# 物理与行为常数表 —— 想调"手感"改这里（= Mac 版 PetConfig）
# ============================================================
PET_SIZE = 96            # 桌宠显示尺寸
TICK_MS = 33             # 主循环间隔（≈30Hz）
WALK_SPEED = 40          # 走路速度（像素/秒）
GRAVITY = 900            # 重力加速度（像素/秒²）
GROUND_GAP = 2           # 判定"在空中"的容差
MEMORY_LIMIT = 60        # 聊天记忆上限条数

from paths import resource_dir, app_dir
HISTORY_PATH = os.path.join(app_dir(), "chat_history.json")   # 私人数据，已在 .gitignore


class PetEngine(QObject):
    # ---- "可观察属性"（≈ Swift @Published：变了视图自动响应）----
    tick_done = Signal()            # 每帧发出：窗口重画（读 frame_index/action/facing）
    moved = Signal(int, int)        # 窗口位置变化（逻辑层 → 真实窗口）
    bubble_show = Signal(str)       # 显示/替换气泡文本
    bubble_hide = Signal()          # 隐藏气泡
    chat_changed = Signal()         # 聊天历史变化（聊天窗重载）
    busy_changed = Signal(bool)     # API 请求进行中
    # ---- 跨线程回调通道：工作线程 emit → Qt 自动排队投递回主线程 ----
    # ⚠️ 不能用 QTimer.singleShot 从工作线程投递：Qt 定时器只允许在主线程
    # 创建，从 threading.Thread 调用会静默失败，回调永远不执行（大坑，
    # 症状：聊天"正在输入"永远转圈、busy 永不复位）。信号是线程安全的。
    _chat_ok = Signal(str)          # 聊天拿到回复
    _chat_fail = Signal(str)        # 聊天出错
    _busy_off = Signal()            # 解除 busy（finally 必发）

    # 戳一戳本地兜底文案（没网/没配 Key 时随机蹦一句）
    POKE_LINES = ["我在。", "戳我干嘛？", "你有事吗", "牛来！", "我是奶龙",
                  "再戳要收费了", "戳坏了赔钱哦", "嗯？", "您有事吗大姐"]

    # 戳一戳专属人设：一次性 system prompt，不进聊天历史（和 Mac 版同款双通道设计）
    POKE_PROMPT = (
        "你是桌宠奶龙，一只圆滚滚的黄色小恐龙。用户戳了你一下。\n"
        "现编一句【25字以内】的贱萌抽象短句回应，越抽象越猎奇越好，"
        "风格参考（禁止照抄）：\n"
        "\"我在\"、\"戳我干嘛？\"、\"你有事吗\"、\"牛来\"、\"我是奶龙\"、"
        "\"哥，你别撩我了我这种处蛙禁不起撩啊\"。\n"
        "直接输出那一句话。禁止解释，禁止重复之前的回复。"
    )

    def __init__(self, ai: ChatService, parent=None):
        super().__init__(parent)
        self.ai = ai
        # ---- 视图要读的状态 ----
        self.state = "idle"        # idle / walk / happy / drag / fall
        self.facing_left = False   # walk 时为 True，视图据此镜像
        self.frame_index = 0
        self.messages = []         # 聊天历史（启动时从磁盘恢复）
        self.is_busy = False
        # ---- 私有运行状态 ----
        self._timer = None
        self._last_tick = 0.0
        self._frame_accum = 0.0        # 帧时间累加器
        self._next_decision = 0.0      # 下次随机换行为的时刻
        self._happy_until = 0.0
        self._bubble_hide_at = 0.0
        self._x = 0.0                 # 窗口左上角坐标（Qt 坐标系）
        self._y = 0.0
        self._vy = 0.0                # 下落速度
        self._drag_base = (0, 0)      # 拖拽起点的窗口位置
        self._drag_start = (0, 0)     # 拖拽起点的全局光标位置
        self._poke_gen = 0            # 戳一戳的"代号"：新戳作废旧请求
        # 跨线程信号 → 主线程槽（发送方在工作线程，Qt 自动排队投递）
        self._chat_ok.connect(self._on_chat_ok)
        self._chat_fail.connect(self._on_chat_fail)
        self._busy_off.connect(lambda: self._set_busy(False))

    # ============================================================
    # 生命周期
    # ============================================================
    def start(self, x: float, y: float):
        """x/y = 初始窗口位置（由 main.py 摆好：屏幕底部居中）"""
        self._x, self._y = float(x), float(y)
        self.restore_memory()
        self._schedule_next_decision(2, 6)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    # ============================================================
    # 主循环（≈ Mac 版 tick()）
    # ============================================================
    def _tick(self):
        now = time.monotonic()
        # dt = 真实间隔，封顶 0.1s：休眠/卡顿后不瞬移（Python 的 time.monotonic
        # ≈ Swift 的 timeIntervalSinceReferenceDate，都不受用户改时钟影响）
        dt = 0.0 if self._last_tick == 0 else min(now - self._last_tick, 0.1)
        self._last_tick = now

        # 1) 动画帧推进（时间累加器：帧率不受 QTimer 抖动影响）
        info = self._sprite_info()
        self._frame_accum += dt
        frame_dur = 1.0 / info["fps"]
        while self._frame_accum >= frame_dur:
            self._frame_accum -= frame_dur
            self.frame_index = (self.frame_index + 1) % max(info["frames"], 1)

        # 2) 状态机行为
        if self.state in ("idle", "walk"):
            self._move_if_walking(dt)
            if now >= self._next_decision:
                self._decide_next_behavior()
        elif self.state == "happy":
            if now >= self._happy_until:
                self._set_state("idle"); self._schedule_next_decision(2, 6)
        elif self.state == "fall":
            self._apply_gravity(dt)
        # drag：位置完全由鼠标回调控制，tick 不插手

        # 3) 气泡到点隐藏（跟随定位由视图层每帧读 self 位置实现）
        if now >= self._bubble_hide_at and self._bubble_hide_at > 0:
            self._bubble_hide_at = 0.0
            self.bubble_hide.emit()

        self.tick_done.emit()

    # ============================================================
    # 交互入口（视图层调用）
    # ============================================================
    def pet_clicked(self):
        """单击 = 戳一戳：happy 反应 + 短气泡（AI 现编 / 本地兜底）"""
        if self.state in ("drag", "fall"):
            return
        self._set_state("happy")
        self._happy_until = time.monotonic() + 1.5
        self._poke()

    def _poke(self):
        if not self.ai.config.usable:
            self.show_bubble(random.choice(self.POKE_LINES))
            return
        # 手速快过网速：新戳作废旧请求（≈ Swift 的 Task.cancel()。
        # Python 线程不能强杀，用"代号"比对：回来的若是旧代号就丢弃）
        self._poke_gen += 1
        gen = self._poke_gen
        self.show_bubble("……", duration=10)
        temp = self.ai.config.poke_temperature

        def worker():
            try:
                reply = self.ai.send(
                    [{"role": "system", "content": self.POKE_PROMPT},
                     {"role": "user", "content": "（戳了一下你的肚皮）"}],
                    temperature=temp, max_tokens=24)
                if gen == self._poke_gen:      # 还是"当前这一戳"才显示
                    self.bubble_show.emit(reply)
            except Exception:
                if gen == self._poke_gen:
                    self.bubble_show.emit(random.choice(self.POKE_LINES))

        threading.Thread(target=worker, daemon=True).start()

    def drag_started(self, gx: int, gy: int):
        """鼠标按下：立刻记录起点。⚠️ Qt 和 SwiftUI 的差异：
        SwiftUI 设 minimumDistance:0 后按下零位移也触发 onChanged；
        Qt 的 mouseMove 只在真的移动时才来——所以起点必须在按下时记，
        否则"原地点击"会拿着上一次拖拽的旧起点算位移。"""
        self._drag_base = (self._x, self._y)
        self._drag_start = (gx, gy)

    def drag_moved(self, gx: int, gy: int):
        """拖拽中。用【全局光标坐标】算位移（和 Mac 版同一个坑的同一个解）：
        相对位移会被"窗口自己也在动"污染，全局坐标不受影响。"""
        if self.state != "drag":
            self._set_state("drag")   # 起点已在 drag_started 记好
        self._x = self._drag_base[0] + (gx - self._drag_start[0])
        self._y = self._drag_base[1] + (gy - self._drag_start[1])
        self._sync()

    def drag_ended(self, gx: int, gy: int):
        """松手：总位移 <6px 判定为"戳"，否则是真拖拽（Mac 版同款规则）"""
        dist = ((gx - self._drag_start[0]) ** 2 + (gy - self._drag_start[1]) ** 2) ** 0.5
        if dist < 6:
            self._x, self._y = self._drag_base       # 弹回按下前位置
            if self._y < self._ground_y() - GROUND_GAP:   # 半空被"戳"到：继续掉
                self._vy = 0
                self._set_state("fall")
            else:
                self._set_state("idle")              # 先解除 drag，pet_clicked 才不拦
                self.pet_clicked()
            self._sync()
            return
        if self._y < self._ground_y() - GROUND_GAP:  # 半空松手 → 掉落
            self._vy = 0
            self._set_state("fall")
        else:                                        # 贴地松手 → 站好
            self._y = self._ground_y()
            self._set_state("idle")
            self._schedule_next_decision(2, 6)
        self._sync()

    def reset_to_ground(self):
        """右键菜单项：回到屏幕底部"""
        r = self._screen_rect()
        self._x = r.left() + (r.width() - PET_SIZE) / 2
        self._y = r.bottom() + 1 - PET_SIZE
        self._set_state("idle")
        self._schedule_next_decision(2, 6)
        self._sync()

    def clamp_to_screen(self):
        """分辨率/Dock 变化时把桌宠夹回可见区"""
        r = self._screen_rect()
        self._x = min(max(self._x, r.left()), r.right() + 1 - PET_SIZE)
        self._y = min(max(self._y, r.top()), r.bottom() + 1 - PET_SIZE)
        self._sync()

    # ============================================================
    # 气泡
    # ============================================================
    def show_bubble(self, text: str, duration: float = None):
        """头顶气泡；默认时长"够读完"（10 秒起，字多自动加时）"""
        if duration is None:
            duration = max(10, len(text) * 0.08)
        self._bubble_hide_at = time.monotonic() + duration
        self.bubble_show.emit(text)

    # ============================================================
    # 长期记忆（= Mac 版的三件套：恢复 / 落盘 / 上限裁剪）
    # ============================================================
    def restore_memory(self):
        if not os.path.exists(HISTORY_PATH):
            return
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                restored = json.load(f)
            if restored:
                self.messages = restored
                print(f"[memory] 已恢复 {len(restored)} 条聊天记忆")
        except (json.JSONDecodeError, OSError):
            pass   # 文件坏了就当失忆，不崩溃

    def _persist_memory(self):
        if len(self.messages) > MEMORY_LIMIT:
            self.messages = self.messages[-MEMORY_LIMIT:]   # 砍最老的
        tmp = HISTORY_PATH + ".tmp"                          # 原子写：先临时文件再改名
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.messages, f, ensure_ascii=False)
            os.replace(tmp, HISTORY_PATH)
        except OSError:
            pass

    # ============================================================
    # AI 聊天（聊天窗调用）
    # ============================================================
    def send_chat(self, text: str):
        if self.is_busy:
            return
        if not self.ai.config.usable:
            self.show_bubble("还没配置 API 哦，看 windows/config.example.json", duration=6)
            return
        self.messages.append({"role": "user", "content": text})
        self._persist_memory()                    # 先落盘用户消息
        self.chat_changed.emit()
        self._set_busy(True)
        history = list(self.messages)

        def worker():
            try:
                reply = self.ai.send(history)
                self._chat_ok.emit(reply)
            except Exception as e:
                self._chat_fail.emit(f"呜…出错了：{e}")
            finally:
                # 无论成败都必须解除"正在输入"（信号投递回主线程执行）
                self._busy_off.emit()

        threading.Thread(target=worker, daemon=True).start()

    def test_api(self):
        """右键菜单"测试 API"：固定一句话，不进聊天历史"""
        if self.is_busy:
            self.show_bubble("上一条还在路上呢…")
            return
        if not self.ai.config.usable:
            self.show_bubble("还没配置 API 哦，看 windows/config.example.json", duration=6)
            return
        self._set_busy(True)
        self.show_bubble("测试中…", duration=60)

        def worker():
            try:
                reply = self.ai.send([{"role": "user", "content": "你好！请用一句话自我介绍。"}])
                self.bubble_show.emit(f"API 正常：{reply}")
            except Exception as e:
                self.bubble_show.emit(f"失败：{e}")
            finally:
                self._busy_off.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_chat_ok(self, reply: str):
        self.messages.append({"role": "assistant", "content": reply})
        self._after_reply()
        self.show_bubble(reply)

    def _on_chat_fail(self, msg: str):
        self.messages.append({"role": "assistant", "content": msg})
        self._after_reply()
        self.show_bubble(msg, duration=6)

    def _after_reply(self):
        self._persist_memory()
        self.chat_changed.emit()

    def _set_busy(self, b: bool):
        self.is_busy = b
        self.busy_changed.emit(b)

    # ============================================================
    # 内部行为逻辑（对照 Mac 版逐段翻译）
    # ============================================================
    def _set_state(self, s: str):
        self.state = s
        self.frame_index = 0        # 切状态重置帧号，避免画面跳变
        self._frame_accum = 0.0

    def _screen_rect(self):
        """可见区域（扣掉 Dock/任务栏）≈ Mac 版 ScreenInfo.visibleFrame"""
        from PySide6.QtWidgets import QApplication
        return QApplication.primaryScreen().availableGeometry()

    def _ground_y(self) -> float:
        """地面 = 可见区域底边（Qt：y 向下，底边是最大 y）"""
        return self._screen_rect().bottom() + 1 - PET_SIZE

    def _move_if_walking(self, dt: float):
        if self.state != "walk":
            return
        v = WALK_SPEED * dt
        self._x += -v if self.facing_left else v
        r = self._screen_rect()
        min_x, max_x = r.left(), r.right() + 1 - PET_SIZE
        if self._x <= min_x or self._x >= max_x:      # 撞屏幕边缘：停下
            self._x = min(max(self._x, min_x), max_x)
            self._set_state("idle")
            self._schedule_next_decision(2, 6)
        self._sync()

    def _decide_next_behavior(self):
        """行为决策：桌宠"性格"就在这个函数（= Mac 版同概率分布）"""
        if self.state == "walk":
            if random.random() < 0.6:                 # 走累了：60% 停，40% 掉头
                self._set_state("idle"); self._schedule_next_decision(2, 6)
            else:
                self.facing_left = not self.facing_left
                self._schedule_next_decision(4, 8)
        else:
            if random.random() < 0.5:                 # 发呆够了：50% 开走
                self._y = self._ground_y()
                self.facing_left = random.random() < 0.5
                self._set_state("walk")
                self._schedule_next_decision(4, 8)
            else:
                self._schedule_next_decision(2, 6)
        self._sync()

    def _apply_gravity(self, dt: float):
        """y 向下为正：下落 = y 增大（与 Mac 版符号相反，注意！）"""
        self._vy += GRAVITY * dt
        self._y += self._vy * dt
        if self._y >= self._ground_y():
            self._y = self._ground_y()
            self._vy = 0
            self._set_state("idle")
            self._schedule_next_decision(2, 6)
        self._sync()

    def _schedule_next_decision(self, lo: float, hi: float):
        self._next_decision = time.monotonic() + random.uniform(lo, hi)

    def _sync(self):
        """逻辑位置 → 真实窗口（≈ Mac 版 syncPanel）"""
        self.moved.emit(int(self._x), int(self._y))

    # ============================================================
    # 视图层要读的数据
    # ============================================================
    def _sprite_info(self) -> dict:
        return self.sprite_config.get(self.state) or self.sprite_config.get("idle") \
               or {"frames": 4, "fps": 6}

    @property
    def sprite_config(self) -> dict:
        if not hasattr(self, "_sprite_cfg"):
            try:
                with open(os.path.join(resource_dir(), "sprites", "SpriteConfig.json"),
                          encoding="utf-8") as f:
                    self._sprite_cfg = json.load(f)["actions"]
            except (OSError, json.JSONDecodeError, KeyError):
                print("⚠️ 未找到 sprites/SpriteConfig.json，动画用兜底参数")
                self._sprite_cfg = {}
        return self._sprite_cfg
