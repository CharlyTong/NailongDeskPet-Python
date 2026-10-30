# 奶龙桌宠 · NailongDeskPet-Python

> 一只在屏幕底部溜达的奶龙：能戳、能拖、能摔、能聊。
> Python + PySide6 实现的**跨平台**桌面宠物（Windows / macOS / Linux 桌面均可运行），
> 接 DeepSeek 等 OpenAI 兼容 API，无 Key 也能当普通桌宠玩。

> macOS 原生版（Swift + SwiftUI）在姐妹仓库：[NailongDeskPet](https://github.com/CharlyTong/NailongDeskPet)

## 功能

| 交互 | 效果 |
|---|---|
| 什么都不做 | 待机摸肚皮，偶尔自己溜达两步 |
| **左键戳一戳** | 弹出对话气泡，AI 生成一句 ≤10 字的抽象短句（可配置温度） |
| **按住拖动** | 被拎起来淡定玩手，拖到半空松手会**边笑边掉落**（重力模拟） |
| **右键菜单** | 和我聊天（AI 对话窗）/ 测试 API / 回到屏幕底部 / 退出 |
| AI 聊天 | 完整上下文记忆，人设可自定义（system prompt） |

- 桌宠不抢键盘焦点：你打字时点它，输入法纹丝不动
- 聊天记忆持久化：重启 / 被杀后不失忆（最近 60 条，存 `chat_history.json`）
- 无网 / 未配置 Key 时自动降级为本地趣味文案，离线也能戳
- 气泡尺寸自适应文字长度（QFontMetrics 实测折行，短句小泡长文大泡）

## 环境要求

Python 3.9+（唯一依赖 PySide6；API 请求用标准库 urllib，零额外依赖）。
可选配 DeepSeek API Key（https://platform.deepseek.com），没有则无 AI 功能但桌宠照常运行。

## 快速开始

**Windows（PowerShell）**：

```powershell
git clone https://github.com/CharlyTong/NailongDeskPet-Python.git
cd NailongDeskPet-Python
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.json config.json
# 编辑 config.json 填入你的 API Key
.venv\Scripts\python main.py
```

**macOS / Linux（开发与日常运行同款）**：

```bash
git clone https://github.com/CharlyTong/NailongDeskPet-Python.git
cd NailongDeskPet-Python
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.json config.json
# 编辑 config.json 填入你的 API Key
.venv/bin/python main.py
```

## 配置说明（config.json）

| 字段 | 作用 | 默认 |
|---|---|---|
| `base_url` | API 入口，OpenAI 兼容格式，换供应商只改这行 | DeepSeek |
| `api_key` | 你的密钥（**此文件已被 .gitignore 保护，不会进仓库**） | — |
| `model` | 模型名 | `deepseek-chat` |
| `system_prompt` | 聊天人设 | 奶龙性格 |
| `temperature` | 聊天随机度（0~2，越低越稳定） | 0.8 |
| `poke_temperature` | 戳一戳短句随机度（调高更抽象发疯） | 1.8 |

注意：配置只在启动时读取，改完需退出重启（右键 → 退出，再运行 `main.py`）。

## 项目结构

与 macOS 原生版镜像同构，逻辑逐段翻译：

```
├── main.py           # 装配入口：创建部件、信号连线、启动（≈ AppDelegate）
├── pet_engine.py     # 大脑：33ms 主循环 + 状态机 + 物理 + AI 调度 + 记忆持久化
├── pet_window.py     # 桌宠窗：透明置顶无边框 + 帧动画 + 鼠标交互 + mac 窗口特调
├── bubble.py         # 气泡窗：漫画气泡 + 尾巴 + 点击穿透 + 尺寸自适应
├── chat_window.py    # 聊天窗：历史渲染 + 输入发送
├── ai_client.py      # OpenAI 兼容客户端（纯标准库 urllib）
├── sprites/          # 帧图 + SpriteConfig.json
└── requirements.txt  # 唯一依赖 PySide6
```

## 换皮肤

帧序列命名：`idle_0.png`、`walk_0.png`…，帧数与帧率在 `sprites/SpriteConfig.json` 里改，改完重启生效。
（macOS 原生版素材在姐妹仓库 `Sources/DeskPet/Resources/Sprites/`，两边格式互通。）

## 素材声明

奶龙与 oiiai 素材均来源于网络，本项目仅作个人学习与技术演示用途，不作任何商业分发，如有侵权请联系删除。

## 已知限制（Roadmap）

- [ ] 尚未打包独立可执行文件（Windows 的 `.exe` / macOS 的 `.app`）
- [ ] 暂无开机自启与托盘常驻图标
- [ ] Windows 真机尚未实测（开发于 macOS，理论兼容，待验证）
