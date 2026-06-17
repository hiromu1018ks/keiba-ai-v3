# Quality Report — PASS

**Verdict:** `pass`

| Check | Severity | Passed | Detail |
|-------|----------|--------|--------|
| `table_exists:n_race` | block | yes | exists=True |
| `table_exists:n_uma_race` | block | yes | exists=True |
| `table_exists:n_harai` | block | yes | exists=True |
| `table_exists:n_hyosu` | block | yes | exists=True |
| `table_exists:n_odds_tanpuku` | block | yes | exists=True |
| `jra_since_2015` | block | yes | count=39593 |
| `n_race_pk_unique` | block | yes | duplicates=0, total=40035, distinct=40035 |
| `n_uma_race_natural_key_unique` | block | yes | duplicates=0, total=554610, distinct=554610 |
| `table_counts` | info | yes | (see INFO section) |
| `date_range` | info | yes | (see INFO section) |
| `null_rates` | info | yes | (see INFO section) |
| `cast_success` | info | yes | (see INFO section) |
| `mojibake` | info | yes | mojibake=0 |
| `code_value_anomalies` | info | yes | anomaly_rows=32203 |

## INFO details

### table_counts

```json
{
  "columns": {
    "n_race": {
      "total": 71972,
      "jra": 40035,
      "non_jra": 31937
    },
    "n_uma_race": {
      "total": 881202,
      "jra": 554610,
      "non_jra": 326592
    },
    "n_harai": {
      "total": 39580,
      "jra": 39580,
      "non_jra": 0
    },
    "n_hyosu": {
      "total": 0,
      "jra": 0,
      "non_jra": 0
    },
    "n_odds_tanpuku": {
      "total": 554217,
      "jra": 554217,
      "non_jra": 0
    }
  }
}
```

### date_range

```json
{
  "columns": {
    "overall_min": "19890401",
    "overall_max": "20260614",
    "jra_min": "19890401",
    "jra_max": "20260614"
  }
}
```

### null_rates

```json
{
  "columns": {
    "n_race": {
      "kyori_null_pct": 0.0,
      "kyori_zero_or_blank_pct": 0.0,
      "hassotime_null_pct": 0.0,
      "hassotime_zero_or_blank_pct": 0.0,
      "jyokencd5_null_pct": 0.0,
      "jyokencd5_zero_or_blank_pct": 0.0,
      "gradecd_null_pct": 0.0,
      "gradecd_zero_or_blank_pct": 73.0461,
      "syubetucd_null_pct": 0.0,
      "syubetucd_zero_or_blank_pct": 0.0
    },
    "n_uma_race": {
      "umaban_null_pct": 0.0,
      "umaban_zero_or_blank_pct": 0.0,
      "kettonum_null_pct": 0.0,
      "kettonum_zero_or_blank_pct": 0.0,
      "kakuteijyuni_null_pct": 0.0,
      "kakuteijyuni_zero_or_blank_pct": 0.0,
      "bamei_null_pct": 0.0,
      "bamei_zero_or_blank_pct": 0.0,
      "futan_null_pct": 0.0,
      "futan_zero_or_blank_pct": 0.0
    }
  }
}
```

### cast_success

```json
{
  "columns": {
    "n_race.kyori": {
      "total": 40035,
      "cast_success": 40035,
      "cast_fail": 0,
      "cast_success_pct": 100.0
    },
    "n_race.hassotime": {
      "total": 40035,
      "cast_success": 40035,
      "cast_fail": 0,
      "cast_success_pct": 100.0
    },
    "n_uma_race.futan": {
      "total": 554610,
      "cast_success": 554610,
      "cast_fail": 0,
      "cast_success_pct": 100.0
    }
  }
}
```

### mojibake

```json
{
  "columns": {
    "n_race.hondai": {
      "count": 0
    },
    "n_race.jyokenname": {
      "count": 0
    },
    "n_uma_race.bamei": {
      "count": 0
    },
    "n_uma_race.kisyuryakusyo": {
      "count": 0
    },
    "n_uma_race.chokyosiryakusyo": {
      "count": 0
    },
    "n_uma_race.banusiname": {
      "count": 0
    }
  },
  "total_mojibake_rows": 0,
  "marker": "U+FFFD (REPLACEMENT CHARACTER)"
}
```

### code_value_anomalies

```json
{
  "columns": {
    "jyokencd5": {
      "count": 256,
      "pct": 0.6394,
      "allowed_count": 6
    },
    "gradecd": {
      "count": 0,
      "pct": 0.0,
      "allowed_count": 10
    },
    "syubetucd": {
      "count": 10,
      "pct": 0.025,
      "allowed_count": 10
    },
    "jyocd_non_jra": {
      "count": 31937,
      "note": "jyocd outside 01-10 (NAR/海外含む)",
      "allowed_count": 10
    }
  },
  "total_jra_rows": 40035
}
```
