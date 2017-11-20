# This code is licensed under the MIT License (see LICENSE file for details)

import cffi
import re

import pathlib
hist_src = pathlib.Path(__file__).parent / '_histogram_src.c'

with hist_src.open() as f:
    hist_source = f.read()
hist_def = re.compile(r'^void.+?\)', flags=re.MULTILINE|re.DOTALL)
hist_headers = '\n'.join(h + ';' for h in hist_def.findall(hist_source))

ffibuilder = cffi.FFI()

ffibuilder.set_source("_histogram", hist_source)
ffibuilder.cdef(hist_headers)

if __name__ == "__main__":
    ffibuilder.compile()