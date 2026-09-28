# Security Guard

这是桌面版动画口播软件的离线许可证模块。它不依赖云端，通过 Ed25519
签名把许可证绑定到一台设备，并验证客户名称、功能和到期日期。

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

## 设计边界

- 客户端只包含公钥，不包含签发私钥。
- 许可证保存在用户目录下的隐藏目录中，并尽量使用系统权限保护。
- 设备更换时，人工重新签发一张绑定新机器码的许可证。
- 这是防止普通复制和账号共享的轻量方案，不是不可破解的 DRM。
