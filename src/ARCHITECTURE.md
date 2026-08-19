# src 架构

本目录固定采用以下调用关系：

```text
commands → application
                 ├→ prepare
                 ├→ pipeline
                 ├→ visual_direction
                 ├→ layouts
                 └→ renderers
```

其中 `prepare` 负责前置内容生成，`pipeline` 负责把准备好的文件整理成场景输入，`visual_direction` 决定视觉策略，`layouts` 负责几何计算，`renderers` 负责输出剪映草稿和预览。

后续功能扩充必须保留这个顺序和职责边界。

## 分层职责

### core

定义跨层共享的数据结构、文字测量和几何基础类型，不包含业务策略、剪映类型或项目文件读取。

### prepare

负责内容和素材准备：
- 01 生成文案
- 02 生成配音时间线
- 03 根据配音时间线识别原文已有的语义阶段；模型返回连续 timeline 索引和分镜标题，程序确定 Shot 时间和原文
- 04 只读取 `shot_timeline_source_time.csv`，按“标题|||分镜文案”处理，为每个 Shot 扩展一张包含标题和精简文字要点、留出叠加空白的背景图，并按文案字数和配音时长生成 2～5 张与背景信息互不重复的元素图
- 05 只给第 04 步的内容设计添加统一白底 Excalidraw 信息图风格规则，输出带素材路径的任务表
- 06 按元素类型生成素材：人物和道具使用文生图，箭头、曲线、空白标签牌等文字敏感素材使用确定性原生图形
- 草稿生成前准备项目级统一背景，按画布方向输出到 `prepared_assets/background_<宽>x<高>.png`
- 草稿生成前从默认 `audio/bgm/bgm1.mp4` 无损提取项目级背景音乐，输出到 `prepared_assets/background_music.m4a`
- 背景图与元素图都使用不透明白底；不抠图，背景保留完整画布，元素只裁掉主体四周多余白边

该层还负责校验大模型输出的 Shot 范围，Shot 必须覆盖对应 timeline 文案和全部元素。它不做布局和渲染。

### pipeline

读取准备阶段输出的文案、时间线、分镜、元素和素材，组装 `SceneFacts`。它描述场景中有什么，不决定如何表现。

元素素材表固定为：

```text
element_id,shot_id,type,role,content,start_ms,end_ms,asset_path
```

该表不保存布局、动画或跨镜头控制字段。

`pipeline` 将每行转换为 `SceneElement`，元素时间改为相对当前 Shot 的时间，但不丢弃或重写。`SceneFacts` 固定包含：

```text
scene_id / scene_index
start_ms / end_ms / duration_ms
source_text / title
elements[]: element_id / type / role / content / start_ms / end_ms / source_content
semantic_role
```

### visual_direction

根据整条视频上下文生成 `VisualPlan`，决定布局模板、布局变体、字体角色、动画语义、视觉强度、进入顺序和入场音效语义。字体预设按场景编号轮换；动画和转场从枚举候选中随机选择，并过滤禁用项、避免相邻重复。音效设计只标记图片、标题和展示区关键词，合并相近触发点，并限制全片密度；底部口播字幕不触发音效。`sequence`、`process`、`risk` 使用 `timeline_flow`，只有明确的 `compare` 语义才使用 `split_compare`。该层禁止生成坐标、尺寸、缩放和关键帧数值。

环境设置固定使用白色主题：`settings` 固化标题、整片背景、字幕和白底生图模式；各业务层只读取与自身职责相关的字段，不在渲染器或项目数据中重新选择主题。

### layouts

根据 `VisualPlan.layout`、画布、元素时间和白底素材的有效主体尺寸计算 `Box` 与层级。新版板书统一使用
`background_stack`：背景图覆盖画布，横屏元素从左到右、竖屏元素从上到下进入确定性槽位。布局层硬校验标题区、
字幕区、画布安全边距和元素碰撞，失败时不输出布局结果。该层不读取 CSV，不调用剪映 API。

### renderers

把 `LayoutResult` 和视觉指令转换为剪映字体、角色字号、原生动画、持续运镜关键帧、轨道、字幕样式、旁白音量、背景音乐、入场音效和草稿文件。音频固定分为旁白 `narration`、背景音乐 `background_music` 和入场音效 `sound_effects` 三类轨道。背景音乐低音量铺满全片，素材不足时自动循环；渲染器从项目内稳定音效库解析具体音效，音效与被选元素的入场时刻严格对齐。布局层字号通过统一的角色映射转换为剪映字号，字幕宽度必须服从布局安全区；全局标题从第一帧直接使用最终位置和样式，不添加入场关键帧，也不触发音效。该层不选择布局模板，不理解原始文案。

### 独立平台发布

`application/jianying_automation.py` 和 `application/douyin_publisher.py` 只由 Qt 界面按钮调用，不属于 01～08 生产流程，不修改 `Runner` 或任何内核产物。剪映操作负责打开已有草稿；抖音操作使用独立的持久化浏览器配置上传视频、填写元数据，并在用户确认后点击发布。

### application

按固定顺序调用输入、前置准备、视觉导演、布局和渲染用例。它只负责编排层之间的数据流，不保存字体、动画或布局规则。

### commands

组合各层并提供命令行入口，不包含布局、字体或动画业务规则。

## 稳定依赖规则

- `prepare`、`pipeline`、`visual_direction`、`layouts` 和 `renderers` 彼此保持独立，由 `application` 组合。
- `prepare` 不依赖 `layouts` 或 `renderers`。
- `pipeline` 不依赖 `visual_direction`、`layouts` 或 `renderers`。
- `visual_direction` 不依赖 `layouts` 或 `renderers`。
- `layouts` 不依赖 `prepare`、`pipeline`、`renderers` 或剪映库。
- `renderers` 可以依赖 `core`，并消费上游已经生成的结果。
- `application` 可以依赖所有业务层，`commands` 只能依赖 `application` 或单一展示用例。
- 新准备步骤只增加到 `prepare/` 对应模块。
- 新输入格式只增加到 `pipeline/`。
- 新布局只增加到 `layouts/`。
- 新导演规则只增加到 `visual_direction/`。
- 新剪映字体和动画映射只增加到 `renderers/`。

## 扩展原则

后续优化效果时只扩充以下内容：

```text
prepare:           更多主题、beat 结构和前置生成步骤
pipeline:          更多输入格式和素材来源
visual_direction:  更多节奏、字体、动画和防重复规则
layouts:           更多布局家族和变体
renderers:         更多剪映能力映射
```

不得把模板选择重新放回 `pipeline`，不得让布局组件直接调用剪映 API，也不得让大模型输出坐标。

## 流程示例

以主题 `什么是示例主题` 为例：

### 1. prepare

输入：
- 主题：`什么是示例主题`
- 故事世界：`西游记`
- 最长字数：`500`

输出：
- `output/什么是示例主题/wenan.txt`
- `output/什么是示例主题/narration.wav`
- `output/什么是示例主题/timeline.csv`
- `output/什么是示例主题/shot_timeline_source_time.csv`
- `output/什么是示例主题/storyboard_prompts.csv`
- `output/什么是示例主题/image_prompts_plus.csv`
- `output/什么是示例主题/element_timeline_with_assets.csv`

### 2. pipeline

输入：
- `output/什么是示例主题/element_timeline_with_assets.csv`
- `output/什么是示例主题/shot_timeline_source_time.csv`
- `output/什么是示例主题/timeline.csv`
- `output/什么是示例主题/narration.wav`
- `mg_asset_library/images/...`
- `output/什么是示例主题/generated_assets_plus/...`

输出：
- `SceneFacts`
  - scene_id
  - scene_index
  - start_ms / end_ms / duration_ms
  - title
  - source_text
  - elements（每个元素保留相对时间）
  - semantic_role

### 3. visual_direction

输入：
- `SceneFacts`

输出：
- `VisualPlan`
  - layout
  - typography
  - motion
  - enter_order

### 4. layouts

输入：
- `VisualPlan.layout`
- `SceneContent`
- `Canvas`
- `Theme`

输出：
- `LayoutResult`
  - 元素坐标
  - 层级
  - 动画建议
  - 布局决策

### Orientation artifact isolation

The pipeline keeps portrait and landscape runs in separate project directories:

```text
output/<topic>/portrait/
output/<topic>/landscape/
```

All direction-dependent files live below that directory, including prompt CSVs,
generated image assets, prepared assets, and `layout_result.json`. Jianying
draft names receive the same orientation suffix. A legacy project directory
without this suffix remains readable when passed directly to the compiler, but
new GUI runs always use the isolated directory.

### Portrait packaging workflow

Portrait packaging is a post-production workflow, not a third orientation. It
accepts an exported landscape video plus the matching landscape project's
`timeline.csv`, then creates a separate `1080x1920` Jianying draft with:

- a portrait background prepared from `picturies/background/background_1.png`;
- one centered landscape video layer fitted to the portrait canvas width with a
  native rectangular rounded-corner mask;
- an optional title in the upper background region;
- optional narration subtitles in the lower background region.

The exported landscape video remains the only audio source. The packaging
workflow does not regenerate prompts or images and does not add narration,
background music, or sound effects again.

### 5. renderers

输入：
- `LayoutResult`
- `VisualPlan`
- 目标草稿目录

输出：
- 剪映草稿
- 预览图
- 可视化产物
