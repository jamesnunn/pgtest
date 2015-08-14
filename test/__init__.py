# encoding: utf-8
import os
import re
import sys
import unittest


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
