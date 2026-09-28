# 发版工具

直接双击当前目录的 `start_release.command`（macOS）或 `start_release.bat`（Windows）即可打开图形化发版工具。

也可以在项目根目录运行：

```bash
python3 tools/release/build_release.py --clean
```

Windows 和 macOS 需要分别在对应系统构建，不能用 macOS 直接生成 Windows 版本。
构建结果默认写入根目录 `release/DonghuaKoubo/`。`build/` 只是 PyInstaller 的中间目录，构建成功后会自动删除；只有使用 `--keep-work` 或构建失败时才会保留，便于排查问题。PyInstaller 会把 Python 模块编译进归档，客户包不包含项目 `.py` 源文件。Windows 和 macOS 的产物必须分别在对应系统上构建。

客户启动：macOS 双击 `DonghuaKoubo.app`，Windows 双击 `DonghuaKoubo.exe`。客户包不附带 `.env` 或 `.env.example`；请由软件提供方单独发放本机专用配置文件，放在包根目录后再启动。

发版前请确认：

- 已安装 `requirements.txt` 和 `pyinstaller`；
- `.env`、`settings.json`、`output/` 不进入客户包；
- 客户电脑另行安装 `ffmpeg` 和 `ffprobe`；
- 私钥只放在 `tools/license/` 对应的卖家电脑，不进入客户包。
