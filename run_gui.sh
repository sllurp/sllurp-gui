#!/bin/bash

python3 -m venv .venv &&
source .venv/bin/activate &&
pip3 install . &&
python3 gui/sllurp_gui.py
deactivate &&
rm -rf .venv
