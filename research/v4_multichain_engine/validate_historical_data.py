import pandas as pd


def validate_csv(path: str):

    df = pd.read_csv(path)

    print("Total rows:", len(df))

    # Check duplicates
    duplicates = df["open_time"].duplicated().sum()
    print("Duplicate timestamps:", duplicates)

    # Sort check
    sorted_check = df["open_time"].is_monotonic_increasing
    print("Sorted correctly:", sorted_check)

    # Gap check
    df["gap"] = df["open_time"].diff()
    expected_gap = 300000  # 5 minutes in ms
    gaps = df[df["gap"] != expected_gap]

    print("Gap issues:", len(gaps))

    # Nulls
    print("Null values:")
    print(df.isnull().sum())

    # Negative price check
    negatives = (df[["open", "high", "low", "close"]] <= 0).sum()
    print("Negative price values:")
    print(negatives)


if __name__ == "__main__":
    validate_csv("data/solusdt_5m_full.csv")