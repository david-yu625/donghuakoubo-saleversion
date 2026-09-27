# Remotion 独立生产框架

这是一条和剪映模式物理隔离的生产链。它借鉴剪映模式的职责划分和图片风格，
但不读取 `src/`、剪映草稿或剪映生成的素材。当前先固定框架和合同，再做图片密度优化。

```text
01 文案 -> 02 配音 -> 03 场景事实 -> 04 视觉方向 -> 05 世界布局
       -> 06 素材准备 -> 07 Remotion manifest -> 08 分层渲染
```

| 步骤 | 层 | 输入 | 输出 | 只负责 |
| --- | --- | --- | --- | --- |
| 01 | `prepare.script` | topic | `script.json` | 标题、口播、场景、关键词、语义画面 |
| 02 | `prepare.voice` | screenplay | `narration.wav`、时长 | 豆包配音 |
| 03 | `pipeline.scene_facts` | screenplay、时长 | `scene_facts.json` | 时间、字幕、媒体类型 |
| 04 | `visual_direction.plan` | SceneFacts | `visual_plan.json` | 镜头意图、重点词、剪映图片风格 |
| 05 | `layouts.world` | SceneFacts | `layout.json` | 无限世界坐标、节点尺寸、安全区 |
| 06 | `prepare.media` | SceneFacts、VisualPlan | `runs/<topic>/assets` | 生成或复制图片/视频 |
| 07 | `renderers.remotion` | 前述产物 | `manifest.json` | 合并并校验合同 |
| 08 | `src/video` | manifest | 帧序列、MP4 | 相机、世界、媒体、关键词、字幕、音频 |

## 合同边界

`remotion_pipeline/contracts.py` 是唯一合同校验入口。

- 文案层不能写 `x/y/width/height`、字体、颜色、转场或 JSX。
- 场景事实层只增加时间和字幕，不重新设计画面。
- 视觉方向层只写语义意图，不能写像素坐标。
- 布局层才产生世界坐标和尺寸，不调用模型。
- 素材层只根据语义生成媒体，并写入 `styleId`；不能决定镜头或字幕。
- manifest 层只合并已有结果；Remotion 不再重新理解文案。

合同版本为 `remotion-scripted-v1`，图片风格为
`jianying-mg-whiteboard-v1`。该风格对应剪映模式：纯白底、MG 白板、手绘
线条、简洁扁平色块、蓝绿黄橙克制配色、留白充足、单一主对象或关系。图片
提示词在 `prepare/image_style.py` 中独立维护，不引用剪映代码。

模型配置沿用剪映模式的环境变量：文案、语义分镜和视觉内容使用
`DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`，配音使用 `DOUBAO_TTS_ACCESS_KEY`、
`DOUBAO_TTS_SPEAKER`，图片使用 `IMAGE_API_KEY`、`IMAGE_MODEL`、`IMAGE_QUALITY`。
Remotion 只消费这些阶段的文件，不在渲染过程中调用模型。

## 无限画布原则

`layout.json` 固定同时保存 viewport 和大于 viewport 的 world。`WorldLayer`
在 world 中绘制网格、节点和路线，`camera.ts` 只改变 world 的相机位置和缩放。
镜头移动时前后节点仍存在于同一张画布；字幕、标题和关键词属于屏幕安全层，
不会随世界坐标漂移。无限画布是渲染框架，而不是单个转场效果。

## 图片密度审计

`pipeline/density.py` 只审计，不在渲染层偷偷删除素材。它区分：镜头过多或过短
来自 `prepare.script`，单镜头多个素材来自素材准备层。当前每个 SceneFacts 镜头
对应一个媒体，先固定合同；后续减少图片时只改被审计指出的上游层，并重新生成后续
产物，布局和 Remotion 层保持不变。

## Remotion 层顺序

`WorldLayer`（无限画布和相机）→ `SceneMediaLayer`（图片/视频节点）→
`KeywordLayer`（重点词）→ `CaptionLayer`（口播字幕）→ `ChromeLayer`
（标题和进度）→ `AudioLayer`（旁白）。每层只读取 manifest 中属于自己的字段。
