"""
Argument parsing for all your configuration needs.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse


def get_parser(intro: str) -> argparse.ArgumentParser:
    """
    Create the argument parser.
    """
    cmd = argparse.ArgumentParser(
        description=intro,
        epilog="SFT dynamic DNS updater HTTPS server",
    )
    cmd.add_argument(
        "conffile",
        type=str,
        nargs="?",
        default="/etc/sftdyn/conf",
        help="conf file, will be exec'd as python3",
    )
    cmd.add_argument(
        "-l", "--http",
        metavar="IP:PORT",
        help="Enable HTTP server",
    )
    cmd.add_argument(
        "-s", "--https",
        metavar="IP:PORT",
        help="Enable HTTPS server",
    )
    cmd.add_argument("-c", "--cert", type=str, help="HTTPS X.509 cert file")
    cmd.add_argument("-k", "--key", type=str, help="HTTPS X.509 key file")
    cmd.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="launch an interactive session",
    )
    cmd.add_argument(
        "--nskeyfile",
        type=str,
        help="optional keyfile for nsupdate",
    )
    cmd.add_argument(
        "-d", "--debug",
        action="store_true",
        help="enable asyncio debugging",
    )
    cmd.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="increase program verbosity",
    )
    cmd.add_argument(
        "-q", "--quiet",
        action="count",
        default=0,
        help="decrease program verbosity",
    )

    return cmd


def stringtoipport(txt: str | int) -> tuple[str, int]:
    """
    Splits an IP:PORT string, as expected for --http and --https.

    txt
        input string, either PORT or an IP4/6-address:port or hostname:port
    returns
        (ip, port) where ip is a string and port is an int
    """
    defaultip = ""

    if isinstance(txt, int):
        port = txt
        ip = defaultip
    elif isinstance(txt, str) and txt.isnumeric():
        port = int(txt)
        ip = defaultip
    elif isinstance(txt, str):
        parsed = urlparse(f"//{txt}")
        if not parsed.hostname or parsed.port is None:
            raise ValueError(f"Invalid [IP:]PORT specification: '{txt}'")
        try:
            ip = str(ipaddress.ip_address(parsed.hostname))
        except ValueError:
            ip = parsed.hostname
        port = parsed.port
    else:
        raise ValueError(f"Invalid address: '{txt}'")

    if not (1 <= port <= 65535):
        raise ValueError(f"Port out of range (1-65535): {port}")

    return ip, port


def parse_args(intro: str) -> argparse.Namespace:
    """
    Parses the args, and returns the namespace.
    The config file is evaluated after the args and may replace its values.

    intro: info text displayed as program description.
    """
    cmd = get_parser(intro)
    args = cmd.parse_args()

    # read the conffile
    if not os.path.isfile(args.conffile):
        cmd.error("Not a valid conf file: " + args.conffile)

    # execute the file so globals defined in it are added to args
    confdefs: dict[str, object] = dict()
    try:
        with open(args.conffile, encoding="utf-8") as cfghdl:
            exec(cfghdl.read(), confdefs)
    except Exception as e:
        cmd.error(f"Error loading conf file '{args.conffile}': {e}")
    vars(args).update(confdefs)

    if not hasattr(args, "get_host") or not callable(args.get_host):
        cmd.error(
            "config file does not provide callable `get_host`"
            " function to look up client hostnames"
        )

    if not hasattr(args, "get_ip"):
        setattr(args, "get_ip", None)
    elif args.get_ip is not None and not callable(args.get_ip):
        cmd.error("config file `get_ip` must be callable if provided")

    if not hasattr(args, "nsparams"):
        setattr(args, "nsparams", getattr(args, "nsupdateparams", None))

    if not hasattr(args, "nsupdatecommands") or not callable(args.nsupdatecommands):
        cmd.error("config file does not define callable `nsupdatecommands` function")

    # check https IP:PORT string
    if args.https:
        try:
            args.https = stringtoipport(args.https)
        except ValueError as e:
            cmd.error(f"Invalid [IP:]PORT for --https: {e}")

    # check http IP:PORT string
    if args.http:
        try:
            args.http = stringtoipport(args.http)
        except ValueError as e:
            cmd.error(f"Invalid [IP:]PORT for --http: {e}")

    # check cert/key
    if args.https or args.cert or args.key:
        if not (args.https and args.cert and args.key):
            cmd.error("--https, --cert and --key need to be used together")

        conffolder = Path(args.conffile).parent
        # make cert paths relative to the conf file
        if not Path(args.cert).is_absolute():
            args.cert = str(conffolder / args.cert)

        if not Path(args.key).is_absolute():
            args.key = str(conffolder / args.key)

    return args
