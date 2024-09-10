#!/usr/bin/env python3

import codecs
import os
import re
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    fname = os.path.join(os.path.join(here, *parts))
    with codecs.open(fname, 'r', encoding='utf-8') as fp:
        return fp.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


test_deps = ['pytest']
install_deps = [
    'PyQt5>=5.15',
    'pyqtgraph',
    'sllurp>=2.0',
]

long_description = """
=========================================================================
sllurp-gui is a QT based graphical interface to control LLRP RFID readers
=========================================================================

sllurp-gui is a GUI frontend for the `sllurp` client.
sllurp is a high performance client and library for the Low Level Reader Protocol (LLRP) to control RFID readers.

A recent version of sllurp (>= 2.0) is required to be able to run this GUI.

The GUI relies on PyQt5, pyqtgraph and using Python 3.6 or higher is recommended.
It has not been tested on any other OS than Linux.

Please report any bug by filing an issue on the [sllurp-gui project Github](https://github.com/sllurp/sllurp-gui/)

sllurp is distributed under version 3 of the GNU General Public License.  See
``LICENSE.txt`` for details.


**Run GUI**
```
sllurp-gui
```

# Authors

    - Florent Viard (florent@sodria.com)
    - Papapel
    - Thijmen Ketel

Project website:
    https://github.com/sllurp/sllurp-gui
"""

setup(
    name='sllurp-gui',
    version=find_version('sllurp_gui', 'version.py'),
    description='RFID LLRP reader control graphical interface using sllurp',
    long_description=long_description,
    author='Florent Viard',
    author_email='florent@sodria.com',
    maintainer="github.com/fviard, https://github.com/papapel, github.com/thijmenketel",
    url='https://github.com/sllurp/sllurp-gui',
    license='GPLv3',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: X11 Applications :: Qt',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
    keywords='llrp rfid reader gui',
    packages=find_packages(),
    install_requires=install_deps,
    tests_require=test_deps,
    extras_require={'test': test_deps},
    setup_requires=['pytest-runner'],
    entry_points={
        'gui_scripts': [
            'sllurp-gui = sllurp_gui.main:main',
        ],
    },
)
