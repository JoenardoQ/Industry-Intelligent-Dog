# 能力：邮件推送（setup-email）

把生成的日报/周报通过 SMTP 推送到邮箱。可选能力，不配置也能正常抓取与保存。

## 何时用
- 希望每天/每周自动收到情报邮件。

## 配置（config/settings.yaml 的 email 段）
```yaml
email:
  enabled: true
  smtp_server: "smtp.qq.com"     # QQ邮箱: smtp.qq.com | 163: smtp.163.com | Gmail: smtp.gmail.com
  smtp_port: 465                 # SSL 端口：QQ/163/Gmail=465, Outlook=587
  use_ssl: true
  sender: "你的邮箱@qq.com"
  password: "邮箱授权码"          # 不是登录密码，是 SMTP 授权码
  recipients:
    - "收件人@example.com"
  daily_time: "08:00"
  weekly_day: "monday"
```

## 验证
```bash
python -m src.main test-email     # 收到测试邮件即配置成功
```

## 触发方式
- 命令行加 `--no-send` 可临时不发邮件（默认会发）。
- 日常跑 `daily`/`weekly` 时，只要 `email.enabled: true` 就自动推送。

## 注意
- 密码填的是**邮箱授权码**，不是登录密码（QQ/163 需在邮箱设置里单独开启 SMTP 并生成授权码）。
- 授权码属敏感信息，`settings.yaml` 不要提交到公开仓库。
