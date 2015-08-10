# encoding: utf-8
from contextlib import closing
import os
import pg8000
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import datetime


class TimeoutError(BaseException):
    def __init__(self, message):
        self.message = message


def is_exe(file_path):
    """Checks whether a file is executable

    Args:
        file_path - str, path to file to check

    Returns:
        is_executable - bool, whether or not the file is executable
    """
    is_executable = os.access(file_path, os.X_OK)
    return is_executable


def which(in_file):
    """Finds an executable program in the system and returns the program name

    Accepts filenames with or without full paths and  with or without file
    extensions.

    Args:
        program - str, program name or path to find

    Returns:
        file_path - str, normalised path to file found or None if not found
    """
    path_no_ext, _ = os.path.splitext(in_file)
    path_with_exe = path_no_ext + '.exe'
    # Look for the exe at the path supplied
    if os.path.split(path_no_ext)[0]:
        if os.path.isfile(in_file):
            file_path = in_file
        elif os.path.isfile(path_with_exe):
            file_path = path_with_exe
        if is_exe(file_path):
            return os.path.normpath(file_path)
    else:
        for path in os.environ['PATH'].split(os.pathsep):
            file_path = os.path.join(path.strip('"'), in_file)
            file_path_with_exe = os.path.join(path.strip('"'), path_with_exe)
            if os.path.isfile(file_path_with_exe):
                if is_exe(file_path_with_exe):
                    return os.path.normpath(file_path_with_exe)
            elif os.path.isfile(file_path):
                if is_exe(file_path):
                    return os.path.normpath(file_path)

    if sys.platform.startswith('win'):
        return
    try:
        exact_file_regex = '/' + in_file + '$'
        results = subprocess.check_output(['locate', '-r', exact_file_regex])
        for file_path in results.split('\n'):
            if is_exe(file_path):
                return os.path.normpath(file_path)
    except subprocess.CalledProcessError:
        return


def is_valid_port(port):
    if not isinstance(port, int):
        raise TypeError('Port must be of type int')
    return 1024 < port < 65535


def bind_unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 0 binds to unused socket
    sock.bind(('localhost', 0))
    _, port = sock.getsockname()
    while not is_valid_port(port):
        port = bind_unused_port()
    sock.close()
    return port


def get_exe_path(filename):
    pg_ctl_exe = which(filename)
    if not pg_ctl_exe:
        raise IOError('File not found: {filename}'.format(filename=filename))
    else:
        return pg_ctl_exe


def str_alphanum(instr):
    for c in instr:
        if not (c.isalpha() or c.isdigit() or c == '_'):
            return False
    return True


def is_server_running(pg_ctl_exe, path):
    status_cmd = '"' + pg_ctl_exe + '" status -D ' + path
    status_proc = subprocess.Popen(status_cmd, shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    out, err = status_proc.communicate()
    if out and 'no server running' not in out:
        return True
    elif err:
        return False


def is_valid_cluster_dir(pg_ctl_exe, path):
    status_cmd = '"' + pg_ctl_exe + '" status -D ' + path
    status_proc = subprocess.Popen(status_cmd, shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    out, err = status_proc.communicate()
    if out and 'server' in out:
        return True
    elif err and 'not a database cluster directory' in err:
        return False


class PGTest(object):
    def __init__(self, database, username='postgres', port=None, log_file=None,
                 no_cleanup=False, copy_data_path=None, base_dir=None,
                 pg_ctl=None):
        assert str_alphanum(database), 'Database must contain only letters and/or numbers'
        self._database = database

        assert str_alphanum(username), 'Username must contain only letters and/or numbers'
        self._username = username

        if pg_ctl:
            assert os.path.exists(pg_ctl), 'Executable does not exist: {path}'.format(path=pg_ctl)
            self._pg_ctl_exe = get_exe_path(pg_ctl)
        else:
            self._pg_ctl_exe = get_exe_path('pg_ctl')

        if copy_data_path:
            assert os.path.exists(copy_data_path), 'Directory does not exist: {path}'.format(path=copy_data_path)
            assert is_valid_cluster_dir(self._pg_ctl_exe, copy_data_path), 'Directory is not a database cluster directory: {path}'.format(path=copy_data_path)
        self._copy_data_path = copy_data_path

        if port:
            assert is_valid_port(port), 'Port is not between 1024 and 65535: {port}'.format(port=port)
            self._port = port
        else:
            self._port = bind_unused_port()

        if base_dir:
            assert os.path.exists(base_dir), 'Directory does not exist: {path}'.format(path=base_dir)
            self._base_dir = base_dir
        else:
            self._base_dir = tempfile.mkdtemp()

        if log_file:
            self._log_file = log_file
        else:
            self._log_file = os.path.join(self._base_dir, 'pgtest_log.txt')

        self._data_dir = os.path.join(self._base_dir, 'data')

        if not sys.platform.startswith('win'):
            self._listen_socket_dir = os.path.join(self._base_dir, 'tmp')
        else:
            self._listen_socket_dir = None

        self._no_cleanup = no_cleanup

        self._create_dirs()
        self._init_base_dir()
        self._set_dir_permissions()

    def __enter__(self):
        self.start_server()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()

    def __repr__(self):
        return ('{!s}(database={!r}, username={!r}, port={!s}, log_file={!r}, '
                'no_cleanup={!r}, copy_data_path={!r}, cluster={!r}, '
                'pg_ctl={!r})').format(self.__class__.__name__,
                self._database, self._username, self._port, self._log_file,
                self._no_cleanup, self._copy_data_path, self._base_dir,
                self._pg_ctl_exe)

    @property
    def port(self):
        return self._port

    @property
    def cluster(self):
        return self._data_dir

    @property
    def log_file(self):
        return self._log_file

    @property
    def username(self):
        return self._username

    @property
    def pg_ctl(self):
        return self._pg_ctl_exe

    @property
    def url(self):
        return 'postgresql://{user}@localhost:{port}/{db}'.format(
                user=self._username, port=self._port, db=self._database)

    def start_server(self):
        try:
            if sys.platform.startswith('win'):
                pg_cmd = ('"' + self._pg_ctl_exe + '" start -D ' + self._data_dir +
                          ' -l ' + self._log_file + ' -o "-F -p ' +
                          str(self._port) + ' -d 1 -c logging_collector=off"')
            else:
                pg_cmd = ('"' + self._pg_ctl_exe + '" start -D ' + self._data_dir +
                          ' -l ' + self._log_file + ' -o "-F -p ' +
                          str(self._port) + ' -d 1 -c logging_collector=off -k ' +
                          self._listen_socket_dir + '"')
            subprocess.Popen(pg_cmd, shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
            self._wait_for_server_ready(10)
        except:
            self.cleanup()
            raise
        try:
            self._create_database()
            return True
        except:
            raise

    def stop_server(self):
        stop_cmd = '"' + self._pg_ctl_exe + '" stop -m fast -D ' + self._data_dir
        stop = subprocess.Popen(stop_cmd, shell=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        _, err = stop.communicate()
        if err:
            self.cleanup()
            raise RuntimeError(err)

    def close(self):
        self.stop_server()
        self.cleanup()

    def cleanup(self):
        if not self._no_cleanup:
            shutil.rmtree(self._base_dir, ignore_errors=True)

    def dsn(self, **kwargs):
        dsn_dict = dict(kwargs)
        dsn_dict.setdefault('port', self._port)
        dsn_dict.setdefault('host', 'localhost')
        dsn_dict.setdefault('user', self._username)
        dsn_dict.setdefault('database', self._database)
        return dsn_dict

    def _init_base_dir(self):
        try:
            if self._copy_data_path:
                shutil.rmtree(self._data_dir)
                shutil.copytree(self._copy_data_path, self._data_dir)
            else:
                init_cmd = ('"' + self._pg_ctl_exe + '" initdb -D ' +
                            self._data_dir + ' -o "-U ' +
                            self._username + ' -A trust"')
                init_proc = subprocess.Popen(init_cmd, shell=True,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)
                _, err = init_proc.communicate()
                if err:
                    raise IOError(err)
            assert is_valid_cluster_dir(self._pg_ctl_exe, self._data_dir), 'Failed to create cluster: {path}'.format(path=self._data_dir)
        except:
            self.cleanup()
            raise

    def _create_dirs(self):
        try:
            for path in (self._base_dir, self._data_dir, self._listen_socket_dir):
                if path and not os.path.exists(path):
                    os.makedirs(path)
        except:
            self.cleanup()
            raise

    def _set_dir_permissions(self):
        try:
            for path in (self._base_dir, self._data_dir, self._listen_socket_dir):
                os.chmod(path, 0o700)
        except:
            self.cleanup()
            raise

    def _is_connection_available(self):
        try:
            with closing(pg8000.connect(**self.dsn(database='template1'))):
                pass
        except pg8000.Error:
            return False
        else:
            return True

    def _wait_for_server_ready(self, timeout):
        endtime = datetime.datetime.utcnow() + datetime.timedelta(seconds=timeout)
        while not self._is_connection_available():
            time.sleep(0.1)
            if datetime.datetime.utcnow() > endtime:
                raise TimeoutError('Server failed to start')

    def _create_database(self):
        with closing(pg8000.connect(**self.dsn(database='postgres'))) as conn:
            conn.autocommit = True
            with closing(conn.cursor()) as cursor:
                cursor.execute("SELECT COUNT(*) FROM pg_database WHERE "
                               "datname='{database}'".format(database=self._database))
                if cursor.fetchone()[0] <= 0:
                    query = 'CREATE DATABASE "{database}"'.format(database=self._database)
                    cursor.execute(query)


def main():
    with PGTest('test', no_cleanup=True) as pg:
        print pg


if __name__ == '__main__':
    main()
