#!/bin/bash

# create the venv
python3 -m venv pyvenv

# activate it
source pyvenv/bin/activate

# upgrade pip inside the venv and add support for the wheel package format
python3 -m pip install -U pip wheel

# wikitools
pip install git+https://github.com/DatGuy1/wikitools.git

# packages for afreporter
pip install cachetools irc pymysql num2words

# packages for wikiwork
pip install mwparserfromhell
