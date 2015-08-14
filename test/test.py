# encoding: utf-8
from contextlib import closing
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

from . import CustomAssertions
from pgtest import pgtest

import pg8000
import psycopg2
import sqlalchemy


class TestThirdPartyDrivers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pg = pgtest.PGTest()
        cls.base_dir = cls.pg._base_dir

    @classmethod
    def tearDownClass(cls):
        cls.pg.close()

    def test_psycopg2(self):
        with closing(psycopg2.connect(**self.pg.dsn)) as cnxn:
            self.assertIsNotNone(cnxn)

    def test_sqlalchemy(self):
        engine = sqlalchemy.create_engine(self.pg.url)
        with closing(engine.connect()) as cnxn:
            self.assertIsNotNone(cnxn)
        engine.dispose()

    def test_pg8000(self):
        with closing(pg8000.connect(**self.pg.dsn)) as cnxn:
            self.assertIsNotNone(cnxn)


class TestPGTestWithParameters(unittest.TestCase, CustomAssertions):

    def test_cleanup(self):
        with pgtest.PGTest() as pg:
            base_dir = pg._base_dir
            self.assertDirExists(base_dir)
        self.assertDirNotExists(base_dir)

    def test_no_cleanup(self):
        with pgtest.PGTest(no_cleanup=True) as pg:
            base_dir = pg._base_dir
            self.assertDirExists(base_dir)
        self.assertDirExists(base_dir)
        shutil.rmtree(base_dir, ignore_errors=True)

    def test_username_valid(self):
        pg_ctl_exe = pgtest.which('pg_ctl')
        with pgtest.PGTest(username='my_user') as pg:
            self.assertTrue(pgtest.is_server_running(pg_ctl_exe, pg.cluster))

    def test_pg_ctl_exe_valid(self):
        pg_ctl_exe = pgtest.which('pg_ctl')
        with pgtest.PGTest(pg_ctl=pg_ctl_exe) as pg:
            self.assertTrue(pgtest.is_server_running(pg_ctl_exe, pg.cluster))

    def test_base_dir_valid(self):
        pg_ctl_exe = pgtest.which('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        with pgtest.PGTest(base_dir=temp_dir) as pg:
            self.assertTrue(pgtest.is_server_running(pg_ctl_exe, pg.cluster))
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_invalid_username_exit(self):
        with self.assertRaises(AssertionError):
            pgtest.PGTest(username='not-a-name')

    def test_invalid_username_exit(self):
        with self.assertRaises(TypeError):
            pgtest.PGTest(username=1)

    def test_invalid_pg_ctl_exe_exit(self):
        with self.assertRaises(AssertionError):
            pgtest.PGTest(pg_ctl='/not/a/path/pg_ctl')

    def test_invalid_copy_cluster_exit(self):
        temp_dir = tempfile.mkdtemp()
        with self.assertRaises(AssertionError):
            pgtest.PGTest(copy_cluster=temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_no_exist_copy_cluster_exit(self):
        with self.assertRaises(AssertionError):
            pgtest.PGTest('/not/a/path')

    def test_invalid_port_exit(self):
        with self.assertRaises(AssertionError):
            pgtest.PGTest(port=1)

    def test_invalid_port_type_exit(self):
        with self.assertRaises(AssertionError):
            pgtest.PGTest(port='5432')

    def test_invalid_port_type_exit(self):
        with self.assertRaises(AssertionError):
            pgtest.PGTest(base_dir='/not/a/path')

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_copy_data(self):
        pg_ctl_exe = pgtest.which('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        curr_dir = os.path.dirname(__file__)
        zf = zipfile.ZipFile(os.path.join(curr_dir, 'data/test_windows_cluster.zip'))
        zf.extractall(temp_dir)
        data_dir = os.path.join(temp_dir, 'data')
        with pgtest.PGTest(copy_cluster=data_dir) as pg:
            self.assertTrue(pgtest.is_server_running(pg_ctl_exe, pg.cluster))
        shutil.rmtree(temp_dir, ignore_errors=True)

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_unix_copy_data(self):
        pg_ctl_exe = pgtest.which('pg_ctl')
        temp_dir = tempfile.mkdtemp()
        curr_dir = os.path.dirname(__file__)
        zf = zipfile.ZipFile(os.path.join(curr_dir, 'data/test_unix_cluster.zip'))
        zf.extractall(temp_dir)
        data_dir = os.path.join(temp_dir, 'data')
        with pgtest.PGTest(copy_cluster=data_dir) as pg:
            self.assertTrue(pgtest.is_server_running(pg_ctl_exe, pg.cluster))
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestPGTestNoParameters(unittest.TestCase, CustomAssertions):

    @classmethod
    def setUpClass(cls):
        cls.pg_ctl_exe = pgtest.which('pg_ctl')
        cls.pg = pgtest.PGTest()

    @classmethod
    def tearDownClass(cls):
        cls.pg.close()

    def test_port_valid(self):
        self.assertTrue(pgtest.is_valid_port(self.pg.port))

    def test_pg_ctl_valid(self):
        self.assertIsNotNone(pgtest.which(self.pg.pg_ctl))

    def test_url_valid(self):
        self.assertRegexMatch(r'postgresql://[\w]+@localhost:[0-9]+/[\w]+', self.pg.url)

    def test_cluster_valid(self):
        self.assertTrue(pgtest.is_valid_cluster_dir(self.pg_ctl_exe, self.pg.cluster))

    def test_cluster_running(self):
        self.assertTrue(pgtest.is_server_running(self.pg_ctl_exe, self.pg.cluster))

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_unix_listen_socket_dir_exists(self):
        self.assertDirExists(self.pg._listen_socket_dir)

    def test_log_file_exists(self):
        self.assertFileExists(self.pg._log_file)

    def test_cant_set_port(self):
        with self.assertRaises(AttributeError):
            self.pg.port = self.pg.port

    def test_cant_set_cluster(self):
        with self.assertRaises(AttributeError):
            self.pg.cluster = self.pg.cluster

    def test_cant_set_log_file(self):
        with self.assertRaises(AttributeError):
            self.pg.log_file = self.pg.log_file

    def test_cant_set_username(self):
        with self.assertRaises(AttributeError):
            self.pg.username = self.pg.username

    def test_cant_set_pg_ctl(self):
        with self.assertRaises(AttributeError):
            self.pg.pg_ctl = self.pg.pg_ctl

    def test_cant_set_url(self):
        with self.assertRaises(AttributeError):
            self.pg.url = self.pg.url


class Test_is_valid_port(unittest.TestCase):

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
            self.assertFalse(pgtest.is_valid_port('1234'))


class Test_is_valid_db_object_name(unittest.TestCase):

    def test_is_valid_db_object_name_is_valid(self):
        self.assertTrue(pgtest.is_valid_db_object_name('_abcdefghijklmnopqrstuvwxyzABCDE'
                                            'FGHIJKLMNOPQRSTUVWXYZ1234567890'))

    def test_is_valid_db_object_name_is_not_valid(self):
        for c in r'`¬!"£$%^&*()+[]{};\'#:@~,./<>? ':
            self.assertFalse(pgtest.is_valid_db_object_name(c))

    def test_is_valid_db_object_name_blank_is_not_valid(self):
        self.assertFalse(pgtest.is_valid_db_object_name(''))

    def test_is_valid_db_object_name_non_string_is_not_valid(self):
        with self.assertRaises(TypeError):
            for c in (1, 1.0, str):
                pgtest.is_valid_db_object_name(c)

    def test_is_valid_db_object_name_pg__is_not_valid(self):
        self.assertFalse(pgtest.is_valid_db_object_name('pg_myname'))



class Test_is_valid_cluster_dir(unittest.TestCase):

    @classmethod
    def setUp(cls):
        cls.pg_ctl_exe = pgtest.which('pg_ctl')
        cls.temp_dir = tempfile.mkdtemp()
        cls.curr_dir = os.path.dirname(__file__)
        cls.data_dir = os.path.join(cls.temp_dir, 'data')

    @classmethod
    def tearDown(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_is_not_valid_cluster_dir(self):
        self.assertFalse(pgtest.is_valid_cluster_dir(self.pg_ctl_exe, self.temp_dir))

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_is_valid_cluster_dir(self):
        zf = zipfile.ZipFile(os.path.join(self.curr_dir, 'data/test_windows_cluster.zip'))
        zf.extractall(self.temp_dir)
        self.assertTrue(pgtest.is_valid_cluster_dir(self.pg_ctl_exe, self.data_dir))

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_unix_is_valid_cluster_dir(self):
        zf = zipfile.ZipFile(os.path.join(self.curr_dir, 'data/test_unix_cluster.zip'))
        zf.extractall(self.temp_dir)
        self.assertTrue(pgtest.is_valid_cluster_dir(self.pg_ctl_exe, self.data_dir))


class Test_is_server_running(unittest.TestCase):

    @classmethod
    def setUp(cls):
        cls.pg_ctl_exe = pgtest.which('pg_ctl')
        cls.temp_dir = tempfile.mkdtemp()
        cls.curr_dir = os.path.dirname(__file__)
        cls.data_dir = os.path.join(cls.temp_dir, 'data')

    @classmethod
    def tearDown(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_is_not_server_running(self):
        zf = zipfile.ZipFile(os.path.join(self.curr_dir, 'data/test_windows_cluster.zip'))
        zf.extractall(self.temp_dir)
        self.assertFalse(pgtest.is_server_running(self.pg_ctl_exe, self.data_dir))

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_unix_is_not_server_running(self):
        zf = zipfile.ZipFile(os.path.join(self.curr_dir, 'data/test_unix_cluster.zip'))
        zf.extractall(self.temp_dir)
        self.assertFalse(pgtest.is_server_running(self.pg_ctl_exe, self.data_dir))


class Test_which(unittest.TestCase):

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_unix_which_is_executable(self):
        self.assertEqual('/bin/ping', pgtest.which('ping'))

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def testunix__which_path_is_executable(self):
        self.assertEqual('/bin/ping', pgtest.which('/bin/ping'))

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_unix_which_is_not_executable(self):
        self.assertEqual(None, pgtest.which('doesnotexist'))

    def test_which_non_string(self):
        with self.assertRaises(TypeError):
            pgtest.which(1)

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_unix_which_unicode(self):
            self.assertEqual('/bin/ping', pgtest.which(u'ping'))

    @unittest.skipIf(sys.platform.startswith('win'), 'Unix only')
    def test_windows_which_unicode(self):
            self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which(u'ping'))

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_which_is_executable(self):
        self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which('ping'))

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_which_with_extension_is_executable(self):
        self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which('ping.exe'))

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_which_path_is_executable(self):
        self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which('C:/Windows/system32/ping'))

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_which_path_with_extension_is_executable(self):
        self.assertEqual('C:\\Windows\\system32\\ping.exe', pgtest.which('C:/Windows/system32/ping.exe'))

    @unittest.skipUnless(sys.platform.startswith('win'), 'Windows only')
    def test_windows_which_is_not_executable(self):
        self.assertEqual(None, pgtest.which('does not exist'))


if __name__ == '__main__':
    unittest.main()
