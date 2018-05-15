"""This file tests internal details of AndroidPlatform. These are not part of the public API,
and should not be accessed or relied upon by user code.
"""

from __future__ import absolute_import, division, print_function

from contextlib import contextmanager
from importlib import import_module
import marshal
import os
from os.path import dirname, exists, isfile, join
import platform
import shlex
import sqlite3
from subprocess import check_output
import sys
import tempfile
from traceback import format_exc
import unittest

if sys.version_info[0] < 3:
    from urllib2 import urlopen
    bytes = str
else:
    from importlib import reload
    from urllib.request import urlopen
    unicode = str


try:
    from android.os import Build
except ImportError:
    API_LEVEL = None
else:
    API_LEVEL = Build.VERSION.SDK_INT
    from java.android import importer
    context = __loader__.finder.context  # noqa: F821

    from com.chaquo.python.android import AndroidPlatform
    APP_ZIP = "app.zip"
    REQS_COMMON_ZIP = "requirements-common.zip"
    REQS_ABI_ZIP = "requirements-{}.zip".format(AndroidPlatform.ABI)

def setUpModule():
    if API_LEVEL is None:
        raise unittest.SkipTest("Not running on Android")


class TestAndroidImport(unittest.TestCase):

    def test_init(self):
        self.check_module("markupsafe", REQS_COMMON_ZIP, "markupsafe/__init__.py",
                          package_path=[asset_path(REQS_COMMON_ZIP), asset_path(REQS_ABI_ZIP)],
                          source_head='# -*- coding: utf-8 -*-\n"""\n    markupsafe\n')

    def test_py(self):
        # Despite its name, this is a pure Python module.
        mod_name = "markupsafe._native"
        filename = "markupsafe/_native.py"
        cache_filename = asset_cache(REQS_COMMON_ZIP, filename + "c")
        mod = self.check_module(
            mod_name, REQS_COMMON_ZIP, filename,
            source_head='# -*- coding: utf-8 -*-\n"""\n    markupsafe._native\n')

        mod.foo = 1
        delattr(mod, "escape")
        reload(mod)
        self.assertEqual(1, mod.foo)
        self.assertTrue(hasattr(mod, "escape"))

        # A valid .pyc should not be written again.
        with self.set_mode(cache_filename, "444"):
            mod = self.clean_reload(mod)

        # And if the header matches, the code in the .pyc should be used, whatever it is.
        header = self.read_pyc_header(cache_filename)
        with open(cache_filename, "wb") as pyc_file:
            pyc_file.write(header)
            code = compile("foo = 2", "<test>", "exec")
            marshal.dump(code, pyc_file)
        self.assertFalse(hasattr(mod, "foo"))  # Should have been removed by clean_reload.
        mod = self.clean_reload(mod)
        self.assertEqual(2, mod.foo)
        self.assertFalse(hasattr(mod, "escape"))

        # A .pyc with mismatching header should be written again.
        new_header = header[0:4] + b"\x00\x01\x02\x03" + header[8:]
        self.write_pyc_header(cache_filename, new_header)
        with self.set_mode(cache_filename, "444"):
            with self.assertRaisesRegexp(IOError, "Permission denied"):
                self.clean_reload(mod)
        self.clean_reload(mod)
        self.assertEqual(header, self.read_pyc_header(cache_filename))

    def read_pyc_header(self, filename):
        return open(filename, "rb").read(12)

    def write_pyc_header(self, filename, header):
        with open(filename, "r+b") as pyc_file:
            pyc_file.seek(0)
            pyc_file.write(header)

    def test_so(self):
        mod_name = "markupsafe._speedups"
        filename = "markupsafe/_speedups.so"
        cache_filename = asset_cache(REQS_ABI_ZIP, filename)
        mod = self.check_module(mod_name, REQS_ABI_ZIP, filename)
        with self.assertRaisesRegexp(ImportError,
                                     "'{}': cannot reload a native module".format(mod_name)):
            reload(mod)

        # A valid file should not be extracted again.
        with self.set_mode(cache_filename, "444"):
            mod = self.clean_reload(mod)

        # A file with mismatching mtime should be extracted again.
        original_mtime = os.stat(cache_filename).st_mtime
        os.utime(cache_filename, None)
        with self.set_mode(cache_filename, "444"):
            with self.assertRaisesRegexp(IOError, "Permission denied"):
                self.clean_reload(mod)
        self.clean_reload(mod)
        self.assertEqual(original_mtime, os.stat(cache_filename).st_mtime)

    @contextmanager
    def set_mode(self, filename, mode_str):
        original_mode = os.stat(filename).st_mode
        try:
            os.chmod(filename, int(mode_str, 8))
            yield
        finally:
            os.chmod(filename, original_mode)

    def clean_reload(self, mod):
        sys.modules.pop(mod.__name__, None)
        new_mod = import_module(mod.__name__)
        self.assertIsNot(new_mod, mod)
        return new_mod

    def check_module(self, mod_name, zip_name, filename, package_path=None, source_head=None):
        cache_filename = asset_cache(zip_name, filename)
        if cache_filename.endswith(".py"):
            cache_filename += "c"
        if exists(cache_filename):
            os.remove(cache_filename)
        sys.modules.pop(mod_name, None)  # Force reload, to check cache file is recreated.
        mod = import_module(mod_name)
        self.assertTrue(exists(cache_filename))

        # Module attributes
        self.assertEqual(mod_name, mod.__name__)
        self.assertEqual(join(asset_path(zip_name), filename), mod.__file__)
        self.assertFalse(isfile(mod.__file__))
        if package_path:
            self.assertEqual(package_path, mod.__path__)
            self.assertEqual(mod_name, mod.__package__)
        else:
            self.assertFalse(hasattr(mod, "__path__"))
            self.assertEqual(mod_name.rpartition(".")[0], mod.__package__)
        loader = mod.__loader__
        self.assertIsInstance(loader, importer.AssetLoader)

        # Optional loader methods
        if zip_name == REQS_COMMON_ZIP:
            data = loader.get_data(asset_path(zip_name, "markupsafe/_constants.py"))
            self.assertTrue(data.startswith(
                b'# -*- coding: utf-8 -*-\n"""\n    markupsafe._constants\n'), repr(data))
        with self.assertRaisesRegexp(IOError, "loader for '{}' can't access '/invalid.py'"
                                     .format(asset_path(zip_name))):
            loader.get_data("/invalid.py")
        with self.assertRaisesRegexp(IOError, "There is no item named 'invalid.py' in the archive"):
            loader.get_data(asset_path(zip_name, "invalid.py"))

        self.assertEqual(bool(package_path), loader.is_package(mod_name))
        self.assertIsNone(loader.get_code(mod_name))
        source = loader.get_source(mod_name)
        if source_head:
            self.assertTrue(source.startswith(source_head), repr(source))
        else:
            self.assertIsNone(source)
        self.assertEqual(mod.__file__, loader.get_filename(mod_name))

        return mod

    # Verify that the traceback builder can get source code from the loader in all contexts.
    # (The "package1" test files are also used in test_import.)
    def test_exception(self):
        # Compilation
        try:
            from package1 import syntax_error  # noqa
        except SyntaxError:
            s = format_exc()
            self.assertRegexpMatches(
                s,
                r'File "{}/package1/syntax_error.py", line 1\n'
                r'    one two\n'
                r'          \^\n'
                r'SyntaxError: invalid syntax\n$'.format(asset_path(APP_ZIP)))
        else:
            self.fail()

        # Module execution
        try:
            from package1 import recursive_import_error  # noqa
        except ImportError:
            s = format_exc()
            self.assertRegexpMatches(
                s,
                r'File "{}/package1/recursive_import_error.py", line 1, in <module>\n'
                r'    from os import nonexistent\n'
                r"ImportError: cannot import name '?nonexistent'?\n$".format(asset_path(APP_ZIP)))
        else:
            self.fail()

        # After import complete
        class C(object):
            __html__ = None
        try:
            from markupsafe import _native
            _native.escape(C)
        except TypeError:
            s = format_exc()
            self.assertRegexpMatches(
                s,
                r'File "{}/markupsafe/_native.py", line 21, in escape\n'.format(
                    asset_path(REQS_COMMON_ZIP)) +
                r'    return s.__html__\(\)\n'
                r"TypeError: 'NoneType' object is not callable\n$")
        else:
            self.fail()

    def test_extract_package(self):
        self.check_extracted_module("certifi", REQS_COMMON_ZIP, "certifi/__init__.py",
                                    package_path=[asset_path(REQS_COMMON_ZIP),
                                                  asset_path(REQS_ABI_ZIP)])
        self.check_extracted_module("certifi.core", REQS_COMMON_ZIP, "certifi/core.py")

        import certifi
        self.assertTrue(isfile(join(dirname(certifi.__file__), "cacert.pem")))

    def check_extracted_module(self, mod_name, zip_name, filename, package_path=None):
        mod = import_module(mod_name)
        self.assertEqual(mod_name, mod.__name__)
        self.assertEqual(asset_cache(zip_name, filename), mod.__file__)
        self.assertTrue(isfile(mod.__file__))
        if package_path:
            self.assertEqual(package_path, mod.__path__)
            self.assertEqual(mod_name, mod.__package__)
        else:
            self.assertFalse(hasattr(mod, "__path__"))
            self.assertEqual(mod_name.rpartition(".")[0], mod.__package__)
        self.assertIsInstance(mod.__loader__, importer.AssetLoader)


def asset_path(*paths):
    return join("/android_asset/chaquopy", *paths)

def asset_cache(*paths):
    return join(context.getCacheDir().toString(), "chaquopy/AssetFinder", *paths)


class TestAndroidStdlib(unittest.TestCase):

    def test_lib2to3(self):
        # Will fail unless grammar files are available in stdlib zip.
        from lib2to3 import pygram  # noqa: F401

    def test_os(self):
        self.assertEqual("posix", os.name)

    def test_platform(self):
        # This depends on sys.executable existing.
        p = platform.platform()
        self.assertRegexpMatches(p, r"^Linux")

    def test_sqlite(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("create table test (a text, b text)")
        conn.execute("insert into test values ('alpha', 'one'), ('bravo', 'two')")
        cur = conn.execute("select b from test where a = 'bravo'")
        self.assertEqual([("two",)], cur.fetchall())

    def test_ssl(self):
        resp = urlopen("https://chaquo.com/chaquopy/")
        self.assertEqual(200, resp.getcode())
        self.assertRegexpMatches(resp.info()["Content-type"], r"^text/html")

    def test_sys(self):
        self.assertEqual([""], sys.argv)
        self.assertTrue(exists(sys.executable), sys.executable)
        for p in sys.path:
            self.assertTrue(exists(p) or p.startswith("/android_asset"), p)
        self.assertRegexpMatches(sys.platform, r"^linux")

    def test_tempfile(self):
        with tempfile.NamedTemporaryFile() as f:
            self.assertEqual(join(str(context.getCacheDir()), "chaquopy/tmp"),
                             dirname(f.name))


@unittest.skipIf(API_LEVEL and API_LEVEL < 16,
                 "logcat command requires READ_LOGS permission on this API level, which we "
                 "don't request because Google Play describes it as giving access to 'browsing "
                 "history and bookmarks'.")
class TestAndroidStreams(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        from android.util import Log
        Log.i(*self.get_marker())
        self.expected_log = []

    def write(self, stream, s, expected_log):
        self.assertEqual(len(s), stream.write(s))
        self.expected_log += [line.decode("utf-8") if isinstance(line, bytes) else line
                              for line in expected_log]

    def tearDown(self):
        actual_log = None
        marker = "I/{}: {}".format(*self.get_marker())
        for line in check_output(shlex.split("logcat -d -v tag")).decode("UTF-8").splitlines():
            if line == marker:
                actual_log = []
            elif actual_log is not None and "/python.std" in line:
                actual_log.append(line)
        self.assertEqual(self.expected_log, actual_log)

    def get_marker(self):
        cls_name, test_name = self.id().split(".")[-2:]
        return cls_name, test_name

    def test_output(self):
        out = sys.stdout
        err = sys.stderr
        for stream in [out, err]:
            self.assertTrue(stream.writable())
            self.assertFalse(stream.readable())

        self.write(out, "a",             ["I/python.stdout: a"])
        self.write(out, "Hello world",   ["I/python.stdout: Hello world"])
        self.write(err, "Hello stderr",  ["W/python.stderr: Hello stderr"])
        self.write(out, " ",             ["I/python.stdout:  "])
        self.write(out, "  ",            ["I/python.stdout:   "])

        non_ascii = [
            (b"ol\xc3\xa9",               u"ol\u00e9"),         # Spanish
            (b"\xe4\xb8\xad\xe6\x96\x87", u"\u4e2d\u6587"),     # Chinese
        ]
        for b, u in non_ascii:
            expected = [u"I/python.stdout: " + u]
            self.write(out, u, expected)
            if sys.version_info[0] < 3:
                self.write(out, b, expected)

        # Empty lines can't be logged, so we change them to a space. Empty strings, on the
        # other hand, should be ignored.
        #
        # Avoid repeating log messages as it may activate "chatty" filtering and break the
        # tests. Also, it makes debugging easier.
        self.write(out, "",              [])
        self.write(out, "\n",            ["I/python.stdout:  "])
        self.write(out, "\na",           ["I/python.stdout:  ",
                                          "I/python.stdout: a"])
        self.write(out, "b\n",           ["I/python.stdout: b"])
        self.write(out, "c\n\n",         ["I/python.stdout: c",
                                          "I/python.stdout:  "])
        self.write(out, "d\ne",          ["I/python.stdout: d",
                                          "I/python.stdout: e"])
        self.write(out, "f\n\ng",        ["I/python.stdout: f",
                                          "I/python.stdout:  ",
                                          "I/python.stdout: g"])

    # The maximum line length is 4000.
    def test_output_long(self):
        self.write(sys.stdout, "foobar" * 700,
                   ["I/python.stdout: " + ("foobar" * 666) + "foob",
                    "I/python.stdout: ar" + ("foobar" * 33)])

    def test_input(self):
        self.assertTrue(sys.stdin.readable())
        self.assertFalse(sys.stdin.writable())
        self.assertEqual("", sys.stdin.read())
        self.assertEqual("", sys.stdin.read(42))
        self.assertEqual("", sys.stdin.readline())
        self.assertEqual("", sys.stdin.readline(42))
