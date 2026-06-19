---
phase: 03-as-of-features-snapshots
reviewed: 2026-06-19T05:01:43Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - src/features/rolling.py
  - src/features/availability.py
  - src/features/builder.py
  - src/features/category_map_consumer.py
  - src/config/feature_availability.yaml
  - scripts/run_feature_build.py
  - tests/features/test_rolling.py
  - tests/features/test_builder.py
  - tests/features/test_allowlist.py
  - tests/features/test_pit_cutoff.py
  - tests/features/test_running_style.py
  - tests/features/test_category_map_consumer.py
  - tests/features/conftest.py
findings:
  critical: 1
  warning: 6
  info: 5
  total: 12
status: issues_found
---

# Phase 3: Code Review Report（Gap-Closure 03-05 再レビュー）

**Reviewed:** 2026-06-19T05:01:43Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 3 plan 03-05 の 5 gap-closure（CR-01..CR-04 + WR-01）に対する再レビュー。修正対象となった 5 課題は概ね正しく閉じられている：

- **CR-01 (registry↔実体 parity)**: `rolling_timediff_*` / `rolling_babacd_*` 計6エントリが `feature_availability.yaml` / `rolling.py::_ROLLING_SYSTEMS` / `availability.py::_ROLLING_SYSTEMS_FOR_RESERVED` の3者から一貫して削除されており、`test_registry_rolling_systems_match_rolling_impl` / `test_no_timediff_babacd_in_registry_or_rolling` が3者一致と残存チェックを機械検証する。**CLOSED（正）**。
- **CR-02 (unfiltered JOIN leak)**: `_fetch_feature_sources` / `_fetch_history` の両 WHERE 句が `project_window_filter('ur') AND project_window_filter('nr')` を適用（builder.py:427, 477）。`test_fetch_history_and_feature_sources_filter_both_join_sides` が両関数で両側 filter を検証。**CLOSED（正）**。
- **CR-03 (fail-loud)**: `build_frozen_category_maps` が `race_date` 列欠損時に `ValueError` を raise（category_map_consumer.py:179-184）。`test_build_frozen_maps_raises_on_missing_race_date` が `pytest.raises(ValueError, match="race_date")` で検証。**CLOSED（正）**。
- **CR-04 (pickle ACE)**: `category_map_consumer.py` は `json.dumps(sort_keys=True)` / `json.loads` のみで永続化し、`import pickle` / `import joblib` / `__getstate__` / `__setstate__` は存在しない。`test_load_category_maps_does_not_use_joblib` が AST 解析で import/Call ノードを検査。**CLOSED（正）**。
- **WR-01 (look-ahead leak)**: `build_feature_matrix` Step 6 が `history.merge(obs_keys_style, on="kettonum")` 後に `expanded_style["as_of_datetime"] < expanded_style["feature_cutoff_datetime"]`（strict `<`・per-observation）を適用してから `groupby("kettonum")` する（builder.py:337-362）。意図通り closure している。

ただし WR-01 には **closure に見せかけた silent fallback 分岐** が残存しており（下記 WR-01'）、Phase 3 の Core Value（リーク防止・再現性）の観点からは完全には閉じていない。また `_fetch_feature_sources` / `_fetch_history` の exception swallow（CR-01 と同じ silent NaN 化の誘因）や、rolling `count` 軸の pandas 3.x 非推奨 API 等、gap-closure 外でも再現性/堅牢性を損なう残留不具合が存在する。Critical 1 件（category map artifact path/順序不整合による Phase 4 読込失敗）を含む。

---

## Critical Issues

### CR-01: persist_category_maps と manifest/category_map_artifact path の順序・解釈基準が不整合で Phase 4 読込を失敗させる

**File:** `scripts/run_feature_build.py:204, 206-223, 227-228`
**Issue:** `run_feature_build.py` は `category_map_artifact = f"snapshots/category_map_{args.snapshot_id}.json"`（相対パス・CWD 依存）を `write_manifest` に渡し（L204, L221）、その **後で** `persist_category_maps(frozen_maps, _SNAPSHOTS_DIR / f"category_map_{args.snapshot_id}.json")`（絶対パス `<repo>/snapshots/category_map_<id>.json`）で実ファイルを書出す（L227-228）。2つの問題がある：

1. **順序依存**: manifest 書出（L206）→ persist（L228）の順なので、persist が失敗（disk full / 権限 / encode error）しても manifest は完成済 SHA256 を含めて書かれ、`raw_touched=False / sha256=OK` なのに category map が欠損した再現性破壊状態が完成する。Phase 3 の Core Value「再現性」を直接損なう。
2. **path 解釈基準未定義**: manifest に記録された相対パス `snapshots/category_map_*.json` を Phase 4 モデルが `load_category_maps(manifest["category_map_artifact"])` で解決する際、CWD が repo-root で無ければ `FileNotFoundError`。manifest YAML に「repo-root 相対」か「絶対」かの表明が無い。

**Fix:**
```python
# persist を manifest 書出より先に実行し、path を絶対↔相対で一意に正規化
category_map_path = _SNAPSHOTS_DIR / f"category_map_{args.snapshot_id}.json"
persist_category_maps(frozen_maps, category_map_path)  # 先に永続化
# manifest には repo-root 相対の安定した表現で記録
category_map_artifact_rel = category_map_path.relative_to(_REPO_ROOT).as_posix()
# ...
write_manifest(..., category_map_artifact=category_map_artifact_rel, ...)
# 永続化直後に存在確認（fail-loud・D-13）
assert category_map_path.exists(), "category map artifact 書出失敗（再現性違反）"
```

---

## Warnings

### WR-01: WR-01 closure の silent no-filter fallback 分岐が残存（再リーク面）

**File:** `src/features/builder.py:347-354`
**Issue:** Step 6 で `if "as_of_datetime" in expanded_style.columns:` の `else` が `pit_filtered_style = expanded_style`（無 filter）に fall する。`build_feature_matrix` の通常経路では `_fetch_history` が必ず `as_of_datetime` を derive するので現状は到達不能だが、将来の refactor で `history` を直接 inject された場合（unit test の合成 history や Phase 4 の再構成 path 等）に silent に未来レースが推定脚質に混入する。WR-01 の intent は「`as_of_datetime` が無ければ未来情報の混入を許さない」であるべきで、現状は「`as_of_datetime` が無ければ filter を skip」になっている。回帰テスト `test_estimated_running_style_applies_pit_prefilter` は `build_feature_matrix` 本体を呼ばずに idiom を手動再現しているため、この else 分岐は機械的に検証されていない。

**Fix:**
```python
# as_of_datetime が無い場合は fail-loud（silent skip させない）
if "as_of_datetime" not in expanded_style.columns:
    raise ValueError(
        "build_feature_matrix Step 6: history に as_of_datetime が無い "
        "(estimated_running_style の PIT pre-filter を適用できない・WR-01)"
    )
pit_filtered_style = expanded_style[
    expanded_style["as_of_datetime"] < expanded_style["feature_cutoff_datetime"]
].copy()
```

### WR-02: _fetch_feature_sources / _fetch_history が例外を swallow して空 DataFrame を返す（CR-01 silent-NaN と同根）

**File:** `src/features/builder.py:455-457, 485-487`
**Issue:** 両関数が `except Exception as exc`（BLE001 抑制）で DB エラーを warn log のみ出して空 DataFrame を返す。`build_feature_matrix` は空 frame をそのまま継続し、`feature_matrix` が空（0行）または history 空となり、全 rolling/estimated_running_style が sentinel 扱い（`__MISSING__`）の 0行 or 全 NaN snapshot を SHA256 付きで書出してしまう。これは CR-01 が解消しようとした「silent NaN 化」と同じ失敗モードを DB 障害時にもたらす。再現性の観点で、DB 接続失敗を空データで上書きして manifest を完成させるのは危険（運用者が SHA256 一致を信用してしまい、データ 0件の snapshot で Phase 4 学習を試みる）。本番/CI で DB 未接続の正当ケースがあるなら `role='readonly'` の接続自体を lazy にするか、明示的な `allow_empty` 引数で制御すべき。

**Fix:** `build_feature_matrix` 側で空 frame を検出したら fail-loud にする。

```python
if len(feature_matrix) == 0:
    raise ValueError(
        "build_feature_matrix: observations 取得結果が空 "
        "(_fetch_feature_sources が DB 接続失敗で空 frame を返した可能性・D-13)"
    )
```

### WR-03: rolling の groupby().apply(lambda) が pandas 3.x で非推奨/将来 SHA256 変更リスク

**File:** `src/features/rolling.py:236-240`
**Issue:** `count_per_obs = recent_sys.groupby("obs_id")["_sys_value"].apply(lambda s: int(s.notna().sum())).to_dict()` は `SeriesGroupBy.apply` の非推奨形（pandas 3.x で `include_groups` デフォルト変更・`try_cast` 挙動変化）。現状は動くが、pandas 3.0.3（CLAUDE.md 推奨版）で `FutureWarning` が出力され、将来の pandas で count 列の挙動が変わると snapshot の SHA256 が変わり、SC#3 byte-reproducibility が破れる。同じ matrix を2回書出す SC#3 自己検証は「同一プロセス同一 pandas」なのでこの drift を検出できない（pandas upgrade 時に発覚する）。

**Fix:**
```python
# apply を使わず groupby().size() で vectorized（pandas 3.x safe）
n_per_obs = (
    recent_sys.dropna(subset=["_sys_value"])
    .groupby("obs_id", sort=False)
    .size()
)
count_per_obs = n_per_obs.to_dict()
```

### WR-04: rolling_sd_*_5 列が object dtype（float と `__MISSING__` 文字列混在）で Phase 4 LightGBM integration 事故の元

**File:** `src/features/rolling.py:174, 268-278`
**Issue:** `mean`/`latest` は `n>=1` で数値を入れるが、`sd` は `n<2` で `__MISSING__` 文字列 sentinel になる（Pitfall 3.3）。これは意図的だが、`result[col] = pd.Series([MISSING] * len(result), dtype=object, ...)` で初期化した object 列に float と `"__MISSING__"` 文字列が混在する。Phase 4 LightGBM がこの列を `category` dtype に cast する際、float 値と文字列 sentinel が同一 category 扱いになり、`__MISSING__` が pandas category code `-1`（CLAUDE.md §14.3 Negative-code hazard）に回るハザードがある。CR-04/HIGH #5 がカテゴリ ID 列について閉じたのに対し、rolling object 列は未対応。これは「リーク防止」ではないが、再現性/学習時 integration で事故の元。

**Fix:** sentinel を `MISSING` 文字列でなく `float("nan")` 等の数値 sentinel にするか、明示的に categorical として登録し Phase 4 で `__MISSING__` を非負 code に変換する工程を文書化・回帰テストする。

### WR-05: estimated_running_style が _CATEGORY_COLUMNS 対象外で `__MISSING__` sentinel が LightGBM -1 code に回る

**File:** `src/features/builder.py:363-367` / `src/features/category_map_consumer.py:48`
**Issue:** `estimated_running_style` は `"逃"/"先"/"差"/"追"` または `"__MISSING__"` を取る object dtype 列。registry は feature として登録するが、`_CATEGORY_COLUMNS = ("jockey_id","trainer_id","sire_id","bms_id","horse_id")` に対象外のため `_code` 化されず、生文字列のまま snapshot に乗る。Phase 4 LightGBM `category` dtype 変換時に `"__MISSING__"` が pandas category code `-1`（LightGBM 非負要件違反・CLAUDE.md §14.3 Negative-code hazard）になる。CR-04 / HIGH #5 は ID 列について閉じたが、この列は未対応で registry/検査をすり抜ける（`assert_matrix_columns_registered` は列名の subset 検査のみ・値域は見ない）。

**Fix:** `estimated_running_style` を `_CATEGORY_COLUMNS` に追加するか、Phase 4 学習時の `category` dtype 変換で `__MISSING__` を明示 sentinel カテゴリ（非負 code）に置換する工程を文書化・回帰テストする。

### WR-06: _construct_derived_columns の days_since_prev sort→reindex が index ラベルに暗黙依存

**File:** `src/features/builder.py:198-204`
**Issue:** `rd = pd.to_datetime(result["race_date"])` で元 index の Series を作り、`ordered = result.sort_values([...])` 後に `ordered["_rd"] = rd.loc[ordered.index]` で値を再添字し、最後に `result["days_since_prev"] = ordered["days_since_prev"].reindex(result.index)` で戻す。現状の呼出経路（`_fetch_history` で `pd.DataFrame(rows, columns=...)` 直後）では index は 0..N-1 で安全だが、関数が `df.reset_index(drop=True)` を前提としていることが docstring/コードから明示されていない。将来の refactor で呼出前に非 default index が入ると silent に rolling_days_since_prev がズレる（CR-01 と同じ silent-NaN の兄弟）。

**Fix:** 関数冒頭で `result = df.reset_index(drop=True).copy()` を明示し、sort/reindex が index ラベル非依存であることを表明。

---

## Info

### IN-01: trackcd / course_kubun が registry に登録されているが builder が生成しない

**File:** `src/config/feature_availability.yaml:121-134` / `src/features/builder.py:74-112`
**Issue:** registry に `trackcd` と `course_kubun`（共に `source_table: raw_everydb2.n_race`）が feature として登録されているが、`_OBS_DB_SELECT_COLUMNS` / `_HISTORY_DB_SELECT_COLUMNS` のいずれにも含まれず、builder は生成しない。`assert_matrix_columns_registered` は出力側 subset 検査のみなので失敗しないが、CR-01 のテーマ（registry↔実体 parity）と同じ亀裂が静かに存在する。Phase 3.1 での再登録対象か、明示的な削除/延期マーカーが必要。

### IN-02: rolling docstring の「8系統」と実体「6系統」の表記揺れ

**File:** `src/features/rolling.py:90, 112, 131`
**Issue:** docstring が「8系統 × 3軸 (mean/latest/sd) + count 軸」「5. 8系統全てに3軸」「(8系統 × 4 = 32) 列」と書いているが、実体の `_ROLLING_SYSTEMS` は 6 系統（CR-01 で timediff/babacd 削除後）。docstring が削除前の数字のままで、読者を誤導する。CR-01 closure の一部として docstring も更新すべきだった。

### IN-03: make_race_nkey が文字列 zfill に依存し jyocd/kaiji 等の型契約が docstring に無い

**File:** `src/features/builder.py:154-160`
**Issue:** `jyocd.astype(str).str.zfill(2)` 等で複合キーを構築。jyocd が `"05"`（文字列）の場合も int `5` の場合も zfill(2) で同一結果になるが、`project_window_filter` の `jyocd BETWEEN '01' AND '10'` は文字列比較を前提とし、`make_race_nkey` と filter の間で jyocd 表現（int vs str）の暗黙契約に依存している。DB カラム型・cursor 返り値型の明示契約が docstring に無く、将来の schema 変更で silent に壊れる余地がある。

### IN-04: test_no_registered_feature_column_all_nan_end_to_end が build_feature_matrix 本体を通さず thin wrapper 呼出

**File:** `tests/features/test_builder.py:155`
**Issue:** CR-01 回帰テストは `builder.build_rolling_features(observations, history)`（thin wrapper・Step 5 経由で `build_feature_matrix` 全体を通さない）を呼ぶ。真の end-to-end（`build_feature_matrix` → `_fetch_history` → rolling 統合 → `assert_matrix_columns_registered`）を通すと、`_fetch_history` が `_construct_derived_columns(with_days_since_prev=True)` を経由するため、`days_since_prev` derived 列の silent 欠損も検出できる。現状は合成 history に `days_since_prev` を直接入れているため derived path の silent 欠損は検出不能。テストの意図（CR-01 regression）は達成されるが、「end-to-end」の命名と実体が一致しない。

### IN-05: jyocd が registry feature と _RESERVED_NON_FEATURE_COLUMNS の二重登録

**File:** `src/features/availability.py:147, 159` / `src/config/feature_availability.yaml:107`
**Issue:** `_RESERVED_NON_FEATURE_COLUMNS` に `"jyocd"` と `{f"rolling_{sys}_count_5" for sys in _ROLLING_SYSTEMS_FOR_RESERVED}` が含まれる。`jyocd` は registry features にも登録されている（YAML L107）。`allowed = registry | reserved` の和集合なので機能上問題無いが、registry にも reserved にも同じ名前が入る構造は可読性を下げ、将来の refactor で reserved 側だけ外れた時に silent に許可状態が変わる。コメントで意図（管理列としての jyocd と feature としての jyocd の両面）を明示すべき。

---

_Reviewed: 2026-06-19T05:01:43Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
