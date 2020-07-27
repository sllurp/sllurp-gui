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
    'PyQt5>=5.14',
    'pyqtgraph'
]


setup(
    name='sllurp_gui',
    version=find_version('sllurpgui', 'version.py'),
    description='RFID LLRP reader control graphical interface using sllurp',
    long_description=read('README.rst'),
    author='Florent Viard',
    author_email='florent@sodria.com',
    maintainer="github.com/fviard, https://github.com/papapel, github.com/thijmenketel",
    url='https://github.com/fviard/sllurp-gui',
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
    ],
    keywords='llrp rfid reader gui',
    packages=find_packages(),
    install_requires=install_deps,
    tests_require=test_deps,
    extras_require={'test': test_deps},
    setup_requires=['pytest-runner'],
    entry_points={
        'gui_scripts': [
            'sllurpgui=sllurpgui.main:main',
        ],
    },
)
