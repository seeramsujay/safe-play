from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "routing",
        sources=["src/routing.pyx"],
        extra_compile_args=["-O3"],
    )
]

setup(
    name="safe-play-routing",
    ext_modules=cythonize(extensions, compiler_directives={"language_level": "3"}),
)
