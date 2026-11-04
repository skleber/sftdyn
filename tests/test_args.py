"""
Tests for sftdyn argument and configuration parsing.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

from sftdyn.args import get_parser, parse_args, stringtoipport


class TestArgs(unittest.TestCase):
    def test_stringtoipport(self) -> None:
        # Port only as int
        self.assertEqual(stringtoipport(8080), ("", 8080))

        # Port only as string
        self.assertEqual(stringtoipport("8080"), ("", 8080))

        # IPv4 and port
        self.assertEqual(stringtoipport("127.0.0.1:8080"), ("127.0.0.1", 8080))

        # IPv6 and port
        self.assertEqual(stringtoipport("[::1]:8080"), ("::1", 8080))

        # Hostname and port
        self.assertEqual(stringtoipport("localhost:8080"), ("localhost", 8080))

        # Out of range port
        with self.assertRaises(ValueError):
            stringtoipport(0)
        with self.assertRaises(ValueError):
            stringtoipport(70000)
        with self.assertRaises(ValueError):
            stringtoipport("80800")

        # Invalid string format
        with self.assertRaises(ValueError):
            stringtoipport("invalid_string_without_port")

    def test_parse_args_valid_conf(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("""
http = "8080"
def get_host(key, ip):
    return "example.com"
def nsupdatecommands(host, ip, headers):
    return ["send"]
""")
            conf_path = f.name

        old_argv = sys.argv
        try:
            sys.argv = ["sftdyn", conf_path]
            args = parse_args("test")
            self.assertEqual(args.http, ("", 8080))
            self.assertEqual(args.get_host("k", "1.2.3.4"), "example.com")
            self.assertIsNone(args.nsparams)
        finally:
            sys.argv = old_argv
            os.remove(conf_path)

    def test_parse_args_with_nsparams(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("""
http = "8080"
nsparams = ["-l", "-v"]
def get_host(key, ip):
    return "example.com"
def nsupdatecommands(host, ip, headers):
    return ["send"]
""")
            conf_path = f.name

        old_argv = sys.argv
        try:
            sys.argv = ["sftdyn", conf_path]
            args = parse_args("test")
            self.assertEqual(args.nsparams, ["-l", "-v"])
        finally:
            sys.argv = old_argv
            os.remove(conf_path)

    def test_parse_args_with_alias_nsupdateparams(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("""
http = "8080"
nsupdateparams = "-l"
def get_host(key, ip):
    return "example.com"
def nsupdatecommands(host, ip, headers):
    return ["send"]
""")
            conf_path = f.name

        old_argv = sys.argv
        try:
            sys.argv = ["sftdyn", conf_path]
            args = parse_args("test")
            self.assertEqual(args.nsparams, "-l")
        finally:
            sys.argv = old_argv
            os.remove(conf_path)

    def test_parse_args_missing_file(self) -> None:
        old_argv = sys.argv
        try:
            sys.argv = ["sftdyn", "/nonexistent/path/to/sftdyn.conf"]
            with self.assertRaises(SystemExit):
                parse_args("test")
        finally:
            sys.argv = old_argv

    def test_parse_args_syntax_error(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("def invalid_syntax(:")
            conf_path = f.name

        old_argv = sys.argv
        try:
            sys.argv = ["sftdyn", conf_path]
            with self.assertRaises(SystemExit):
                parse_args("test")
        finally:
            sys.argv = old_argv
            os.remove(conf_path)

    def test_parse_args_relative_cert_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_file = os.path.join(tmpdir, "test.conf")
            with open(conf_file, "w") as f:
                f.write("""
https = "4443"
cert = "cert.pem"
key = "key.pem"
def get_host(key, ip): return "h"
def nsupdatecommands(h, ip, hdr): return ["send"]
""")
            old_argv = sys.argv
            try:
                sys.argv = ["sftdyn", conf_file]
                args = parse_args("test")
                self.assertEqual(args.cert, os.path.join(tmpdir, "cert.pem"))
                self.assertEqual(args.key, os.path.join(tmpdir, "key.pem"))
            finally:
                sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
