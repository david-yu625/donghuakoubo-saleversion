# 授权工具

这里是卖家专用的许可证签发工具，与客户发版工具分开保存。

```bash
python3 -m tools.license.issuer_dialog
```

也可以使用同目录下的平台启动脚本。签发实现和私钥工具只放在这里；`src/security_guard/` 只保留客户侧许可证校验和兼容包装。私钥请保存在本机安全目录，绝不能放进客户包或提交 Git。
