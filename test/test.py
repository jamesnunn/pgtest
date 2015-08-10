# encoding: utf-8
import os
import re
import socket
import shutil
import sys
import tempfile
import unittest
import zipfile

import pgtest


def unzip(source_filename, dest_dir):
    zf = zipfile.ZipFile(source_filename)
    zf.extractall(dest_dir)


class CustomAssertions():

    def assertRegexMatch(self, pattern, target, msg=None):
        comp = re.compile(pattern)
        if not re.match(comp, target):
            if not msg:
                msg = '{!r} does not match pattern {!r}'.format(target, pattern)
            raise AssertionError(msg)

    def assertFileExists(self, path):
        if not os.path.isfile(path):
            raise AssertionError('File does not exist: {!r}'.format(path))

    def assertDirExists(self, path):
        if not os.path.isdir(path):
            raise AssertionError('Directory does not exist: {!r}'.format(path))

    def assertFileNotExists(self, path):
        if os.path.isfile(path):
            raise AssertionError('File exists: {!r}'.format(path))

    def assertDirNotExists(self, path):
        if os.path.isdir(path):
            raise AssertionError('Directory exists: {!r}'.format(path))


class TestPgTestSetupOptions(unittest.TestCase, CustomAssertions):

    def test_cleanup(self):
        with pgtest.PGTest('test') as pg:
            base_dir = pg._base_dir
        self.assertDirNotExists(base_dir)

    def test_no_cleanup(self):
        with pgtest.PGTest('test', no_cleanup=True) as pg:
            base_dir = pg._base_dir
            cluster = pg.cluster
        self.assertDirExists(base_dir)
        self.assertDirExists(cluster)
        shutil.rmtree(base_dir, ignore_errors=True)

    def test_username(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        with pgtest.PGTest('test', username='jamesnunn') as pg:
            self.assertTrue(pgtest.is_server_running(pg_ctl_exe, pg.cluster))

    def test_invalid_username(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        with self.assertRaises(AssertionError):
            with pgtest.PGTest('test', username='james-nunn') as pg:
                self.assertFalse(pgtest.is_server_running(pg_ctl_exe, pg.cluster))

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_copy_data(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        curr_dir = os.path.dirname(__file__)
        unzip(os.path.join(curr_dir, 'test_windows_cluster.zip'), temp_dir)
        data_dir = os.path.join(temp_dir, 'data')
        with pgtest.PGTest('test', copy_data_path=data_dir) as pg:
            self.assertTrue(pgtest.is_server_running(pg_ctl_exe, pg.cluster))
        shutil.rmtree(temp_dir, ignore_errors=True)

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_unix_copy_data(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        curr_dir = os.path.dirname(__file__)
        unzip(os.path.join(curr_dir, 'test_unix_cluster.zip'), temp_dir)
        data_dir = os.path.join(temp_dir, 'data')
        with pgtest.PGTest('test', copy_data_path=data_dir) as pg:
            self.assertTrue(pgtest.is_server_running(pg_ctl_exe, pg.cluster))
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestPgTestDefault(unittest.TestCase, CustomAssertions):

    @classmethod
    def setUpClass(cls):
        cls.pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        cls.pg = pgtest.PGTest('test')
        cls.pg.start_server()
        cls.base_dir = cls.pg._base_dir

    @classmethod
    def tearDownClass(cls):
        cls.pg.close()

    def test_pg_ctl_valid(self):
        self.assertTrue(pgtest.is_valid_port(self.pg.port))

    def test_port_valid(self):
        self.assertTrue(pgtest.get_exe_path(self.pg.pg_ctl))

    def test_url_valid(self):
        self.assertRegexMatch(r'postgresql://[\w]+@localhost:[0-9]+/[\w]+', self.pg.url)

    def test_cluster_valid(self):
        self.assertTrue(pgtest.is_valid_cluster_dir(self.pg_ctl_exe, self.pg.cluster))

    def test_cluster_running(self):
        self.assertTrue(pgtest.is_server_running(self.pg_ctl_exe, self.pg.cluster))

    def test_server_stop_start(self):
        self.assertTrue(pgtest.is_server_running(self.pg_ctl_exe, self.pg.cluster))
        self.pg.stop_server()
        self.assertFalse(pgtest.is_server_running(self.pg_ctl_exe, self.pg.cluster))
        self.pg.start_server()
        self.assertTrue(pgtest.is_server_running(self.pg_ctl_exe, self.pg.cluster))

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_listen_socket_dir_exists(self):
        self.assertDirExists(self.pg._listen_socket_dir)

    def test_log_file_exists(self):
        self.assertFileExists(self.pg._log_file)


class ModuleFunctionsTest(unittest.TestCase):

    def test_is_valid_port(self):
        for i in range(1025, 65534):
            self.assertTrue(pgtest.is_valid_port(i))

    def test_is_not_valid_port_too_low(self):
        for l in range(1024):
            self.assertFalse(pgtest.is_valid_port(l))

    def test_is_not_valid_port_too_high(self):
        for u in range(65535, 100000):
            self.assertFalse(pgtest.is_valid_port(u))

    def test_is_not_valid_port_neg(self):
        self.assertFalse(pgtest.is_valid_port(-1))

    def test_is_not_valid_port_str(self):
        with self.assertRaises(TypeError):
            pgtest.is_valid_port('1234')

    def test_get_exe_path(self):
        with self.assertRaises(IOError):
            pgtest.get_exe_path('notafile')

    def test_str_alphanum_is_valid(self):
        self.assertTrue(pgtest.str_alphanum('_abcdefghijklmnopqrstuvwxyzABCDE'
                                            'FGHIJKLMNOPQRSTUVWXYZ1234567890'))

    def test_str_alphanum_is_not_valid(self):
        for c in r'`¬!"£$%^&*()+[]{};\'#:@~,./<>? ':
            self.assertFalse(pgtest.str_alphanum(c))

    def test_is_not_valid_cluster_dir(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        self.assertFalse(pgtest.is_valid_cluster_dir(pg_ctl_exe, temp_dir))
        shutil.rmtree(temp_dir, ignore_errors=True)

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_is_valid_cluster_dir(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        curr_dir = os.path.dirname(__file__)
        unzip(os.path.join(curr_dir,'test_windows_cluster.zip'), temp_dir)
        data_dir = os.path.join(temp_dir, 'data')
        self.assertTrue(pgtest.is_valid_cluster_dir(pg_ctl_exe, data_dir))
        shutil.rmtree(temp_dir, ignore_errors=True)

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_linux_is_valid_cluster_dir(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        curr_dir = os.path.dirname(__file__)
        unzip(os.path.join(curr_dir,'test_unix_cluster.zip'), temp_dir)
        data_dir = os.path.join(temp_dir, 'data')
        self.assertTrue(pgtest.is_valid_cluster_dir(pg_ctl_exe, data_dir))
        shutil.rmtree(temp_dir, ignore_errors=True)

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_is_not_server_running(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        curr_dir = os.path.dirname(__file__)
        unzip(os.path.join(curr_dir,'test_windows_cluster.zip'), temp_dir)
        data_dir = os.path.join(temp_dir, 'data')
        self.assertFalse(pgtest.is_server_running(pg_ctl_exe, data_dir))
        shutil.rmtree(temp_dir, ignore_errors=True)

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_is_not_server_running(self):
        pg_ctl_exe = pgtest.get_exe_path('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        curr_dir = os.path.dirname(__file__)
        unzip(os.path.join(curr_dir,'test_unix_cluster.zip'), temp_dir)
        data_dir = os.path.join(temp_dir, 'data')
        self.assertFalse(pgtest.is_server_running(pg_ctl_exe, data_dir))
        shutil.rmtree(temp_dir, ignore_errors=True)


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


@unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
class WindowsFileTest(unittest.TestCase):

    def test_exe_path_is_executable(self):
        self.assertEqual(True, pgtest.is_exe('C:/Windows/system32/ping.exe'))

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


if __name__ == '__main__':
    unittest.main()
