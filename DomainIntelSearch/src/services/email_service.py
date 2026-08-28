"""邮件服务：SMTP 多平台支持，HTML 格式推送."""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header


class EmailService:
    """邮件推送服务."""

    # 常见邮箱服务商的默认配置
    PROVIDERS = {
        "qq":      {"server": "smtp.qq.com", "port": 465, "ssl": True},
        "163":     {"server": "smtp.163.com", "port": 465, "ssl": True},
        "gmail":   {"server": "smtp.gmail.com", "port": 465, "ssl": True},
        "outlook": {"server": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    }

    def __init__(self, config: dict):
        self.email_cfg = config.get("email", {})
        self.enabled = self.email_cfg.get("enabled", False)
        self._resolve_provider()

    def _resolve_provider(self):
        cfg = self.email_cfg
        self.server = cfg.get("smtp_server", "")
        self.port = int(cfg.get("smtp_port", 465))
        self.use_ssl = cfg.get("use_ssl", True)
        self.sender = cfg.get("sender", "")
        self.password = os.environ.get("INTDOG_SMTP_PASSWORD") or cfg.get("password", "")
        self.recipients = cfg.get("recipients", [])
        # 如果用户填写了 provider 别名（如 "qq"），自动补全
        alias = (cfg.get("provider") or "").lower()
        if alias in self.PROVIDERS and not self.server:
            p = self.PROVIDERS[alias]
            self.server, self.port, self.use_ssl = p["server"], p["port"], p["ssl"]

    def send_html(self, subject: str, html_body: str) -> bool:
        """发送 HTML 邮件."""
        if not self.enabled:
            print("[Email] 邮件未启用，跳过发送。")
            return False
        placeholders = {"your_auth_code", "password", "changeme"}
        if (not (self.server and self.sender and self.password and self.recipients)
                or self.password.lower() in placeholders):
            print("[Email] 配置不完整，跳过发送。")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.server, self.port, context=context,
                                      timeout=30) as server:
                    server.login(self.sender, self.password)
                    server.send_message(msg)
            else:
                context = ssl.create_default_context()
                with smtplib.SMTP(self.server, self.port, timeout=30) as server:
                    server.starttls(context=context)
                    server.login(self.sender, self.password)
                    server.send_message(msg)
            print(f"[Email] 已发送至 {', '.join(self.recipients)}")
            return True
        except Exception as e:
            print(f"[Email] 发送失败: {e}")
            return False

    def send_plain(self, subject: str, text_body: str) -> bool:
        """发送纯文本邮件."""
        return self.send_html(subject, f"<pre>{text_body}</pre>")
