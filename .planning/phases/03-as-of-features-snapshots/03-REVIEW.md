---
phase: 03-as-of-features-snapshots
reviewed: 2026-06-19T00:00:00Z
depth: deep
files_reviewed: 22
files_reviewed_list:
  - scripts/run_feature_build.py
  - scripts/run_label_race_date_backfill.py
  - snapshots/.gitignore
  - src/config/feature_availability.yaml
  - src/etl/label_race_date_backfill.py
  - src/features/__init__.py
  - src/features/availability.py
  - src/features/builder.py
  - src/features/category_map_consumer.py
  - src/features/rolling.py
  - src/features/running_style.py
  - src/features/snapshot.py
  - tests/features/__init__.py
  - tests/features/conftest.py
  - tests/features/test_allowlist.py
  - tests/features/test_builder.py
  - tests/features/test_category_map_consumer.py
  - tests/features/test_pit_cutoff.py
  - tests/features/test_rolling.py
  - tests/features/test_running_style.py
  - tests/features/test_snapshot_repro.py
  - tests/test_label_race_date_backfill.py
findings:
  critical: 4
  warning: 11
  info: 6
  total: 21
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-19T00:00:00Z
**Depth:** deep
**Files Reviewed:** 22
**Status:** issues_found

## Summary

Phase 3（as-of feature snapshots）22ファイルを deep 深度で cross-file 分析した。PIT / leak-safety 不変条件の大部分（strict `<` pre-filter・per-observation `obs_id` window・train-only category map fit・raw 不変性・byte-reproducibility・禁止カラム排除）は堅実に実装されており、allowlist 検査・sentinel 区別・staging-swap idempotency など防御層が厚い。しかし **Critical 4件** のデータ正確性・リーク不変条件違反を発見した:

1. **CR-01**: `builder.py` の rolling 統合が行順不整合で silent な row-misalignment を起こす（rolling 値が別の observation に割当てられる）。Phase 4 学習データが直接的に破損する。
2. **CR-02**: `rolling_jyocd` 系統がカテゴリカル競馬場コード（"01".."10"）を数値集計（mean/sd/latest）する意味論的バグ。registry に登録済みで SC#2 通過するが、特徴量として意味をなさない。
3. **CR-03**: `post_position_confirmed` timing の feature が 1-A 出力に無条件混入する。`futan`/`jockey_id`/`umaban`/`wakuban` が race_date - 1 day の cutoff で「確定済」として扱われ、feature 毎の `available_from_timing` と PIT cutoff の個別照合が行われないリーク経路。
4. **CR-04**: `snapshot.py` が `_DETERMINISTIC_CREATED_AT` sentinel で `feature_snapshot_id` を schema metadata に埋め込むため、Parquet ファイル単体から snapshot_id が失われ、§12.4「feature_snapshot_id を Parquet metadata に埋込」要件と矛盾。

これらに加え、Warning 11件（test gap・型安全性・例外握り潰し等）・Info 6件（ドキュメント・重複定義等）を報告する。

---

## Critical Issues

### CR-01: rolling 統合での行順不整合による silent row-misalignment（データ破損）

**File:** `src/features/builder.py:403-409`
**Issue:**

`build_feature_matrix` Step 5 で rolling feature を統合する際、行順の不整合が発生する。

```python
# builder.py:287-299 の薄ラッパ
def build_rolling_features(observations, history):
    obs_sorted = observations.sort_values("feature_cutoff_datetime").reset_index(drop=True)
    ...
    return _build_rolling_features_impl(obs_sorted, hist_sorted)

# builder.py:400-409 の統合ブロック
if len(history) > 0 and len(feature_matrix) > 0:
    rolling_df = build_rolling_features(feature_matrix, history)  # 内部で sort される
    rolling_cols = [c for c in rolling_df.columns if c.startswith("rolling_")]
    fm_reset = feature_matrix.reset_index(drop=True)        # ← ソートされていない元の順序
    rolling_reset = rolling_df[rolling_cols].reset_index(drop=True)  # ← cutoff 昇順
    feature_matrix = pd.concat([fm_reset, rolling_reset], axis=1)   # ← 行 i 同士が別の馬!
```

`build_rolling_features` ラッパは入力 `observations` を `feature_cutoff_datetime` 昇順にソートして rolling 実装に渡す。しかし統合側は **(a) 元の `feature_matrix`**（未ソート）と **(b) ソート済み `rolling_df`** を単純に位置ベース（`axis=1`）で concat する。両者の `iloc[i]` は異なる観測行を指すため、**rolling 値が誤った馬に割当てられる**。

`_build_rolling_features_impl` 内部では `result = observations.copy()` → `result.at[idx, ...]` 代入 を行うが、`idx` は `result.index`（reset 済みの 0..N-1）を反復するため、rolling 実装自体は sort 済み observation に整合している。問題は **呼出側が rolling_df の rolling_* 列だけを抜き出して元の未ソート feature_matrix と concat する** 点にある。

**影響:**

- Phase 4 モデルの学習データが直接的に破損する。ある馬の過去5走成績が別の馬の属性に紐付く。
- 後段の `assert_matrix_columns_registered` はカラム名のみ検査するため、この row-misalignment を検出しない。
- canonical key 一意性検証（L460-465）も `(race_nkey, kettonum)` の一意性は保たれるため素通りする（行は増減しない）。
- テスト `test_no_registered_feature_column_all_nan_end_to_end`（test_builder.py）は `len(feature_matrix)` が小さく、かつ両馬の race_date が同一（2023-06-04）なため、ソートが安定して row-misalignment が顕在化しない。**テストがこのバグを捕捉しない**。

**Fix:**

rolling 統合をカノニカルキーで align する。最も安全なのは merge で明示的にキー結合すること:

```python
if len(history) > 0 and len(feature_matrix) > 0:
    rolling_df = build_rolling_features(feature_matrix, history)
    rolling_cols = [c for c in rolling_df.columns if c.startswith("rolling_")]
    # rolling_df に (race_nkey, kettonum) があれば merge、無ければ obs_id で merge
    merge_keys = ["race_nkey", "kettonum"] if "race_nkey" in rolling_df.columns else ["obs_id"]
    feature_matrix = feature_matrix.merge(
        rolling_df[merge_keys + rolling_cols], on=merge_keys, how="left"
    )
```

加えて回帰テストを追加すべき: 異なる `feature_cutoff_datetime` を持つ複数 observation で、各 observation の rolling 値が canonical key で正しく対応付けられていることを検証する（現状のテストは同日 observation のみでソート順が一意になるためバグを逃す）。

---

### CR-02: `rolling_jyocd` 系統がカテゴリカル競馬場コードを数値集計する意味論的バグ

**File:** `src/config/feature_availability.yaml:316-337`, `src/features/rolling.py:65-88,225-240`
**Issue:**

`jyocd` は JRA 競馬場コード（"01"=札幌, "05"=東京, "10"=高知 等）の **カテゴリカルな varchar(2)** である（`src/etl/filters.py:31` の `jyocd BETWEEN '01' AND '10'` が string 比較であることからも明白）。しかし:

1. `feature_availability.yaml:316-337` は `rolling_jyocd_mean_5` / `rolling_jyocd_latest_5` / `rolling_jyocd_sd_5` を **leakage_risk_level: low** で登録している。
2. `rolling.py:79-88` の `_SYSTEM_SOURCE["jyocd"] = ("jyocd",)` が jyocd を rolling source とする。
3. `rolling.py:237-240` が `pd.to_numeric(recent[system], errors="coerce")` で jyocd を数値化して mean/sd/latest を計算する。

結果として「過去5走の平均競馬場コード」=(5+7+5+5+7)/5 = 5.8 のような **意味をなさない数値** が特徴量として生成される。これは単なる無意味 feature でなく、誤ったシグナルをモデルに与える data quality 欠陥であり、CLAUDE.md「能力予測とEV計算を分離」の前提を脅かす。

**影響:**

- 学習特徴量として意味をなさない（カテゴリカルの算術平均）。
- jyocd は high-cardinality ID 扱いされるべき（jockey_id/horse_id 等と同様）が、category map consumer の `_CATEGORY_COLUMNS`（`category_map_consumer.py:48`）に含まれていない。本来は LightGBM native categorical または CatBoost `cat_features` で処理すべき。
- SC#2 allowlist 検査は feature_name の存在のみ検査し、集計方法の妥当性を検査しないため、このバグは構造的に検出されない。

**Fix:**

選択肢:
1. `rolling_jyocd_*` 3エントリを registry / `_ROLLING_SYSTEMS` / `_ROLLING_SYSTEMS_FOR_RESERVED` から削除する（jyocd は rolling 対象外とする）。
2. jyocd を高基数カテゴリ扱いし、rolling ではなく `_CATEGORY_COLUMNS` + category map でエンコードする。
3. もし「過去走の競馬場分布」を特徴量化したいなら、most-frequent（最頻値）等のカテゴリカル集計に切り替える（mean/sd は不適切）。

CLAUDE.md §13 の PIT semantics 上はリークではないが、**特徴量の意味論的正しさ** の観点で Critical（Phase 4 学習データの質が直接損なわれる）。

---

### CR-03: `post_position_confirmed` timing feature が 1-A 出力に無条件混入するリーク経路

**File:** `src/config/feature_availability.yaml:72-155`, `src/features/builder.py:366-468`, `src/features/availability.py:69-72`
**Issue:**

`feature_availability.yaml` は Phase 1-A 許可タイミングとして `{entry_confirmed, post_position_confirmed}` の2つを `ALLOWED_TIMINGS`（availability.py:69-72）に許可している。しかし CLAUDE.md「§13.2 Phase 1-A (出馬表・馬番・枠番確定後)」と「§13.4 禁止リスト」の文脈では、**`entry_confirmed` と `post_position_confirmed` は異なる確定タイミング** である:

- `entry_confirmed`: 出馬表確定（馬番・枠番は未確定）
- `post_position_confirmed`: 馬番・枠番確定（数日前〜前日）

`futan` (負担重量) / `jockey_id` / `umaban` / `wakuban` は全て `post_position_confirmed` で登録されている（feature_availability.yaml:72-155）。しかし `build_feature_matrix` は全期間1枚（D-09）で構築し、**`prediction_timing="1A"` を全行に固定 stamp する**（builder.py:457）。1-A = 出馬表確定後 と 1-A = 馬番確定後 の定義が曖昧なまま、post_position_confirmed 由来の feature が「1-A で取得可能」として扱われている。

問題は、**`feature_cutoff_datetime = race_date - 1 day`** の PIT 不変条件が、各 feature の `available_from_timing` と **個別に照合されていない** 点にある。`futan`/`jockey_id`/`umaban`/`wakuban` が post_position_confirmed で確定する情報なら、1-A cutoff 時点で「確定済か否か」を判定すべきだが、現状は allowlist が「許可リストに含まれる＝1-A で使える」と解釈され、timing の区別が実データに反映されない。

CLAUDE.md「§13.4 禁止: 当日馬番・枠番」が post_position_confirmed に該当する場合、これは禁止カラムが許可タイミング経由で feature_matrix に出力されるリークとなる。

**影響:**

- バックテスト時、prediction_timing="1A" の marker と実際の feature 可用性が不一致。
- `futan`/`jockey_id`/`umaban`/`wakuban` が race_date-1 day の cutoff で「確定済」として扱われるが、現実には馬番確定はレース直前〜数日前の場合がある。
- 再現性（§19.1）が損なわれる: snapshot 生成時点でこれら feature の確定状況が明記されない。

**Fix:**

1. CLAUDE.md §13.2 と調整し、Phase 1-A の正確な定義（出馬表確定 = entry_confirmed のみ、または post_position_confirmed 含む）を明文化する。
2. もし 1-A = `entry_confirmed` 限定 なら、`futan`/`jockey_id`/`umaban`/`wakuban` を別途 `1A_BANNED_TIMINGS` に分類し、feature_matrix に出力しない。
3. もし 1-A = `post_position_confirmed` 含む なら、`feature_availability.yaml` のコメントと `CUTOFF_RULE_METADATA` にその旨を明記し、各 feature の確定タイミングが cutoff と整合することを単体テストで検証する。
4. `assert_all_entries_allowed` は timing 集合の「許可」のみ検査し、「1-A で確定済か」を検査しないため、timing×cutoff の組合せ検査を追加する。

---

### CR-04: Parquet schema metadata の `feature_snapshot_id` が sentinel で埋められ §12.4 監査証跡が消失

**File:** `src/features/snapshot.py:179-189,70-76`
**Issue:**

`write_snapshot` は schema metadata 9キーを構築するが、`feature_snapshot_id` と `created_at` の両方を `_DETERMINISTIC_CREATED_AT = "deterministic-by-design-parquet-bytes-only"` sentinel で埋める:

```python
metadata: dict[bytes, bytes] = {
    b"dataset_version": dataset_version.encode(),
    b"feature_snapshot_id": _DETERMINISTIC_CREATED_AT.encode(),  # ← sentinel
    ...
    b"created_at": _DETERMINISTIC_CREATED_AT.encode(),            # ← sentinel
    ...
}
```

これは REVIEWS HIGH #6 の「SHA256 を Parquet bytes のみに依存させる」意図には合致するが、**§12.4「Parquet schema metadata に feature_snapshot_id を埋込」の要件を実質的に満たさない**。Parquet ファイルを単体で読んでも、それがどの snapshot か特定できない。`feature_snapshot_id` は manifest 側にのみ記録され、Parquet bytes と manifest の紐付けが manifest→Parquet 一方向になる。

**影響:**

- Parquet ファイルが manifest と分離された場合（ファイルだけ流用・移動・別環境持込）、snapshot_id 復元が不可能。再現性（§19.1）の監査証跡が失われる。
- DuckDB で `read_parquet()` した際、schema metadata から snapshot_id を取ろうとすると sentinel 文字列が返る。
- `feature_snapshot_id` sentinel が複数 snapshot で同一になるため、SHA256 は不変だが「これは本当に snapshot X か？」の検証が Parquet 単体でできない。

**Fix:**

SHA256 deterministic 性を保ちつつ snapshot_id を metadata に埋め込む方法:

1. **推奨**: SHA256 計算を schema metadata 構築 **前** に、metadata 無しの schema で行う。その後 metadata（snapshot_id 含む）を付与して書込む。これで SHA256 は「データ内容のみ」に依存し、かつ Parquet bytes にも snapshot_id が埋まる。
2. もしくは `feature_snapshot_id` を SHA256 の **入力に含める** ことを受け入れ、test_byte_reproducible_by_hash を「同一 snapshot_id で同一 SHA256」に修正する（snapshot_id が異なれば異なる SHA256 になるのは正しい挙動）。
3. 現状の sentinel 方式を維持するなら、§12.4 の要件文と CLAUDE.md を改訂し「snapshot_id は manifest 側のみ」と明記する。ただしこの場合 Parquet 単体の監査性は諦めることになる。

いずれにせよ、現状は「§12.4 要件を満たしているように見えて実質的に満たしていない」ため文書と実装の乖離を解消すべき。

---

## Warnings

### WR-01: `_fetch_feature_sources` / `_fetch_history` が `except Exception` で全例外を握り潰し空 DataFrame を返す

**File:** `src/features/builder.py:539-541,569-571`
**Issue:**

```python
except Exception as exc:  # noqa: BLE001 - unit test / DB 未接続時は空 frame で安全フォールバック
    logger.warning("feature source fetch failed (returning empty frame): %s", exc)
    return pd.DataFrame(columns=_OBS_SELECT_COLUMN_NAMES)
```

全ての例外（DB 接続エラー・SQL 構文エラー・権限エラー・ネットワークエラー・psycopg ProgrammingError 等）を catch して空 DF を返す。`build_feature_matrix` の Step 2 で `len(feature_matrix) == 0` を RuntimeError にする（WR-02 fail-loud）ため、最終的には気づかれるが、**「なぜ空になったか」の情報が warning log にしか残らず、例外型も消える**。本番 DB 障害時に `logger.warning` が見逃されると、WR-02 の RuntimeError だけが残り原因究明が困難。

また `noqa: BLE001` は意図的だが、`MemoryError` 等の重大例外も握り潰される（`KeyboardInterrupt` / `SystemExit` は `Exception` を継承しないため安全）。

**Fix:**

少なくとも `psycopg.errors.Error` と接続関連例外は区別し、想定外例外（`RuntimeError`/`MemoryError`/`TypeError` 等）は re-raise する:

```python
except (psycopg.errors.OperationalError, psycopg.errors.InterfaceError) as exc:
    logger.warning("feature source fetch failed (DB unavailable): %s", exc)
    return pd.DataFrame(columns=_OBS_SELECT_COLUMN_NAMES)
# その他の例外は re-raise して WR-02 で捕捉させる
```

テスト用途の「DB 未接続フォールバック」は monkey-patch で明示的に空 DF を返す方に寄せるべき（test_builder.py は既にそのパターンを採用している）。

---

### WR-02: `days_since_prev` が全 history で計算されるが、rolling の PIT フィルタ後に再計算されない

**File:** `src/features/builder.py:221-234`, `src/features/rolling.py:225-240`
**Issue:**

`_construct_derived_columns(with_days_since_prev=True)` は history 全行で `days_since_prev = groupby("kettonum")["race_date"].diff().dt.total_seconds() / 86400` を計算する（builder.py:221-234）。この時点では PIT フィルタ未適用。

その後 rolling 側で `history_filtered = expanded[as_of_datetime < feature_cutoff_datetime]` で PIT フィルタ（rolling.py:206-208）してから `sort_values DESC + groupby("obs_id").head(5)` で latest-5 を取得する。`days_since_prev` の **値自体** は各 history 行の「前走からの日数」なので PIT 後も意味は保つ。しかし rolling の `latest` 軸は「window 内の最新1件」を取るため、window 外のより古い走が `days_since_prev` の基準（前走）として使われている可能性がある。

つまり「target observation の5走前」と「4走前」の間隔は正しいが、「5走前の days_since_prev」は **5走前のレースの前走（= window 外の6走前）** からの日数を参照しており、window 内の文脈と整合しない場合がある。

**影響:** リークではないが、`rolling_days_since_prev_latest_5` の意味が曖昧（window 内の最新走の、window 外も含めた前走日数）。ドキュメント未整備。

**Fix:**

`days_since_prev` を rolling window 内で再計算する（window 内のソート順で diff を取る）か、registry / docstring で「window 外前走参照」を明記する。

---

### WR-03: `estimated_running_style` の groupby が `kettonum` 単位で cross-observation leak の再発リスク

**File:** `src/features/builder.py:416-449`
**Issue:**

Step 6 の推定脚質は `feature_matrix[["kettonum", "feature_cutoff_datetime"]]` で history を expand し、PIT フィルタ後に `pit_filtered_style.groupby("kettonum")` で集約する。CYCLE-2 HIGH #1 で rolling 側が `groupby("obs_id")` に切り替えた理由は「同一 horse が複数 observation に現れると horse 単位 groupby で cross-obs leak する」ためであった。

推定脚質も「同一 kettonum が複数 target observation に現れる」ケース（同一馬が同一 snapshot 内で複数レースに出走する場合、例えば週末に2レース）では `groupby("kettonum")` が両 observation の過去走を統合してしまう。PIT フィルタが cutoff 毎に異なるため、obs_A の PIT フィルタ後集合 と obs_B の PIT フィルタ後集合 を kettonum で groupby すると、obs_A の cutoff 以降・obs_B の cutoff 以前の走が obs_A に混入する可能性がある。

実データでは同一 snapshot 内に同一馬の複数 target observation が含まれるか不明だが、rolling 側で obs_id を導入したのと対称に、推定脚質も obs_id 単位で groupby すべき。

**Fix:**

```python
# obs_id 構築（rolling と同一 idiom）
if "obs_id" not in feature_matrix.columns:
    feature_matrix["obs_id"] = list(zip(
        feature_matrix.get("race_nkey", feature_matrix.index),
        feature_matrix["kettonum"], strict=False
    ))
obs_keys_style = feature_matrix[["obs_id", "kettonum", "feature_cutoff_datetime"]].copy()
expanded_style = history.merge(obs_keys_style, on="kettonum", ...)
...
for obs_id, group in pit_filtered_style.groupby("obs_id"):
    style_map[obs_id] = estimate_running_style(rows)
# feature_matrix["estimated_running_style"] = feature_matrix["obs_id"].map(style_map).fillna("__MISSING__")
```

race_nkey が無い場合（テスト）のフォールバックも必要。

---

### WR-04: `feature_availability.yaml` の `available_from_timing` 値が `entry_confirmed` と `post_position_confirmed` を混在させるが、SC#1 PIT 検査が個別に行われない

**File:** `src/config/feature_availability.yaml:57-363`, `src/features/availability.py:69-72`
**Issue:**

CR-03 と関連。`ALLOWED_TIMINGS` に両タイミングを許可し、`assert_all_entries_allowed` は「未知 timing を弾く」だけ。各 feature の `available_from_timing` と `prediction_timing="1A"`（builder.py:457）の整合性を検査する層が無い。1-A が entry_confirmed 限定なら、post_position_confirmed feature は 1-A 出力に含むべきでない。

**Fix:**

`prediction_timing` 毎の許可 timing を定義し、feature_matrix 構築時に stamp する `prediction_timing` と整合する feature のみ出力する検査を追加する。

---

### WR-05: `as_of_datetime` が naive datetime で timezone 考慮がない（JST midnight 不変条件が形式的）

**File:** `src/features/builder.py:219-220,379-382`, `src/features/availability.py:45-56`
**Issue:**

`CUTOFF_SEMANTICS["timezone"] = "Asia/Tokyo"` を宣言するが、実装は:

```python
feature_matrix["feature_cutoff_datetime"] = (
    pd.to_datetime(feature_matrix["race_date"]) - pd.Timedelta(days=1)
)
feature_matrix["as_of_datetime"] = pd.to_datetime(feature_matrix["race_start_datetime"])
```

`pd.to_datetime(race_date)` は naive datetime（tz-naive）になる。JST midnight を表現するには `tz_localize("Asia/Tokyo")` が必要。JRA データでは `race_date` が date 型で日付境界が明確なため、実害は限定的だが、`as_of_datetime = race_start_datetime` が JST 発走時刻を naive で扱うと、`as_of_datetime < feature_cutoff_datetime` の比較が tz 非考慮で行われる。

**影響:** JRA データでは same-day 同一 JST midnight 境界のため実害軽微だが、CUTOFF_SEMANTICS の「timezone: Asia/Tokyo」宣言と実装が乖離している。将来のマルチタイムゾーンデータ混入時に silent leak の危険。

**Fix:**

`feature_cutoff_datetime` と `as_of_datetime` に `.dt.tz_localize("Asia/Tokyo")` を適用するか、`CUTOFF_SEMANTICS` の timezone 宣言を削除して naive 運用を明示する。

---

### WR-06: `test_wr01_prime_raises_on_missing_as_of_datetime` が `KeyError` 受け入れで本来の ValueError 検証を弱体化

**File:** `tests/features/test_builder.py:317-374`
**Issue:**

```python
with pytest.raises((ValueError, KeyError)) as exc_info:
    builder.build_feature_matrix(...)
```

`as_of_datetime` 欠損時に `ValueError`（WR-01' fail-loud message）**または** `KeyError`（rolling sort_values）のいずれかを受け入れる。WR-01' の意図は「明示的な ValueError で fail-loud」だが、KeyError 受け入れにより rolling 側の sort_values で偶然 raise した場合も GREEN になる。もし将来 rolling 実装が sort_values を使わなくなった場合、ValueError だけが頼りになるが、テストが両方を受け入れると regression を逃す。

**Fix:**

`pytest.raises(ValueError, match="as_of_datetime")` のみに絞る。実装側で KeyError が発生するなら明示的に ValueError に wrap すべき。

---

### WR-07: backfill idempotent verify がスクリプト全体での raw 不変性を検証しない

**File:** `scripts/run_label_race_date_backfill.py:62-100`, `src/etl/label_race_date_backfill.py:213-266`
**Issue:**

`backfill_label_race_date` は内部で `compute_raw_fingerprint(before)` → staging-swap → `compute_raw_fingerprint(after)` → `assert_raw_unchanged` を実行する。`run_label_race_date_backfill.py` は `backfill_label_race_date` を2回呼ぶが、**各呼出が独立して raw fingerprint before/after を取る**。1回目の backfill が raw を変更した場合、1回目の呼出内の `assert_raw_unchanged` で検出される。しかし2回目実行時、1回目で既に raw が変更されていた場合、2回目の before は「1回目後の変更済状態」となり、2回目の after も同状態なら assert は素通りする。

つまり idempotent verify（run #1 == run #2）は backfill 結果の rowcount/checksum 一致を見るだけで、**1回目と2回目の間に別プロセスが raw を変更した場合**を検出できない。これは競合条件下でのみ発現する稀なケースだが、D-06 raw 不変性の二重保護としては弱い。

**Fix:**

run_label_race_date_backfill.py の main で backfill 呼出前に1回、全工程終了後に1回、raw fingerprint を取り、両者が一致することを assert する（スクリプト全体での raw 不変性）。

---

### WR-08: `estimate_running_style_batch` が前方参照型アノテーション `pd.Series` を持ち、かつ dead code の可能性

**File:** `src/features/running_style.py:104-129`
**Issue:**

```python
def estimate_running_style_batch(
    history_by_horse: Any,
) -> pd.Series:  # noqa: F821 (pandas import below for type only)
    ...
    import pandas as pd
    def _per_group(group: pd.DataFrame) -> str:  # noqa: F821
        ...
```

戻り値型 `pd.Series` と内側 `_per_group` の引数 `pd.DataFrame` が `# noqa: F821` で黙られているが、module top-level に `import pandas as pd` が無く、関数内 import のみ。mypy / pyright は関数シグネチャの `pd.Series` を未定義名として警告する（`noqa: F821` は ruff を黙らせるが type checker は黙らない）。また実際に builder.py から `estimate_running_style_batch` は呼出されておらず（builder は `estimate_running_style` のみ使用）、dead code の可能性が高い。

**Fix:**

1. もし未使用なら `estimate_running_style_batch` を削除する（YAGNI）。
2. 使うなら module top に `import pandas as pd` を置き、`# noqa: F821` を削除する。

---

### WR-09: `_construct_derived_columns` の `days_since_prev` 再代入が index の再整列に依存し壊れやすい

**File:** `src/features/builder.py:221-234`
**Issue:**

```python
ordered = result.sort_values(["kettonum", "race_date"]).copy()
ordered["_rd"] = rd.loc[ordered.index]
ordered["days_since_prev"] = (
    ordered.groupby("kettonum")["_rd"].diff().dt.total_seconds() / 86400.0
)
result["days_since_prev"] = ordered["days_since_prev"].reindex(result.index)
```

`ordered["_rd"] = rd.loc[ordered.index]` で `rd`（= `pd.to_datetime(result["race_date"])`、index は `result.index`）を `ordered.index` で lookup する。`ordered` は `result.sort_values(...)` だが `sort_values` は index を保持するため `ordered.index` は元の `result.index` の順序並び替え版となる。`rd.loc[ordered.index]` は index label で lookup するため、一意 index なら正しい。しかし `result` の index が重複している場合（reset_index 忘れ等）、`rd.loc[ordered.index]` が複数行を返し `ordered["_rd"]` への代入が alignment エラーを起こす。

`_fetch_history` は `pd.DataFrame(rows, columns=...)` で構築し reset していないため、index は 0..N-1 の一意だが、呼出パスによっては重複 index が混入し得る。壊れやすいイディオム。

**Fix:**

`reset_index(drop=True)` してから計算し、元の index に戻す。または `result` を最初から reset しておく:

```python
result = result.reset_index(drop=True)
rd = pd.to_datetime(result["race_date"])
ordered = result.sort_values(["kettonum", "race_date"])
ordered["days_since_prev"] = (
    ordered.groupby("kettonum")[rd.name].diff().dt.total_seconds() / 86400.0
)
result["days_since_prev"] = ordered.sort_index()["days_since_prev"]
```

---

### WR-10: `persist_category_maps` が atomic write でなく partial JSON を残す可能性

**File:** `src/features/category_map_consumer.py:243-263`
**Issue:**

```python
def persist_category_maps(maps, artifact_path):
    Path(artifact_path).parent.mkdir(parents=True, exist_ok=True)
    serialisable = {col: dict(m.items()) for col, m in maps.items()}
    Path(artifact_path).write_text(
        json.dumps(serialisable, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
```

`Path.write_text` は atomic write でない。書込中にプロセス kill / disk full / 権限エラー が発生すると partial / 空 / 破損 JSON が残る。CR-01新（03-REVIEW）の partial-failure 抑止意図に反する。

**Fix:**

tmp file に書いて os.replace で atomic rename する:

```python
import os
tmp = Path(artifact_path).with_suffix(Path(artifact_path).suffix + ".tmp")
tmp.write_text(json_data, encoding="utf-8")
os.replace(tmp, Path(artifact_path))
```

---

### WR-11: `_LABEL_INSERT_COLUMNS` の private API 跨 module 参照 + staging 再利用時の schema drift リスク

**File:** `src/etl/label_race_date_backfill.py:52,133-137,121-125`
**Issue:**

`from src.etl.fukusho_label import _LABEL_INSERT_COLUMNS` で private（`_` prefix）定数を跨 module import している。`_LABEL_INSERT_COLUMNS` は `_LABEL_TABLE_COLUMNS`（fukusho_label.py:880-912）から `c.split()[0]` で派生し、`race_date` は index 7。backfill は `cols_list = list(_LABEL_INSERT_COLUMNS)` で INSERT 列順序を fukusho_label 側に依存し、SELECT 側は `nr.race_date if c == "race_date" else fl.{c}` で位置整列する。

もし fukusho_label.py で `_LABEL_TABLE_COLUMNS` の列順序が変更された場合（例: `race_date` の位置が変わる、新しい列が追加される）、backfill の INSERT SELECT は位置ベースで整合する（cols_list と select_cols_sql を同順序で構築するため）が、**staging table の LIKE INCLUDING ALL で作成された既存 staging が再利用される場合**（`CREATE TABLE IF NOT EXISTS`）、列順序・型の drift が生じ得る。`TRUNCATE` は行を消すだけで schema は変えないため、fukusho_label 側で列追加されると staging は古い schema のまま残る。

加えて private API の cross-module import は保守性を下げる。

**Fix:**

1. `_LABEL_INSERT_COLUMNS` を public（`LABEL_INSERT_COLUMNS`）に昇格するか、backfill 側で列リストを明示的に持つ。
2. staging table を `DROP TABLE IF EXISTS ... _staging` を前段で発行してから `CREATE TABLE` で必ず新規作成する（schema drift を防ぐ）。`CREATE TABLE IF NOT EXISTS` は既存 staging があれば schema を更新しないため危険。

---

## Info

### IN-01: `_ROLLING_SYSTEMS` / `_ROLLING_SYSTEMS_FOR_RESERVED` の3重定義（rolling.py / availability.py / feature_availability.yaml）

**File:** `src/features/rolling.py:65-74`, `src/features/availability.py:131-140`, `src/config/feature_availability.yaml:56-363`
**Issue:**

rolling 系統リストが3箇所で個別に定義されている。`test_registry_rolling_systems_match_rolling_impl`（test_builder.py:220-246）が parity を検査する回帰テストを提供しているため drift は機械検出されるが、3重定義自体が DRY 違反。availability.py のコメント「循環依存を回避するため再定義」とあるが、rolling.py から availability.py は import 済み（`from src.features.availability import CUTOFF_SEMANTICS`）なため、循環依存回避の理由は弱い。

**Fix:** rolling.py を single source とし、availability.py は `from src.features.rolling import _ROLLING_SYSTEMS` で参照する。循環依存懸念は rolling.py が availability.py を import しつつ availability.py が rolling.py を import することで生じるが、機能的に availability.py のほうが primitive な定数層のため、`_ROLLING_SYSTEMS` を availability.py 側に統合するのが自然。

---

### IN-02: `_DEFAULT_CONFIG_PATH = Path("src/config/feature_availability.yaml")` が CWD 相対で壊れやすい

**File:** `src/features/availability.py:30`
**Issue:**

```python
_DEFAULT_CONFIG_PATH = Path("src/config/feature_availability.yaml")
```

CWD 依存。リポジトリルート以外から実行すると FileNotFoundError。`__file__` ベースの絶対 path にすべき。

**Fix:**
```python
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "feature_availability.yaml"
```

---

### IN-03: `snapshot.py` の `write_snapshot` が `created_at` 引数を受け取るが schema metadata には `_DETERMINISTIC_CREATED_AT` を埋め込み引数を無視

**File:** `src/features/snapshot.py:105-189`
**Issue:**

関数シグネチャ `created_at: str` 引数があるが、schema metadata 構築では `b"created_at": _DETERMINISTIC_CREATED_AT.encode()` で sentinel を使い、引数 `created_at` は schema metadata に使われない（return_manifest=True の場合のみ manifest の `created_at_fixed` に記録）。引数の役割が直感に反する。docstring には「schema metadata 埋込用の固定タイムスタンプ文字列」とあるが、実際には schema metadata には埋め込まれない。

**Fix:**

`created_at` 引数を `created_at_fixed` に rename し、役割を明示する（manifest の `created_at_fixed` 専用）。schema metadata には sentinel を使う意図を docstring で明記。

---

### IN-04: `conftest.py` の `_build_race_obs_row` が `as_of_datetime = race_date` を設定（実 builder は `race_start_datetime` を使う）

**File:** `tests/features/conftest.py:69-71`
**Issue:**

テスト fixture は `as_of_datetime = rd`（race_date の真夜中）を設定するが、実 builder（builder.py:220,382）は `as_of_datetime = race_start_datetime`（発走時刻）を使う。PIT フィルタの境界テストで `as_of_datetime` が使われるため、テストの `as_of_datetime` が実データと異なると境界判定が実運用と合わない可能性がある。現状の adversarial テストは同日除外を検証するため実害は無いが、テストと実装の不整合は分かりにくいバグを生む土壌。

**Fix:**

fixture の `as_of_datetime` を `rd + pd.Timedelta(hours=12)`（race_start_datetime と同値）に揃える。

---

### IN-05: `builder.py` の `make_race_nkey` docstring に `YYYYJJJKK< nichiji>NN` のレンダリング崩れ

**File:** `src/features/builder.py:178-179`
**Issue:**

```
``YYYYJJJKK< nichiji>NN`` で構築する。
```

`< nichiji>` の `< ` と `>` がレンダリング崩れ。`nichiji` は変数名だが backtick で囲まれていない。

**Fix:** ``` ``YYYYJJJKK{nichiji}NN`` ``` のように整形。

---

### IN-06: `test_snapshot_repro.py` の `test_persist_before_manifest_order` が `dict[str, dict]` を `FrozenCategoryMap` の代わりに渡す（型不一致）

**File:** `tests/features/test_snapshot_repro.py:144-148`
**Issue:**

```python
frozen_maps = {"jockey_id": {"jk001": 0, "jk002": 1}}
with pytest.raises(OSError):
    persist_category_maps(frozen_maps, unwriteable_map_path)
```

`persist_category_maps` のシグネチャは `maps: dict[str, FrozenCategoryMap]`。テストは `dict[str, dict[str, int]]` を渡す。実装は `dict(m.items())` を呼ぶため、`dict` も `.items()` を持つので偶然動作するが、型契約違反。`FrozenCategoryMap` インスタンスでないと `dict(m.items())` の戻り値型が変わる（FrozenCategoryMap.items は dict_items を返すが、plain dict も同じ）。動作はするが型安全性を損ねる。

**Fix:**

```python
from src.features.category_map_consumer import FrozenCategoryMap
frozen_maps = {"jockey_id": FrozenCategoryMap({"jk001": 0, "jk002": 1})}
```

---

_Reviewed: 2026-06-19T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
