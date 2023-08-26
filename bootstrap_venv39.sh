#!/bin/bash

# create the venv
python3 -m venv py39

# activate it
source py39/bin/activate

python3 -m pip install -U pip wheel

# packages for imageresizer
pip install defusedxml Pillow pyexiv2==2.5.0
# anything above 2.5.0 requires GLIBC 2.29, ldd --version returns GLIBC 2.28. if GLIBC is bumped, switch to modify_raw_xmp() and Python 3.11

# mwclient for imageresizer
pip install git+https://github.com/mwclient/mwclient.git
