import setuptools

from scrapy_nodriver import __version__


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


setuptools.setup(
    name="scrapy-nodriver",
    version=__version__,
    license="BSD",
    description="Nodriver integration for Scrapy",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Ehsan U.",
    author_email="au85265@gmail.com",
    url="https://github.com/Ehsan-U/scrapy-nodriver",
    packages=["scrapy_nodriver"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Framework :: Scrapy",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=[
        "scrapy>=2.0,!=2.4.0",
        "nodriver-extras",
    ],
)