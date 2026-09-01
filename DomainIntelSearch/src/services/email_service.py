"""邮件服务：SMTP 多平台支持，HTML 格式推送."""

class EmailService:
    """Disabled compatibility surface.

    IntDog is a local research product and deliberately has no mail delivery
    path.  Keeping this object avoids breaking old module graphs, but neither
    configuration nor environment variables can enable network delivery.
    """

    # 常见邮箱服务商的默认配置
    PROVIDERS = {
        "qq":      {"server": "smtp.qq.com", "port": 465, "ssl": True},
        "163":     {"server": "smtp.163.com", "port": 465, "ssl": True},
        "gmail":   {"server": "smtp.gmail.com", "port": 465, "ssl": True},
        "outlook": {"server": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    }

    def __init__(self, config: dict):
        self.email_cfg = config.get("email", {})
        self.enabled = False
        self._resolve_provider()

    def _resolve_provider(self):
        cfg = self.email_cfg
        self.server = cfg.get("smtp_server", "")
        self.port = int(cfg.get("smtp_port", 465))
        self.use_ssl = cfg.get("use_ssl", True)
        self.sender = cfg.get("sender", "")
        self.password = ""
        self.recipients = cfg.get("recipients", [])
        # 如果用户填写了 provider 别名（如 "qq"），自动补全
        alias = (cfg.get("provider") or "").lower()
        if alias in self.PROVIDERS and not self.server:
            p = self.PROVIDERS[alias]
            self.server, self.port, self.use_ssl = p["server"], p["port"], p["ssl"]

    def send_html(self, subject: str, html_body: str) -> bool:
        """Mail is a product-level non-capability and always returns false."""
        print("[Email] 产品邮件路径已禁用。")
        return False

    def send_plain(self, subject: str, text_body: str) -> bool:
        """发送纯文本邮件."""
        return self.send_html(subject, f"<pre>{text_body}</pre>")
