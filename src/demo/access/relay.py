"""The one door out of the demo: a TCP relay to the mail server, and nowhere else.

The demo API runs on a Docker network with no route to the internet, so it can
make no outbound call even by accident. Sign-in codes still have to reach Neo, so
a second, tiny container runs this module on both networks: it accepts
connections from the API and pipes each one to a single fixed ``host:port``
(``MAIL_RELAY_TARGET``, ``smtp0001.neo.space:587``). Whatever the client sends,
the destination does not change -- there is no protocol to ask for another one.

It only ever carries ciphertext: the API upgrades the connection with STARTTLS and
verifies Neo's certificate by name (``mailer._RelaySMTP``). It holds no secrets
and reads no ``.env``.

Run: ``python -m src.demo.access.relay`` with ``MAIL_RELAY_TARGET`` set, and
optionally ``MAIL_RELAY_LISTEN`` (default ``0.0.0.0:2587``).
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from typing import Callable

logger = logging.getLogger("demo.mail_relay")

DEFAULT_LISTEN = "0.0.0.0:2587"
MAX_CONNECTIONS = 20
IDLE_SECONDS = 120
_CHUNK = 64 * 1024


def parse_address(raw: str) -> tuple[str, int]:
    """``host:port`` → ``(host, port)``. Raises ``ValueError`` on anything else."""
    host, sep, port = (raw or "").strip().rpartition(":")
    if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError(f"expected host:port, got {raw!r}")
    return host, int(port)


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(_CHUNK)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class MailRelay:
    """Accepts on ``listen`` and forwards every connection to ``target``."""

    def __init__(
        self,
        listen: tuple[str, int],
        target: tuple[str, int],
        *,
        connect: Callable[..., socket.socket] = socket.create_connection,
    ) -> None:
        self.target = target
        self._connect = connect
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._server = socket.create_server(listen, reuse_port=False)
        self._closed = threading.Event()

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.getsockname()[:2]
        return host, port

    def close(self) -> None:
        self._closed.set()
        self._server.close()

    def serve_forever(self) -> None:
        while not self._closed.is_set():
            try:
                client, _ = self._server.accept()
            except OSError:
                if self._closed.is_set():
                    return
                continue
            if not self._slots.acquire(blocking=False):
                client.close()
                continue
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client: socket.socket) -> None:
        try:
            client.settimeout(IDLE_SECONDS)
            try:
                upstream = self._connect(self.target, IDLE_SECONDS)
            except OSError as exc:
                logger.error("mail relay: cannot reach %s:%s (%s)", *self.target, exc)
                client.close()
                return
            upstream.settimeout(IDLE_SECONDS)
            back = threading.Thread(target=_pipe, args=(upstream, client), daemon=True)
            back.start()
            _pipe(client, upstream)
            back.join(IDLE_SECONDS)
            upstream.close()
            client.close()
        finally:
            self._slots.release()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    target = parse_address(os.environ.get("MAIL_RELAY_TARGET", ""))
    listen = parse_address(os.environ.get("MAIL_RELAY_LISTEN", DEFAULT_LISTEN))
    relay = MailRelay(listen, target)
    logger.info("mail relay: %s:%s -> %s:%s, nothing else", *relay.address, *target)
    relay.serve_forever()


if __name__ == "__main__":
    main()
