# 1_replacing pandas with polars for faster operations 
# 6_expand parsers module for other file types like .parquet .sqlite .db 
# 7_smarter excel parsing by extracting the formulas too and addressing them to their cells so llm gets a better understanding , also can be turned off with --no-excel-formulas 
# 8_detect partitioned data's (.csv, .xlsx, .xls) , if their schema is exactly the same ,only spawn the parser on one of them and ignore other partitions,this logic can be turned on with --ignore-partitions 

# --- Implemented and graduated to docs/ ---
# 2_adding direct clipboard output --clipboard
# 3_adding --schema-only flag for just extracting the schema
# 4_adding a metadata header/tag with stats summary, dtypes and missing counts/% per column, toggle with --no-stats-summary
# 5_show .env variable names with redacted values instead of skipping the whole file, toggle with --no-env-keys
