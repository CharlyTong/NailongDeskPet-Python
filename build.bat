@echo off
chcp 65001 >nul
REM ============================================================
REM  一键打包 Windows exe（在 Windows 机器上双击本文件运行）
REM  产物：dist\NailongDeskPet.exe
REM  使用：把 exe 和 config.json 放同一文件夹，双击即可
REM ============================================================

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\python -m PyInstaller NailongDeskPet.spec --noconfirm --clean

echo.
if exist dist\NailongDeskPet.exe (
    echo 打包成功！exe 在 dist\NailongDeskPet.exe
    echo 记得在 exe 旁边放一份 config.json（参考 config.example.json）
) else (
    echo 打包失败，把上面的报错发给我
)
pause
