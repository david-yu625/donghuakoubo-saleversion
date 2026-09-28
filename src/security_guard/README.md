# Security Guard

这是桌面版动画口播软件的离线许可证模块。它不依赖云端，通过 Ed25519
签名把许可证绑定到一台设备，并验证客户名称、功能和到期日期。

## 过程文件保密

项目生成的文案、时间线、分镜、图片提示词、布局 JSON、Markdown 以及流程临时文件会在
流程空闲时使用本机安装 ID 派生的密钥加密。每个流程步骤开始前临时解密，
步骤结束后自动重新加密；软件里的查看和编辑窗口会自动完成一次性解密读取。

这能防止客户直接打开 `output/` 目录批量查看提示词。程序运行时为了调用模型
和生成剪映草稿，相关内容仍会短暂存在于进程和文件系统明文中；它不是针对有
调试权限用户的绝对 DRM。

## 发布者准备

首次发布时生成一套密钥：

```bash
python3 -m src.security_guard.generate_keys \
  --output-dir "$HOME/.donghuakoubo-release"
```

把 `public_key.txt` 的内容填入 `src/security_guard/license.py` 的
`PUBLIC_KEY_B64`，然后发布软件。`private_key.pem` 不能提交 Git，也不能发给客户。

如果已经配置过发布公钥，不要重新生成密钥，否则旧客户的许可证将无法在新版本中验证。

## 给客户激活

客户首次打开软件时会看到机器码。客户把机器码发给你后，在自己的电脑上签发：

```bash
python3 -m src.security_guard \
  --private-key "$HOME/.donghuakoubo-release/private_key.pem" \
  --machine-code CLIENT_MACHINE_CODE \
  --customer "客户名称" \
  --days 365 \
  --features image,voice,render \
  --output ./customer-license.json
```

把生成的 `customer-license.json` 发给客户，客户在激活窗口中导入即可。

## 图形化签发

卖家不需要执行命令。双击项目里的：

- macOS：`tools/start_license_issuer.command`
- Windows：`tools/start_license_issuer.bat`

这个窗口只在卖家电脑上使用。客户版不应包含 `tools/` 目录、
`issuer_dialog.py`、`issue_license.py`、`generate_keys.py` 或私钥文件；
客户版只保留许可证验证和导入功能。

## 设计边界

- 客户端只包含公钥，不包含签发私钥。
- 许可证保存在用户目录下的隐藏目录中，并尽量使用系统权限保护。
- 设备更换时，人工重新签发一张绑定新机器码的许可证。
- 这是防止普通复制和账号共享的轻量方案，不是不可破解的 DRM。
