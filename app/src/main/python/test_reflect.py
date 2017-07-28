from __future__ import absolute_import, division, print_function
import unittest
from java import *


class TestReflect(unittest.TestCase):

    def setUp(self):
        self.Test = jclass('com.chaquo.python.TestBasics')
        self.t = self.Test()

    def test_bootstrap(self):
        # Test a non-inherited method which we are unlikely ever to use in the reflection
        # process.
        klass = jclass("java.lang.Class").forName("java.lang.String")
        self.assertIsInstance(klass.desiredAssertionStatus(), bool)

    def test_jclass(self):
        Stack = jclass('java.util.Stack')
        StackSlash = jclass('java/util/Stack')
        self.assertIs(Stack, StackSlash)
        StackL = jclass('Ljava/util/Stack;')
        self.assertIs(Stack, StackL)

        stack = Stack()
        self.assertIsInstance(stack, Stack)

        # Java SE 8 throws NoClassDefFoundError like the JNI spec says, but Android 6 throws
        # ClassNotFoundException.
        with self.assertRaises(jclass("java.lang.NoClassDefFoundError")):
            jclass("java.lang.Nonexistent")

    def test_cast(self):
        Object = jclass("java.lang.Object")
        Boolean = jclass("java.lang.Boolean")
        o = Object()
        b = Boolean(True)

        cast(Object, b)
        with self.assertRaisesRegexp(TypeError, "cannot create java.lang.Boolean proxy from "
                                     "java.lang.Object instance"):
            cast(Boolean, o)

    def test_identity(self):
        # TODO #5181
        # self.assertIs(System.out, System.out)
        pass

    # See notes in PyObjectTest.finalize_
    def test_gc(self):
        System = jclass('java.lang.System')
        DelTrigger = jclass("com.chaquo.python.TestReflect$DelTrigger")
        DelTrigger.delTriggered = False
        dt = DelTrigger()
        self.assertFalse(DelTrigger.delTriggered)
        del dt
        System.gc()
        System.runFinalization()
        self.assertTrue(DelTrigger.delTriggered)

    def test_str_repr(self):
        Object = jclass('java.lang.Object')
        String = jclass('java.lang.String')

        o = Object()
        object_str = str(o)
        self.assertRegexpMatches(object_str, "^java.lang.Object@")
        self.assertEqual("<" + object_str + ">", repr(o))

        s = String("hello")
        self.assertEqual("hello", str(s))
        self.assertEqual("<java.lang.String 'hello'>", repr(s))

        self.assertEqual("cast('Ljava/lang/Object;', None)", repr(cast(Object, None)))
        self.assertEqual("cast('Ljava/lang/String;', None)", repr(cast(String, None)))

    def test_eq_hash(self):
        String = jclass('java.lang.String')
        self.verify_equal(String("hello"), String("hello"))
        self.verify_not_equal(String("hello"), String("world"))

        LinkedList = jclass("java.util.LinkedList")
        ArrayList = jclass("java.util.ArrayList")
        Arrays = jclass("java.util.Arrays")
        l = [1, 2]
        ll = LinkedList(Arrays.asList(l))
        al = ArrayList(Arrays.asList(l))
        self.verify_equal(ll, al)
        ll.set(1, 7)
        self.verify_not_equal(ll, al)

    def verify_equal(self, a, b):
        self.assertEqual(a, b)
        self.assertEqual(b, a)
        self.assertFalse(a != b)
        self.assertFalse(b != a)
        self.assertEqual(hash(a), hash(b))

    def verify_not_equal(self, a, b):
        self.assertNotEqual(a, b)
        self.assertNotEqual(b, a)
        self.assertFalse(a == b)
        self.assertFalse(b == a)
        self.assertNotEqual(hash(a), hash(b))

    # Most of the positive tests are in test_conversion, but here are some error tests.
    def test_static(self):
        for obj in [self.Test, self.t]:
            no_attr_msg = ("' object has no attribute" if obj is self.t
                           else "type object '.+' has no attribute")
            with self.assertRaisesRegexp(AttributeError, no_attr_msg):
                obj.staticNonexistent
            with self.assertRaisesRegexp(AttributeError, no_attr_msg):
                obj.staticNonexistent = True
            with self.assertRaisesRegexp(AttributeError, "final"):
                obj.fieldStaticFinalZ = True
            with self.assertRaisesRegexp(AttributeError, "not a field"):
                obj.setStaticZ = True
            with self.assertRaisesRegexp(AttributeError, "not a field"):
                obj.Nested = 99
            with self.assertRaisesRegexp(TypeError, "not callable"):
                obj.fieldStaticZ()
            with self.assertRaisesRegexp(TypeError, "takes 0 arguments \(1 given\)"):
                obj.staticNoArgs(True)
            with self.assertRaisesRegexp(TypeError, "takes at least 1 argument \(0 given\)"):
                obj.staticVarargs1()
            with self.assertRaisesRegexp(TypeError, "takes 1 argument \(0 given\)"):
                obj.setStaticZ()

    # Most of the positive tests are in test_conversion, but here are some error tests.
    def test_instance(self):
        with self.assertRaisesRegexp(AttributeError, "object has no attribute"):
            self.t.nonexistent
        with self.assertRaisesRegexp(AttributeError, "object has no attribute"):
            self.t.nonexistent = True
        with self.assertRaisesRegexp(AttributeError, "final"):
            self.t.fieldFinalZ = True
        with self.assertRaisesRegexp(AttributeError, "not a field"):
            self.t.setZ = True
        with self.assertRaisesRegexp(TypeError, "not callable"):
            self.t.fieldZ()
        with self.assertRaisesRegexp(TypeError, "takes 0 arguments \(1 given\)"):
            self.t.noArgs(True)
        with self.assertRaisesRegexp(TypeError, "takes at least 1 argument \(0 given\)"):
            self.t.varargs1()
        with self.assertRaisesRegexp(TypeError, "takes at least 1 argument \(0 given\)"):
            self.Test.varargs1(self.t)
        with self.assertRaisesRegexp(TypeError, "takes 1 argument \(0 given\)"):
            self.t.setZ()

        Object = jclass("java.lang.Object")
        with self.assertRaisesRegexp(AttributeError, "static context"):
            self.Test.fieldZ
        with self.assertRaisesRegexp(AttributeError, "static context"):
            self.Test.fieldZ = True
        with self.assertRaisesRegexp(TypeError, "must be called with .*TestBasics instance "
                                     "as first argument \(got nothing instead\)"):
            self.Test.getZ()
        with self.assertRaisesRegexp(TypeError, "must be called with .*TestBasics instance "
                                     "as first argument \(got Object instance instead\)"):
            self.Test.getZ(Object())
        self.assertEqual(False, self.Test.getZ(self.t))

    # This might seem silly, but an older version had a bug where bound methods could be
    # rebound by getting the same method from a different object, or instantiating a new object
    # of the same class.
    def test_multiple_instances(self):
        test1, test2 = self.Test(), self.Test()
        test1.fieldB = 127
        test2.fieldB = 10

        self.assertEquals(test2.fieldB, 10)
        self.assertEquals(test1.fieldB, 127)
        self.assertEquals(test2.fieldB, 10)
        self.assertEquals(test2.getB(), 10)
        self.assertEquals(test1.getB(), 127)
        self.assertEquals(test2.getB(), 10)

        method1 = test1.getB
        method2 = test2.getB
        self.assertEquals(method1(), 127)
        self.assertEquals(method2(), 10)
        self.assertEquals(method1(), 127)
        test3 = self.Test()
        test3.fieldB = 42
        self.assertEquals(method1(), 127)
        self.assertEquals(method2(), 10)

        test1.fieldB = 11
        test2.fieldB = 22
        self.assertEquals(test1.fieldB, 11)
        self.assertEquals(test2.fieldB, 22)
        self.assertEquals(test1.getB(), 11)
        self.assertEquals(test2.getB(), 22)

    def test_mixed_params(self):
        test = jclass('com.chaquo.python.TestBasics')()
        self.assertEquals(test.methodParamsZBCSIJFD(
            True, 127, 'k', 32767, 2147483467, 9223372036854775807, 1.23, 9.87), True)

    def test_out(self):
        # System.out implies recursive lookup and instantiation of the PrintWriter proxy class.
        System = jclass('java.lang.System')
        self.assertEqual(False, System.out.checkError())
        self.assertIsNone(System.out.flush())

    def test_unconstructible(self):
        System = jclass("java.lang.System")
        with self.assertRaisesRegexp(TypeError, "no accessible constructors"):
            System()

    def test_reserved_words(self):
        StringWriter = jclass("java.io.StringWriter")
        PrintWriter = jclass("java.io.PrintWriter")
        self.assertIs(PrintWriter.__dict__["print"], PrintWriter.__dict__["print_"])
        sw = StringWriter()
        pw = PrintWriter(sw)
        self.assertTrue(hasattr(pw, "print_"))
        self.assertFalse(hasattr(pw, "flush_"))
        pw.print_("Hello")
        pw.print_(" world")
        self.assertEqual("Hello world", sw.toString())

    # TODO #5183
    def test_name_clash(self):
        NameClash = jclass("com.chaquo.python.TestReflect$NameClash")
        self.assertEqual("method", NameClash.member())
        self.assertNotEqual("field", NameClash.member)

    def test_enum(self):
        SimpleEnum = jclass('com.chaquo.python.TestReflect$SimpleEnum')
        self.assertTrue(SimpleEnum.GOOD)
        self.assertTrue(SimpleEnum.BAD)
        self.assertTrue(SimpleEnum.UGLY)

        self.assertEqual(SimpleEnum.GOOD, SimpleEnum.GOOD)
        self.assertNotEqual(SimpleEnum.GOOD, SimpleEnum.BAD)

        self.assertEqual(0, SimpleEnum.GOOD.ordinal())
        self.assertEqual(1, SimpleEnum.BAD.ordinal())
        self.assertEqual(SimpleEnum.values()[0], SimpleEnum.GOOD)
        self.assertEqual(SimpleEnum.values()[1], SimpleEnum.BAD)

    def test_interface(self):
        Interface = jclass("com.chaquo.python.TestReflect$Interface")
        with self.assertRaisesRegexp(TypeError, "abstract"):
            Interface()

        self.assertEqual("Interface constant", Interface.iConstant)
        with self.assertRaisesRegexp(AttributeError, "final"):
            Interface.iConstant = "not constant"

        Child = jclass("com.chaquo.python.TestReflect$Child")
        with self.assertRaisesRegexp(TypeError, "must be called with .*Interface instance as "
                                     "first argument \(got nothing instead\)"):
            Interface.iMethod()
        self.assertEqual("Implemented method", Interface.iMethod(Child()))

        # Interfaces should expose all Object class methods.
        self.assertEqual("Child object", Interface.toString(Child()))

    def test_inheritance(self):
        Object = jclass("java.lang.Object")
        Interface = jclass("com.chaquo.python.TestReflect$Interface")
        SubInterface = jclass("com.chaquo.python.TestReflect$SubInterface")
        Parent = jclass("com.chaquo.python.TestReflect$Parent")
        Child = jclass("com.chaquo.python.TestReflect$Child")

        self.assertEqual((object,), Object.__bases__)
        self.assertEqual((Object,), Interface.__bases__)
        self.assertEqual((Interface,), SubInterface.__bases__)
        self.assertEqual((Object,), Parent.__bases__)
        self.assertEqual((Parent, Interface), Child.__bases__)

        self.assertEqual("Interface constant", Child.iConstant)
        self.verify_field(Child, "pStaticField", "Parent static field")
        self.assertEqual("Parent static method", Child.pStaticMethod())
        self.verify_field(Child, "oStaticField", "Overridden static field")
        self.assertEqual("Overridden static method", Child.oStaticMethod())

        c = Child()
        self.assertTrue(isinstance(c, Child))
        self.assertTrue(isinstance(c, Parent))
        self.assertTrue(isinstance(c, Interface))
        self.assertTrue(isinstance(c, Object))
        self.assertEqual("Interface constant", c.iConstant)
        self.assertEqual("Implemented method", c.iMethod())
        self.verify_field(c, "pStaticField", "Parent static field")
        self.verify_field(c, "pField", "Parent field")
        self.assertEqual("Parent static method", c.pStaticMethod())
        self.assertEqual("Parent method", c.pMethod())
        self.verify_field(c, "oStaticField", "Overridden static field")
        self.verify_field(c, "oField", "Overridden field")
        self.assertEqual("Overridden static method", c.oStaticMethod())
        self.assertEqual("Overridden method", c.oMethod())

        c_Interface = cast(Interface, c)
        self.assertFalse(isinstance(c_Interface, Child))
        self.assertFalse(isinstance(c_Interface, Parent))
        self.assertTrue(isinstance(c_Interface, Interface))
        self.assertTrue(isinstance(c_Interface, Object))
        self.assertEqual("Interface constant", c_Interface.iConstant)
        self.assertEqual("Implemented method", c_Interface.iMethod())

        c_Parent = cast(Parent, c)
        self.assertFalse(isinstance(c_Parent, Child))
        self.assertTrue(isinstance(c_Parent, Parent))
        self.assertFalse(isinstance(c_Parent, Interface))
        self.assertTrue(isinstance(c_Parent, Object))
        self.verify_field(c_Parent, "pStaticField", "Parent static field")
        self.verify_field(c_Parent, "pField", "Parent field")
        self.assertEqual("Parent static method", c_Parent.pStaticMethod())
        self.assertEqual("Parent method", c_Parent.pMethod())
        self.verify_field(c_Parent, "oStaticField", "Non-overridden static field")
        self.verify_field(c_Parent, "oField", "Non-overridden field")
        self.assertEqual("Non-overridden static method", c_Parent.oStaticMethod())
        self.assertEqual("Overridden method", c_Parent.oMethod())

    def verify_field(self, obj, name, value):
        self.assertEqual(value, getattr(obj, name))
        setattr(obj, name, "Modified")
        self.assertEqual("Modified", getattr(obj, name))
        setattr(obj, name, value)
        self.assertEqual(value, getattr(obj, name))

    def test_abstract(self):
        Abstract = jclass("com.chaquo.python.TestReflect$Abstract")
        with self.assertRaisesRegexp(TypeError, "abstract"):
            Abstract()

    def test_nested(self):
        TestReflect = jclass("com.chaquo.python.TestReflect")
        for cls_name in ["Interface", "Parent", "SimpleEnum", "Abstract"]:
            self.assertIs(jclass("com.chaquo.python.TestReflect$" + cls_name),
                          getattr(TestReflect, cls_name))

        self.assertTrue(issubclass(TestReflect.ParentOuter.ChildNested, TestReflect.ParentOuter))
