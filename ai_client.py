# -*- coding: utf-8 -*-
"""
ai_client —— OpenAI 兼容 API 客户端（对应 Mac 版的 ChatService.swift）

为什么按"OpenAI 兼容格式"写？
这个格式已是行业标准：DeepSeek、智谱 GLM、OpenAI、Ollama…
全都支持同一套 /chat/completions 接口，换供应商只改 config.json
里的 base_url / api_key / model 三个字段，代码零改动。

配置查找顺序：本目录(windows/) → 项目根(../)。
这样开发时共用根目录的 config.json，拷到 Windows 机器后
在 windows/ 里放一份独立配置也行。

用标准库 urllib 而不是 requests：零额外依赖，Windows 上
只需 pip install PySide6 一个包。
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urljoin


class ChatError(Exception):
    """带"人话"描述的错误，可直接显示给用户（对应 Swift 的 ChatError）"""


class ChatConfig:
    """config.json 的内存形态；缺字段用默认值，不强制写全"""

    def __init__(self, **kw):
        self.base_url = kw.get("base_url", "https://api.deepseek.com/v1").rstrip("/")
        self.api_key = kw.get("api_key", "")
        self.model = kw.get("model", "deepseek-chat")
        self.system_prompt = kw.get("system_prompt", "你是一只叫奶龙的桌宠，贱萌抽象，回复简短。")
        self.temperature = float(kw.get("temperature", 0.8))
        # 戳一戳独立温度：短句要发疯，聊天要稳定（Mac 版同款设计）
        self.poke_temperature = float(kw.get("poke_temperature", 1.5))

    @classmethod
    def load(cls) -> "ChatConfig":
        """找 config.json：exe 旁边（打包后）→ 脚本目录 → 上级目录（源码开发）"""
        from paths import app_dir
        base = app_dir()
        for path in (os.path.join(base, "config.json"),
                     os.path.join(base, "..", "config.json")):
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return cls(**json.load(f))
        print(f"⚠️ 未找到 config.json（在 {base} 放一份，参考 config.example.json）")
        return cls()   # 空配置：API 调用会失败，但桌宠本地功能照常

    @property
    def usable(self) -> bool:
        return bool(self.api_key)


class ChatService:
    """同步 HTTP 客户端。阻塞式请求——调用方必须放在后台线程跑，
    否则会冻住 30Hz 动画主循环（对应 Swift 版 async 的位置）。"""

    def __init__(self, config: ChatConfig):
        self.config = config

    def send(self, history, temperature=None, max_tokens=None) -> str:
        """history: [{"role": ..., "content": ...}, ...] → 回复文本。
        temperature / max_tokens 供"戳一戳"这类特殊场景单次覆盖。"""
        cfg = self.config
        if not cfg.usable:
            raise ChatError("还没配置 api_key，请看 config.example.json")

        # 1) 拼 URL（urljoin 处理末尾斜杠，对应 Swift 的 appendingPathComponent）
        url = urljoin(cfg.base_url + "/", "chat/completions")

        # 2) 组装请求体：人设 system 放最前，之后接对话历史
        all_msgs = list(history)
        if cfg.system_prompt:
            all_msgs.insert(0, {"role": "system", "content": cfg.system_prompt})
        body = {
            "model": cfg.model,
            "messages": all_msgs,
            "stream": False,
            "temperature": temperature if temperature is not None else cfg.temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {cfg.api_key}")
        req.add_header("Content-Type", "application/json")

        # 3) 发请求（在后台线程里阻塞 60 秒也没关系）
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            # 尽量把服务端的错误消息挖出来（如 401 = Key 错）
            try:
                msg = json.loads(e.read()).get("error", {}).get("message", "")
            except Exception:
                msg = ""
            raise ChatError(f"API 错误({e.code})：{msg}" if msg else f"API 错误，HTTP {e.code}")
        except urllib.error.URLError as e:
            raise ChatError(f"网络不通：{e.reason}")

        # 4) 解析回复
        try:
            content = json.loads(raw)["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError):
            raise ChatError("API 返回格式异常")
        if not content.strip():
            raise ChatError("API 没有返回内容")
        return content.strip()
