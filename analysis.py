import pandas as pd

DATA_PATH = "data/IAIR7EFL.DTA"

# StataReader opens the file for reading only. It reads the small header and
# metadata sections up front; data rows are only read when we ask for them.
with pd.io.stata.StataReader(DATA_PATH, convert_categoricals=False) as reader:
    # Dict of {variable name: description}, taken from the file's metadata.
    labels = reader.variable_labels()

    # Row count from the file header. pandas has no public attribute for this,
    # so we use the internal `_nobs` (it may change in future pandas versions).
    n_rows = reader._nobs
    n_cols = len(labels)

    # Read only the first 100 rows (all columns) instead of the whole file.
    df = reader.read(nrows=100)

print("Dataset size (from metadata):")
print("  Rows:   ", f"{n_rows:,}")
print("  Columns:", f"{n_cols:,}")

print("\nSample loaded:", len(df), "rows x", len(df.columns), "columns")

first_30 = df.columns[:30].tolist()

print("\nFirst 30 variable names:")
print(first_30)

print("\nFirst 30 variables with descriptions:")
for name in first_30:
    print(f"  {name:<8} {labels[name]}")
