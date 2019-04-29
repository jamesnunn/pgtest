# encoding: utf-8
# The MIT License (MIT)
#
# Copyright (c) 2015 James Nunn
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


from __future__ import print_function
from contextlib import closing
import os
import re
import glob
import shutil
import socket
import subprocess
import sys
import tempfile
import numbers
import time
import datetime

if sys.version_info >= (3, 0):
    unicode = str
    basestring = (str, bytes)

try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError

import pg8000


class TimeoutError(BaseException):
    def __init__(self, message):
        super(TimeoutError, self).__init__(message)

def is_executable(file_path):
    """Checks whether file_path points to executable file."""
    return file_path and os.path.isfile(file_path) and os.access(file_path, os.X_OK)

def which(in_file):
    """Finds an executable program in the system and returns the program name

    Accepts filenames with or without full paths with or without file
    extensions. If running on unix, /usr/lib/postgresql will be searched and
    the `locate` commmand will be used as a last resort to find the
    executable.

    Args:
        in_file - str, program name or path to find

    Returns:
        file_path - str, normalised path to file found
        
    Raises:
        FileNotFoundError, if no executable file not found
    """
    if not isinstance(in_file, basestring):
        raise TypeError('file must be a valid string')
    path_no_ext, _ = os.path.splitext(in_file)
    path_with_exe = path_no_ext + '.exe'

    # Look for the exe at the path supplied
    if os.path.split(path_no_ext)[0]:
        if is_executable(in_file):
            return os.path.normpath(in_file)
        elif is_executable(path_with_exe):
            return os.path.normpath(path_with_exe)
    # Search inside the PATH
    else:
        for path in os.environ['PATH'].split(os.pathsep):
            file_path = os.path.join(path.strip('"'), in_file)
            file_path_with_exe = os.path.join(path.strip('"'), path_with_exe)
            if is_executable(file_path_with_exe):
                return os.path.normpath(file_path_with_exe)
            elif is_executable(file_path):
                return os.path.normpath(file_path)

    if not sys.platform.startswith('win'):
        # first, search default locations, inspired by Debian's PgCommon.pm
        try:
            pg_ctls = {float(re.search(r'postgresql/([\d\.]+)/bin', p).group(1)):
                    p for p in glob.glob('/usr/lib/postgresql/*/bin/' + in_file)}
            file_path = pg_ctls[max(pg_ctls)]
            if is_executable(file_path):
                return os.path.normpath(file_path)

        except (AttributeError, ValueError):
            # AttributeError occurs if re.search returns None,
            # ValueError if pg_ctls is empty
            pass

        # otherwise fall back to `locate` command
        try:
            exact_file_regex = '/' + in_file + '$'
            locate_cmd = ['locate', '-r', exact_file_regex]
            results = subprocess.check_output(locate_cmd)
            for file_path in results.decode('utf-8').split('\n'):
                if is_executable(file_path):
                    return os.path.normpath(file_path)
        except subprocess.CalledProcessError:
            pass

        raise FileNotFoundError("'{}' could not be found.".format(in_file))

def is_valid_port(port):
    """Checks a port number to check if it is within the valid range

    Args:
        port - int, port number to check

    Returns:
        bool, True if the port is within the valid range or False if not
    """
    if not isinstance(port, int):
        return False
    return 1024 < port < 65535


def bind_unused_port():
    """Gets an unused port number.

    There is the possibility that another process will steal the port between
    this function getting the port and your intended process using it - you
    must make sure that you handle this situation the time of starting your
    process.

    Returns:
        port - int, an as-yet unused port
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 0 binds to unused socket
    sock.bind(('localhost', 0))
    _, port = sock.getsockname()
    while not is_valid_port(port):
        port = bind_unused_port()
    sock.close()
    return port


def is_valid_db_object_name(name):
    """Checks if a name is a valid postgres object name

    Args:
        name - str, name to check for validity

    Returns:
        bool, whether the name is valid or not
    """
    if not isinstance(name, basestring):
        raise TypeError('name must be a valid string')
    pattern = re.compile('^(?!pg_)[a-zA-Z_][a-zA-Z0-9_]*$')
    if not re.match(pattern, name):
        return False
    return True


def is_server_running(path):
    """Checks whether a server process is running in a given cluster path

    Args:
        pg_ctl_exe - str, path to pg_ctl executable
        path - str, path to cluster directory

    Returns:
        bool, whether or not a server is running
    """
    pg_ctl_exe = which('pg_ctl')
    cmd = '"{pg_ctl}" status -D "{path}"'.format(pg_ctl=pg_ctl_exe, path=path)
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    out, _ = proc.communicate()
    if out.decode('utf-8').strip() == 'pg_ctl: no server running':
        return False
    else:
        return True


def is_valid_cluster_dir(path):
    """Checks whether a given path is a valid postgres cluster

    Args:
        pg_ctl_exe - str, path to pg_ctl executable
        path - str, path to directory

    Returns:
        bool, whether or not a directory is a valid postgres cluster
    """
    pg_controldata_exe = which('pg_controldata')
    cmd = '"{pg_controldata}" "{path}"'.format(
        pg_controldata=pg_controldata_exe, path=path)
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    _, err = proc.communicate()
    if 'No such file or directory' in err.decode('utf-8'):
        return False
    else:
        return True


# pylint: disable=too-many-instance-attributes
class PGTest(object):
    """Sets up a *very* temporary postgres cluster which can be used as a
    context or instantiated like any other class.

    Args:
        username - str, username for default database superuser
        port - int, port to connect on; you must ensure that the port is unused
        log_file - str, path to place the log file
        no_cleanup - bool, don't clean up dirs after PGTest.close() is called
        copy_cluster - str, copies cluster from this path
        base_dir - str, path to the base directory to init the cluster
        pg_ctl - str, path to the pg_ctl executable to use
        max_connections - int, maximum number of connections to the cluster
           defaults to 11 since PostgreSQL 10 on Ubuntu 18.04 defaults
           max_wal_senders = 10 and PostgreSQL requires the max_connections
           to be larger than the number of max_wal_senders

    Attributes:
        PGTest.port - int, port number bound by PGTest
        PGTest.cluster - str, cluster directory generated by PGTest
        PGTest.username - str, username used by PGTest. Default is 'postgres'
        PGTest.log_file - str, path to postgres log file
        PGTest.pg_ctl - str, path to pg_ctl executable
        PGTest.url - str, url for default postgres database on the cluster
        PGTest.dsn - dict, dictionary containing dsn key-value pairs for the
                     default postgres database on the cluster

    Methods:
        close() - Closes this instance of PGTest, cleans up directories

    Usage:
        As an instance:
            >>> import pgtest, psycopg2
            >>> pg = pgtest.PGTest()
            Server started: postgresql://postgres@localhost:47251/postgres
            >>> pg.port
            47251
            >>> pg.cluster
            '/tmp/tmpiDtBjs/data'
            >>> pg.username
            'postgres'
            >>> pg.log_file
            '/tmp/tmpiDtBjs/pgtest_log.txt'
            >>> pg.pg_ctl
            u'/usr/lib/postgresql/9.4/bin/pg_ctl'
            >>> pg.url
            'postgresql://postgres@localhost:47251/postgres'
            >>> pg.dsn
            {'user': 'postgres', 'host': 'localhost',
            'port': 47251, 'database': 'postgres'}

            >>> # Connect with other db driver here, e.g. psql, psycopg2,
            >>> # sqlalchemy etc
            >>> psycopg2.connect(**pg.dsn)

            >>> pg.close()
            Server stopped

        As a context:
            >>> with pgtest.PGTest() as pg:
            ...    # connect to db with psycopg/sqlalchemy etc
            ...    psycopg2.connect(**pg.dsn)
    """
    # pylint: disable=too-many-arguments
    def __init__(self, username='postgres', port=None, log_file=None,
                 no_cleanup=False, copy_cluster=None, base_dir=None,
                 pg_ctl=None, max_connections=11):
        self._database = 'postgres'

        assert is_valid_db_object_name(username), (
            'Username must contain only letters and/or numbers')
        self._username = username

        if pg_ctl:
            assert os.path.exists(pg_ctl), (
                'Executable does not exist: {path}').format(path=pg_ctl)
            self._pg_ctl_exe = which(pg_ctl)
        else:
            self._pg_ctl_exe = which('pg_ctl')

        if copy_cluster:
            assert os.path.exists(copy_cluster), (
                'Directory does not exist: {path}').format(path=copy_cluster)
            assert is_valid_cluster_dir(copy_cluster), (
                'Directory is not a cluster directory: '
                '{path}').format(path=copy_cluster)
        self._copy_cluster = copy_cluster

        if port:
            assert is_valid_port(port), (
                'Port is not between 1024 and 65535: {port}').format(port=port)
            self._port = port
        else:
            self._port = bind_unused_port()

        if base_dir:
            assert os.path.exists(base_dir), (
                'Directory does not exist: {path}').format(path=base_dir)
            self._base_dir = base_dir
        else:
            self._base_dir = tempfile.mkdtemp()

        if log_file:
            self._log_file = log_file
        else:
            self._log_file = os.path.join(self._base_dir, 'pgtest_log.txt')

        self._cluster = os.path.join(self._base_dir, 'data')

        if not sys.platform.startswith('win'):
            self._listen_socket_dir = os.path.join(self._base_dir, 'tmp')
        else:
            self._listen_socket_dir = None

        self._no_cleanup = no_cleanup
        assert isinstance(max_connections, numbers.Integral), (
            'Maximum number of connections must be an integer.')
        self._max_connections = max_connections

        self._create_dirs()
        self._init_base_dir()
        self._set_dir_permissions()
        self._start_server()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()

    def __repr__(self):
        return ('{!s}(database={!r}, username={!r}, port={!s}, log_file={!r}, '
                'no_cleanup={!r}, copy_cluster={!r}, cluster={!r}, '
                'pg_ctl={!r}), max_connections={!r}').format(
                    self.__class__.__name__, self._database, self._username,
                    self._port, self._log_file, self._no_cleanup,
                    self._copy_cluster, self._base_dir, self._pg_ctl_exe,
                    self._max_connections)

    @property
    def port(self):
        """Returns the port used by this instance
        """
        return self._port

    @property
    def cluster(self):
        """Returns the cluster directory path used by this instance
        """
        return self._cluster

    @property
    def log_file(self):
        """Returns the postgres log file path usef by this instance
        """
        return self._log_file

    @property
    def username(self):
        """Returns the username from this instance
        """
        return self._username

    @property
    def pg_ctl(self):
        """Returns the pg_ctl executable path from this instance
        """
        return self._pg_ctl_exe

    @property
    def url(self):
        """Returns a url of the database created by this instance of PGTest
        which can be passed into postgresql libraries, e.g:

            >>> import pgtest, sqlalchemy
            >>> pg = pgtest.PGTest()
            >>> engine = sqlalchemy.create_engine(self.pg.url)
        """
        return 'postgresql://{user}@localhost:{port}/{db}'.format(
            user=self._username, port=self._port, db=self._database)

    @property
    def dsn(self):
        """Return a dictionary containing key-value pairs which match dsn
        keys, for unpacking into other functions requiring a dsn, e.g:

            >>> import pgtest, psycopg2
            >>> pg = pgtest.PGTest()
            >>> # e.g. psycopg2 requires a dsn like:
            >>> # psycopg2.connect(database="test",
            >>> ...user="postgres", password="secret")
            >>> cnxn = psycopg2.connect(**pg.dsn)
        """
        return {'port': self._port,
                'host': 'localhost',
                'database': self._database,
                'user': self._username}

    def _start_server(self):
        """Start the portgres server and wait for it to respond before
        continuing. If an exception is raised, cleanup
        """
        if sys.platform.startswith('win'):
            socket_opt = ''
        else:
            socket_opt = '-k {unix_socket}'.format(
                unix_socket=self._listen_socket_dir)

        cmd = ('"{pg_ctl}" start -D "{cluster}" -l "{log_file}" -o "-F -d 1 '
               '-p {port} -c logging_collector=off '
               '-N {max_connections} {socket_opt}"').format(pg_ctl=self._pg_ctl_exe,
                                            cluster=self._cluster,
                                            log_file=self._log_file,
                                            port=self._port,
                                            max_connections=self._max_connections,
                                            socket_opt=socket_opt)
        try:
            subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
            self._wait_for_server_ready(5)
        except:
            print('Server failed to start')
            self._cleanup()
            raise

    def _stop_server(self):
        """Stop the postgres server. If an exception is raised, cleanup
        """
        cmd = '"{pg_ctl}" stop -m fast -D {cluster}'.format(
            pg_ctl=self._pg_ctl_exe, cluster=self._cluster)

        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            _, err = proc.communicate()
            if err:
                raise RuntimeError(err)
        except:
            self._cleanup()
            raise

    def close(self):
        """Stop the server and cleanup the direcotries created
        """
        self._stop_server()
        self._cleanup()

    def _cleanup(self):
        """Deletes all generated directories (but not log files) created by
        this instance. If not cleaned up for any reason, no big deal since by
        default the directories are created in the users own temp directory
        """
        if not self._no_cleanup:
            shutil.rmtree(self._base_dir, ignore_errors=True)

    def _init_base_dir(self):
        """Initiates the base directory and creates a cluster, either brand new
        or by copying the cluster defined by the user
        """
        try:
            if self._copy_cluster:
                shutil.rmtree(self._cluster)
                shutil.copytree(self._copy_cluster, self._cluster)
            else:
                cmd = ('"{pg_ctl}" initdb -D "{cluster}" -o "-U {username} -A '
                       'trust"').format(pg_ctl=self._pg_ctl_exe,
                                        cluster=self._cluster,
                                        username=self._username)

                proc = subprocess.Popen(cmd, shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                _, err = proc.communicate()
                if err:
                    raise IOError(err)
            assert is_valid_cluster_dir(self._cluster), (
                'Failed to create cluster: {path}').format(path=self._cluster)
        except:
            self._cleanup()
            raise

    def _create_dirs(self):
        """Creates the directories required by postgres to create the cluster
        """
        try:
            for path in (self._base_dir, self._cluster,
                         self._listen_socket_dir):
                if path and not os.path.exists(path):
                    os.makedirs(path)
        except:
            self._cleanup()
            raise

    def _set_dir_permissions(self):
        """Sets the directory permissions to 777
        """
        try:
            for path in (self._base_dir, self._cluster,
                         self._listen_socket_dir):
                if path and os.path.exists(path):
                    os.chmod(path, 0o700)
        except:
            self._cleanup()
            raise

    def _is_connection_available(self):
        """Tests if the connection to the new cluster is available
        """
        try:
            with closing(pg8000.connect(**self.dsn)):
                return True
        except pg8000.Error:
            return False

    def _wait_for_server_ready(self, wait):
        """Sleep while we have no connection, timing out after `wait` seconds

        Args:
            wait - int, number of seconds to timeout the connection
        """
        endtime = datetime.datetime.utcnow() + datetime.timedelta(seconds=wait)
        while not self._is_connection_available():
            time.sleep(0.1)
            if datetime.datetime.utcnow() > endtime:
                raise TimeoutError('Server failed to start')
