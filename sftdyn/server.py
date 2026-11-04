"""
HTTP(S) server implementation for sftdyn.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Iterable
import ipaddress
import logging
import re
import shlex
import ssl
from typing import Any

from aiohttp import web

logger = logging.getLogger("sftdyn")

# RFC 1123 hostname validation: labels 1-63 alphanumeric/hyphen, total length <= 253
HOSTNAME_REGEX = re.compile(
    r"^(?!-)[A-Za-z0-9-_]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-_]{1,63}(?<!-))*\.?$"
)


def is_valid_hostname(hostname: str) -> bool:
    """Check if the given string is a valid DNS hostname."""
    if not isinstance(hostname, str) or not hostname or len(hostname) > 253:
        return False
    return bool(HOSTNAME_REGEX.match(hostname))


def is_valid_ip(ip_str: str) -> bool:
    """Check if the given string is a valid IPv4 or IPv6 address."""
    if not isinstance(ip_str, str) or not ip_str:
        return False
    try:
        ipaddress.ip_address(ip_str.strip())
        return True
    except (ValueError, TypeError):
        return False


class Server:
    """
    HTTP(S) server for DNS record update requests.
    """

    def __init__(
        self,
        addr: tuple[str, int],
        get_host: Callable[[str, str], str | None],
        associations: dict[str, str],
        get_ip: Callable[[str, dict[str, str], str], str] | None,
        nsupdatecommands: Callable[[str, str, dict[str, str]], Iterable[str]],
        nskeyfile: str | None = None,
        nsparams: Iterable[str] | str | None = None,
        tls: tuple[str, str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        """
        addr: (ip, port) to listen on
        get_host: function that provides hostname to update
        associations: {dnshostname: ipaddr} map to cache current dynamic ips
        get_ip: function that can update the ip to set, e.g. by headers
        nsupdatecommands: function to generate the `nsupdate` stdin,
                          will be called with `host` and `new_ip` args.
        nskeyfile: optional keyfile for nsupdate
        nsparams: optional parameter(s) for nsupdate command
        tls: (certfilename, keyfilename) to use for the tls socket
        timeout: timeout in seconds for the nsupdate subprocess
        """
        self.addr = addr
        self.get_host = get_host
        self.associations = associations
        self.get_ip = get_ip
        self.nsupdatecommands = nsupdatecommands
        self.nskeyfile = nskeyfile
        self.timeout = timeout
        self.server: asyncio.Server | None = None
        self.web_server: web.Server | None = None
        self._host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        if nsparams is None:
            self.nsparams: list[str] = []
        elif isinstance(nsparams, str):
            self.nsparams = shlex.split(nsparams)
        else:
            self.nsparams = [str(p) for p in nsparams]

        if tls:
            self.sslcontext: ssl.SSLContext | None = ssl.create_default_context(
                purpose=ssl.Purpose.CLIENT_AUTH
            )
            self.sslcontext.load_cert_chain(tls[0], tls[1])
        else:
            self.sslcontext = None

    async def listen(self, loop: asyncio.AbstractEventLoop) -> asyncio.Server:
        """
        Let the server listen on the given event loop.
        """
        self.web_server = web.Server(self.handler)
        self.server = await loop.create_server(
            self.web_server,
            self.addr[0],
            self.addr[1],
            ssl=self.sslcontext,
        )
        return self.server

    async def close(self) -> None:
        """
        Close the server listening socket and active connections.
        """
        if self.server is not None:
            self.server.close()
        if self.web_server is not None:
            await asyncio.sleep(0)
            if hasattr(self.web_server, "pre_shutdown"):
                self.web_server.pre_shutdown()
            if hasattr(self.web_server, "shutdown"):
                shutdown_coro = self.web_server.shutdown(timeout=1.0)
                if shutdown_coro is not None and hasattr(shutdown_coro, "__await__"):
                    await shutdown_coro
            self.web_server = None
        if self.server is not None:
            try:
                await asyncio.wait_for(self.server.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            self.server = None

    async def handler(self, request: web.BaseRequest) -> web.Response:
        """
        Handler for a single request.
        """
        try:
            if request.method != "GET":
                return web.Response(text="Method Not Allowed\n", status=405)

            path = request.path_qs.lstrip("/")
            peername = request.transport.get_extra_info("peername") if request.transport else None
            if peername is None:
                logger.error("Could not determine client address from transport")
                return web.Response(text="Could not determine client address\n", status=500)

            addr = str(peername[0])
            text, code = await self.handle_request(path, addr, dict(request.headers))
            return web.Response(text=text, status=code)
        except Exception as e:
            logger.exception("Unhandled error processing request: %s", e)
            return web.Response(text="FAIL\n", status=500)

    async def handle_request(
        self,
        key: str,
        ip: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, int]:
        """
        Process the dynamic DNS update request.

        key: the path part of the client request URL, without the leading '/'
        ip: the IP address of the client
        headers: HTTP headers dict

        returns: (status_text, http_status_code)
        """
        if headers is None:
            headers = dict()

        # Call user-defined IP preprocessing function if provided
        if self.get_ip is not None:
            try:
                ip = str(self.get_ip(ip, headers, key))
            except Exception as e:
                logger.exception("Error in user get_ip function: %s", e)
                return "FAIL", 500

        # Validate IP address syntax
        if not is_valid_ip(ip):
            logger.warning("Invalid IP address '%s'", ip)
            return "BADIP", 400

        # Querying root path without key simply returns the detected IP
        if not key:
            return ip, 200

        # Look up host by key
        try:
            host = self.get_host(key, ip)
        except Exception as e:
            logger.exception("Error in user get_host function for key: %s", e)
            return "FAIL", 500

        if not host or not is_valid_hostname(host):
            logger.warning("Bad or unknown key: '%s' (host: %r)", key, host)
            return "BADKEY", 403

        # Prevent concurrent nsupdate runs for the same host
        async with self._host_locks[host]:
            if self.associations.get(host) == ip:
                return "UPTODATE", 200

            logger.info("Update request for %s => %s", host, ip)

            # Generate nsupdate commands
            try:
                cmdlist = self.nsupdatecommands(host, ip, headers)
                cmd = "\n".join(cmdlist) + "\n"
            except Exception as e:
                logger.exception("Error in user nsupdatecommands for host %s: %s", host, e)
                return "FAIL", 500

            nsupdate = ["nsupdate"]
            if self.nsparams:
                nsupdate.extend(self.nsparams)
            if self.nskeyfile:
                nsupdate.extend(["-k", self.nskeyfile])

            logger.debug("Executing command: %s with stdin:\n%s", nsupdate, cmd)

            try:
                proc = await asyncio.create_subprocess_exec(
                    *nsupdate,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=cmd.encode()),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except (ProcessLookupError, AttributeError):
                    pass
                logger.error("nsupdate timed out after %ss for %s => %s", self.timeout, host, ip)
                return "TIMEOUT", 504
            except FileNotFoundError:
                logger.error("nsupdate executable not found in PATH")
                return "FAIL", 500
            except Exception as e:
                logger.exception("Failed to execute nsupdate: %s", e)
                return "FAIL", 500

            if proc.returncode == 0:
                self.associations[host] = ip
                logger.info("Successfully updated %s => %s", host, ip)
                return "OK", 200

            err_msg = stderr.decode(errors="replace").strip()
            out_msg = stdout.decode(errors="replace").strip()
            logger.error(
                "nsupdate failed (exit code %d) for %s => %s. Stderr: %s | Stdout: %s",
                proc.returncode,
                host,
                ip,
                err_msg or "<none>",
                out_msg or "<none>",
            )
            return "FAIL", 500
