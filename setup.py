import pathlib
from setuptools import setup
import sys

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

__version__ = "0.0.1"

# This call to setup() does all the work
setup(
    name="audiocat_clark",
    version=__version__,
    description = "Audio tunnel for secure chat, file transfer or reverse shell on Linux.",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/ClarkFieseln/audiocat",
    author="Clark Fieseln",
    author_email="",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Developers",
        "Operating System :: POSIX :: Linux",
        "Topic :: Security",
    ],
    packages=["audiocat_clark"],
    include_package_data=True,
    keywords=['chat','messenger','reverse shell','file transfer','modem','audio','cryptography','encryption','security','cybersecurity','linux'],
    entry_points={
        "console_scripts": [
            "audiocat=audiocat_clark.audiocat:main",
        ]
    },
    project_urls={  # Optional
    'Source': 'https://github.com/ClarkFieseln/audiocat',
    },
)

