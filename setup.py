from setuptools import setup

setup(
    name='heospy',
    version='0.1.1',
    author='Stephan Heuel',
    author_email='mail@ping13.net',
    packages=['heospy'],
    entry_points = {
        'console_scripts': ['heos_player=heospy.heos_player:main'],
    },
    url='http://pypi.python.org/pypi/heospy/',
    license='LICENSE.txt',
    description='Control Denon\'s HEOS speakers with Python.',
    install_requires=[
        'six',
        'future'
    ],
    long_description=open('Readme.md').read()
)
