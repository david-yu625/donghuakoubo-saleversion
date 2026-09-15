# src

`src` 是一个面向通用知识动画讲解的、数据驱动的工作流。它先把内容整理成稳定的输入，再由后续渲染器转换成剪映草稿。

## 目录与功能阶段

```text
src/
├── core/             共享数据模型、几何计算、文本测量
├── pipeline/         读取文案、字幕、元素和素材
├── visual_direction/ 布局导演、字体、动效和整片节奏
├── layouts/          布局模板、几何计算、降级和重排
├── renderers/        输出剪映草稿或 PNG 预览
├── application/      按固定顺序组合以上业务层
├── commands/         单场景、完整项目和预览命令
├── examples/       示例场景输入
└── tests/          布局回归测试
```

阶段之间的数据流：

```text
commands
  -> application
      -> pipeline 生成 SceneFacts
      -> visual_direction 生成 VisualPlan
      -> layouts 生成 LayoutResult
      -> renderers 生成剪映草稿或 PNG
```

最终分层、依赖方向和扩展规则固定在 [ARCHITECTURE.md](ARCHITECTURE.md)。后续增加能力只在对应层内部扩充，不改变处理顺序。

## 固定画面区域

竖屏 `1080x1920` 使用固定标题、展示和字幕安全区：

```text
顶部标题条：约 y=155-287px，中心为剪映坐标 y=0.77
主要内容区：y=340-1480px
底部字幕中心：约 y=1534px，剪映坐标约 y=-0.60
底部安全区：字幕下方继续保留平台操作区空间
```

所有新增布局必须使用 `Canvas.content_top` 和 `Canvas.content_bottom`，不得侵入全局标题条或字幕区域。

当前模板：

- `board_overview`：第一分镜展示总图和 `1、2、3、4` 四个大点
- `board_section`：后续分镜把 `1.1、1.2` 等小点与元素图一一配对
- `timeline_flow`：图片与关键词按时间段共同编排
- `title_image`、`single_side`、`single_focus`：单图构图
- `focus_history`、`multi_grid`、`multi_stack`：多图构图
- `split_compare`：明确对比语义
- `quote`：纯文字场景

运行布局预览：

```bash
cd /path/to/caijingkepu
python3 -m src.commands.cli layout \
  src/examples/scene.json \
  --output output/layout_example.json
```

运行测试：

```bash
python3 -m unittest \
  src.tests.test_layout \
  src.tests.test_visual_direction \
  src.tests.test_architecture
```

输出结果包含：

- 每个元素的像素位置和尺寸
- 字号和真实换行结果
- 元素的时间范围和入场动画建议
- 超出区域、文字降级和图片容量的警告
- 从布局坐标转换到剪映归一化坐标所需的数据

生成 PNG 预览：

```bash
python3 -m src.commands.render_preview \
  src/examples/focus_history.json \
  --output output/focus_history.png
```

从已有项目输出编译布局，再生成完整草稿：

```bash
python3 -m src.07_compile_layout \
  output/什么是示例主题 \
  --title 什么是示例主题 \
  --output output/什么是示例主题/layout_result.json

python3 -m src.08_generate_jianying_draft \
  output/什么是示例主题 \
  --layout output/什么是示例主题/layout_result.json \
  --title 什么是示例主题 \
  --draft-name src_什么是示例主题 \
  --replace
```

完整编译器读取 `element_timeline_with_assets.csv`、`shot_timeline_source_time.csv`、`timeline.csv` 和 `narration.wav`。大模型只提供内容和语义，分镜模板、坐标、字号、图片尺寸和安全区全部由本目录的 Python 代码计算。

图片素材按以下顺序解析：CSV 中存在的真实素材、可选的 `mg_asset_library/images` 素材库、项目占位图。素材库缺失时会自动回退，素材库回退按固定顺序分配，确保重复生成得到一致画面。

布局组件只负责空间计算。入场顺序保存在 `AnimationSpec` 中，剪映渲染器会在下一层把它转换成关键帧或剪映动画。

`jianying_renderer.py` 负责把像素布局转换为剪映归一化坐标、素材缩放和入场关键帧。相对素材路径统一按项目根目录解析。

## 快速使用

```text
1. 输入主题
2. 生成文案和前置文件
3. 整理输入并生成布局
4. 输出剪映草稿或预览
```

## 使用说明

```text
src 使用说明

1. 项目定位
- 这是一个面向通用知识动画讲解的工作流。
- 输入一个主题，输出可用于剪映的完整动画项目。
- 适合历史、科学、生活、人物、机制类内容。

2. 总流程
- prepare：生成内容和前置文件
- pipeline：整理输入，组装 SceneFacts
- visual_direction：决定视觉策略
- layouts：计算位置和大小
- renderers：输出剪映草稿和预览

3. prepare 阶段
- 01_generate_copywriting.py (entry; implementation in prepare/copywriting.py)
  - 输入：主题、故事载体、最长字数
  - 输出：wenan.txt
  - 围绕一个中心问题组织“总论点 -> 四个大点 -> 每个大点的细节”，保证内容能逐层讲清
- 02_generate_voice_timeline.py (entry; implementation in prepare/voice_timeline.py)
  - 输入：wenan.txt
  - 输出：narration.wav、timeline.csv
- 03_generate_shot_timeline.py (entry; implementation in prepare/shot_timeline.py)
  - 输入：wenan.txt、timeline.csv
  - 输出：shot_timeline_source_time.csv
  - 按原文已有的语义阶段划分连续 Shot，不预设 Shot 数量
  - 为每个 Shot 输出可直接显示的分镜标题；不生成图片内容、景别、运镜、光影或风格
- 04_generate_storyboard_prompts.py (entry; implementation in prepare/storyboard_prompts.py)
  - 输入：shot_timeline_source_time.csv
  - 输出：storyboard_prompts.csv
  - 每个 Shot 按“标题|||分镜文案”处理：生成一张包含标题和精简文字要点、并留出元素叠加空白的 1920*1080 背景图提示词
  - 每个 Shot 至少生成 2 张能够逐步拼成同一幅板书的元素图提示词；背景文字与元素图分担文案信息且互不重复
- 05_generate_image_prompts.py (entry; implementation in prepare/image_prompts.py)
  - 输入：storyboard_prompts.csv
  - 输出：image_prompts_plus.csv、element_timeline_with_assets.csv
  - 只给第04步内容添加统一纯白底 Excalidraw 白板信息图风格及横竖屏规则，不重新解释文案或增加对象
- 06_generate_images.py (entry; implementation in prepare/images.py)
  - 输入：image_prompts_plus.csv
  - 输出：generated_assets_plus/
  - 人物和道具默认调用即梦；箭头、曲线、空白标签牌和日期牌使用确定性原生图形
  - 背景图和元素图统一保存为不透明白底 RGB PNG，不进行背景移除或透明化
  - 背景图保留完整画布；元素图只裁掉主体四周多余白边
  - 图片统一保存到每条 `asset_path`

4. pipeline 阶段
- 读取 element_timeline_with_assets.csv
- 读取 shot_timeline_source_time.csv
- 读取 timeline.csv
- 读取 narration.wav
- 读取素材路径
- 校验 Shot 覆盖范围
- 组装带元素相对时间和语义角色的 SceneFacts

5. visual_direction 阶段
- 根据 SceneFacts 决定布局模板
- 顺序、流程和风险场景使用 timeline_flow；明确对比场景才使用 split_compare
- 决定字体、动效、进入顺序
- 不输出坐标，不碰剪映草稿

6. layouts 阶段
- 计算每个元素的位置、大小、字号、层级
- 保留元素源时间，按白底图片的有效主体尺寸计算布局
- 新版板书统一使用 `background_stack`：背景铺满，横屏元素从左到右、竖屏元素从上到下逐步累加
- 对标题区、字幕区、画布安全边距和元素碰撞执行硬校验，失败时不输出布局结果
- 输出 LayoutResult

7. renderers 阶段
- 把 LayoutResult 转成剪映草稿
- 映射克制的入场动画、字幕样式、音效和旁白音量
- 也可以输出预览图
- 不重新做布局决策或修改元素位置

8. 布局编译与草稿
- `python3 -m src.07_compile_layout ...` 输出 `layout_result.json`
- `python3 -m src.08_generate_jianying_draft ...` 读取该 `layout_result.json` 并输出剪映草稿；08 不重新计算布局

9. GUI 用法
- 直接运行 `python3 -m src`
- 输入主题后点击开始执行
- 可单步运行，也可一键跑全流程
- 默认勾选“自动生成真实图片（即梦）”；关闭后可以先用素材库或占位图预览

10. 发布作品
- 在当前主题工作台进入“作品发布”，会自动扫描该主题的最新导出视频和作品封面。
- 可以手动选择视频或封面，填写作品标题、话题和描述，然后确认发布。
- 发布使用专用浏览器配置，首次点击“登录/检查抖音”后登录一次即可；程序不会读取现有浏览器账号。
- 首次安装依赖后，如本机没有可用 Chrome/Edge，请执行 `python3 -m playwright install chromium`。

11. 推荐使用顺序
- 先跑 prepare
- 再跑 pipeline
- 再跑视觉、布局、渲染
- 如果只做预览，可以先停在 prepare 后面

11. 目录理解
- `core/`：基础数据模型
- `prepare`：前置生成步骤
- `pipeline/`：输入整理
- `visual_direction/`：视觉策略
- `layouts/`：空间计算
- `renderers/`：草稿输出
- `examples/`：示例输入
- `tests/`：回归测试
```
