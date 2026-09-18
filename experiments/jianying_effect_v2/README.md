# 剪映效果 v2 实验

这里是与正式流程隔离的预演目录。它只读取已有主题项目中的：

- `layout_result.json`
- `generated_assets_plus/` 或布局文件引用的图片
- `narration.wav`
- 项目背景与背景音乐

实验会把一份新的布局写到 `experiments/jianying_effect_v2/runs/<主题>/`。默认草稿也放在该目录下；使用 `--install-to-jianying` 时，会用 `实验_v2_<主题>` 的独立名称安装到剪映草稿目录，便于在剪映首页查看。不会修改 `src/`、`output/` 中的正式文件，也不会覆盖正式草稿。

## 当前效果方向

`v2_rhythm_focus`：

- 图片镜头轮换使用推近、横移、拉远，减少所有素材同一种运动；
- 图片入场轮换缩放、左移、轻弹入场；
- 文字按节奏使用上移、缩放淡入、左移；
- 继续使用原主题、原图片、原旁白和原背景音乐。

## 运行

```bash
python3 -m experiments.jianying_effect_v2.build output/计算机硬盘的起源与发展/landscape
```

生成后直接在剪映首页查看：

```bash
python3 -m experiments.jianying_effect_v2.build output/计算机硬盘的起源与发展/landscape --install-to-jianying
```

若需要覆盖同名实验草稿：

```bash
python3 -m experiments.jianying_effect_v2.build output/计算机硬盘的起源与发展/landscape --replace
```
