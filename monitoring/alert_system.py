# monitoring/alert_system.py
import smtplib
from email.mime.text import MIMEText

class AlertSystem:
    """
    Botta kritik durumlar veya uyarılar için alert mekanizması
    """
    def __init__(self, email_config=None):
        self.email_config = email_config or {
            "smtp_server": "smtp.example.com",
            "port": 587,
            "username": "user@example.com",
            "password": "password",
            "to_email": "alert@example.com"
        }

    def send_email_alert(self, subject, message):
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = self.email_config["username"]
        msg["To"] = self.email_config["to_email"]

        try:
            with smtplib.SMTP(self.email_config["smtp_server"], self.email_config["port"]) as server:
                server.starttls()
                server.login(self.email_config["username"], self.email_config["password"])
                server.sendmail(self.email_config["username"], [self.email_config["to_email"]], msg.as_string())
            print(f"✅ Alert gönderildi: {subject}")
        except Exception as e:
            print(f"❌ Alert gönderilemedi: {e}")
