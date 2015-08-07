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


def url(user, password, host, port, db):
    return 'postgresql://{user}:{password}@{host}:{port}/{db}'.format(
            user=user, password=password, host=host, port=port, db=db)


def is_valid_cluster_dir(path):
    status_cmd = PG_CTL_EXE + ' status -D ' + path
    status_proc = subprocess.Popen(status_cmd, shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    out, err = status_proc.communicate()
    if out and 'server' in out:
        return True
    elif err and 'not a database cluster directory' in err:
        return False


def is_valid_cluster_dir(path):
    status_cmd = PG_CTL_EXE + ' status -D ' + path
    status_proc = subprocess.Popen(status_cmd, shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    out, err = status_proc.communicate()
    if out and 'running' in out:
        return True
    elif err and 'not a database cluster directory' in err:
        return False


def str_alphanum(instr):
    for c in instr:
        if not (c.isalpha() or c.isdigit()):
            return False
    return True


class PGTest(object):
    def __init__(self, db_name='test', copy_data_path=None):
        assert str_alphanum(db_name), 'Database name must contain only letters and/or numbers'
        if copy_data_path:
            assert os.path.exists(copy_data_path), 'Directory does not exist: {path}'.format(path=copy_data_path)
            assert is_valid_cluster_dir(copy_data_path), 'Directory is not a database cluster directory: {path}'.format(path=copy_data_path)

        self._pg_ctl_exe = get_exe_path('pg_ctl')
        self._copy_data_path = copy_data_path
        self._temp_dir = tempfile.mkdtemp()
        self._log_file = os.path.join(self._temp_dir, 'log.txt')
        self._data_dir = os.path.join(self._temp_dir, 'data')
        self._db_name = db_name
        self._port = bind_unused_port()
        if not sys.platform.startswith('win'):
            self._listen_socket_dir = os.path.join(self._temp_dir, 'tmp')
        else:
            self._listen_socket_dir = None

        self._create_dirs()
        self._init_cluster()
        self._set_dir_permissions()
        self.start_server()
        self._create_database()
        self.stop_server()
        self.cleanup()

    def _init_cluster(self):
        if self._copy_data_path:
            shutil.copytree(self._copy_data_path, self._data_dir)
        else:
            init_cmd = PG_CTL_EXE + ' initdb -D ' + self._data_dir + ' -o "-U postgres -A trust"'
            init_proc = subprocess.Popen(init_cmd, shell=True,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
            out, err = init_proc.communicate()
            if err:
                raise IOError(err)
        assert is_valid_cluster_dir(self._data_dir), 'Failed to create cluster: {path}'.format(path=self._data_dir)

    def _create_dirs(self):
        for path in (self._temp_dir, self._data_dir, self._listen_socket_dir):
            if path and not os.path.exists(path):
                os.makedirs(path)

    def _set_dir_permissions(self):
        for path in (self._temp_dir, self._data_dir, self._listen_socket_dir):
            os.chmod(path, 0o700)

    def start_server(self):
        if sys.platform.startswith('win'):
            pg_cmd = (self._pg_ctl_exe + ' start -D ' + self._data_dir + ' -l ' + self._log_file +
                    ' -o "-F -p ' + str(self._port) + ' -d 1 -c logging_collector=off"')
        else:
            pg_cmd = (self._pg_ctl_exe + ' start -D ' + self._data_dir + ' -l ' + self._log_file +
                    ' -o "-F -p ' + str(self._port) +
                    ' -d 1 -c logging_collector=off -k ' + self._listen_socket_dir + '"')
        subprocess.Popen(pg_cmd, shell=True)
        self._wait_for_server_ready(10)

    def dsn(self, **kwargs):
        # "database=test host=localhost user=postgres"
        params = dict(kwargs)
        params.setdefault('port', self._port)
        params.setdefault('host', 'localhost')
        params.setdefault('user', 'postgres')
        params.setdefault('database', self._db_name)
        return params

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
            if datetime.datetime.utcnow() > endtime: # if more than two seconds has elapsed
                raise TimeoutError('Server failed to start')

    def _create_database(self):
        with closing(pg8000.connect(**self.dsn(database='postgres'))) as conn:
            conn.autocommit = True
            with closing(conn.cursor()) as cursor:
                cursor.execute('CREATE DATABASE {db_name}'.format(db_name=self._db_name))

    def stop_server(self):
        stop_cmd = self._pg_ctl_exe + ' stop -m fast -D ' + self._data_dir
        stop = subprocess.Popen(stop_cmd, shell=True,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
        out, err = stop.communicate()
        if err:
            raise RuntimeError(err)

    def _cleanup(self):
        shutil.rmtree(self._temp_dir, ignore_errors=True)


def main():
    pg = PGTest()


if __name__ == '__main__':
    main()

