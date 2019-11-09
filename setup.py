import pathlib
from setuptools import setup

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

# This call to setup() does all the work
setup(
    name="ubgrade",
    version="0.1.6",
    description="Automates some tasks related to preparation and grading of exams.",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/bbadzioch/ubgrade",
    author="Bernard Badzioch",
    author_email="bernard.badzioch@gmail.com",
    license="GPLv3",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    packages=["ubgrade"],
    include_package_data=True,
    install_requires=["pdf2image", "reportlab", "PyPDF2", "pyzbar", "numpy", "matplotlib", "pandas", "opencv-python"]
)
