package com.chaquo.python.demo;

import com.chaquo.python.*;

public class PythonTestActivity extends UnitTestActivity {

    @Override
    protected void runTests() {
        Python py = Python.getInstance();
        PyObject unittest = py.getModule("unittest");
        PyObject stream = py.getModule("sys").get("stdout");  // https://bugs.python.org/issue10786
        PyObject runner = unittest.callAttr("TextTestRunner",
                                            new Kwarg("stream", stream),
                                            new Kwarg("verbosity", 2));
        PyObject loader = unittest.get("defaultTestLoader");
        PyObject suite = loader.callAttr("loadTestsFromModule", py.getModule("chaquopy.test"));
        runner.callAttr("run", suite);
    }

}
