from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="cassandra-axonops-analyzer",
    version="0.1.0",
    author="AxonOps Team",
    author_email="support@axonops.com",
    description="Comprehensive Cassandra cluster analysis tool powered by AxonOps",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/axonops/cassandra-analyzer",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: System Administrators",
        "Topic :: Database",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.11",
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