"""
Cassandra AxonOps Analyzer

A Python-based Cassandra cluster analysis tool that performs Montecristo-style 
analysis using AxonOps API as the data source.
"""

__version__ = "0.1.0"
__author__ = "Your Name"

from .analyzer import CassandraAnalyzer

__all__ = ["CassandraAnalyzer"]