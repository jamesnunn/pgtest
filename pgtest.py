# encoding: utf-8
from contextlib import closing
import multiprocessing
import os
import pg8000
import shutil
import socket
import subprocess
import sys
import tempfile
from time import sleep
import signal



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
        raise IOError('File not found: filename'.format(filename=filename))
    else:
        return pg_ctl_exe


def url(user, password, host, port, db):
    return 'postgresql://{user}:{password}@{host}:{port}/{db}'.format(
            user=user, password=password, host=host, port=port, db=db)


class PGTest(object):
    def __init__(self):
        pass




PG_CTL_NAME = 'pg_ctl'
TEMP_DIR = tempfile.mkdtemp()
DATA_DIR = os.path.join(TEMP_DIR, 'data')
LISTEN_DIR = os.path.join(TEMP_DIR, 'tmp')  # Only for Unix
PORT = bind_unused_port()


PG_CTL_EXE = get_exe_path(PG_CTL_NAME)


def dsn(**kwargs):
    # "database=test host=localhost user=postgres"
    params = dict(kwargs)
    params.setdefault('port', PORT)
    params.setdefault('host', 'localhost')
    params.setdefault('user', 'postgres')
    params.setdefault('database', 'test')
    return params


def is_connection_available():
    try:
        with closing(pg8000.connect(**dsn(database='template1'))):
            pass
    except pg8000.Error:
        return False
    else:
        return True


def main():
    for d in (TEMP_DIR, DATA_DIR, LISTEN_DIR):
        if not os.path.exists(d):
            os.makedirs(d)
            os.chmod(d, 0o700)

    if sys.platform.startswith('win') or sys.platform.startswith('darwin'):
        init_cmd = PG_CTL_EXE + ' initdb -D ' + DATA_DIR + ' -o "-U postgres -A trust"'
    else:
        init_cmd = PG_CTL_EXE + ' initdb -D ' + DATA_DIR + ' -o "-U postgres -A trust"'

    init_proc = subprocess.check_output(init_cmd, shell=True)

    if sys.platform.startswith('win') or sys.platform.startswith('darwin'):
        pg_cmd = PG_CTL_EXE + ' start -D ' + DATA_DIR + ' -o "-F -p ' + str(PORT) + ' -c logging_collector=off"'
    else:
        pg_cmd = PG_CTL_EXE + ' start -D ' + DATA_DIR + ' -o "-F -p ' + str(PORT) + ' -c logging_collector=off -k ' + LISTEN_DIR + '"'

    pg_proc = subprocess.Popen(pg_cmd, shell=True)

    while not is_connection_available():
        sleep(0.1)

    with closing(pg8000.connect(**dsn(database='postgres'))) as conn:
        conn.autocommit = True
        with closing(conn.cursor()) as cursor:
            cursor.execute('CREATE DATABASE test')
            cursor.execute('select 23456789')
            print cursor.fetchone()

    if sys.platform.startswith('win') or sys.platform.startswith('darwin'):
        stop = subprocess.check_output(PG_CTL_EXE + ' stop -m fast -D ' + DATA_DIR)
    else:
        stop = subprocess.check_output(PG_CTL_EXE + ' stop -m fast -D ' + DATA_DIR, shell=True)

    shutil.rmtree(TEMP_DIR, ignore_errors=True)

# if __name__ == '__main__':
#     main()
