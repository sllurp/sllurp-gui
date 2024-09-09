=========================================================================
sllurp-gui is a QT based graphical interface to control LLRP RFID readers
=========================================================================

Project website:
    https://github.com/sllurp/sllurp-gui

sllurp-gui is a GUI frontend to the sllurp Python library.
sllurp is an implementation of a client for the Low Level Reader Protocol (LLRP).

A recent version of sllurp (>= 2.0) is required to be able to run this GUI.

The GUI relies on PyQt5, pyqtgraph and using Python 3.6 or higher is
recommended. It has not been tested on any other OS than Linux.

Important note:
This project is still in a `Beta` state, and a few bugs and unfinished
features are to be expected.

Please report any bug by filing an issue on the [sllurp-gui project Github](https://github.com/sllurp/sllurp-gui/)

sllurp is distributed under version 3 of the GNU General Public License.  See
``LICENSE.txt`` for details.

![SllurpGUI Screenshot](/docs/sllurpgui_screenshot.png?raw=true "SllurpGUI Screenshot")


# Features

Available features:
- inventory

Tag memory read/write are not available.


# Getting started

**Install requirements**
```
pip install pyqtgraph pyqt5
```

**Install sllurp-gui**
```
python3 setup.py install
```

**Run GUI**
```
sllurp-gui
```


# DEPRECTAED: Generate single-file exe

TO BE UPDATED

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


# Authors

    - Florent Viard (florent@sodria.com)
    - Papapel
    - Thijmen Ketel
