# src 概要设计

`src` 把知识主题转换成文案、配音、分镜、图片素材、布局结果和剪映草稿。前置生成步骤负责准备文件，核心画面链路固定为：

```text
pipeline -> visual_direction -> layouts -> renderers
```

## 数据流

```text
主题
  |
  v
01 文案 -> wenan.txt（一件事：总论点 -> 四个大点 -> 分层细节）
  |
  v
02 配音 -> narration.wav + timeline.csv
  |
  v
03 分镜 -> shot_timeline_source_time.csv（语义边界 + 分镜标题）
  |
  v
04 图片内容设计 -> storyboard_prompts.csv
                    （每镜一张标题与文案背景 + 按字数和时长动态生成 2～5 张连续元素图；只扩展画什么）
  |
05 生图提示词 -> image_prompts_plus.csv（统一纯白底手绘知识信息图风格）
                  + element_timeline_with_assets.csv
  |
  v
06 图片 -> generated_assets_plus/
  |
  v
07 pipeline -> SceneFacts -> visual_direction -> layouts -> layout_result.json
  |
  v
08 背景/BGM准备 -> renderers -> 剪映草稿
```

## 核心边界

- `pipeline/` 读取 CSV、字幕和素材，整理场景事实，不选择布局。
- `visual_direction/` 选择模板、字体角色和动效语义，不计算坐标。
- `layouts/` 使用模板计算坐标、尺寸、字号、层级和降级结果，不读取 CSV。
- `renderers/` 把布局结果转换为剪映轨道、动画和关键帧，不重新选择布局。
- `application/` 只按固定顺序编排这些层。

## 主要产物

| 产物 | 来源 | 用途 |
| --- | --- | --- |
| `wenan.txt` | 01 文案 | 口播文案 |
| `narration.wav` | 02 配音 | 旁白音频 |
| `timeline.csv` | 02 配音 | 真实配音时间线 |
| `shot_timeline_source_time.csv` | 03 分镜 | 分镜标题、时间和原始文案 |
| `storyboard_prompts.csv` | 04 分镜内容设计 | 根据 Shot 原文扩展的完整背景图和元素图内容 |
| `image_prompts_plus.csv` | 05 生图提示词 | 只按图片类型添加视觉风格和模型规则 |
| `element_timeline_with_assets.csv` | 05 生图提示词 | 带素材路径的元素表 |
| `generated_assets_plus/` | 06 真实图片 | 自动生成的真实图片素材 |
| `prepared_assets/background_<宽>x<高>.png` | 08 草稿 | 按画布方向生成统一背景 |
| `prepared_assets/background_music.m4a` | 08 草稿 | 从默认 `bgm1.mp4` 提取的项目背景音乐 |
| `audio/sound_effect/library/*.mp3` | 项目固定素材 | 从参考草稿整理出的稳定入场音效库 |
| `layout_result.json` | 07 布局 | 08 直接消费的完整 `LayoutResult` |
| 剪映草稿目录 | 08 草稿 | 最终可编辑项目 |

03 输出字段为 `shot_id,分镜标题,开始时间ms,结束时间ms,分镜对应原始文案内容`。Shot 数量完全由原文已有的
语义阶段决定。模型返回连续 timeline 行的起止索引和每个阶段的成品标题；时间和原文由程序从
`timeline.csv` 生成。03 不产生图片内容或视觉决策。

04 是唯一决定“画什么”的步骤。它按“标题|||分镜文案”读取 03 的每个 Shot，为每个 Shot 输出一张包含标题和精简文字要点、留出叠加空白的背景图，并根据文案字数和配音时长确定 2～5 张局部元素图。每张元素图只承载一个独立视觉信息，全部元素逐步拼成完整板书。背景文字与元素图分担文案信息且互不重复。04 不重新概括标题，不强制总分结构，也不写颜色、画风或模型参数。
05 是唯一决定“怎么画”的步骤，不增加或改写 04 已确定的对象、动作和关系。

06 直接生成不透明白底 RGB PNG，不进行抠图或透明化。背景图保留完整画布，元素图只裁掉多余白边；
07 使用 `background_stack`：背景图覆盖画布，2～5 张元素图使用渐进槽位。横屏 5 图采用上三下二的居中构图，竖屏从上到下等距排列；元素随入场阶段动态重排。
元素按素材真实可见尺寸等比缩放，标题区、字幕区、画布安全边距和元素间距均由代码硬校验；任何越界或碰撞都会阻止
`layout_result.json` 输出。08 只读取该结果添加剪映轨道、入场动画、音效和音频，不重新计算位置。

`05_generate_image_prompts.py` is the step entry point; its implementation is in `prepare/image_prompts.py`. It does not participate in shot continuity or time derivation, and only adds `asset_path` to this table:

```text
element_id,shot_id,type,role,content,start_ms,end_ms,asset_path
```

元素只属于自己的 `shot_id`。跨镜头连续性由 `visual_direction` 和 `layouts` 根据完整视频上下文处理，不在 CSV 中保存 `cross_shot` 一类控制字段。

GUI 默认执行第 06 步。`06_generate_images.py` calls the image service from `prepare/image_generation.py`; the step implementation is in `prepare/images.py`.

生成完整草稿时，`application` 会调用 `prepare` 在项目目录中确定性生成统一背景，并从 `audio/bgm/bgm1.mp4` 提取背景音乐。背景音乐以低音量独立音轨铺满全片，时长不足时自动循环。图片和展示区关键词的入场动画会由视觉层分配克制的音效语义：相近时刻只保留一个，任意 4 秒最多两个；渲染层再从项目音效库中确定性轮换具体声音并写入独立音轨。字幕和顶部全局标题不参与音效触发。

## 布局体系

布局核心位于 `layouts/`：

```text
layouts/
├── engine.py       模板注册、选择和执行
└── templates.py    具体几何布局、文字适配和降级规则
```

当前板书主模板为 `background_stack`；其他通用模板只用于兼容旧项目。`VisualDirector` 根据场景语义选择模板，
`LayoutEngine` 再计算具体元素。新版板书场景中的文字由背景图标题和元素图内容承载，不另设会与图片争抢位置的文字栏。

项目不使用单独的 `layout_strategies` 层，也不再生成旧的 `motion_layout_source_time.csv`。动画语义保存在 `VisualPlan` 和 `AnimationSpec` 中，由渲染器转换成剪映能力。

### 竖屏视觉分区

1080x1920 画布按固定安全区编排：

- `y=0–395`：背景图中的分镜标题区，元素图禁止进入。
- `y=396–1425`：板书元素安全内容区；4~5 张元素图从上到下使用互不重叠的固定槽位。
- `y=1454–1614`：底部口播字幕区，使用“未光体”白字、玫红底和轻阴影；长句在编译层先按标点和语义词切成连续的单行字幕，再移除可见标点，不由剪映自动换行。

横屏 1920x1080 使用同一规则：背景图覆盖画布，标题保留区在顶部，元素在中部从左到右排列，底部保留字幕安全距离。
CSV 和提示词层不保存任何坐标或字体信息。
