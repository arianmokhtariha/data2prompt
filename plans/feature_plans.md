# replacing pandas with polars for faster operations 
# adding direct clipboard output --clipboard
# adding --schema-only flag for just extracting the schema 
# adding a metadata header/tag that contains stats summary and table data types and missing counts/percentage of each column, it also can be turned off with         --no-stats-summary   
# instead of skipping the whole .env file ,only show the variable names in the output, it helps to better understand the project with .env vars
# expand parsers module for other file types like .parquet .sqlite .db 
# smarter excel parsing by extracting the formulas too and addressing them to their cells so llm gets a better understanding , also can be turned off with --no-excel-formulas 
# detect partitioned data's (.csv, .xlsx, .xls) , if their schema is exactly the same ,only spawn the parser on one of them and ignore other partitions,this logic can be turned on with --ignore-partitions 
