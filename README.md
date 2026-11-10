# 咕咕嘎嘎 —— Windows 桌面宠物

「咕咕嘎嘎」是一只穿黑色企鹅连体服的桌宠：兜帽上有白色假眼睛与黄色喙、齐刘海与大
灰蓝眼、项圈 O 环 + 银色登山扣、白肚皮、橙色蹼足，形象对标原素材绘制。
双击启动后它会出现在屏幕最下方，贴着任务栏来回踱步——行走时使用侧视图（向左走
左视图、向右走右视图），停下休息时转回正面；鼠标逗它会有反应，可以把它拖到屏幕
任意位置，松手后它会自己跑回屏幕底部。全部素材为程序生成的矢量贴纸风帧动画，
无需联网、无后台服务，单进程单线程（全部 QTimer 驱动）。

> 本项目仅供交流学习使用，请勿用于商业用途；因使用本作品而产生的任何问题，
> 需由使用者自行承担相关责任。

## 功能列表

| # | 功能 | 说明 |
|---|------|------|
| F1 | 零配置启动贴底 | 双击启动器后 ≤5s 出现在主屏工作区底部（自动避开任务栏） |
| F2 | 底部来回踱步 | 屏幕底边水平行走，随机目标点/速度/停顿；行走用左/右侧视图（镜像切换朝向），停顿回正面 |
| F3 | 闲置行为 | 随机眨眼/张望/跳跃/发呆；60s 无交互进入睡觉（Zzz），任何鼠标事件唤醒 |
| F4 | 鼠标悬停反应 | 悬停进入时角色惊讶看向鼠标（约 800ms），离开后可再次触发 |
| F5 | 单击反应 | 原地跳跃 + 「咕咕嘎嘎！」气泡帧动画 |
| F6 | 双击反应 | 开心动画（眯眼笑 + 挥鳍翼）后回到闲置 |
| F7 | 拖拽 | 按住可拖到屏幕任意位置（含多显示器），拖拽中显示惊慌帧 |
| F8 | 拖拽回底 | 松手后角色沿重力抛物线落到所在屏幕底部，落地缓冲后继续踱步 |
| F9 | 右键菜单 | 窗口与托盘图标共用一份右键菜单：暂停走动(勾选)、置顶(勾选)、退出 |
| F10 | 托盘常驻 | 托盘图标显示，气泡提示「咕咕嘎嘎来啦！」；关闭唯一窗口即退出 |
| F11 | 多显示器 | 拖到副屏后按副屏工作区贴底；位置始终钳制在所在屏幕内 |

## 运行方法

### 方式一：双击启动器（推荐）

1. 确认已安装 Python 3.10+（已加入 PATH）；
2. 双击项目根目录的 **`启动咕咕嘎嘎.bat`**；
3. 首次运行会自动创建 `.venv` 虚拟环境并安装依赖（需要联网下载 PySide6），
   之后每次双击直接启动，无黑窗。

### 方式二：手动 venv 运行

```bat
cd /d <项目目录>
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\pythonw.exe main.py
```

> 调试时可换用 `python.exe` 在控制台运行；正式使用建议 `pythonw.exe`（无控制台窗口）。

## 开发说明

### 重新生成素材（sprites/ 与 assets/tray.png）

素材由 `tools/` 下的参数化矢量绘制器生成（正面 `character_art.py`、
侧面 `character_side.py`），需要 Pillow：

```bat
.venv\Scripts\python.exe tools\generate_sprites.py   # 导出 sprites/*.png + assets/tray.png
.venv\Scripts\python.exe tools\make_preview.py       # 生成全帧预览拼图 tools_out/preview.png
```

调整角色外观：正面编辑 `tools/character_art.py` 顶部的部件/颜色常量区，
侧面编辑 `tools/character_side.py` 顶部的 `S_*` 布局常量区，然后重新生成。

### 跑测试

```bat
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python.exe -m pytest tests\ -v
```

测试文件与需求验收用例（T1–T14）的对应关系如下（offscreen 平台可重复运行）：

| 测试文件 | 覆盖用例 | 内容 |
|---|---|---|
| `tests/conftest.py` | — | offscreen QApplication fixture、测试用精灵帧生成 |
| `tests/test_animator.py` | T1 / T2 / T3 | 帧推进与回绕、pixmap 尺寸=150、单播完成信号、水平镜像翻转 |
| `tests/test_window.py` | T4 / T5 / T6 / T14 | 启动贴底、move_to 钳制、拖拽信号序列、main 导入冒烟 |
| `tests/test_controller.py` | T4(控制器层) / T7–T11 | 起步贴底并行走、单击/双击反应、松手回底、暂停走动、睡眠与唤醒 |
| `tests/test_assets.py` | T12 | sprites/ 各动画帧数、320×320 RGBA、脚底基线 y=312±2 |
| `tests/test_pet_app.py` | T13 + 关窗退出回归 | 托盘可见/tooltip/气泡、菜单结构与勾选态、暂停/置顶/退出联动、closed→quit |

### 代码结构速览

- `app/sprite_animator.py`：帧动画播放器，`frame_changed`/`animation_finished` 信号；
- `app/pet_window.py`：透明无边框置顶窗口，鼠标事件转信号、拖拽、屏幕几何工具；
- `app/pet_controller.py`：行为状态机（WALK/IDLE/DRAG/FALL/REACT/SLEEP）与 AI 决策；
- `app/pet_app.py`：托盘图标 + 共享右键菜单组装层（暂停/置顶/退出）；
- `main.py`：入口，组装以上组件并进入事件循环。

## 打包为单文件 exe（PyInstaller）

```bat
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\pyinstaller.exe -F -w --name GuguGaga ^
  --add-data "sprites;sprites" ^
  --add-data "assets;assets" ^
  main.py
```

- `-F` 单文件、`-w` 无控制台窗口；
- `--add-data` 把动画帧与托盘图标打进包内（`app/resources.py` 已兼容
  PyInstaller 的 `_MEIPASS` 临时目录解包路径）；
- 产物位于 `dist/GuguGaga.exe`，双击即可运行；如需中文文件名可自行重命名。

## 目录结构

```
gugu-gaga-desktop-pet/
├── main.py                  # 程序入口
├── app/
│   ├── __init__.py
│   ├── resources.py         # 资源路径解析（兼容 PyInstaller _MEIPASS）
│   ├── sprite_animator.py   # 精灵帧动画播放器
│   ├── pet_window.py        # 透明置顶宠物窗口（拖拽/贴底/多屏）
│   ├── pet_controller.py    # 行为状态机 + AI 决策
│   └── pet_app.py           # 托盘图标 + 全局菜单组装层
├── tools/
│   ├── character_art.py     # 参数化角色绘制器（正面视图）
│   ├── character_side.py    # 参数化角色绘制器（侧面视图，walk_side 用）
│   ├── generate_sprites.py  # 批量导出 sprites/*.png、assets/tray.png
│   └── make_preview.py      # 全帧预览拼图
├── tests/                   # pytest 用例（offscreen 运行）
├── sprites/                 # 生成物：{动画名}_{帧号}.png（320×320 RGBA）
├── assets/tray.png          # 托盘图标 64×64
├── requirements.txt
├── 启动咕咕嘎嘎.bat          # 一键启动器
└── docs/qdev/               # 需求文档
```

## 版权与使用说明

本项目的角色形象为参数化矢量重绘，形象对标「咕咕嘎嘎」（《明日方舟：终末地》
「管理员」企鹅装二创形象）原素材追求还原，兜帽假眼/黄喙、齐刘海大眼、项圈登山扣、
白肚皮等特征均来自原形象：

- 本项目与生成的素材**仅供交流学习使用**，请勿用于商业用途；
- 因使用本作品而产生的任何问题，由使用者自行承担相关责任；
- 原始形象的美术权利归原权利方所有；
- 参考图（`_reference/`）仅作本地绘制参考输入。
