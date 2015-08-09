# encoding: utf-8
import socket
import sys
import unittest

import pgtest


@unittest.skip
class TestPgTest(unittest.TestCase):
    pass
    # def test_basic(self):
    #     try:
    #         # start postgresql server
    #         pgsql = testing.postgresql.Postgresql()
    #         self.assertIsNotNone(pgsql)
    #         params = pgsql.dsn()
    #         self.assertEqual('test', params['database'])
    #         self.assertEqual('127.0.0.1', params['host'])
    #         self.assertEqual(pgsql.port, params['port'])
    #         self.assertEqual('postgres', params['user'])

    #         # connect to postgresql (w/ psycopg2)
    #         conn = psycopg2.connect(**pgsql.dsn())
    #         self.assertIsNotNone(conn)
    #         self.assertRegexpMatches(pgsql.read_log(), 'is ready to accept connections')
    #         conn.close()

    #         # connect to postgresql (w/ sqlalchemy)
    #         engine = sqlalchemy.create_engine(pgsql.url())
    #         self.assertIsNotNone(engine)

    #         # connect to postgresql (w/ pg8000)
    #         conn = pg8000.connect(**pgsql.dsn())
    #         self.assertIsNotNone(conn)
    #         self.assertRegexpMatches(pgsql.read_log(), 'is ready to accept connections')
    #         conn.close()
    #     finally:
    #         # shutting down
    #         pid = pgsql.pid
    #         self.assertTrue(pid)
    #         os.kill(pid, 0)  # process is alive

    #         pgsql.stop()
    #         sleep(1)

    #         self.assertIsNone(pgsql.pid)
    #         with self.assertRaises(OSError):
    #             os.kill(pid, 0)  # process is down


class ModuleFunctionsTest(unittest.TestCase):

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

    def test_get_exe_path(self):
        with self.assertRaises(IOError):
            pgtest.get_exe_path('notafile')

    def test_wait_for_server_timeout(self):
        with self.assertRaises(pgtest.TimeoutError):
            pgtest._wait_for_server_ready(0.1)


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
        with self.assertRaises(OSError):
            pgtest.locate('ping')


if __name__ == '__main__':
    unittest.main()
