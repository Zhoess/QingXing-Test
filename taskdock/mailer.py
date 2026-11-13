# -*- coding: utf-8 -*-
"""DingTalk / IMAP mail reading and MIME parsing (read-only)."""

import email
import hashlib
import imaplib
import os
import re
import socket
import ssl
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime, parseaddr

from . import model


class MailError(Exception):
    pass


def _decode_header(value):
    if not value:
        return ""
    pieces = []
    try:
        for part, charset in decode_header(value):
            if isinstance(part, bytes):
                charset = charset or "utf-8"
                if charset.lower() in ("gb2312", "gbk"):
                    charset = "gb18030"
                pieces.append(part.decode(charset, errors="replace"))
            else:
                pieces.append(part)
    except Exception:
        return str(value)
    return re.sub(r"\s+", " ", "".join(pieces)).strip()


def _html_to_text(html):
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for tag in soup.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4"]):
            tag.append("\n")
        text = soup.get_text("\n")
    except Exception:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.I | re.S)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</(?:p|div|li|tr|h\d)>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
    import html as html_module

    text = html_module.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _payload_text(part):
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        return ""
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    if charset.lower() in ("gb2312", "gbk"):
        charset = "gb18030"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeError):
        return payload.decode("utf-8", errors="replace")


def _body_from_message(message):
    plain, rich = [], []
    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain":
                text = _payload_text(part)
                if text.strip():
                    plain.append(text)
            elif content_type == "text/html":
                text = _payload_text(part)
                if text.strip():
                    rich.append(text)
    else:
        content_type = message.get_content_type()
        text = _payload_text(message)
        if content_type == "text/html":
            rich.append(text)
        elif text.strip():
            plain.append(text)
    body = "\n\n".join(plain).strip()
    if not body and rich:
        body = _html_to_text("\n".join(rich))
    elif rich and len(body) < 40:
        body = _html_to_text("\n".join(rich))
    body = re.sub(r"\n{3,}", "\n\n", body.replace("\r\n", "\n")).strip()
    return body[:30000]


def _snippet(body, limit=110):
    clean = re.sub(r"\s+", " ", body or "").strip()
    if len(clean) > limit:
        clean = clean[: limit - 1].rstrip() + "…"
    return clean


def _email_id(seed):
    return "m_" + hashlib.sha1(seed.encode("utf-8", errors="replace")).hexdigest()[:14]


def parse_email_bytes(raw, uid=None, folder="INBOX", fallback_date=None, account=""):
    try:
        message = email.message_from_bytes(raw)
    except Exception as exc:
        raise MailError("邮件内容解析失败：%s" % exc)
    subject = _decode_header(message.get("Subject")) or "（无主题）"
    sender_name, sender_email = parseaddr(_decode_header(message.get("From")) or "")
    sender_name = sender_name or sender_email or "未知发件人"
    date_value = None
    try:
        parsed = parsedate_to_datetime(message.get("Date"))
        if parsed is not None:
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            date_value = parsed.replace(second=0, microsecond=0)
    except Exception:
        date_value = None
    date_value = date_value or fallback_date or model.now()
    body = _body_from_message(message)
    if not body:
        body = "（该邮件没有可读取的正文，可能仅包含附件。）"
    uid = str(uid or _email_id(raw[:200000].decode("latin-1", errors="ignore")))
    email_id = _email_id("%s|%s|%s" % (account, folder, uid))
    return {
        "id": email_id,
        "uid": str(uid),
        "subject": subject,
        "sender": sender_name,
        "sender_email": sender_email,
        "date": model.iso(date_value),
        "body": body,
        "snippet": _snippet(body),
        "read": False,
        "analysis": None,
        "demo": False,
        "folder": folder,
    }


def import_eml(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    uid = hashlib.sha1(raw).hexdigest()[:14]
    email_data = parse_email_bytes(raw, uid=uid, folder="LOCAL", account="local")
    email_data["id"] = _email_id("local|" + path + "|" + uid)
    email_data["source_path"] = path
    return email_data


class MailClient(object):
    def __init__(self, host, port, account, password, days=14, limit=40):
        self.host = (host or "").strip()
        self.port = int(port or 993)
        self.account = (account or "").strip()
        self.password = password or ""
        self.days = max(1, min(90, int(days or 14)))
        self.limit = max(1, min(100, int(limit or 40)))
        self.connection = None

    def connect(self):
        if not self.host or not self.account or not self.password:
            raise MailError("请先在设置中填写邮箱账号和专用密码")
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(20)
        try:
            context = ssl.create_default_context()
            self.connection = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=context)
        except socket.gaierror:
            socket.setdefaulttimeout(old_timeout)
            raise MailError("找不到邮件服务器「%s」，请检查服务器地址和网络" % self.host)
        except ssl.SSLError as exc:
            socket.setdefaulttimeout(old_timeout)
            raise MailError("SSL 连接失败，请确认端口为 993：%s" % exc)
        except (socket.timeout, TimeoutError):
            socket.setdefaulttimeout(old_timeout)
            raise MailError("连接邮件服务器超时，请检查网络或代理")
        except Exception as exc:
            socket.setdefaulttimeout(old_timeout)
            raise MailError("无法连接 %s:%s（%s）" % (self.host, self.port, exc))
        try:
            self.connection.login(self.account, self.password)
        except imaplib.IMAP4.error as exc:
            self.close()
            socket.setdefaulttimeout(old_timeout)
            message = str(exc)
            if "LOGIN" in message.upper() or "AUTH" in message.upper() or "FAILED" in message.upper():
                raise MailError("登录失败：账号或专用密码不正确，请确认已开启 IMAP 并使用授权码")
            raise MailError("邮箱登录被拒绝：%s" % message)
        except Exception as exc:
            self.close()
            socket.setdefaulttimeout(old_timeout)
            raise MailError("邮箱登录失败：%s" % exc)
        socket.setdefaulttimeout(old_timeout)
        self._identify()
        try:
            typ, _ = self.connection.select("INBOX", readonly=True)
            if typ != "OK":
                raise MailError("无法打开收件箱")
        except imaplib.IMAP4.error as exc:
            self.close()
            raise MailError("无法打开收件箱：%s" % exc)

    def _identify(self):
        # Some Chinese providers require the IMAP ID command before SELECT.
        try:
            imaplib.Commands["ID"] = ("AUTH",)
            args = '("name" "TaskDock" "version" "1.0" "vendor" "local")'
            self.connection._simple_command("ID", args)
            self.connection._untagged_response("OK", [None], "ID")
        except Exception:
            pass

    def close(self):
        if self.connection is not None:
            try:
                self.connection.logout()
            except Exception:
                pass
            self.connection = None

    def test(self):
        self.connect()
        self.close()
        return True

    def fetch(self):
        if self.connection is None:
            self.connect()
        since = (datetime.now() - timedelta(days=self.days)).strftime("%d-%b-%Y")
        try:
            typ, data = self.connection.uid("search", None, '(SINCE "%s")' % since)
            if typ != "OK":
                raise MailError("收件箱搜索失败，请稍后再试")
            uids = []
            for chunk in data or []:
                if chunk:
                    uids.extend(chunk.decode("ascii", errors="ignore").split())
            uids = uids[-self.limit:]
        except imaplib.IMAP4.error as exc:
            raise MailError("收件箱搜索失败：%s" % exc)

        messages = []
        for uid in reversed(uids):
            try:
                typ, payload = self.connection.uid("fetch", uid, "(RFC822)")
                if typ != "OK":
                    continue
                raw = None
                for item in payload or []:
                    if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
                        raw = item[1]
                        break
                if not raw:
                    continue
                messages.append(parse_email_bytes(
                    raw, uid=uid, folder="INBOX", account=self.account
                ))
            except (imaplib.IMAP4.error, MailError):
                continue
        return messages


def check_connection(host, port, account, password, days=14):
    client = MailClient(host, port, account, password, days=days)
    client.test()
    return True
