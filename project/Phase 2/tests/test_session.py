import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import protocol as P
from session import ErrorCode, Session, State


class NullLogger:
    """Session only calls .command() on the FILE_LIST/LOGOUT paths tested here."""

    def command(self, ip, cmd, result):
        pass


def start_session(user_id: int = 0, username: str = "alice", storage_dir: str | None = None):
    """Spin up a Session on one end of a socketpair, served on a background thread.

    Returns (session, client_sock, thread, cleanup). The caller drives
    ``client_sock`` with ``P.pack_packet``/``P.read_packet`` exactly like a
    real client would; ``cleanup()`` closes both ends and joins the thread.
    """
    if storage_dir is None:
        storage_dir = tempfile.mkdtemp()
    server_sock, client_sock = socket.socketpair()
    session = Session(server_sock, ("127.0.0.1", 0), storage_dir, NullLogger(),
                       user_id=user_id, username=username)
    thread = threading.Thread(target=_serve_ignoring_disconnect, args=(session,), daemon=True)
    thread.start()

    def cleanup():
        try:
            client_sock.close()
        except OSError:
            pass
        try:
            server_sock.close()
        except OSError:
            pass
        thread.join(timeout=2)

    return session, client_sock, thread, cleanup


def _serve_ignoring_disconnect(session: Session) -> None:
    try:
        session.serve()
    except (ConnectionError, OSError):
        pass


def logout(client_sock) -> None:
    """Send LOGOUT and wait for its ACK, so the session thread exits cleanly."""
    client_sock.sendall(P.pack_packet(P.LOGOUT, 0))
    P.read_packet(client_sock)


class WrongStateOpcodeTests(unittest.TestCase):
    def test_opcode_not_allowed_in_state_returns_error_and_keeps_session_open(self):
        session, client, thread, cleanup = start_session()
        try:
            # FILE_CHUNK is only allowed in UPLOADING; the session starts in
            # AUTHENTICATED, so this must be refused without closing.
            client.sendall(P.pack_packet(P.FILE_CHUNK, 0, P.pack_chunk(0, b"x")))
            opcode, _uid, payload = P.read_packet(client)
            self.assertEqual(opcode, P.ERROR)
            code, _msg_len = payload[0:2], payload[2:4]
            self.assertEqual(int.from_bytes(code, "big"), ErrorCode.MALFORMED)

            # The session must still be usable afterwards.
            client.sendall(P.pack_packet(P.FILE_LIST, 0))
            opcode, _uid, payload = P.read_packet(client)
            self.assertEqual(opcode, P.FILE_LIST_RESP)

            logout(client)
            thread.join(timeout=2)
            self.assertEqual(session.state, State.CLOSED)
        finally:
            cleanup()


class UserIdMismatchTests(unittest.TestCase):
    def test_mismatched_user_id_returns_error_and_keeps_session_open(self):
        session, client, thread, cleanup = start_session(user_id=42)
        try:
            client.sendall(P.pack_packet(P.FILE_LIST, 99))  # wrong uid
            opcode, _uid, payload = P.read_packet(client)
            self.assertEqual(opcode, P.ERROR)
            code = int.from_bytes(payload[0:2], "big")
            self.assertEqual(code, ErrorCode.USER_ID_MISMATCH)

            # Correct uid still works.
            client.sendall(P.pack_packet(P.FILE_LIST, 42))
            opcode, _uid, payload = P.read_packet(client)
            self.assertEqual(opcode, P.FILE_LIST_RESP)

            logout(client)
        finally:
            cleanup()


class FileListNamespaceIsolationTests(unittest.TestCase):
    def test_file_list_only_sees_its_own_storage_dir(self):
        alice_dir = tempfile.mkdtemp()
        bob_dir = tempfile.mkdtemp()
        with open(os.path.join(alice_dir, "alice_only.txt"), "wb") as f:
            f.write(b"alice's file")
        with open(os.path.join(bob_dir, "bob_only.txt"), "wb") as f:
            f.write(b"bob's file")

        alice_session, alice_client, _t1, alice_cleanup = start_session(
            username="alice", storage_dir=alice_dir)
        bob_session, bob_client, _t2, bob_cleanup = start_session(
            username="bob", storage_dir=bob_dir)
        try:
            alice_client.sendall(P.pack_packet(P.FILE_LIST, 0))
            _op, _uid, payload = P.read_packet(alice_client)
            alice_entries = [name for name, _size in P.unpack_file_list_response(payload)]
            self.assertEqual(alice_entries, ["alice_only.txt"])

            bob_client.sendall(P.pack_packet(P.FILE_LIST, 0))
            _op, _uid, payload = P.read_packet(bob_client)
            bob_entries = [name for name, _size in P.unpack_file_list_response(payload)]
            self.assertEqual(bob_entries, ["bob_only.txt"])

            logout(alice_client)
            logout(bob_client)
        finally:
            alice_cleanup()
            bob_cleanup()


class LogoutTests(unittest.TestCase):
    def test_logout_returns_ack_and_enters_closed(self):
        session, client, thread, cleanup = start_session()
        try:
            client.sendall(P.pack_packet(P.LOGOUT, 0))
            opcode, _uid, payload = P.read_packet(client)
            self.assertEqual(opcode, P.ACK)
            acked_opcode, _next_offset, _sha256 = P.unpack_ack(payload)
            self.assertEqual(acked_opcode, P.LOGOUT)

            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(session.state, State.CLOSED)
        finally:
            cleanup()


class UnexpectedPayloadTests(unittest.TestCase):
    def test_file_list_ignores_garbage_payload(self):
        session, client, thread, cleanup = start_session()
        try:
            client.sendall(P.pack_packet(P.FILE_LIST, 0, b"\xff\xff\xff garbage"))
            opcode, _uid, payload = P.read_packet(client)
            self.assertEqual(opcode, P.FILE_LIST_RESP)
            logout(client)
        finally:
            cleanup()

    def test_logout_ignores_garbage_payload(self):
        session, client, thread, cleanup = start_session()
        try:
            client.sendall(P.pack_packet(P.LOGOUT, 0, b"\x00\x01unexpected"))
            opcode, _uid, payload = P.read_packet(client)
            self.assertEqual(opcode, P.ACK)
            acked_opcode, _next_offset, _sha256 = P.unpack_ack(payload)
            self.assertEqual(acked_opcode, P.LOGOUT)

            thread.join(timeout=2)
            self.assertEqual(session.state, State.CLOSED)
        finally:
            cleanup()


if __name__ == "__main__":
    unittest.main()
