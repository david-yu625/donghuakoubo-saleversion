# 通用动画口播工程

当前工程只维护 `src` 主流程：生成文案、配音时间线、分镜元素、图片素材、布局结果和剪映草稿。

## 目录

```text
.
├── src/       主程序、布局、视觉导演、剪映渲染和测试
├── audio/               通用背景音乐和入场音效素材
├── picturies/           默认背景和界面预览素材
├── reference_example/   示例视频文件
├── mg_asset_library/    可选图片素材库（当前仓库未内置）
├── output/              用户项目与生成结果
├── vendor/              pyJianYingDraft 依赖源码
├── .env                 本地接口配置
├── start_pipeline_app.command
└── start_pipeline_app.bat
```

`output/` 是用户数据目录，不参与代码清理。`vendor/` 是运行剪映草稿生成所需的第三方源码；`mg_asset_library/` 是可选素材库，缺失时程序会使用生成素材或占位图回退。

## 启动

使用 Python 3.11 或 3.12，安装已验证版本的依赖：

```bash
python3 -m pip install -r requirements.txt
```

系统还需要可执行的 `ffmpeg` 和 `ffprobe`。首次配置时复制 `.env.example` 为 `.env` 并填写密钥；`.env` 已被忽略，不应进入发布包。

图片生成支持在客户端选择模型。`jimeng_*` 使用火山引擎凭据；`gpt-image-2` 等其他模型使用 `IMAGE_API_KEY` 和 `IMAGE_BASE_URL` 指向 OpenAI 兼容 Images API。

环境设置固定使用“白色主题”。第 05 步统一添加手绘知识信息图风格：纯白画布、黑色粗轮廓和橙紫黄浅蓝浅绿重点色；分区框、虚线、箭头等关系工具只在第 04 步识别出的内容关系确实需要时出现。第 06 步把背景图与元素图都保存为不透明白底 PNG。元素图只裁掉主体四周多余白边，不抠图。

第 06 步会把模型返回的原始图片保存在 `generated_assets_plus/originals/`，最终处理图仍保存在 `generated_assets_plus/`。客户端的“查看并修改图片”只展示原始图片，可多选后重新生成对应元素。

macOS 或 Linux：

```bash
python3 -m src
```

Windows：

```bat
py -3 -m src
```

也可以直接运行根目录对应的启动脚本。

## 主流程

```text
01 文案
02 配音
03 分镜
04 分镜内容设计
05 生图提示词
06 图片
07 布局
08 剪映草稿
```

完整架构和视觉分区见：

- `src/ARCHITECTURE.md`
- `src/DESIGN.md`
- `src/README.md`

## 测试

```bash
python3 -m unittest discover -s src/tests -t .
```
