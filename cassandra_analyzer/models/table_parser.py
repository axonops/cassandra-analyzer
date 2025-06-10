"""
Table CQL parser for extracting table structure and options
"""

import re
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass


@dataclass
class ParsedColumn:
    """Represents a parsed column from CQL"""
    name: str
    data_type: str
    is_static: bool = False
    is_frozen: bool = False


@dataclass
class ParsedPrimaryKey:
    """Represents the primary key structure"""
    partition_keys: List[str]
    clustering_keys: List[str]


@dataclass
class ParsedTableOptions:
    """Represents table options from WITH clause"""
    bloom_filter_fp_chance: float = 0.01
    caching: Dict[str, str] = None
    comment: str = ""
    compaction: Dict[str, Any] = None
    compression: Dict[str, Any] = None
    gc_grace_seconds: int = 864000
    memtable_flush_period_in_ms: int = 0
    min_index_interval: int = 128
    max_index_interval: int = 2048
    speculative_retry: str = "99p"
    crc_check_chance: float = 1.0
    cdc: bool = False
    additional_write_policy: str = "99p"
    default_time_to_live: int = 0
    
    def __post_init__(self):
        if self.caching is None:
            self.caching = {}
        if self.compaction is None:
            self.compaction = {}
        if self.compression is None:
            self.compression = {}


class TableCQLParser:
    """Parser for Cassandra table CQL statements"""
    
    def parse_create_table(self, cql: str) -> Dict[str, Any]:
        """
        Parse a CREATE TABLE CQL statement
        
        Returns:
            Dict containing:
            - columns: List of ParsedColumn
            - primary_key: ParsedPrimaryKey
            - options: ParsedTableOptions
            - is_counter: bool
            - has_collections: bool
            - has_frozen_collections: bool
        """
        result = {
            "columns": [],
            "primary_key": None,
            "options": ParsedTableOptions(),
            "is_counter": False,
            "has_collections": False,
            "has_frozen_collections": False,
            "column_families": []
        }
        
        # Clean up the CQL
        cql = self._clean_cql(cql)
        
        # Extract table definition and WITH clause
        table_def, with_clause = self._split_table_and_options(cql)
        
        # Parse columns and primary key
        columns, primary_key = self._parse_table_definition(table_def)
        result["columns"] = columns
        result["primary_key"] = primary_key
        
        # Check for counter columns
        result["is_counter"] = any("counter" in col.data_type.lower() for col in columns)
        
        # Check for collections
        collection_types = ["list", "set", "map"]
        for col in columns:
            if any(ctype in col.data_type.lower() for ctype in collection_types):
                result["has_collections"] = True
                if "frozen" in col.data_type.lower():
                    result["has_frozen_collections"] = True
        
        # Parse WITH options
        if with_clause:
            result["options"] = self._parse_with_clause(with_clause)
        
        # Extract column families for compound primary keys
        if primary_key and len(primary_key.clustering_keys) > 0:
            result["column_families"] = primary_key.partition_keys + primary_key.clustering_keys
        
        return result
    
    def _clean_cql(self, cql: str) -> str:
        """Clean and normalize CQL statement"""
        # Remove newlines and extra spaces
        cql = re.sub(r'\s+', ' ', cql)
        # Remove IF NOT EXISTS
        cql = re.sub(r'IF\s+NOT\s+EXISTS\s+', '', cql, flags=re.IGNORECASE)
        return cql.strip()
    
    def _split_table_and_options(self, cql: str) -> Tuple[str, str]:
        """Split CQL into table definition and WITH clause"""
        # Find the last ) before WITH
        with_match = re.search(r'\)\s*WITH\s+', cql, re.IGNORECASE)
        if with_match:
            table_def = cql[:with_match.start() + 1]
            with_clause = cql[with_match.end():]
            # Remove trailing semicolon
            with_clause = with_clause.rstrip(';')
            return table_def, with_clause
        else:
            # No WITH clause
            return cql.rstrip(';'), ""
    
    def _parse_table_definition(self, table_def: str) -> Tuple[List[ParsedColumn], ParsedPrimaryKey]:
        """Parse the table definition to extract columns and primary key"""
        columns = []
        primary_key = None
        
        # Extract content between CREATE TABLE ... (  and final )
        match = re.search(r'CREATE\s+TABLE\s+[\w\.]+\s*\((.*)\)', table_def, re.IGNORECASE | re.DOTALL)
        if not match:
            return columns, primary_key
        
        content = match.group(1)
        
        # Split by commas (but not within parentheses)
        parts = self._split_respecting_parentheses(content)
        
        for part in parts:
            part = part.strip()
            
            # Check if this is the PRIMARY KEY definition
            if part.upper().startswith('PRIMARY KEY'):
                primary_key = self._parse_primary_key(part)
            else:
                # This is a column definition
                col = self._parse_column_definition(part)
                if col:
                    columns.append(col)
        
        return columns, primary_key
    
    def _parse_column_definition(self, col_def: str) -> Optional[ParsedColumn]:
        """Parse a single column definition"""
        # Handle special keywords
        is_static = 'STATIC' in col_def.upper()
        col_def = re.sub(r'\s+STATIC\s*', ' ', col_def, flags=re.IGNORECASE)
        
        # Extract column name and type
        # Handle complex types like frozen<map<text, text>>
        match = re.match(r'(\w+)\s+(.+?)(?:\s+PRIMARY\s+KEY)?$', col_def.strip())
        if match:
            name = match.group(1)
            data_type = match.group(2).strip()
            
            return ParsedColumn(
                name=name,
                data_type=data_type,
                is_static=is_static,
                is_frozen='frozen' in data_type.lower()
            )
        
        return None
    
    def _parse_primary_key(self, pk_def: str) -> ParsedPrimaryKey:
        """Parse PRIMARY KEY definition"""
        # Extract content within PRIMARY KEY (...)
        match = re.search(r'PRIMARY\s+KEY\s*\((.*)\)', pk_def, re.IGNORECASE)
        if not match:
            return ParsedPrimaryKey([], [])
        
        content = match.group(1).strip()
        
        # Check if partition key is composite (within parentheses)
        if content.startswith('('):
            # Composite partition key
            partition_match = re.match(r'\(([^)]+)\)\s*(?:,\s*(.+))?', content)
            if partition_match:
                partition_keys = [k.strip() for k in partition_match.group(1).split(',')]
                clustering_keys = []
                if partition_match.group(2):
                    clustering_keys = [k.strip() for k in partition_match.group(2).split(',')]
                return ParsedPrimaryKey(partition_keys, clustering_keys)
        else:
            # Simple primary key
            keys = [k.strip() for k in content.split(',')]
            if len(keys) == 1:
                return ParsedPrimaryKey(keys, [])
            else:
                return ParsedPrimaryKey([keys[0]], keys[1:])
        
        return ParsedPrimaryKey([], [])
    
    def _parse_with_clause(self, with_clause: str) -> ParsedTableOptions:
        """Parse the WITH clause options"""
        options = ParsedTableOptions()
        
        # Parse each AND-separated option
        option_pattern = r"(\w+)\s*=\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|{[^}]+}|\S+)"
        
        for match in re.finditer(option_pattern, with_clause):
            key = match.group(1).lower()
            value = match.group(2)
            
            # Remove quotes if present
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            
            # Parse based on key
            if key == 'bloom_filter_fp_chance':
                options.bloom_filter_fp_chance = float(value)
            elif key == 'gc_grace_seconds':
                options.gc_grace_seconds = int(value)
            elif key == 'memtable_flush_period_in_ms':
                options.memtable_flush_period_in_ms = int(value)
            elif key == 'min_index_interval':
                options.min_index_interval = int(value)
            elif key == 'max_index_interval':
                options.max_index_interval = int(value)
            elif key == 'crc_check_chance':
                options.crc_check_chance = float(value)
            elif key == 'default_time_to_live':
                options.default_time_to_live = int(value)
            elif key == 'cdc':
                options.cdc = value.lower() == 'true'
            elif key == 'speculative_retry':
                options.speculative_retry = value
            elif key == 'additional_write_policy':
                options.additional_write_policy = value
            elif key == 'comment':
                options.comment = value
            elif key == 'caching':
                options.caching = self._parse_dict_value(value)
            elif key == 'compaction':
                options.compaction = self._parse_dict_value(value)
            elif key == 'compression':
                options.compression = self._parse_dict_value(value)
        
        return options
    
    def _parse_dict_value(self, value: str) -> Dict[str, str]:
        """Parse dictionary-style values like {'key': 'value', ...}"""
        result = {}
        if value.startswith('{') and value.endswith('}'):
            content = value[1:-1]
            # Simple parsing - might need enhancement for complex values
            pairs = re.findall(r"'([^']+)'\s*:\s*'([^']+)'", content)
            for k, v in pairs:
                result[k] = v
        return result
    
    def _split_respecting_parentheses(self, text: str) -> List[str]:
        """Split text by commas, but respect parentheses"""
        parts = []
        current = ""
        paren_depth = 0
        
        for char in text:
            if char == '(' :
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == ',' and paren_depth == 0:
                parts.append(current.strip())
                current = ""
                continue
            
            current += char
        
        if current.strip():
            parts.append(current.strip())
        
        return parts