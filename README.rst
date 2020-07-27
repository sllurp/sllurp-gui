!! WARNING - WORK IN PROGRESS - BUGS AND UNFINISHED FEATURES TO BE EXPECTED !!

Sllurpgui is a QT Graphical Interface to control LLRP RFID readers.

Authors:
    - Florent Viard (florent@sodria.com)
    - Papapel
    - Thijmen Ketel

Website:
    https://github.com/fviard/sllurp-gui

License:
    GPL Version 3

Sllurpgui is a GUI frontend to the sllurp Python library.
Sllurp is an implementation of a client for the Low Level Reader Protocol.

An experimental v2 version of Sllurp is required for this GUI
(see: github.com/fviard/sllurp/tree/fviard-develop-v2)

The GUI relies on PyQt5, pyqtgraph and using Python 3.6 or higher is
recommended. It has not been tested on any other OS than Linux.

Important warning:
This project is in a Work In Progress state, and a few bugs and unfinished
features are to be expected.



--- Original readme from qtgui ---

# Introduction

An example which implements sllurp through a graphical unit interface.

Available feature:
- inventory

Tag memory read/write are not available.


# Getting started

**Install requirements**
```
pip install pyqtgraph pyqt5
```

**Run GUI**
```
python3 main.py
```

# Generate single-file exe

**Install requirements**
```
pip install pyinstaller
```

Install sllurp because the `import initExample` in main.py does not work with pyinstaller
```
cd ../../.. # move to the root of sllurp repository
pip install .
```

**Linux**
``` bash
PyInstaller --noconfirm --log-level=INFO \
--onefile \
--windowed \
--hidden-import='pkg_resources.py2_warn' \
main.py

```

**Windows**

``` bash
PyInstaller --noconfirm --log-level=INFO ^
    --onefile ^
    --paths="C:\Users\root\AppData\Roaming\Python\Python37\site-packages\PyQt5\Qt\bin" ^
    --hidden-import="pkg_resources.py2_warn" ^
    main.py
```
Note: update the `--paths` option to set the Qt path according to your setup.
