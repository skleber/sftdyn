"""
Tests for sftdyn server implementation.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

try:
    from aiohttp import web
except ImportError:
    class MockResponse:
        def __init__(self, text: str = "", status: int = 200) -> None:
            self.text = text
            self.status = status

    aiohttp_mock = MagicMock()
    web_mock = MagicMock()
    web_mock.Response = MockResponse
    mock_server_instance = MagicMock()
    mock_server_instance.shutdown = AsyncMock()
    web_mock.Server.return_value = mock_server_instance
    aiohttp_mock.web = web_mock
    sys.modules["aiohttp"] = aiohttp_mock
    sys.modules["aiohttp.web"] = web_mock
    web = web_mock

from sftdyn.server import Server, is_valid_hostname, is_valid_ip


class TestServer(unittest.IsolatedAsyncioTestCase):
    def test_is_valid_hostname(self) -> None:
        self.assertTrue(is_valid_hostname("example.com"))
        self.assertTrue(is_valid_hostname("sub.example.com"))
        self.assertTrue(is_valid_hostname("sub-domain.example.com"))
        self.assertTrue(is_valid_hostname("host123"))
        self.assertTrue(is_valid_hostname("host.dyn.sft.rofl"))

        # Invalid hostnames
        self.assertFalse(is_valid_hostname(""))
        self.assertFalse(is_valid_hostname("   "))
        self.assertFalse(is_valid_hostname("host with spaces"))
        self.assertFalse(is_valid_hostname("host\nnewline"))
        self.assertFalse(is_valid_hostname("-startwithhyphen.com"))
        self.assertFalse(is_valid_hostname("endwithhyphen-.com"))
        self.assertFalse(is_valid_hostname("a" * 254))

    def test_is_valid_ip(self) -> None:
        self.assertTrue(is_valid_ip("127.0.0.1"))
        self.assertTrue(is_valid_ip("192.168.1.1"))
        self.assertTrue(is_valid_ip("::1"))
        self.assertTrue(is_valid_ip("2001:db8::1"))

        # Invalid IPs
        self.assertFalse(is_valid_ip(""))
        self.assertFalse(is_valid_ip("999.999.999.999"))
        self.assertFalse(is_valid_ip("not-an-ip"))
        self.assertFalse(is_valid_ip("127.0.0.1.1"))

    async def test_handle_request_root(self) -> None:
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "host.example.com",
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )
        text, code = await s.handle_request("", "192.168.1.50")
        self.assertEqual(code, 200)
        self.assertEqual(text, "192.168.1.50")

    async def test_handle_request_bad_key(self) -> None:
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: None,
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )
        text, code = await s.handle_request("unknown_key", "192.168.1.50")
        self.assertEqual(code, 403)
        self.assertEqual(text, "BADKEY")

    async def test_handle_request_invalid_hostname(self) -> None:
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "bad hostname with spaces",
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )
        text, code = await s.handle_request("mykey", "192.168.1.50")
        self.assertEqual(code, 403)
        self.assertEqual(text, "BADKEY")

    async def test_handle_request_invalid_client_ip(self) -> None:
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "host.example.com",
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )
        text, code = await s.handle_request("mykey", "not.an.ip.address")
        self.assertEqual(code, 400)
        self.assertEqual(text, "BADIP")

    async def test_handle_request_uptodate(self) -> None:
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "host.example.com",
            associations={"host.example.com": "192.168.1.50"},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )
        text, code = await s.handle_request("mykey", "192.168.1.50")
        self.assertEqual(code, 200)
        self.assertEqual(text, "UPTODATE")

    async def test_handle_request_nsupdate_success(self) -> None:
        associations: dict[str, str] = {}
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "host.example.com",
            associations=associations,
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["update add host 30 A " + ip, "send"],
            nsparams=["-l"],
            nskeyfile="/etc/bind/test.key",
        )

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            text, code = await s.handle_request("mykey", "1.2.3.4")

            self.assertEqual(code, 200)
            self.assertEqual(text, "OK")
            self.assertEqual(associations["host.example.com"], "1.2.3.4")

            # Check command and flags
            mock_exec.assert_called_once()
            cmd_args = mock_exec.call_args[0]
            self.assertEqual(cmd_args, ("nsupdate", "-l", "-k", "/etc/bind/test.key"))

    async def test_handle_request_nsupdate_failure(self) -> None:
        associations: dict[str, str] = {}
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "host.example.com",
            associations=associations,
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )

        mock_proc = MagicMock()
        mock_proc.returncode = 2
        mock_proc.communicate = AsyncMock(return_value=(b"", b"update failed: REFUSED"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            text, code = await s.handle_request("mykey", "1.2.3.4")
            self.assertEqual(code, 500)
            self.assertEqual(text, "FAIL")
            self.assertNotIn("host.example.com", associations)

    async def test_handle_request_nsupdate_timeout(self) -> None:
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "host.example.com",
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
            timeout=0.01,
        )

        async def slow_communicate(*args: object, **kwargs: object) -> tuple[bytes, bytes]:
            await asyncio.sleep(0.5)
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.communicate = slow_communicate
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            text, code = await s.handle_request("mykey", "1.2.3.4")
            self.assertEqual(code, 504)
            self.assertEqual(text, "TIMEOUT")
            mock_proc.kill.assert_called_once()

    async def test_handle_request_concurrency(self) -> None:
        associations: dict[str, str] = {}
        call_count = 0

        def mock_nsupdate_commands(h: str, ip: str, hdr: dict[str, str]) -> list[str]:
            nonlocal call_count
            call_count += 1
            return ["send"]

        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "host.example.com",
            associations=associations,
            get_ip=None,
            nsupdatecommands=mock_nsupdate_commands,
        )

        async def fake_communicate(input: bytes | None = None) -> tuple[bytes, bytes]:
            await asyncio.sleep(0.05)
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(side_effect=fake_communicate)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await asyncio.gather(
                s.handle_request("key1", "1.1.1.1"),
                s.handle_request("key1", "1.1.1.1"),
            )
            self.assertIn(results[0], [("OK", 200), ("UPTODATE", 200)])
            self.assertIn(results[1], [("OK", 200), ("UPTODATE", 200)])
            self.assertEqual(call_count, 1)

    async def test_http_handler_method_not_allowed(self) -> None:
        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=lambda k, ip: "h",
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )
        req = MagicMock()
        req.method = "POST"
        resp = await s.handler(req)
        self.assertEqual(resp.status, 405)

    async def test_http_handler_exception_safety(self) -> None:
        def buggy_get_host(key: str, ip: str) -> None:
            raise RuntimeError("database connection failed")

        s = Server(
            addr=("127.0.0.1", 8080),
            get_host=buggy_get_host,
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )

        req = MagicMock()
        req.method = "GET"
        req.path_qs = "/secretkey"
        req.headers = {}
        transport = MagicMock()
        transport.get_extra_info.return_value = ("1.2.3.4", 54321)
        req.transport = transport

        resp = await s.handler(req)
        self.assertEqual(resp.status, 500)
        self.assertIn("FAIL", resp.text)

    async def test_server_listen_and_close(self) -> None:
        loop = asyncio.get_running_loop()
        s = Server(
            addr=("127.0.0.1", 0),
            get_host=lambda k, ip: "host.example.com",
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )
        srv = await s.listen(loop)
        self.assertIsNotNone(s.server)
        self.assertIsNotNone(s.web_server)
        await s.close()
        self.assertIsNone(s.server)
        self.assertIsNone(s.web_server)

    async def test_server_close_with_active_connection(self) -> None:
        if isinstance(web, MagicMock):
            return

        loop = asyncio.get_running_loop()
        s = Server(
            addr=("127.0.0.1", 0),
            get_host=lambda k, ip: "host.example.com",
            associations={},
            get_ip=None,
            nsupdatecommands=lambda h, ip, hdr: ["send"],
        )
        srv = await s.listen(loop)
        if not hasattr(srv, "sockets") or not srv.sockets:
            await s.close()
            return

        port = srv.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")

        await asyncio.wait_for(s.close(), timeout=3.0)
        self.assertIsNone(s.server)
        self.assertIsNone(s.web_server)

        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
