import os
import tempfile
from src.data2prompt.parsers import process_sql

def test_process_sql_handles_multi_row_inserts():
    """
    Test that multi-row INSERT statements (starting with ,) are correctly 
    identified as data and sampled, rather than being treated as generic lines.
    """
    sql_content = """
CREATE TABLE `table1` (
  `id` int(11) NOT NULL
);

INSERT INTO `table1` VALUES (1)
, (2)
, (3)
, (4)
, (5);

CREATE TABLE `table2` (
  `id` int(11) NOT NULL
);
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as temp_sql:
        temp_sql.write(sql_content)
        temp_sql_path = temp_sql.name
    
    try:
        # Use a small sample size and small max_lines to trigger the bug
        # If the rows starting with ',' are not recognized as data, 
        # they will count towards max_lines.
        result = process_sql(temp_sql_path, sample_size=2, max_lines=5)
        
        # 1. Table 2 schema should be preserved even if max_lines is low
        assert "CREATE TABLE `table2`" in result
        
        # 2. Data should be truncated according to sample_size
        assert "[Table data truncated" in result
        assert ", (1)" in result or "VALUES (1)" in result
        assert ", (3)" not in result
        
    finally:
        if os.path.exists(temp_sql_path):
            os.remove(temp_sql_path)

def test_process_sql_preserves_full_schema():
    """
    Test that the entire CREATE TABLE block is preserved regardless of max_lines.
    """
    sql_content = """
-- Some comments at the top
-- More comments
-- Even more comments
CREATE TABLE `large_table` (
  `col1` int,
  `col2` int,
  `col3` int,
  `col4` int,
  `col5` int,
  `col6` int
) ENGINE=InnoDB;

INSERT INTO `large_table` VALUES (1,2,3,4,5,6);
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as temp_sql:
        temp_sql.write(sql_content)
        temp_sql_path = temp_sql.name
        
    try:
        # Set max_lines very low (e.g., 2)
        # The comments might be truncated, but the CREATE TABLE block must remain intact.
        result = process_sql(temp_sql_path, sample_size=10, max_lines=2)
        
        assert "CREATE TABLE `large_table`" in result
        assert "`col6` int" in result
        assert ") ENGINE=InnoDB;" in result
        assert "INSERT INTO `large_table`" in result
        
    finally:
        if os.path.exists(temp_sql_path):
            os.remove(temp_sql_path)
