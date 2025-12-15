from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="rps-game-cli",
    version="2.1.0",
    author="Sohanur Rahman Sohan",
    description="A fun Rock Paper Scissors game for the terminal",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "pyfiglet",
        "rich",
    ],
    entry_points={
        "console_scripts": [
            "rps=rps_game.game:cli",
        ],
    },
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
