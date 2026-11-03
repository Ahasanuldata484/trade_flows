import re
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, types
from sqlalchemy.engine import URL

DB_URL = URL.create(
    drivername="postgresql+psycopg2",
    username="postgres",
    password="47289-+#AKn24 D",
    host="localhost",
    port=5432,
    database="postgres",
)

engine = create_engine(DB_URL)

# The configuration

FILE_PATH = r"C:\Users\aknah\OneDrive\Documents\data_engineering\trade_flows_all\trade_flows.xlsx"

# Columns that look like numbers (e.g. HS code, country/reporter code) but
# should actually be kept as text (to prevent missing leading zeros —
# for example, the country code "008" would be 8, which is incorrect),
# put their names (after cleaning) here.
# For examples: FORCE_TEXT_COLUMNS = ['reporter_code', 'partner_code', 'hs_code']
FORCE_TEXT_COLUMNS = []

# If at least 0.95% of a column's value is numeric, it will be considered a numeric column.
NUMERIC_DETECTION_THRESHOLD = 0.95

# 2. Loading data

print("Loading data...")
df = pd.read_excel(FILE_PATH)
print(f"Loaded {len(df)} rows, {len(df.columns)} columns.\n")

# 3.Cleaning column names

df.columns = [
    re.sub(r'[^a-z0-9]+', '_', str(c).strip().lower()).strip('_')
    for c in df.columns
]

# 4. Numeric data cleaning

def clean_numeric_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.str.replace(',', '', regex=False)
    s = s.str.replace(r'[^0-9.\-]', '', regex=True)
    s = s.replace({'': np.nan, 'nan': np.nan, '.': np.nan,
                    '-': np.nan, 'none': np.nan})
    return pd.to_numeric(s, errors='coerce')


def is_mostly_numeric(s: pd.Series, threshold: float = NUMERIC_DETECTION_THRESHOLD) -> bool:
    non_null = s.dropna()
    if len(non_null) == 0:
        return False
    converted = clean_numeric_series(non_null)
    return (converted.notna().sum() / len(non_null)) >= threshold

# 5. Cleaning text based data

def clean_text_series(s: pd.Series) -> pd.Series:
    na_mask = s.isna()
    s = s.astype(str).str.strip().str.lower()
    s = s.str.replace(',', '_', regex=False)
    s = s.str.replace(r'\s+', '_', regex=True) 
    s = s.str.replace(r'[^a-z0-9_\-]', '', regex=True)
    s = s.str.replace(r'_+', '_', regex=True).str.strip('_')
    s.loc[na_mask] = np.nan
    s = s.replace({'': np.nan, 'nan': np.nan, 'none': np.nan})
    return s

# 6. Separating columns into numeric / text and cleaning them

numeric_cols, text_cols = [], []

for col in df.columns:
    if col in FORCE_TEXT_COLUMNS:
        text_cols.append(col)
    elif is_mostly_numeric(df[col]):
        numeric_cols.append(col)
    else:
        text_cols.append(col)
#The job of these 2 lines below is to show is to display the result as output on the monitor, 
#So you can be sure that Python has marked which columns as numbers & which columns as text.
print("considered as numeric:", numeric_cols)
print("considered as text:", text_cols, "\n")

for col in numeric_cols:
    df[col] = clean_numeric_series(df[col])

for col in text_cols:
    df[col] = clean_text_series(df[col])

# 7. Fixing data types

def get_sqlalchemy_type(series: pd.Series):
    non_null = series.dropna()
    if non_null.empty:
        return types.VARCHAR(200)

    if pd.api.types.is_numeric_dtype(series):
        if (non_null % 1 == 0).all():
            return types.Integer()
        return types.Numeric(18, 4)

    max_len = int(non_null.astype(str).str.len().max())
    return types.VARCHAR(max(max_len + 20, 50))


dtype_mapping = {col: get_sqlalchemy_type(df[col]) for col in df.columns}

# Inserting the data into the database

try:
    df.to_sql(
        name='trade_flows',
        con=engine,
        schema='analysis',
        if_exists='replace',
        index=False,
        dtype=dtype_mapping
    )

    print(f"Success! Total {len(df)} rows pushed.")

except Exception as e:
    print(f"Error occurred: {e}")