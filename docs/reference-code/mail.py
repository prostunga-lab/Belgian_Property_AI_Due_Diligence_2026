import os, smtplib, ssl
from email.message import EmailMessage

def send(to: str, subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST")
    if not host:  # mode dev: le message (lien inclus) s'affiche dans la console du serveur
        print(f"[MAIL dev] à: {to}\n{subject}\n{body}\n", flush=True)
        return
    m = EmailMessage()
    m["From"] = os.getenv("MAIL_FROM", "no-reply@localhost")
    m["To"], m["Subject"] = to, subject
    m.set_content(body)
    port = int(os.getenv("SMTP_PORT", "587"))
    ctx = ssl.create_default_context()
    try:
        s = smtplib.SMTP_SSL(host, port, timeout=15, context=ctx) if port == 465 else smtplib.SMTP(host, port, timeout=15)
        with s:
            if port != 465:
                s.starttls(context=ctx)
            if os.getenv("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
            s.send_message(m)
    except Exception as e:
        print("[MAIL] échec d'envoi:", type(e).__name__, flush=True)
