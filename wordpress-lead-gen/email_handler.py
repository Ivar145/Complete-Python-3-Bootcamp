import imaplib
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(
    gmail_address: str,
    app_password: str,
    to_address: str,
    subject: str,
    body: str,
) -> tuple[bool, str, str]:
    message_id = f"<{uuid.uuid4()}@gmail.com>"
    try:
        msg = MIMEMultipart()
        msg["From"] = gmail_address
        msg["To"] = to_address
        msg["Subject"] = subject
        msg["Message-ID"] = message_id
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, to_address, msg.as_string())

        return True, message_id, ""
    except smtplib.SMTPAuthenticationError:
        return False, "", "Authentication failed — check your Gmail address and app password"
    except smtplib.SMTPException as e:
        return False, "", f"SMTP error: {str(e)}"
    except Exception as e:
        return False, "", f"Error sending email: {str(e)}"


def check_for_reply(gmail_address: str, app_password: str, message_id: str) -> bool:
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
            mail.login(gmail_address, app_password)
            mail.select("INBOX")
            search_id = message_id.strip("<>")
            _, data = mail.search(None, f'(HEADER In-Reply-To "{search_id}")')
            if data and data[0]:
                return True
            _, data = mail.search(None, f'(HEADER In-Reply-To "<{search_id}>")')
            if data and data[0]:
                return True
        return False
    except Exception:
        return False


def check_all_replies(gmail_address: str, app_password: str, leads: list[dict]) -> list[int]:
    replied_ids = []
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
            mail.login(gmail_address, app_password)
            mail.select("INBOX")

            for lead in leads:
                message_id = lead.get("email_thread_id", "")
                if not message_id:
                    continue
                search_id = message_id.strip("<>")
                try:
                    _, data = mail.search(None, f'(HEADER In-Reply-To "{search_id}")')
                    if data and data[0]:
                        replied_ids.append(lead["id"])
                        continue
                    _, data = mail.search(None, f'(HEADER In-Reply-To "<{search_id}>")')
                    if data and data[0]:
                        replied_ids.append(lead["id"])
                except Exception:
                    continue
    except Exception:
        pass
    return replied_ids
