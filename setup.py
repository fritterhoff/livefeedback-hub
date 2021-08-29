"""
livefeedback setup
"""
from pathlib import Path

import setuptools

HERE = Path(__file__).parent.resolve()

# The name of the project
name = "livefeedback-hub"


long_description = (HERE / "README.md").read_text()

# get requirements
with open("requirements.txt") as f:
    install_requires = f.readlines()

setup_args = dict(
    name=name,
    version="0.1.0",
    url="https://github.com/fritterhoff/livefeedback-hub",
    author="Florian Ritterhoff",
    author_email="ritterhoff.florian@hm.edu",
    description="JupyterHub Service extension for livefeedback using otter-grader",
    license="BSD-3-Clause",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    install_requires=install_requires,
    zip_safe=False,
    include_package_data=True,
    python_requires=">=3.6",
    platforms="Linux, Mac OS X, Windows",
    keywords=["Jupyter", "JupyterHub", "Otter-Grader"],
    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Framework :: Jupyter",
    ],
    entry_points={
        "console_scripts": [
            "livefeedback-hub.py = livefeedback_hub.server:main",
            "livefeedback-hub = livefeedback_hub.server:main",
        ]
    },
)


if __name__ == "__main__":
    setuptools.setup(**setup_args)
