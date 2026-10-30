# -*- coding: utf-8 -*-
"""
路径中枢：统一处理「源码运行」与「PyInstaller 打包后」的差异。

打包成单文件 exe 后的世界和平时代码不一样：
  - 代码和资源被解包到一个**临时目录**（sys._MEIPASS），每次启动都是新的
  - exe 自己躺在用户放的任意位置

所以路径分两类：
  resource_dir() → 只读资源（sprites/）：打包后从临时解包目录读
  app_dir()      → 用户数据（config.json / chat_history.json）：
                   打包后放在 **exe 旁边**——用户要能找到、能编辑、能备份

getattr(sys, "frozen", False) 是 PyInstaller 的官方探测方式。
"""

import os
import sys


def resource_dir() -> str:
    """只读资源目录（sprites 等）"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS                    # 单文件模式的解包临时目录
    return os.path.dirname(os.path.abspath(__file__))


def app_dir() -> str:
    """用户数据目录（config.json / chat_history.json）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)  # exe 所在目录
    return os.path.dirname(os.path.abspath(__file__))
