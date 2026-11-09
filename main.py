"""咕咕嘎嘎 —— Windows 桌面宠物程序入口。

用法：
    1. 双击项目根目录的 ``启动咕咕嘎嘎.bat``（推荐）：
       首次运行自动创建 .venv 并安装依赖，随后无黑窗启动。
    2. 手动运行：
           python -m venv .venv
           .venv\\Scripts\\python.exe -m pip install -r requirements.txt
           .venv\\Scripts\\pythonw.exe main.py

说明：
    - 基于 PySide6（Qt6 自动启用高 DPI 缩放，无需手动设置 AA 宏）；
    - 启动流程：QApplication → SpriteAnimator → PetWindow → PetController
      → PetApp（托盘/菜单组装）→ controller.start() → window.show() → 事件循环；
    - sprites/ 素材缺失等致命错误会弹出中文提示并以退出码 1 结束；
    - 本模块仅作为入口：被 import 时不会启动事件循环（__main__ 保护）。
"""
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.pet_app import PetApp
from app.pet_controller import PetController
from app.pet_window import PetWindow
from app.resources import asset_path, sprite_dir
from app.sprite_animator import SpriteAnimator

APP_NAME = "咕咕嘎嘎"


def main() -> None:
    app = QApplication(sys.argv)  # Qt6 自动高 DPI，无需 AA_* 宏
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(QIcon(asset_path("tray.png")))

    try:
        animator = SpriteAnimator(sprite_dir())
        window = PetWindow(animator)
        controller = PetController(window, animator)
        pet_app = PetApp(window, controller)
    except Exception as exc:  # 兜底：素材缺失等致命错误，弹中文提示后退出
        QMessageBox.critical(
            None,
            APP_NAME,
            "启动失败：" + str(exc) + "\n\n"
            "请确认项目目录下存在 sprites/ 动画帧与 assets/tray.png。\n"
            "可运行 tools/generate_sprites.py 重新生成素材后重试。",
        )
        sys.exit(1)

    controller.start()          # 行为状态机开始踱步
    window.show()               # 宠物窗口贴底出现
    pet_app.bind_window_menu()  # 共享菜单接到窗口右键
    pet_app.show_tray()         # 托盘常驻 + 气泡「咕咕嘎嘎来啦！」

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
