from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="cassandra-axonops-analyzer",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A Cassandra cluster analyzer using AxonOps API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/cassandra-axonops-analyzer",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: System Administrators",
        "Topic :: Database",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "cassandra-analyzer=cassandra_analyzer.__main__:main",
        ],
    },
    include_package_data=True,
    package_data={
        "cassandra_analyzer": ["templates/*.j2", "config/*.yaml"],
    },
)