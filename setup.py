# encoding: utf-8
from setuptools import setup

setup(
    name='pgtest',
    version='1.3.2',
    description=('Creates a temporary, local PostgreSQL database cluster and '
                 'server for unittesting, and cleans up after itself'),
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/jamesnunn/pgtest',
    author='James Nunn',
    author_email='jamesnunn123@gmail.com',
    license='MIT',
    packages=['pgtest'],
    install_requires = ['pg8000 >= 1.10'])
