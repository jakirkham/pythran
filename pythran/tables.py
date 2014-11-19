""" This modules provides the translation tables from python to c++. """

from pythran.intrinsic import Class, ReadOnceFunctionIntr, ConstExceptionIntr
from pythran.intrinsic import ClassWithConstConstructor, ExceptionClass
from pythran.intrinsic import ClassWithReadOnceConstructor
from pythran.intrinsic import ConstFunctionIntr, FunctionIntr, UpdateEffect
from pythran.intrinsic import ConstMethodIntr, MethodIntr, AttributeIntr
from pythran.intrinsic import ReadEffect, ConstantIntr
from pythran.conversion import to_ast, ToNotEval
from pythran.cxxtypes import NamedType
from pythran.types.conversion import PYTYPE_TO_CTYPE_TABLE
import pythran.cxxtypes as cxxtypes

import ast
import sys
import inspect
import logging

logger = logging.getLogger("pythran")

pythran_ward = '__pythran_'

namespace = "pythonic"

cxx_keywords = {
    'and', 'and_eq', 'asm', 'auto', 'bitand', 'bitor',
    'bool', 'break', 'case', 'catch', 'char', 'class',
    'compl', 'const', 'const_cast', 'continue', 'default', 'delete',
    'do', 'double', 'dynamic_cast', 'else', 'enum', 'explicit',
    'export', 'extern', 'false', 'float', 'for', 'friend',
    'goto', 'if', 'inline', 'int', 'long', 'mutable', 'namespace', 'new',
    'not', 'not_eq', 'operator', 'or', 'or_eq', 'private', 'protected',
    'public', 'register', 'reinterpret_cast', 'return', 'short', 'signed',
    'sizeof', 'static', 'static_cast',
    'struct', 'switch', 'template', 'this', 'throw', 'true',
    'try', 'typedef', 'typeid', 'typename', 'union', 'unsigned',
    'using', 'virtual', 'void', 'volatile', 'wchar_t', 'while',
    'xor', 'xor_eq',
    # C++11 additions
    'constexpr', 'decltype', 'noexcept', 'nullptr', 'static_assert',
    # reserved namespaces
    'std',
    }


operator_to_lambda = {
    # boolop
    ast.And: "(pythonic::__builtin__::bool_({0})?({1}):({0}))".format,
    ast.Or: "(pythonic::__builtin__::bool_({0})?({0}):({1}))".format,
    # operator
    ast.Add: "({0} + {1})".format,
    ast.Sub: "({0} - {1})".format,
    ast.Mult: "({0} * {1})".format,
    ast.Div: "({0} / {1})".format,
    ast.Mod: "(pythonic::operator_::mod({0}, {1}))".format,
    ast.Pow: "(pythonic::__builtin__::pow({0}, {1}))".format,
    ast.LShift: "({0} << {1})".format,
    ast.RShift: "({0} >> {1})".format,
    ast.BitOr: "({0} | {1})".format,
    ast.BitXor: "({0} ^ {1})".format,
    ast.BitAnd: "({0} & {1})".format,
    # assume from __future__ import division
    ast.FloorDiv: "(pythonic::operator_::floordiv({0}, {1}))".format,
    # unaryop
    ast.Invert: "(~{0})".format,
    ast.Not: "(not {0})".format,
    ast.UAdd: "(+{0})".format,
    ast.USub: "(-{0})".format,
    # cmpop
    ast.Eq: "({0} == {1})".format,
    ast.NotEq: "({0} != {1})".format,
    ast.Lt: "({0} < {1})".format,
    ast.LtE: "({0} <= {1})".format,
    ast.Gt: "({0} > {1})".format,
    ast.GtE: "({0} >= {1})".format,
    ast.Is: ("(pythonic::__builtin__::id({0}) == "
             "pythonic::__builtin__::id({1}))").format,
    ast.IsNot: ("(pythonic::__builtin__::id({0}) != "
                "pythonic::__builtin__::id({1}))").format,
    ast.In: "(pythonic::in({1}, {0}))".format,
    ast.NotIn: "(not pythonic::in({1}, {0}))".format,
}

update_effects = (lambda self, node:
                  [self.combine(node.args[0], node_args_k, register=True,
                                aliasing_type=True)
                   for node_args_k in node.args[1:]
                   ])

classes = {
    "list": {
        "append": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                unary_op=lambda f: cxxtypes.ListType(f),
                register=True,
                aliasing_type=True)
            ),
        "extend": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "index": ConstMethodIntr(),
        "pop": MethodIntr(),
        "reverse": MethodIntr(),
        "sort": MethodIntr(),
        "count": ConstMethodIntr(),
        "remove": MethodIntr(),
        "insert": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[2],
                unary_op=lambda f: cxxtypes.ListType(f),
                register=True,
                aliasing_type=True)
            ),
        },
    "str": {
        "capitalize": ConstMethodIntr(),
        "count": ConstMethodIntr(),
        "endswith": ConstMethodIntr(),
        "startswith": ConstMethodIntr(),
        "find": ConstMethodIntr(),
        "isalpha": ConstMethodIntr(),
        "isdigit": ConstMethodIntr(),
        "join": ConstMethodIntr(),
        "lower": ConstMethodIntr(),
        "replace": ConstMethodIntr(),
        "split": ConstMethodIntr(),
        "strip": ConstMethodIntr(),
        "lstrip": ConstMethodIntr(),
        "rstrip": ConstMethodIntr(),
        "upper": ConstMethodIntr(),
    },
    "set": {
        "add": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                unary_op=lambda f: cxxtypes.SetType(f),
                register=True,
                aliasing_type=True)
        ),
        "clear": MethodIntr(),
        "copy": ConstMethodIntr(),
        "discard": MethodIntr(),
        "remove": MethodIntr(),
        "isdisjoint": ConstMethodIntr(),
        "union_": ConstMethodIntr(),
        "update": MethodIntr(update_effects),
        "intersection": ConstMethodIntr(),
        "intersection_update": MethodIntr(
            lambda self, node:
            [
                self.combine(
                    node.args[0],
                    node_args_k,
                    register=True,
                    aliasing_type=True)
                for node_args_k in node.args[1:]
            ]
        ),
        "difference": ConstMethodIntr(),
        "difference_update": MethodIntr(
            lambda self, node:
            [
                self.combine(
                    node.args[0],
                    node_args_k,
                    register=True,
                    aliasing_type=True)
                for node_args_k in node.args[1:]
            ]
        ),
        "symmetric_difference": ConstMethodIntr(),
        "symmetric_difference_update": MethodIntr(
            lambda self, node:
            [
                self.combine(
                    node.args[0],
                    node_args_k,
                    register=True,
                    aliasing_type=True)
                for node_args_k in node.args[1:]
            ]
        ),
        "issuperset": ConstMethodIntr(),
        "issubset": ConstMethodIntr(),
    },
    "Exception": {
        "args": AttributeIntr(return_type=NamedType("pythonic::types::str")),
        "errno": AttributeIntr(return_type=NamedType("pythonic::types::str")),
        "strerror": AttributeIntr(
            return_type=NamedType("pythonic::types::str")),
        "filename": AttributeIntr(
            return_type=NamedType("pythonic::types::str")),
    },
    "float": {
        "is_integer": ConstMethodIntr(),
    },
    "complex": {
        "conjugate": ConstMethodIntr(),
        "real": AttributeIntr(return_type=NamedType("double")),
        "imag": AttributeIntr(return_type=NamedType("double")),
    },
    "dict": {
        "fromkeys": ConstFunctionIntr(),
        "clear": MethodIntr(),
        "copy": ConstMethodIntr(),
        "get": ConstMethodIntr(),
        "has_key": ConstMethodIntr(),
        "items": MethodIntr(),
        "iteritems": MethodIntr(),
        "iterkeys": MethodIntr(),
        "itervalues": MethodIntr(),
        "keys": MethodIntr(),
        "pop": MethodIntr(),
        "popitem": MethodIntr(),
        "setdefault": MethodIntr(
            lambda self, node:
            len(node.args) == 3 and
            self.combine(
                node.args[0],
                node.args[1],
                unary_op=lambda x: cxxtypes.DictType(
                    x,
                    self.result[node.args[2]]),
                register=True,
                aliasing_type=True),
            return_alias=lambda node: {
                ast.Subscript(node.args[0],
                              ast.Index(node.args[1]),
                              ast.Load())
            }
        ),
        "update": MethodIntr(update_effects),
        "values": MethodIntr(),
        "viewitems": MethodIntr(),
        "viewkeys": MethodIntr(),
        "viewvalues": MethodIntr(),
    },
    "file": {
        # Member variables
        "closed": AttributeIntr(return_type=NamedType("bool")),
        "mode": AttributeIntr(return_type=NamedType("pythonic::types::str")),
        "name": AttributeIntr(return_type=NamedType("pythonic::types::str")),
        "newlines": AttributeIntr(
            return_type=NamedType("pythonic::types::str")),
        # Member functions
        "close": MethodIntr(global_effects=True),
        "flush": MethodIntr(global_effects=True),
        "fileno": MethodIntr(),
        "isatty": MethodIntr(),
        "next": MethodIntr(global_effects=True),
        "read": MethodIntr(global_effects=True),
        "readline": MethodIntr(global_effects=True),
        "readlines": MethodIntr(global_effects=True),
        "xreadlines": MethodIntr(global_effects=True),
        "seek": MethodIntr(global_effects=True),
        "tell": MethodIntr(),
        "truncate": MethodIntr(global_effects=True),
        "write": MethodIntr(global_effects=True),
        "writelines": MethodIntr(global_effects=True),
    },
    "finfo": {
        "eps": AttributeIntr(),
    },
    "ndarray": {
        "dtype": AttributeIntr(),
        "fill": MethodIntr(),
        "flat": AttributeIntr(),
        "flatten": MethodIntr(),
        "item": MethodIntr(),
        "itemsize": AttributeIntr(return_type=NamedType("long")),
        "nbytes": AttributeIntr(return_type=NamedType("long")),
        "ndim": AttributeIntr(return_type=NamedType("long")),
        "shape": AttributeIntr(),
        "size": AttributeIntr(return_type=NamedType("long")),
        "strides": AttributeIntr(),
        "T": AttributeIntr(),
        "tolist": ConstMethodIntr(),
        "tostring": ConstMethodIntr(),
    },
}

# each module consist in a module_name <> set of symbols
MODULES = {
    "__builtin__": {
        "pythran": {
            "len_set": ConstFunctionIntr()
        },
        "abs": ConstFunctionIntr(),
        "BaseException": ConstExceptionIntr(),
        "SystemExit": ConstExceptionIntr(),
        "KeyboardInterrupt": ConstExceptionIntr(),
        "GeneratorExit": ConstExceptionIntr(),
        "Exception": ExceptionClass(classes["Exception"]),
        "StopIteration": ConstExceptionIntr(),
        "StandardError": ConstExceptionIntr(),
        "Warning": ConstExceptionIntr(),
        "BytesWarning": ConstExceptionIntr(),
        "UnicodeWarning": ConstExceptionIntr(),
        "ImportWarning": ConstExceptionIntr(),
        "FutureWarning": ConstExceptionIntr(),
        "UserWarning": ConstExceptionIntr(),
        "SyntaxWarning": ConstExceptionIntr(),
        "RuntimeWarning": ConstExceptionIntr(),
        "PendingDeprecationWarning": ConstExceptionIntr(),
        "DeprecationWarning": ConstExceptionIntr(),
        "BufferError": ConstExceptionIntr(),
        "ArithmeticError": ConstExceptionIntr(),
        "AssertionError": ConstExceptionIntr(),
        "AttributeError": ConstExceptionIntr(),
        "EnvironmentError": ConstExceptionIntr(),
        "EOFError": ConstExceptionIntr(),
        "ImportError": ConstExceptionIntr(),
        "LookupError": ConstExceptionIntr(),
        "MemoryError": ConstExceptionIntr(),
        "NameError": ConstExceptionIntr(),
        "ReferenceError": ConstExceptionIntr(),
        "RuntimeError": ConstExceptionIntr(),
        "SyntaxError": ConstExceptionIntr(),
        "SystemError": ConstExceptionIntr(),
        "TypeError": ConstExceptionIntr(),
        "ValueError": ConstExceptionIntr(),
        "FloatingPointError": ConstExceptionIntr(),
        "OverflowError": ConstExceptionIntr(),
        "ZeroDivisionError": ConstExceptionIntr(),
        "IOError": ConstExceptionIntr(),
        "OSError": ConstExceptionIntr(),
        "IndexError": ConstExceptionIntr(),
        "KeyError": ConstExceptionIntr(),
        "UnboundLocalError": ConstExceptionIntr(),
        "NotImplementedError": ConstExceptionIntr(),
        "IndentationError": ConstExceptionIntr(),
        "TabError": ConstExceptionIntr(),
        "UnicodeError": ConstExceptionIntr(),
        #  "UnicodeDecodeError": ConstExceptionIntr(),
        #  "UnicodeEncodeError": ConstExceptionIntr(),
        #  "UnicodeTranslateError": ConstExceptionIntr(),
        "all": ReadOnceFunctionIntr(),
        "any": ReadOnceFunctionIntr(),
        "bin": ConstFunctionIntr(),
        "bool_": ConstFunctionIntr(),
        "chr": ConstFunctionIntr(),
        "cmp": ConstFunctionIntr(),
        "complex": ClassWithConstConstructor(classes['complex']),
        "dict": ClassWithReadOnceConstructor(classes['dict']),
        "divmod": ConstFunctionIntr(),
        "enumerate": ReadOnceFunctionIntr(),
        "file": ClassWithConstConstructor(classes['file']),
        "filter": ReadOnceFunctionIntr(),
        "float_": ClassWithConstConstructor(classes['float']),
        "getattr": ConstFunctionIntr(),
        "hex": ConstFunctionIntr(),
        "id": ConstFunctionIntr(),
        "int_": ConstFunctionIntr(),
        "iter": FunctionIntr(),  # not const
        "len": ConstFunctionIntr(),
        "list": ClassWithReadOnceConstructor(classes['list']),
        "long_": ConstFunctionIntr(),
        "map": ReadOnceFunctionIntr(),
        "max": ReadOnceFunctionIntr(),
        "min": ReadOnceFunctionIntr(),
        "next": FunctionIntr(),  # not const
        "oct": ConstFunctionIntr(),
        "ord": ConstFunctionIntr(),
        "open": ConstFunctionIntr(),
        "pow": ConstFunctionIntr(),
        "range": ConstFunctionIntr(),
        "reduce": ReadOnceFunctionIntr(),
        "reversed": ReadOnceFunctionIntr(),
        "round": ConstFunctionIntr(),
        "set": ClassWithReadOnceConstructor(classes['set']),
        "sorted": ConstFunctionIntr(),
        "str": ClassWithConstConstructor(classes['str']),
        "sum": ReadOnceFunctionIntr(),
        "tuple": ReadOnceFunctionIntr(),
        "xrange": ConstFunctionIntr(),
        "zip": ReadOnceFunctionIntr(),
        "False": ConstantIntr(),
        "None": ConstantIntr(),
        "True": ConstantIntr(),
        },
    "numpy": {
        "abs": ConstFunctionIntr(),
        "absolute": ConstFunctionIntr(),
        "add": ConstFunctionIntr(),
        "alen": ConstFunctionIntr(),
        "all": ConstMethodIntr(),
        "allclose": ConstFunctionIntr(),
        "alltrue": ConstFunctionIntr(),
        "amax": ConstFunctionIntr(),
        "amin": ConstFunctionIntr(),
        "angle": ConstFunctionIntr(),
        "any": ConstMethodIntr(),
        "append": ConstFunctionIntr(),
        "arange": ConstFunctionIntr(),
        "arccos": ConstFunctionIntr(),
        "arccos": ConstFunctionIntr(),
        "arccosh": ConstFunctionIntr(),
        "arcsin": ConstFunctionIntr(),
        "arcsin": ConstFunctionIntr(),
        "arcsinh": ConstFunctionIntr(),
        "arctan": ConstFunctionIntr(),
        "arctan": ConstFunctionIntr(),
        "arctan2": ConstFunctionIntr(),
        "arctan2": ConstFunctionIntr(),
        "arctanh": ConstFunctionIntr(),
        "argmax": ConstFunctionIntr(),
        "argmin": ConstFunctionIntr(),
        "argsort": ConstFunctionIntr(),
        "argwhere": ConstFunctionIntr(),
        "around": ConstFunctionIntr(),
        "array": ConstFunctionIntr(),
        "array2string": ConstFunctionIntr(),
        "array_equal": ConstFunctionIntr(),
        "array_equiv": ConstFunctionIntr(),
        "array_split": ConstFunctionIntr(),
        "array_str": ConstFunctionIntr(),
        "asarray": ConstFunctionIntr(),
        "asarray_chkfinite": ConstFunctionIntr(),
        "ascontiguousarray": ConstFunctionIntr(),
        "asscalar": ConstFunctionIntr(),
        "atleast_1d": ConstFunctionIntr(),
        "atleast_2d": ConstFunctionIntr(),
        "atleast_3d": ConstFunctionIntr(),
        "average": ConstFunctionIntr(),
        "base_repr": ConstFunctionIntr(),
        "binary_repr": ConstFunctionIntr(),
        "bincount": ConstFunctionIntr(),
        "bitwise_and": ConstFunctionIntr(),
        "bitwise_not": ConstFunctionIntr(),
        "bitwise_or": ConstFunctionIntr(),
        "bitwise_xor": ConstFunctionIntr(),
        "ceil": ConstFunctionIntr(),
        "clip": ConstFunctionIntr(),
        "concatenate": ConstFunctionIntr(),
        "complex": ConstFunctionIntr(),
        "complex64": ConstFunctionIntr(),
        "conj": ConstMethodIntr(),
        "conjugate": ConstMethodIntr(),
        "copy": ConstMethodIntr(),
        "copyto": FunctionIntr(argument_effects=[UpdateEffect(), ReadEffect(),
                                                 ReadEffect(), ReadEffect()]),
        "copysign": ConstFunctionIntr(),
        "count_nonzero": ConstFunctionIntr(),
        "cos": ConstFunctionIntr(),
        "cosh": ConstFunctionIntr(),
        "cumprod": ConstMethodIntr(),
        "cumproduct": ConstMethodIntr(),
        "cumsum": ConstMethodIntr(),
        "deg2rad": ConstFunctionIntr(),
        "degrees": ConstFunctionIntr(),
        "delete_": ConstFunctionIntr(),
        "diag": ConstFunctionIntr(),
        "diagflat": ConstFunctionIntr(),
        "diagonal": ConstFunctionIntr(),
        "diff": ConstFunctionIntr(),
        "digitize": ConstFunctionIntr(),
        "divide": ConstFunctionIntr(),
        "dot": ConstFunctionIntr(),
        "double_": ConstFunctionIntr(),
        "e": ConstantIntr(),
        "ediff1d": ConstFunctionIntr(),
        "empty": ConstFunctionIntr(args=('shape', 'dtype'),
                                   defaults=("numpy.float64",)),
        "empty_like": ConstFunctionIntr(),
        "equal": ConstFunctionIntr(),
        "exp": ConstFunctionIntr(),
        "expm1": ConstFunctionIntr(),
        "eye": ConstFunctionIntr(),
        "fabs": ConstFunctionIntr(),
        "finfo": ClassWithConstConstructor(classes['finfo']),
        "fix": ConstFunctionIntr(),
        "flatnonzero": ConstFunctionIntr(),
        "fliplr": ConstFunctionIntr(),
        "flipud": ConstFunctionIntr(),
        "float32": ConstFunctionIntr(),
        "float64": ConstFunctionIntr(),
        "float_": ConstFunctionIntr(),
        "floor": ConstFunctionIntr(),
        "floor_divide": ConstFunctionIntr(),
        "fmax": ConstFunctionIntr(),
        "fmin": ConstFunctionIntr(),
        "fmod": ConstFunctionIntr(),
        "frexp": ConstFunctionIntr(),
        "fromfunction": ConstFunctionIntr(),
        "fromiter": ConstFunctionIntr(),
        "fromstring": ConstFunctionIntr(),
        "greater": ConstFunctionIntr(),
        "greater_equal": ConstFunctionIntr(),
        "hypot": ConstFunctionIntr(),
        "identity": ConstFunctionIntr(),
        "imag": FunctionIntr(),
        "indices": ConstFunctionIntr(),
        "inf": ConstantIntr(),
        "inner": ConstFunctionIntr(),
        "insert": ConstFunctionIntr(),
        "intersect1d": ConstFunctionIntr(),
        "int16": ConstFunctionIntr(),
        "int32": ConstFunctionIntr(),
        "int64": ConstFunctionIntr(),
        "int8": ConstFunctionIntr(),
        "invert": ConstFunctionIntr(),
        "isclose": ConstFunctionIntr(),
        "iscomplex": ConstFunctionIntr(),
        "isfinite": ConstFunctionIntr(),
        "isinf": ConstFunctionIntr(),
        "isnan": ConstFunctionIntr(),
        "isneginf": ConstFunctionIntr(),
        "isposinf": ConstFunctionIntr(),
        "isreal": ConstFunctionIntr(),
        "isrealobj": ConstFunctionIntr(),
        "isscalar": ConstFunctionIntr(),
        "issctype": ConstFunctionIntr(),
        "ldexp": ConstFunctionIntr(),
        "left_shift": ConstFunctionIntr(),
        "less": ConstFunctionIntr(),
        "less_equal": ConstFunctionIntr(),
        "lexsort": ConstFunctionIntr(),
        "linspace": ConstFunctionIntr(),
        "log": ConstFunctionIntr(),
        "log10": ConstFunctionIntr(),
        "log1p": ConstFunctionIntr(),
        "log2": ConstFunctionIntr(),
        "logaddexp": ConstFunctionIntr(),
        "logaddexp2": ConstFunctionIntr(),
        "logspace": ConstFunctionIntr(),
        "logical_and": ConstFunctionIntr(),
        "logical_not": ConstFunctionIntr(),
        "logical_or": ConstFunctionIntr(),
        "logical_xor": ConstFunctionIntr(),
        "max": ConstMethodIntr(),
        "maximum": ConstFunctionIntr(),
        "mean": ConstMethodIntr(),
        "median": ConstFunctionIntr(),
        "min": ConstMethodIntr(),
        "minimum": ConstFunctionIntr(),
        "mod": ConstFunctionIntr(),
        "multiply": ConstFunctionIntr(),
        "nan": ConstantIntr(),
        "nan_to_num": ConstFunctionIntr(),
        "nanargmax": ConstFunctionIntr(),
        "nanargmin": ConstFunctionIntr(),
        "nanmax": ConstFunctionIntr(),
        "nanmin": ConstFunctionIntr(),
        "nansum": ConstFunctionIntr(),
        "ndenumerate": ConstFunctionIntr(),
        "ndarray": ClassWithConstConstructor(classes["ndarray"]),
        "ndindex": ConstFunctionIntr(),
        "ndim": ConstFunctionIntr(),
        "negative": ConstFunctionIntr(),
        "nextafter": ConstFunctionIntr(),
        "NINF": ConstantIntr(),
        "nonzero": ConstFunctionIntr(),
        "not_equal": ConstFunctionIntr(),
        "ones": ConstFunctionIntr(),
        "ones_like": ConstFunctionIntr(),
        "outer": ConstFunctionIntr(),
        "pi": ConstantIntr(),
        "place": FunctionIntr(),
        "power": ConstFunctionIntr(),
        "prod": ConstMethodIntr(),
        "product": ConstFunctionIntr(),
        "ptp": ConstFunctionIntr(),
        "put": FunctionIntr(),
        "putmask": FunctionIntr(),
        "rad2deg": ConstFunctionIntr(),
        "radians": ConstFunctionIntr(),
        "rank": ConstFunctionIntr(),
        "ravel": ConstFunctionIntr(),
        "real": FunctionIntr(),
        "reciprocal": ConstFunctionIntr(),
        "remainder": ConstFunctionIntr(),
        "repeat": ConstFunctionIntr(),
        "reshape": ConstMethodIntr(),
        "resize": ConstMethodIntr(),
        "right_shift": ConstFunctionIntr(),
        "rint": ConstFunctionIntr(),
        "roll": ConstFunctionIntr(),
        "rollaxis": ConstFunctionIntr(),
        "rot90": ConstFunctionIntr(),
        "round": ConstFunctionIntr(),
        "round_": ConstFunctionIntr(),
        "searchsorted": ConstFunctionIntr(),
        "select": ConstFunctionIntr(),
        "shape": ConstFunctionIntr(),
        "sign": ConstFunctionIntr(),
        "signbit": ConstFunctionIntr(),
        "sin": ConstFunctionIntr(),
        "sinh": ConstFunctionIntr(),
        "size": ConstFunctionIntr(),
        "sometrue": ConstFunctionIntr(),
        "sort": ConstFunctionIntr(),
        "sort_complex": ConstFunctionIntr(),
        "spacing": ConstFunctionIntr(),
        "split": ConstFunctionIntr(),
        "sqrt": ConstFunctionIntr(),
        "square": ConstFunctionIntr(),
        "subtract": ConstFunctionIntr(),
        "sum": ConstMethodIntr(),
        "swapaxes": ConstMethodIntr(),
        "take": ConstFunctionIntr(),
        "tan": ConstFunctionIntr(),
        "tanh": ConstFunctionIntr(),
        "tile": ConstFunctionIntr(),
        "trace": ConstFunctionIntr(),
        "transpose": ConstMethodIntr(),
        "tri": ConstMethodIntr(),
        "tril": ConstMethodIntr(),
        "trim_zeros": ConstMethodIntr(),
        "triu": ConstMethodIntr(),
        "true_divide": ConstFunctionIntr(),
        "trunc": ConstFunctionIntr(),
        "uint16": ConstFunctionIntr(),
        "uint32": ConstFunctionIntr(),
        "uint64": ConstFunctionIntr(),
        "uint8": ConstFunctionIntr(),
        "union1d": ConstFunctionIntr(),
        "unique": ConstFunctionIntr(),
        "unwrap": ConstFunctionIntr(),
        "var": ConstMethodIntr(),
        "where": ConstFunctionIntr(),
        "zeros": ConstFunctionIntr(args=('shape', 'dtype'),
                                   defaults=("numpy.float64",)),
        "zeros_like": ConstFunctionIntr(),
        },
    "time": {
        "sleep": FunctionIntr(global_effects=True),
        "time": FunctionIntr(global_effects=True),
        },
    "math": {
        "isinf": ConstFunctionIntr(),
        "modf": ConstFunctionIntr(),
        "frexp": ConstFunctionIntr(),
        "factorial": ConstFunctionIntr(),
        "gamma": ConstFunctionIntr(),
        "lgamma": ConstFunctionIntr(),
        "trunc": ConstFunctionIntr(),
        "erf": ConstFunctionIntr(),
        "erfc": ConstFunctionIntr(),
        "asinh": ConstFunctionIntr(),
        "atanh": ConstFunctionIntr(),
        "acosh": ConstFunctionIntr(),
        "radians": ConstFunctionIntr(),
        "degrees": ConstFunctionIntr(),
        "hypot": ConstFunctionIntr(),
        "tanh": ConstFunctionIntr(),
        "cosh": ConstFunctionIntr(),
        "sinh": ConstFunctionIntr(),
        "atan": ConstFunctionIntr(),
        "atan2": ConstFunctionIntr(),
        "asin": ConstFunctionIntr(),
        "tan": ConstFunctionIntr(),
        "log": ConstFunctionIntr(),
        "log1p": ConstFunctionIntr(),
        "expm1": ConstFunctionIntr(),
        "ldexp": ConstFunctionIntr(),
        "fmod": ConstFunctionIntr(),
        "fabs": ConstFunctionIntr(),
        "copysign": ConstFunctionIntr(),
        "acos": ConstFunctionIntr(),
        "cos": ConstFunctionIntr(),
        "sin": ConstFunctionIntr(),
        "exp": ConstFunctionIntr(),
        "sqrt": ConstFunctionIntr(),
        "log10": ConstFunctionIntr(),
        "isnan": ConstFunctionIntr(),
        "ceil": ConstFunctionIntr(),
        "floor": ConstFunctionIntr(),
        "pow": ConstFunctionIntr(),
        "pi": ConstantIntr(),
        "e": ConstantIntr(),
        },
    "functools": {
        "partial": FunctionIntr(),
        },
    "bisect": {
        "bisect_left": ConstFunctionIntr(),
        "bisect_right": ConstFunctionIntr(),
        "bisect": ConstFunctionIntr(),
        },
    "cmath": {
        "cos": FunctionIntr(),
        "sin": FunctionIntr(),
        "exp": FunctionIntr(),
        "sqrt": FunctionIntr(),
        "log10": FunctionIntr(),
        "isnan": FunctionIntr(),
        "pi": ConstantIntr(),
        "e": ConstantIntr(),
        },
    "itertools": {
        "count": ReadOnceFunctionIntr(),
        "imap": ReadOnceFunctionIntr(),
        "ifilter": ReadOnceFunctionIntr(),
        "islice": ReadOnceFunctionIntr(),
        "product": ConstFunctionIntr(),
        "izip": ReadOnceFunctionIntr(),
        "combinations": ConstFunctionIntr(),
        "permutations": ConstFunctionIntr(),
        },
    "random": {
        "seed": FunctionIntr(global_effects=True),
        "random": FunctionIntr(global_effects=True),
        "randint": FunctionIntr(global_effects=True),
        "randrange": FunctionIntr(global_effects=True),
        "gauss": FunctionIntr(global_effects=True),
        "uniform": FunctionIntr(global_effects=True),
        "expovariate": FunctionIntr(global_effects=True),
        "sample": FunctionIntr(global_effects=True),
        "choice": FunctionIntr(global_effects=True),
        },
    "omp": {
        "set_num_threads": FunctionIntr(global_effects=True),
        "get_num_threads": FunctionIntr(global_effects=True),
        "get_max_threads": FunctionIntr(global_effects=True),
        "get_thread_num": FunctionIntr(global_effects=True),
        "get_num_procs": FunctionIntr(global_effects=True),
        "in_parallel": FunctionIntr(global_effects=True),
        "set_dynamic": FunctionIntr(global_effects=True),
        "get_dynamic": FunctionIntr(global_effects=True),
        "set_nested": FunctionIntr(global_effects=True),
        "get_nested": FunctionIntr(global_effects=True),
        "init_lock": FunctionIntr(global_effects=True),
        "destroy_lock": FunctionIntr(global_effects=True),
        "set_lock": FunctionIntr(global_effects=True),
        "unset_lock": FunctionIntr(global_effects=True),
        "test_lock": FunctionIntr(global_effects=True),
        "init_nest_lock": FunctionIntr(global_effects=True),
        "destroy_nest_lock": FunctionIntr(global_effects=True),
        "set_nest_lock": FunctionIntr(global_effects=True),
        "unset_nest_lock": FunctionIntr(global_effects=True),
        "test_nest_lock": FunctionIntr(global_effects=True),
        "get_wtime": FunctionIntr(global_effects=True),
        "get_wtick": FunctionIntr(global_effects=True),
        "set_schedule": FunctionIntr(global_effects=True),
        "get_schedule": FunctionIntr(global_effects=True),
        "get_thread_limit": FunctionIntr(global_effects=True),
        "set_max_active_levels": FunctionIntr(global_effects=True),
        "get_max_active_levels": FunctionIntr(global_effects=True),
        "get_level": FunctionIntr(global_effects=True),
        "get_ancestor_thread_num": FunctionIntr(global_effects=True),
        "get_team_size": FunctionIntr(global_effects=True),
        "get_active_level": FunctionIntr(global_effects=True),
        "in_final": FunctionIntr(global_effects=True),
        },
    "operator_": {
        "lt": ConstFunctionIntr(),
        "le": ConstFunctionIntr(),
        "eq": ConstFunctionIntr(),
        "ne": ConstFunctionIntr(),
        "ge": ConstFunctionIntr(),
        "gt": ConstFunctionIntr(),
        "__lt__": ConstFunctionIntr(),
        "__le__": ConstFunctionIntr(),
        "__eq__": ConstFunctionIntr(),
        "__ne__": ConstFunctionIntr(),
        "__ge__": ConstFunctionIntr(),
        "__gt__": ConstFunctionIntr(),
        "not_": ConstFunctionIntr(),
        "__not__": ConstFunctionIntr(),
        "truth": ConstFunctionIntr(),
        "is_": ConstFunctionIntr(),
        "is_not": ConstFunctionIntr(),
        "__abs__": ConstFunctionIntr(),
        "add": ConstFunctionIntr(),
        "__add__": ConstFunctionIntr(),
        "and_": ConstFunctionIntr(),
        "__and__": ConstFunctionIntr(),
        "div": ConstFunctionIntr(),
        "__div__": ConstFunctionIntr(),
        "floordiv": ConstFunctionIntr(),
        "__floordiv__": ConstFunctionIntr(),
        "inv": ConstFunctionIntr(),
        "invert": ConstFunctionIntr(),
        "__inv__": ConstFunctionIntr(),
        "__invert__": ConstFunctionIntr(),
        "lshift": ConstFunctionIntr(),
        "__lshift__": ConstFunctionIntr(),
        "mod": ConstFunctionIntr(),
        "__mod__": ConstFunctionIntr(),
        "mul": ConstFunctionIntr(),
        "__mul__": ConstFunctionIntr(),
        "neg": ConstFunctionIntr(),
        "__neg__": ConstFunctionIntr(),
        "or_": ConstFunctionIntr(),
        "__or__": ConstFunctionIntr(),
        "pos": ConstFunctionIntr(),
        "__pos__": ConstFunctionIntr(),
        "rshift": ConstFunctionIntr(),
        "__rshift__": ConstFunctionIntr(),
        "sub": ConstFunctionIntr(),
        "__sub__": ConstFunctionIntr(),
        "truediv": ConstFunctionIntr(),
        "__truediv__": ConstFunctionIntr(),
        "__xor__": ConstFunctionIntr(),
        "concat": ConstFunctionIntr(),
        "__concat__": ConstFunctionIntr(),
        "iadd": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__iadd__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "iand": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__iand__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "iconcat": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__iconcat__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "idiv": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__idiv__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "ifloordiv": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__ifloordiv__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "ilshift": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__ilshift__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "imod": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__imod__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "imul": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__imul__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "ior": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__ior__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "ipow": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__ipow__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "irshift": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__irshift__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "isub": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__isub__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "itruediv": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__itruediv__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "ixor": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__ixor__": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "contains": MethodIntr(
            lambda self, node:
            self.combine(
                node.args[0],
                node.args[1],
                register=True,
                aliasing_type=True)
            ),
        "__contains__": ConstFunctionIntr(),
        "countOf": ConstFunctionIntr(),
        "delitem": FunctionIntr(
            argument_effects=[UpdateEffect(), ReadEffect()]),
        "__delitem__": FunctionIntr(
            argument_effects=[UpdateEffect(), ReadEffect()]),
        "getitem": ConstFunctionIntr(),
        "__getitem__": ConstFunctionIntr(),
        "indexOf": ConstFunctionIntr(),
        "__theitemgetter__": ConstFunctionIntr(),
        "itemgetter": MethodIntr(
            return_alias=lambda node: {
                MODULES['operator_']['__theitemgetter__']}
            ),

    },
    "string": {
        "ascii_lowercase": ConstantIntr(),
        "ascii_uppercase": ConstantIntr(),
        "ascii_letters": ConstantIntr(),
        "digits": ConstantIntr(),
        "find": ConstFunctionIntr(),
        "hexdigits": ConstantIntr(),
        "octdigits": ConstantIntr(),
        },
    "os": {
        "path": {
            "join": ConstFunctionIntr(),
            }
        },
    # conflicting method names must be listed here
    "__dispatch__": {
        "clear": MethodIntr(),
        "conjugate": ConstMethodIntr(),
        "copy": ConstMethodIntr(),
        "count": ConstMethodIntr(),
        "next": MethodIntr(global_effects=True),  # because of file.next
        "pop": MethodIntr(),
        "remove": MethodIntr(),
        "update": MethodIntr(update_effects),
        },
    }

# VMSError is only available on VMS
if 'VMSError' in sys.modules['__builtin__'].__dict__:
    MODULES['__builtin__']['VMSError'] = ConstExceptionIntr()

# WindowsError is only available on Windows
if 'WindowsError' in sys.modules['__builtin__'].__dict__:
    MODULES['__builtin__']['WindowsError'] = ConstExceptionIntr()

# detect and prune unsupported modules
try:
    __import__("omp")
except EnvironmentError:
    logger.warn("Pythran support disabled for module: omp")
    del MODULES["omp"]

# a method name to module binding
# {method_name : ((full module path), signature)}
methods = {}


def save_method(elements, module_path):
    """ Recursively save methods with module name and signature. """
    for elem, signature in elements.iteritems():
        if isinstance(signature, dict):  # Submodule case
            save_method(signature, module_path + (elem,))
        elif isinstance(signature, Class):
            save_method(signature.fields, module_path + (elem,))
        elif signature.ismethod():
            # in case of duplicates, there must be a __dispatch__ record
            # and it is the only recorded one
            if elem in methods and module_path[0] != '__dispatch__':
                assert elem in MODULES['__dispatch__']
                path = ('__dispatch__',)
                methods[elem] = (path, MODULES['__dispatch__'][elem])
            else:
                methods[elem] = (module_path, signature)

for module, elems in MODULES.iteritems():
    save_method(elems, (module,))

# a function name to module binding
# {function_name : [((full module path), signature)]}
functions = {}


def save_function(elements, module_path):
    """ Recursively save functions with module name and signature. """
    for elem, signature in elements.iteritems():
        if isinstance(signature, dict):  # Submodule case
            save_function(signature, module_path + (elem,))
        elif signature.isstaticfunction():
            functions.setdefault(elem, []).append((module_path, signature,))
        elif isinstance(signature, Class):
            save_function(signature.fields, module_path + (elem,))

for module, elems in MODULES.iteritems():
    save_function(elems, (module,))

# a attribute name to module binding
# {attribute_name : ((full module path), signature)}
attributes = {}


def save_attribute(elements, module_path):
    """ Recursively save attributes with module name and signature. """
    for elem, signature in elements.iteritems():
        if isinstance(signature, dict):  # Submodule case
            save_attribute(signature, module_path + (elem,))
        elif signature.isattribute():
            assert elem not in attributes  # we need unicity
            attributes[elem] = (module_path, signature,)
        elif isinstance(signature, Class):
            save_attribute(signature.fields, module_path + (elem,))

for module, elems in MODULES.iteritems():
    save_attribute(elems, (module,))


# populate argument description through introspection
def save_arguments(module_name, elements):
    """ Recursively save arguments name and default value. """
    for elem, signature in elements.iteritems():
        if isinstance(signature, dict):  # Submodule case
            save_arguments(".".join((module_name, elem)), signature)
        else:
            # use introspection to get the Python obj
            try:
                themodule = __import__(module_name)
                obj = getattr(themodule, elem)
                spec = inspect.getargspec(obj)
                assert not signature.args.args
                signature.args.args = [ast.Name(arg, ast.Param())
                                       for arg in spec.args]
                if spec.defaults:
                    signature.args.defaults = map(to_ast, spec.defaults)
            except (AttributeError, ImportError, TypeError, ToNotEval):
                pass

for module, elems in MODULES.iteritems():
    save_arguments(module, elems)


# Fill return_type field for constants
def fill_constants_types(module_name, elements):
    """ Recursively save arguments name and default value. """
    for elem, intrinsic in elements.iteritems():
        if isinstance(intrinsic, dict):  # Submodule case
            fill_constants_types(module_name + (elem,), intrinsic)
        elif isinstance(intrinsic, ConstantIntr):
            # use introspection to get the Python constants types
            cst = getattr(__import__(".".join(module_name)), elem)
            intrinsic.return_type = NamedType(PYTYPE_TO_CTYPE_TABLE[type(cst)])

for module, elems in MODULES.iteritems():
    fill_constants_types((module,), elems)
