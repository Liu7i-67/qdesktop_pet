# 需求文档：咕咕嘎嘎 Windows 桌面宠物

- 日期：2026-11-09
- 分支：feat/gugu-gaga-desktop-pet（新建独立仓库，无用户既有基线，故不建 worktree，全部开发在本分支进行）
- 需求来源：用户原话——"制作一个可以在 window 系统运行的桌面宠物，形象使用咕咕嘎嘎……在不修改任何配置的情况下，我希望它出现在电脑屏幕的最下方，在电脑屏幕底部来回踱步，鼠标和它交互时它会有动作，可以拖动它把它放到电脑的任意位置，它会自己往电脑屏幕底部跑"

## 1. 背景与目标

「咕咕嘎嘎」是《明日方舟：终末地》"管理员"的企鹅装二创爆火形象：穿黑色企鹅连体服的女孩，兜帽上有白色假眼睛与黄色喙，黑发齐刘海、灰蓝大眼、腮红、项圈 O 环、白肚皮、橙色蹼足（参考图 `_reference/ref1_merch.jpg` 2D 贴纸风、`ref3_table.jpg` 全身姿）。

目标：交付一个 Windows 可双击运行的桌宠，零配置启动即出现在屏幕最下方并来回踱步，支持鼠标交互与拖拽回底。

## 2. 功能点明细（逐条可验收）

| # | 功能 | 验收标准 |
|---|---|---|
| F1 | 零配置启动贴底 | 双击启动器后 ≤5s 出现在主屏工作区底部（自动避开任务栏），无需任何配置 |
| F2 | 底部来回踱步 | 在屏幕底边水平来回行走，随机目标点/速度/停顿，转身时水平翻转朝向 |
| F3 | 闲置行为 | 随机眨眼/张望/跳跃/发呆；60s 无交互进入睡觉（Zzz），任何鼠标事件唤醒 |
| F4 | 鼠标悬停反应 | 悬停进入时角色惊讶看向鼠标（约 800ms），离开后可再次触发 |
| F5 | 单击反应 | 单击：原地跳跃 + "咕咕嘎嘎！"气泡帧动画 |
| F6 | 双击反应 | 双击：开心动画（眯眼笑 + 挥鳍翼）后回到闲置 |
| F7 | 拖拽 | 按住可拖到屏幕任意位置（含多显示器），拖拽中显示惊慌帧 |
| F8 | 拖拽回底 | 松手后角色下落（重力抛物线）落到所在屏幕底部，落地缓冲后继续踱步 |
| F9 | 右键菜单 | 窗口与托盘图标右键菜单：暂停走动(勾选)、置顶(勾选)、退出 |
| F10 | 托盘常驻 | 托盘图标显示，气泡提示"咕咕嘎嘎来啦！"；关闭唯一窗口即退出 |
| F11 | 多显示器 | 拖到副屏后按副屏工作区贴底；位置始终钳制在所在屏幕内 |
| F12 | 交付物 | 提供 `启动咕咕嘎嘎.bat`（自动建 venv 装依赖并启动，无黑窗）+ README；另验证 PyInstaller 单文件 exe 构建可行（可行则以 exe 为最终交付物） |

## 3. 技术路线与决策记录（用户已授权全程自行决策）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 运行时 | Python 3.14 + PySide6 | 原生逐像素透明/无边框/置顶/托盘/动画定时器，桌宠事实标准；本机已装 Python 3.14。Electron 需下载百MB级运行时；tkinter 不支持逐像素 alpha（透明色键有毛边）；无 .NET SDK |
| 形象方案 | 参数化矢量 2D 逐帧精灵图（PIL 4x 超采样→LANCZOS 缩小，RGBA） | Blender 未安装且 3D 管线成本高、在 ~140px 显示尺寸收益低；直接抠用网图有版权风险（2026-07 字节已登记该形象美术版权）。矢量重绘二创贴纸风最贴近原图且干净 |
| 帧资源 | 程序生成 PNG，命名 `sprites/{anim}_{i:02d}.png` | 可版本化、可质检（预览拼图人工审）、运行时零绘制开销 |
| 交付形态 | venv+bat 启动器为主，PyInstaller exe 验证后优先 | exe 双击即用体验最好；构建失败则 bat 兜底 |
| 版权边界 | 参考形象特征矢量重绘，仅供用户本机个人使用 | 不分发、不商用 |
| 音效 | 不做 | 需求未提；避免额外资产与依赖 |

## 4. 组件拆分方案

### 目录结构与文件清单（单文件 ≤500 行）

```
gugu-gaga-desktop-pet/
├── main.py                    (~50行)  入口：QApplication、DPI、启动 PetApp      [WP4]
├── app/
│   ├── __init__.py            (~5行)                                                  [WP2]
│   ├── resources.py           (~70行)  资源路径解析(支持 PyInstaller _MEIPASS)         [WP2]
│   ├── sprite_animator.py     (~120行) 动画播放器：帧循环/单播+完成信号/翻转           [WP2]
│   ├── pet_window.py          (~280行) 透明置顶窗：事件→信号、拖拽、屏幕几何工具       [WP2]
│   ├── pet_controller.py      (~260行) 行为状态机+AI 决策（核心逻辑）                 [WP3]
│   └── pet_app.py             (~160行) 托盘图标+菜单、装配、暂停/置顶/退出            [WP4]
├── tools/
│   ├── character_art.py       (~330行) 参数化角色绘制器 draw_frame(params)->Image     [WP1]
│   ├── generate_sprites.py    (~200行) 动画关键帧表→批量导出 sprites/*.png、托盘图标  [WP1]
│   └── make_preview.py        (~60行)  全帧预览拼图 tools_out/preview.png             [WP1]
├── tests/
│   ├── conftest.py            (~40行)  offscreen QApplication fixture                 [WP5]
│   ├── test_animator.py       (~80行)                                                 [WP5]
│   ├── test_controller.py     (~160行)                                                [WP5]
│   └── test_window.py         (~120行)                                                [WP5]
├── sprites/                   生成物：{anim}_{i:02d}.png（320×320 RGBA）              [WP1]
├── assets/tray.png            托盘图标 64×64                                          [WP1]
├── requirements.txt                                                                   [WP4]
├── 启动咕咕嘎嘎.bat                                                                   [WP4]
├── README.md                                                                          [WP4]
└── docs/qdev/…md                      本文档
```

### 组件职责与对外接口（契约，开发前已冻结）

**SpriteAnimator**（`app/sprite_animator.py`）
```python
class SpriteAnimator(QObject):
    frame_changed = Signal(QPixmap)          # 每帧发射（已按 logical_size 缩放、已含翻转）
    animation_finished = Signal(str)         # 非循环动画播完，参数为动画名
    def __init__(self, sprite_dir: str, logical_size: int = 150)
    def play(self, name: str, loop: bool = True, fps: float | None = None, flipped: bool = False) -> None
    def current_animation(self) -> str
    def stop(self) -> None
```
- 帧文件约定：`{sprite_dir}/{name}_{i:02d}.png`，自动探测帧数（编号连续），`fps=None` 用各动画默认表。
- 翻转 = 水平镜像（QTransform.mirrored），同一份素材支持左右朝向。

**PetWindow**（`app/pet_window.py`）
```python
class PetWindow(QWidget):
    clicked = Signal(); double_clicked = Signal()
    drag_started = Signal(); drag_moved = Signal(QPoint)   # 窗口左上角全局坐标
    drag_released = Signal(QPoint)
    hover_entered = Signal(); hover_left = Signal()
    def __init__(self, animator: SpriteAnimator)
    def set_flipped(self, flipped: bool) -> None           # 转发给 animator.play 保持当前动画
    def move_to(self, x: float, y: float) -> None          # 逻辑坐标，钳制在当前屏幕内
    def pos_f(self) -> QPointF
    def floor_y(self) -> int        # 当前屏幕 availableGeometry().bottom()+1 - 窗口高
    def screen_rect(self) -> QRect  # 当前所在屏幕 availableGeometry()
    def apply_always_on_top(self, on: bool) -> None
```
- 窗口固定 150×150 逻辑像素；无边框+WA_TranslucentBackground+Tool+StaysOnTop； pixmap 由 animator.frame_changed 直连 `QLabel.setPixmap`。
- 拖拽判定：mousePressEvent 记录锚点；move 距离 >6px 判为拖拽（期间发 drag_started 一次）；否则 mouseReleaseEvent 发 clicked。双击用 mouseDoubleClickEvent。
- 静态工具：`PetWindow.floor_y()`/`screen_rect()` 按 `QApplication.screenAt(窗口中心)` 计算，screenAt 失败回退主屏。

**PetController**（`app/pet_controller.py`）
```python
class PetController(QObject):
    def __init__(self, window: PetWindow, animator: SpriteAnimator)
    def start(self) -> None            # 启动 33ms 行为定时器，进入 WALK
    def set_walking_paused(self, paused: bool) -> None
    def wake(self) -> None             # 任意交互唤醒（供 app 层菜单等调用）
```
- 状态机：`WALK / IDLE / DRAG / FALL / REACT(jump|happy|surprised|quack) / SLEEP`。
- WALK：随机目标 x（屏宽 20px 边距内）→ 40~90 px/s 匀速，朝向=移动方向；到达或随机 2~6s 换目标；随机小概率穿插 REACT。
- 交互接线：hover_entered→REACT_surprised(800ms)；clicked→REACT_quack（跳+气泡，跳由控制器做 y 抛物线 0→-60→0）；double_clicked→REACT_happy；drag_started→DRAG（follow drag_moved）；drag_released→FALL（重力 2000px/s²，落地用 jump 缓冲帧）→ WALK。
- SLEEP：IDLE 持续 60s 进入；任何 window 事件唤醒。
- 暂停走动：paused=True 时保持 IDLE 不移动，交互反应仍可用。

**PetApp**（`app/pet_app.py`）
- 创建托盘 QSystemTrayIcon + 共享 QMenu（暂停走动/置顶/退出，三项均联动控制器与窗口）；`aboutToQuit` 清理；退出即 `QApplication.quit()`。

**动画资产契约**（WP1 产出 ↔ WP2/3 消费，必须一致）

| 动画名 | 帧数 | fps | 循环 | 内容 |
|---|---|---|---|---|
| idle | 4 | 3 | ✓ | 呼吸起伏 + 其中1帧眨眼 |
| walk | 8 | 10 | ✓ | 身体上下+左右脚交替+鳍翼摆动 |
| drag | 2 | 6 | ✓ | 惊慌（鳍翼上举、眼睛圆睁、腿悬空） |
| jump | 6 | 12 | ✗ | 下蹲→腾空→落地压扁缓冲 |
| happy | 4 | 6 | ✗ | 眯眼^^+腮红加深+挥鳍翼 |
| quack | 4 | 8 | ✗ | 张喙+头顶气泡"咕咕嘎嘎!" |
| surprised | 2 | 6 | ✗ | 惊讶定格（瞳孔缩小+微张嘴） |
| sleep | 2 | 2 | ✓ | 闭眼+呼吸+旁侧 Zzz |
- 全部 320×320 RGBA PNG；站立帧脚底基线固定 y=312（±1px）；朝向统一面朝右（左向由运行时镜像）。
- 另导出 `assets/tray.png` 64×64（兜帽头部特写）。
- 帧内角色的主体绘制参数（颜色/部件）集中在 `character_art.py` 顶部常量区，便于调参。

### 组件依赖与数据流

`main.py → PetApp(pet_app.py) → 创建 SpriteAnimator + PetWindow + PetController 并互连信号；窗口事件→控制器→调 animator.play / window.move_to`。无网络、无数据库、单进程单线程（全部 QTimer）。

### 可复用资产映射

无既有项目资产可复用；PySide6/Pillow 为引入的外部公共库；`_reference/` 图片仅作绘制参考输入。

## 5. 数据库修改方案

不涉及。

## 6. 接口定义

不涉及（无网络接口）；进程内契约见第 4 节。

## 7. 前端/后端改动点

不涉及 Web 前后端；全部为桌面端 Python 组件（见第 4 节清单）。

## 8. 测试功能点

| # | 用例 | 断言 |
|---|---|---|
| T1 | SpriteAnimator 帧推进 | play("walk") 后按 fps 推进 QTimer，frame_changed 依次发射，尺寸=150 |
| T2 | SpriteAnimator 单播完成 | play("jump", loop=False) 播完发 animation_finished("jump") 且停末帧 |
| T3 | 翻转 | 同帧 flipped=True 时 pixmap 与原图水平镜像 |
| T4 | 贴底 | start() 后窗口底=所在屏 availableGeometry().bottom()+1 |
| T5 | 钳制 | move_to 越界值被钳制在 screen_rect() 内 |
| T6 | 拖拽流程 | 模拟 press→move>6px→release：依次收到 drag_started/drag_moved/drag_released，且 press-move<6px 只发 clicked |
| T7 | 单击反应 | clicked 后当前动画=quack；结束后回 walk/idle |
| T8 | 双击反应 | double_clicked 后动画=happy |
| T9 | 松手回底 | 拖到屏幕中部释放，FALL 结束后窗口底= floor_y() |
| T10 | 暂停走动 | set_walking_paused(True) 后 2s 内位置不变 |
| T11 | 睡眠与唤醒 | 模拟 60s 闲置（直接调内部入口）进入 sleep；hover/click 后退出 |
| T12 | 资源完整 | sprites/ 各动画帧数≥契约表、尺寸=320、RGBA、基线 y=312±2 |
| T13 | 托盘与菜单 | PetApp 构建后托盘图标可见( isVisible )，菜单含 3 个动作且可勾选项可切换 |
| T14 | 回归 | 全部用例在 offscreen 平台通过；启动 smoke：main 模块可导入可实例化不崩溃 |

T12 由 PM 在验收阶段以脚本实际执行核对；T13 在 offscreen 下仅验证对象构建与菜单结构。

## 9. 风险与红线评估

- 可行性：✅ 可行，成本可控（无不可行红线触发）。
- 风险1：PySide6 在 Python 3.14 的 wheel 可用性 → 已在 venv 实测安装通过（见验收记录）。
- 风险2：字体（气泡文字"咕咕嘎嘎"）→ 优先 `C:/Windows/Fonts/msyh.ttc`，失败回退手绘感叹号/音符，不得因字体崩溃。
- 风险3：拖拽在透明窗口的手感 → 锚点偏移取 press 相对坐标，避免跳变。
