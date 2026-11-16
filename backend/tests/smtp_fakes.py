"""A small SMTP server on localhost for the notification tests (tests only):
it speaks the real protocol over a real socket, so smtplib talks to it as it
would to the owner's mail server, and it keeps what it was sent."""

import base64
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from email import message_from_bytes
from email.message import Message


@dataclass
class Mailbox:
    """What the server received: messages, the AUTH PLAIN logins
    (user, password) and the envelope recipients of each message."""

    messages: list[Message] = field(default_factory=list)
    logins: list[tuple[str, str]] = field(default_factory=list)
    recipients: list[list[str]] = field(default_factory=list)


class _Handler(socketserver.StreamRequestHandler):
    def reply(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self) -> None:
        box: Mailbox = self.server.mailbox  # type: ignore[attr-defined]
        auth: bool = self.server.auth  # type: ignore[attr-defined]
        rcpt: list[str] = []
        self.reply("220 fake ESMTP")
        for raw in self.rfile:
            line = raw.decode().strip()
            verb = line.split(" ", 1)[0].upper()
            if verb == "EHLO":
                self.reply("250-fake")
                self.reply("250 AUTH PLAIN" if auth else "250 SIZE 100000")
            elif verb == "AUTH":
                _, user, password = base64.b64decode(line.split()[-1]).split(b"\0")
                box.logins.append((user.decode(), password.decode()))
                self.reply("235 ok")
            elif verb == "RCPT":
                rcpt.append(line.split(":", 1)[1].strip(" <>"))
                self.reply("250 ok")
            elif verb == "DATA":
                self.reply("354 go on")
                body = b""
                for part in self.rfile:
                    if part == b".\r\n":
                        break
                    body += part
                box.messages.append(message_from_bytes(body))
                box.recipients.append(rcpt)
                rcpt = []
                self.reply("250 queued")
            elif verb == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("250 ok")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@contextmanager
def smtp_server(auth: bool = False) -> Iterator[tuple[int, Mailbox]]:
    """Run the fake server (offering AUTH PLAIN if auth) and yield its port and
    its Mailbox."""
    server = _Server(("127.0.0.1", 0), _Handler)
    server.mailbox = Mailbox()  # type: ignore[attr-defined]
    server.auth = auth  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], server.mailbox  # type: ignore[misc]
    finally:
        server.shutdown()
        server.server_close()
