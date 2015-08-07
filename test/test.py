# encoding: utf-8
import os
import random
import socket
import sys
import unittest

import pgtest


class CommonTest(unittest.TestCase):

    def test_bind_unused_port(self):
        for _ in xrange(1000):
            port = pgtest.bind_unused_port()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.assertEqual(sock.connect_ex(('localhost', port)), 111)
            sock.close()

    def test_is_valid_port(self):
        for i in range(1025, 65534):
            self.assertEqual(True, pgtest.is_valid_port(i))

    def test_is_not_valid_port(self):
        for i in range(1024):
            self.assertEqual(False, pgtest.is_valid_port(i))
        for i in range(65535, 100000):
            self.assertEqual(False, pgtest.is_valid_port(i))

    def test_url(self):
        url = 'postgresql://postgres:pass@localhost:5432/testdb'
        self.assertEqual(url, pgtest.url('postgres', 'pass', 'localhost', 5432, 'testdb'))


@unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
class UnixFileTest(unittest.TestCase):

    def test_exe_path_is_executable(self):
        self.assertEqual(True, pgtest.is_exe('/bin/ping'))

    def test_which_is_executable(self):
        self.assertEqual('/bin/ping', pgtest.which('ping'))

    def test_which_path_is_executable(self):
        self.assertEqual('/bin/ping', pgtest.which('/bin/ping'))

    def test_which_is_not_executable(self):
        self.assertEqual(None, pgtest.which('does not exist'))

    def test_locate(self):
        self.assertEqual('/bin/ping', pgtest.locate('ping'))

    def test_locate_fail(self):
        self.assertEqual(None, pgtest.locate('notafile'))


@unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
class WindowsFileTest(unittest.TestCase):

    def test_which_is_executable(self):
        self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which('ping'))

    def test_which_with_extension_is_executable(self):
        self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which('ping.exe'))

    def test_which_path_is_executable(self):
        self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which('C:/Windows/system32/ping'))

    def test_which_path_with_extension_is_executable(self):
        self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which('C:/Windows/system32/ping.exe'))

    def test_which_is_not_executable(self):
        self.assertEqual(None, pgtest.which('does not exist'))

    def test_locate_unavailable(self):
        self.assertRaises(OSError, pgtest.locate('ping'))


if __name__ == '__main__':
    unittest.main()
