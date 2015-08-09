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
    path_no_ext, ext = os.path.splitext(in_file)
    path_with_exe = path_no_ext + '.exe'
    # Look for the exe at the path supplied
    if os.path.split(path_no_ext)[0]:
        if os.path.isfile(in_file):
            file_path = in_file
        elif os.path.isfile(path_with_exe):
            file_path = path_with_exe
    else:
        for path in os.environ['PATH'].split(os.pathsep):
            file_path = os.path.join(path.strip('"'), in_file)
            file_path_with_exe = os.path.join(path.strip('"'), path_with_exe)
            if os.path.isfile(file_path_with_exe):
                file_path = file_path_with_exe
                break
            elif os.path.isfile(file_path):
                file_path = file_path
                break
    if is_exe(file_path):
        return os.path.normpath(file_path)


def locate(file_name):
    if sys.platform.startswith('win'):
        raise OSError('Not available on Windows')
    try:
        exact_file_regex = '/' + file_name + '$'
        results = subprocess.check_output(['locate', '-r', exact_file_regex])
        for file_path in results.split('\n'):
            if is_exe(file_path):
                return os.path.normpath(file_path)
    except subprocess.CalledProcessError:
        return


def is_valid_port(port):
    return 1024 < port < 65535


def bind_unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 0))
    _, port = sock.getsockname()
    while not is_valid_port(port):
        port = bind_unused_port()
    sock.close()
    return port


def get_exe_path(filename):
    if sys.platform.startswith('win'):
        pg_ctl_exe = which(filename)
    else:
        pg_ctl_exe = locate(filename)
    if not pg_ctl_exe:
        raise IOError('File not found: {filename}'.format(filename=filename))
    else:
        return pg_ctl_exe


def str_alphanum(instr):
    for c in instr:
        if not (c.isalpha() or c.isdigit()):
            return False
    return True


class PGTest(object):
    def __init__(self, database, username='postgres', port=None, log_file=None,
                 no_cleanup=False, copy_data_path=None, cluster=None,
                 pg_ctl=None):
        assert str_alphanum(database), 'Database must contain only letters and/or numbers'
        self._database = database

        assert str_alphanum(username), 'Username must contain only letters and/or numbers'
        self._username = username
        if copy_data_path:
            assert os.path.exists(copy_data_path), 'Directory does not exist: {path}'.format(path=copy_data_path)
            assert self._is_valid_cluster_dir(copy_data_path), 'Directory is not a database cluster directory: {path}'.format(path=copy_data_path)
        self._copy_data_path = copy_data_path

        if port:
            assert is_valid_port(port), 'Port is not between 1024 and 65535: {port}'.format(port=port)
            self._port = port
        else:
            self._port = bind_unused_port()

        if pg_ctl:
            assert os.path.exists(pg_ctl), 'Executable does not exist: {path}'.format(path=pg_ctl)
            self._pg_ctl_exe = get_exe_path(pg_ctl)
        else:
            self._pg_ctl_exe = get_exe_path('pg_ctl')

        if cluster:
            assert os.path.exists(cluster), 'Directory does not exist: {path}'.format(path=cluster)
            self._cluster = cluster
        else:
            self._cluster = tempfile.mkdtemp()

        if log_file:
            self._log_file = log_file
        else:
            self._log_file = os.path.join(self._cluster, 'pgtest_log.txt')

        self._data_dir = os.path.join(self._cluster, 'data')

        if not sys.platform.startswith('win'):
            self._listen_socket_dir = os.path.join(self._cluster, 'tmp')
        else:
            self._listen_socket_dir = None

        self._no_cleanup = no_cleanup

        self._create_dirs()
        self._init_cluster()
        self._set_dir_permissions()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()

    def __repr__(self):
        return ('{!s}(database={!r}, username={!r}, port={!s}, log_file={!r}, '
                'no_cleanup={!r}, copy_data_path={!r}, cluster={!r}, '
                'pg_ctl={!r})').format(self.__class__.__name__,
                self._database, self._username, self._port, self._log_file,
                self._no_cleanup, self._copy_data_path, self._cluster,
                self._pg_ctl_exe)

    @property
    def port(self):
        return self._port

    @property
    def cluster(self):
        return self._cluster

    @property
    def log_file(self):
        return self._log_file

    @property
    def username(self):
        return self._username

    @property
    def pg_ctl(self):
        return self._pg_ctl_exe


    def start_server(self):
        if sys.platform.startswith('win'):
            pg_cmd = (self._pg_ctl_exe + ' start -D ' + self._data_dir +
                      ' -l ' + self._log_file + ' -o "-F -p ' +
                      str(self._port) + ' -d 1 -c logging_collector=off"')
        else:
            pg_cmd = (self._pg_ctl_exe + ' start -D ' + self._data_dir +
                      ' -l ' + self._log_file + ' -o "-F -p ' +
                      str(self._port) + ' -d 1 -c logging_collector=off -k ' +
                      self._listen_socket_dir + '"')
        subprocess.Popen(pg_cmd, shell=True)
        self._wait_for_server_ready(10)
        self._create_database()

    def stop_server(self):
        stop_cmd = self._pg_ctl_exe + ' stop -m fast -D ' + self._data_dir
        stop = subprocess.Popen(stop_cmd, shell=True,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
        _, err = stop.communicate()
        if err:
            raise RuntimeError(err)

    def close(self):
        self.stop_server()
        if not self._no_cleanup:
            self.cleanup()

    def cleanup(self):
        shutil.rmtree(self._cluster, ignore_errors=True)

    def dsn(self, **kwargs):
        dsn_dict = dict(kwargs)
        dsn_dict.setdefault('port', self._port)
        dsn_dict.setdefault('host', 'localhost')
        dsn_dict.setdefault('user', self._username)
        dsn_dict.setdefault('database', self._database)
        return dsn_dict

    def url(self):
        return 'postgresql://{user}@localhost:{port}/{db}'.format(
                user=self._username, port=self._port, db=self._database)

    def _init_cluster(self):
        if self._copy_data_path:
            shutil.copytree(self._copy_data_path, self._data_dir)
        else:
            init_cmd = (self._pg_ctl_exe + ' initdb -D ' +
                        self._data_dir + ' -o "-U ' +
                        self._username + ' -A trust"')
            init_proc = subprocess.Popen(init_cmd, shell=True,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
            _, err = init_proc.communicate()
            if err:
                raise IOError(err)
        assert self._is_valid_cluster_dir(self._data_dir), 'Failed to create cluster: {path}'.format(path=self._data_dir)

    def _create_dirs(self):
        for path in (self._cluster, self._data_dir, self._listen_socket_dir):
            if path and not os.path.exists(path):
                os.makedirs(path)

    def _set_dir_permissions(self):
        for path in (self._cluster, self._data_dir, self._listen_socket_dir):
            os.chmod(path, 0o700)

    def _is_connection_available(self):
        try:
            with closing(pg8000.connect(**self.dsn(database='postgres'))):
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
                query = 'CREATE DATABASE "{database}"'.format(database=self._database)
                cursor.execute(query)

    def _is_valid_cluster_dir(self, path):
        status_cmd = self._pg_ctl_exe + ' status -D ' + path
        status_proc = subprocess.Popen(status_cmd, shell=True,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
        out, err = status_proc.communicate()
        if out and 'server' in out:
            return True
        elif err and 'not a database cluster directory' in err:
            return False

    def _is_cluster_running(self, path):
        status_cmd = self._pg_ctl_exe + ' status -D ' + path
        status_proc = subprocess.Popen(status_cmd, shell=True,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
        out, err = status_proc.communicate()
        if out and 'no server running' not in out:
            return True
        elif err:
            return False


def main():
    with PGTest('test') as pg:
        pg.start_server()


if __name__ == '__main__':
    main()

