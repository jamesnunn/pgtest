# pgtest [![Build Status](https://travis-ci.org/jamesnunn/pgtest.svg?branch=master)](https://travis-ci.org/jamesnunn/pgtest)

Creates a temporary, local PostgreSQL database cluster and server specifically for unittesting, and cleans up after itself

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
