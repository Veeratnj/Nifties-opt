import pandas as pd
from pathlib import Path

# ---------- CONFIG ----------
CSV_FILE = "historical_data_202601091034.csv"
TIMESTAMP_COL = "timestamp"
OUTPUT_DIR = "split_output"
DAY_SPLIT = [3, 2]  # <-- change pattern here
# ----------------------------

Path(OUTPUT_DIR).mkdir(exist_ok=True)

# Read CSV
df = pd.read_csv(CSV_FILE)

# Parse timestamp column
df[TIMESTAMP_COL] = pd.to_datetime(
    df[TIMESTAMP_COL],
    format="%Y-%m-%d %H:%M:%S.%f %z"
)

# Extract date
df["trade_date"] = df[TIMESTAMP_COL].dt.date

# Get unique sorted dates
unique_dates = sorted(df["trade_date"].unique())

print(f"Total unique days: {len(unique_dates)}")

start = 0
for idx, days_count in enumerate(DAY_SPLIT, start=1):
    selected_dates = unique_dates[start:start + days_count]
    start += days_count

    split_df = df[df["trade_date"].isin(selected_dates)]

    output_file = f"{OUTPUT_DIR}/output_part_{idx}.csv"
    split_df.drop(columns=["trade_date"]).to_csv(output_file, index=False)

    print(f"Created {output_file} with {len(selected_dates)} days")

print("✅ Split completed")
