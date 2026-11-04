"""
sftdyn is a simple dynamic dns server for http requests
which then update dns records with nsupdate.
"""

from __future__ import annotations

import asyncio
import logging
import signal

VERSION = "0.10"
__author__ = "Michael Ensslin <michael@ensslin.cc>"
__maintainer__ = "Stephan Kleber <stephan@skleber.de>"


def main() -> None:
    """
    Launch sftdyn server.
    """
    from . import server
    from .args import parse_args
    from .util import log_setup

    args = parse_args(__doc__)

    logger = log_setup(args.verbose - args.quiet)

    # the known ip associations: maps host => ip
    associations: dict[str, str] = dict()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_debug(args.debug)

    servers: list[server.Server] = []
    timeout = getattr(args, "nsupdatetimeout", getattr(args, "timeout", 10.0))

    if args.http:
        http_server = server.Server(
            args.http,
            args.get_host,
            associations,
            args.get_ip,
            args.nsupdatecommands,
            nskeyfile=getattr(args, "nskeyfile", None),
            nsparams=getattr(args, "nsparams", None),
            timeout=timeout,
        )
        logger.info("Starting http server at %s:%d", args.http[0] or "*", args.http[1])
        loop.run_until_complete(http_server.listen(loop))
        servers.append(http_server)

    if args.https:
        https_server = server.Server(
            args.https,
            args.get_host,
            associations,
            args.get_ip,
            args.nsupdatecommands,
            nskeyfile=getattr(args, "nskeyfile", None),
            nsparams=getattr(args, "nsparams", None),
            tls=(args.cert, args.key),
            timeout=timeout,
        )
        logger.info("Starting https server at %s:%d", args.https[0] or "*", args.https[1])
        loop.run_until_complete(https_server.listen(loop))
        servers.append(https_server)

    if not servers:
        logger.error("Neither HTTP nor HTTPS server was configured to listen. Exiting.")
        loop.close()
        return

    stop_event = asyncio.Event()

    def handle_signal() -> None:
        logger.info("Received termination signal, stopping server...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except (NotImplementedError, RuntimeError):
            pass

    async def run_until_stop() -> None:
        await stop_event.wait()
        logger.info("Closing server listeners...")
        for s in servers:
            await s.close()

    try:
        loop.run_until_complete(run_until_stop())
    except KeyboardInterrupt:
        logger.info("Interrupted by user, exiting...")
        for s in servers:
            loop.run_until_complete(s.close())
    finally:
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        logger.info("Shutdown complete.")
