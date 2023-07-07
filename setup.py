import os
import pathlib
import subprocess
import sys
from typing import List, Tuple

import numpy as np
from Cython.Build import cythonize
from setuptools import find_packages, setup
from setuptools.command.build_ext import build_ext
from setuptools.extension import Extension

is_posix = (os.name == "posix")

if is_posix:
    os_name = subprocess.check_output("uname").decode("utf8")
    if "Darwin" in os_name:
        os.environ["CFLAGS"] = "-stdlib=libc++ -std=c++11"
    else:
        os.environ["CFLAGS"] = "-std=c++11"

if os.environ.get('WITHOUT_CYTHON_OPTIMIZATIONS'):
    if "CFLAGS" in os.environ:
        os.environ["CFLAGS"] = os.environ.get("CFLAGS") + " -O0"
    else:
        os.environ["CFLAGS"] = "-O0"

IS_PY_DEBUG = os.getenv('EXT_BUILD_PY_DEBUG', False)

coverage_macros = []
coverage_compiler_directives = dict()
coverage_include_path = []

if IS_PY_DEBUG:
    print('Extension IS_CYTHON_COVERAGE=True!')
    # Adding cython line trace for coverage report
    coverage_macros += ("CYTHON_TRACE_NOGIL", 1), ("CYTHON_TRACE", 1)
    # Adding upper directory for supporting code coverage when running tests inside the cython package
    coverage_include_path += ['..']
    # Some extra info for cython compiler
    coverage_compiler_directives = dict(linetrace=True, profile=True, binding=True)


# Avoid a gcc warning below:
# cc1plus: warning: command line option ???-Wstrict-prototypes??? is valid
# for C/ObjC but not for C++
class BuildExt(build_ext):
    def build_extensions(self):
        if os.name != "nt" and '-Wstrict-prototypes' in self.compiler.compiler_so:
            self.compiler.compiler_so.remove('-Wstrict-prototypes')
        super().build_extensions()


include_dirs: List[str] = ["hummingbot/core",
                           "hummingbot/core/data_type",
                           "hummingbot/core/cpp"]
numpy_warning: Tuple[str, str] = ("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")


def get_extension(name: str, sources: List[str]) -> Extension:
    return Extension(name,
                     sources=sources,
                     include_dirs=include_dirs,
                     define_macros=[numpy_warning] + coverage_macros,
                     language="c++")


def py_inline_cython_callback(file: str, parent: str, obj: str) -> Extension:
    with open(file, "r", encoding="utf8") as f:
        for i, line in enumerate(f):
            if " cython " in line:
                return get_extension(parent + "." + obj, [file])


def pxd_py_callback(file: str, parent: str, obj: str) -> Extension:
    py_file: str = os.path.splitext(file)[0] + ".py"
    if os.path.isfile(py_file):
        return get_extension(parent + "." + obj, [py_file])


def find_files_with_pattern(pattern: str, callback) -> List[Extension]:
    extensions: List[Extension] = []
    files = pathlib.Path().glob(pattern=pattern)
    for file in files:
        parent = str(file.parent).replace("/", ".")
        obj = file.stem
        extension: Extension = callback(str(file), parent, obj)
        if extension is not None:
            extensions.append(extension)
    return extensions


def find_py_with_cython_inline() -> List[Extension]:
    return find_files_with_pattern("hummingbot/**/*.py", py_inline_cython_callback)


def find_py_with_pxd() -> List[Extension]:
    return find_files_with_pattern("hummingbot/**/*.pxd", pxd_py_callback)


def main():
    cpu_count = os.cpu_count() or 8
    version = "20230626"
    packages = find_packages(include=["hummingbot", "hummingbot.*"])
    package_data = {
        "hummingbot": [
            "core/cpp/*",
            "VERSION",
            "templates/*TEMPLATE.yml"
        ],
    }

    cython_kwargs = {
        "language_level": '3',
        "gdb_debug": False,
        "force": False,
        "annotate": False,
    }

    if os.environ.get('WITHOUT_CYTHON_OPTIMIZATIONS'):
        compiler_directives = {
            "optimize.use_switch": False,
            "optimize.unpack_method_calls": False,
        }
    else:
        compiler_directives = {}

    if is_posix:
        cython_kwargs["nthreads"] = cpu_count

    if "DEV_MODE" in os.environ:
        version += ".dev1"
        package_data[""] = [
            "*.pxd", "*.pyx", "*.h"
        ]
        package_data["hummingbot"].append("core/cpp/*.cpp")

    if len(sys.argv) > 1 and sys.argv[1] == "build_ext" and is_posix:
        sys.argv.append(f"--parallel={cpu_count}")

    cythonized_py = []
    if not IS_PY_DEBUG:
        python_sources = find_py_with_pxd() + find_py_with_cython_inline()
        if python_sources is not None:
            cythonized_py = cythonize(python_sources, compiler_directives=coverage_compiler_directives, **cython_kwargs)

    cythonized_pyx = cythonize(Extension("*",
                                         sources=["hummingbot/**/*.pyx"],
                                         define_macros=[numpy_warning],
                                         language="c++"),
                               compiler_directives=compiler_directives, **cython_kwargs)

    setup(name="hummingbot",
          version=version,
          description="Hummingbot",
          url="https://github.com/hummingbot/hummingbot",
          author="CoinAlpha, Inc.",
          author_email="dev@hummingbot.io",
          license="Apache 2.0",
          packages=packages,
          package_data=package_data,
          zip_safe=False,
          ext_modules=[*cythonized_py, *cythonized_pyx],
          include_dirs=[
              np.get_include()
          ],
          scripts=[
              "bin/hummingbot.py",
              "bin/hummingbot_quickstart.py"
          ],
          cmdclass={'build_ext': BuildExt},
          )


if __name__ == "__main__":
    main()
