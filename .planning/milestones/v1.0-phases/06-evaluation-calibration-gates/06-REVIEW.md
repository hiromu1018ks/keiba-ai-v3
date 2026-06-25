---
phase: 06-evaluation-calibration-gates
reviewed: 2026-06-24T00:00:00Z
depth: deep
files_reviewed: 16
files_reviewed_list:
  - reports/06-evaluation.json
  - reports/06-evaluation.md
  - scripts/run_apply_schema.py
  - scripts/run_evaluation.py
  - src/db/prediction_load.py
  - src/db/schema.py
  - src/model/evaluator.py
  - src/model/predict.py
  - src/model/segment_eval.py
  - tests/db/test_is_primary_flag.py
  - tests/model/test_evaluator_gate.py
  - tests/model/test_evaluator.py
  - tests/model/test_prediction_load.py
  - tests/model/test_run_evaluation.py
  - tests/model/test_segment_axis_columns.py
  - tests/model/test_segment_eval.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 6 Code Review Report（cycle 4 再確認）

**Reviewed:** 2026-06-24
**Depth:** deep（cross-file: import graph / call chain）
**Files Reviewed:** 16
**Status:** issues_found

## Summary

前回 cycle の Critical 4件（CR-01/CR-02/CR-03/CR-04）は**全て正しく修正完了**している。リーク防止聖域（§8.4/§13/§15）と監査性聖域（§19.1/SC#1/SC#2/EVAL-01）は維持されている。`set_primary_model` の post-condition fail-loud（REVIEW HIGH#7）は 8テストで実証済み・staging-swap idempotent load（review HIGH#1）も model_version scoped で他モデルを破壊しないことが検証されている。

ただし deep cross-file 解析で**1件の BLOCKER**（`fetch_market_data` の race_keys 引数無視による silent API 契約違反）と**6件の WARNING**（segment 軸欠損の silent skip・閾値根拠の循環参照・max_drawdown 集計方法の未明記等）を新たに発見した。意図的に未変更とされた WR-05/WR-10 の判断については妥当と判断する（別途記載）。

**前回 Critical 4件の修正検証結果:**
- **CR-01 (§8.4 race_id disjoint)**: `check_race_id_split_disjoint` で vacuous check 回避（両 split 非空で真検証・空は "N/A" + diagnostic_note + logger.warning）。`_fetch_split_integrity_df` で全 split を SELECT し test-only の vacuous True を回避。test_run_evaluation.py Test 9 で (a)disjoint=True / (b)leak=False / (c)空="N/A" の3ケース検証。**修正は正しく完全。**
- **CR-02 (sum_p_threshold_rationale)**: `generate_evaluation_reports` で `threshold_appropriate` により分岐（True: 偽陽性 BLOCK なし確認 / False: 閾値調整推奨）。実レポート `reports/06-evaluation.json` で `threshold_appropriate: false` が正直に記録され矛盾文言解消。**修正は正しく完全。**
- **CR-03 (hit_rate 重み付き平均)**: `aggregate_backtest_for_model` で `Σ(hit_rate_i × effective_bet_i) / Σ effective_bet_i` を実装。test_run_evaluation.py `test_aggregate_backtest_hit_rate_weighted_by_effective_bet` で単純平均 0.15 との差異を明示検証。**修正は正しく完全。**
- **CR-04 (_compute_ece 単一 bin 退化)**: `_compute_calibration_curve_bins` の `n_bins_actual<1` 分岐で全サンプル単一 bin を返すよう修正。test_evaluator.py `test_ece_single_bin_constant_predictions` で定数予測 p=0.8 / frac_pos=0.3 → ECE=0.5 を検証。**修正は正しく完全。**

## Structural Findings (fallow)

（本レビューは structural pre-pass なしで実施。以下は deep 解析中に発見された構造的事実。）

- `src/model/baseline.py::fetch_market_data` は `race_keys` 仮引数を受け取るが docstring の「指定された場合その race に絞る」に反して**実装では無視**。`run_evaluation.py::_fetch_market_data` が `race_keys=race_keys_for_market` を渡すが無視される。結果として全件取得 → 呼出側の LEFT JOIN で絞り込まれるため機能的には正しいが性能的には O(全件)。
- `src/model/evaluator.py::_compute_quantile_max_dev`（ガードなし worst-case）と `_compute_mce`（ガード付き worst-case）は strategy も同一（quantile デフォルト）のため名前重複の疑いあり。実装は分離されている（TEST 16 で検証）。

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `fetch_market_data` が `race_keys` 引数を無視（silent API 契約違反・§19.1 監査性）

**File:** `src/model/baseline.py:462-520`
**Issue:** `fetch_market_data(readonly_cur, race_keys=None, *, year=None)` は `race_keys` 仮引数を受け取るが、SQL の WHERE 句構築で `year` のみを使用し `race_keys` は**完全に無視**している。docstring（478-480行）には「指定された場合その race に絞る（正準 race_key = year-jyocd-kaiji-nichiji-racenum）」と明記されているため、API 契約違反（silent no-op）。

`scripts/run_evaluation.py::_fetch_market_data` はこの関数をラップし、明示的に `race_keys=race_keys_for_market` を渡すが無視される。`_fetch_market_data` 自身の docstring（`run_evaluation.py:270`）にも「race_keys フィルタは baseline 側で未実装のため無視（全件取得→呼出側で JOIN 時に絞り込まれる）」と**問題を認識しつつ放置**している記述がある。

影響:
1. **監査性（§19.1）**: 「race_keys で絞った market データを JOIN した」という仮定でレポート生成されるが、実際は全件 JOIN → LEFT JOIN で予測 race_key に属さない行が除外される。機能的には正しいが・実行計画と docstring の乖離は Phase 8 対抗的監査で誤解を招く。
2. **将来の regression 源**: `race_keys` 引数が「機能している」と誤認されたまま残るため、将来の呼出側が `race_keys` で絞れる前提でコードを書くと silent に全件取得される（例: memory 外爆発・timeout）。
3. **性能**: `raw_everydb2.n_odds_tanpuku` + `normalized.n_uma_race` の全期間 LEFT JOIN を実行。JRA 2015-2024 データでは数十万〜数百万行規模。`run_evaluation.py` の Step 1 が律速になる。※ 性能は v1 scope 外だが silent no-op な API 契約違反は監査性に直結。

**Fix:** 仮引数を削除して API 契約を正直化する（推奨）、または WHERE 句に `race_keys` フィルタを実装する。

```python
# 推奨: 仮引数削除で API 契約を正直化
def fetch_market_data(
    readonly_cur: Cursor,
    *,
    year: int | None = None,
) -> pd.DataFrame:
    """market データを全件取得する（race_keys 絞り込みは呼出側で LEFT JOIN で実施）。"""
    # ...実装は year のみ使用...
```

```python
# 代替: race_keys フィルタを実装（性能改善）
if race_keys:
    where_clauses.append(
        "(o.year || '-' || o.jyocd || '-' || o.kaiji || '-' || "
        "o.nichiji || '-' || o.racenum) = ANY(%s)"
    )
    params.append(list(race_keys))
```

## Warnings

### WR-01: segment 軸（ninki/fukuoddslower）欠損時の silent WARN skip（SC#3 部分達成の可能性）

**File:** `scripts/run_evaluation.py:1351-1360` / `src/model/segment_eval.py:340-348`
**Issue:** `main` 関数の WR-02 fail-loud は `jyocd/race_date`（label 由来 core カラム）のみを検査する。`ninki/fukuoddslower`（market 由来）は「部分欠損が正常系」として検査対象外。しかし market データが空（`fetch_market_data` が 0 行）または JOIN 失敗の場合、`evaluate_all_segments` は該当軸を `warnings.warn` で WARN skip し空 dict を返す。

結果として SC#3「6軸全て生成」が silent に 4軸（year/month/jyocd/entry_count）のみ達成される可能性がある。`segment_summary` に空 dict が含まれるため発見可能だが、`reports/06-evaluation.md` の「segment 安定性サマリ」テーブルでは `n_segments: 0` として表示されるだけで BLOCK されない。

実レポート（`reports/06-evaluation.json`）では `odds_band` が2 segment（`10+`/`__MISSING__`）で生成されており現状は問題ないが、`__MISSING__` が52サンプル（MIN_BIN_COUNT=30 を超える）で残留しているのは `fukuoddslower` NULL 行が多いことを示唆する（市場データ JOIN カバレッジが不完全）。

**Fix:** `main` で `ninki/fukuoddslower` の全面欠損（全行 NaN）を logger.warning 対象に追加するか、segment 評価後に期待軸数（6）と実際の非空軸数を比較して不足時は WARN を MD/JSON の目立つセクションに記録する。

```python
# scripts/run_evaluation.py main() の WR-02 拡張案
if len(prediction_df) > 0:
    _missing_market_seg = [
        c for c in ("ninki", "fukuoddslower")
        if c not in prediction_df.columns or prediction_df[c].isna().all()
    ]
    if _missing_market_seg:
        logger.warning(
            "market 由来 segment 軸が全面欠損: %s. SC#3 の ninki/odds_band 軸が WARN skip される",
            _missing_market_seg,
        )
```

### WR-02: `aggregate_backtest_for_model` で `max_drawdown` のみ max 集計（他は平均・集計方法の未明記）

**File:** `scripts/run_evaluation.py:564` / `run_evaluation.py:122-124`
**Issue:** 代表窓集計で `recovery_rate/hit_rate/profit_loss` は平均（`hit_rate` は CR-03 で effective_bet 重み付き平均）だが、`max_drawdown` のみ `max(int(r.get("max_DD", 0)))` で worst-case 最大値を取る。D-08 設計上の選択（max_drawdown は worst-case 指標のため max が意味的）だが、`reports/06-evaluation.md` の「backtest 集計方法（REVIEW C8）」注記は「優位 policy の代表窓（recovery_rate が高い方を代表）」としか書かず・max_drawdown だけ別集計であることを明記していない。

監査時に「代表窓の max_drawdown」と誤読されるリスクがある（実際は全窓の worst max_drawdown）。

**Fix:** `BACKTEST_AGGREGATION_METHOD` 注記に max_drawdown の集計方法を明記する。

```python
BACKTEST_AGGREGATION_METHOD = (
    "優位 policy の代表窓（30min_before/10min_before のうち recovery_rate が高い方を代表）。"
    "recovery_rate/hit_rate/profit_loss は代表窓の平均・max_drawdown のみ全窓の worst-case 最大値。"
)
```

### WR-03: `SUM_P_BLOCK_THRESHOLD` 定数コメントが実データと矛盾（循環参照）

**File:** `src/model/evaluator.py:106-110` / `reports/06-evaluation.json` notes.sum_p_threshold_rationale
**Issue:** `sum_p_measurement.diagnostic_note` と `notes.sum_p_threshold_rationale` は実データ `large_violation_rate=0.7139` / `small_violation_rate=0.7667` を正直に記録し `threshold_appropriate=False` を提示している（CR-02 修正で矛盾文言解消済み）。しかし `evaluator.py:108-109` の定数コメントには「REVIEW HIGH#5: 0.30 は仮置き・Plan 06-05 Wave 3 Step 3a で実データ violation_rate を計測し偽陽性 BLOCK を出さないか検証する。現データ LightGBM sum_p_mean=3.04 でほぼ 0% 想定」と書かれており・**実データ violation_rate（71-77%）と定数コメント（ほぼ 0% 想定）が矛盾**している。

これは「0.30 は安全網」という当初想定が実データで崩れた状態。BLOCK は D-02 AND 条件のため単独では発火せず機能的問題なし。しかし将来のデータで `baselines_all_lose=True` になった場合、`sum_p_violation=True` が高確率で成立するため BLOCK が頻発する可能性がある。

**Fix:** `evaluator.py:108-110` のコメントを実データに合わせて修正する。

```python
# SUM_P_BLOCK_THRESHOLD — D-02 構造的 BLOCK 条件2（sum(p) 著乖離）の閾値
# §15.2 [2.7,3.3]/[1.8,2.2] から 30% 超違反で BLOCK（large/small いずれかの bucket）
# REVIEW HIGH#5: 実データ（reports/06-evaluation.json）では violation_rate が
# large=71.4% / small=76.7% と閾値 0.30 を大幅超過。threshold_appropriate=False。
# 現状は D-02 AND 条件のため baselines_all_lose=False で BLOCK 非発火だが・
# 閾値調整（0.80 等）または sum(p) の WARN 専門化を Phase 8 で検討すること。
SUM_P_BLOCK_THRESHOLD: float = 0.30
```

### WR-04: `predict_p_fukusho` のデフォルト `datetime.now(timezone.utc)` が DB naive timestamp と潜在的不一致

**File:** `src/model/predict.py:252-255` / `src/db/prediction_load.py:419-444`
**Issue:** `predict_p_fukusho(as_of_datetime=None)` は `datetime.now(timezone.utc)`（tz-aware）を使う。DB カラムは `timestamp NOT NULL`（naive）。psycopg3 は tz-aware datetime を naive timestamp に挿入する際 UTC を仮定して truncate するため機能的には正しい。しかし `set_primary_model` の `_canonicalize_as_of_datetime` は「tzinfo が付いている場合は UTC に正規化せずそのまま返す」（docstring 429行）。

前回 cycle の WR-05（set_primary_model tz strip）は「Z 付き ISO8601 の WHERE 不一致は REVIEW HIGH#7 の 0行 RuntimeError（fail-loud）で防止済み」として**却下された**。この判断は妥当（CLI は `--as-of-datetime` required で明示的に ISO8601 文字列を渡すため問題ない）。ただし残余リスクとして `predict_p_fukusho(as_of_datetime=None)` を呼ぶ経路（例: `run_train_predict.py`）で tz-aware で格納された値と・後続の `set_primary_model` が文字列 `"2026-06-20T20:13:33.368966+00:00"` を渡した場合の比較で psycopg3/PostgreSQL のバージョン依存挙動が残る。

実レポート（`reports/06-evaluation.json`）の `as_of_datetime: "2026-06-20T20:13:33.368966"` は naive 表記で格納されており現状は問題ない。WR-05 却下判断を維持するが・`predict.py:253` の `datetime.now(timezone.utc)` を `datetime.utcnow()`（naive）に変更する方が defense-in-depth として安全。

**Fix:** （WR-05 却下を維持しつつ残余リスクを軽減する予防的修正）

```python
# src/model/predict.py:252-255
if as_of_datetime is None:
    # DB カラムは naive timestamp のため・tz-aware でなく naive UTC を格納する
    # （set_primary_model との一貫性・REVIEW HIGH#7 の 0行 UPDATE RuntimeError 予防の defense-in-depth）
    as_of_dt = datetime.utcnow()
else:
    as_of_dt = as_of_datetime
```

### WR-05: `prediction_is_primary_domain` CHECK 制約が boolean に対して vacuous（C16 注記済み・冗長性確認）

**File:** `src/db/schema.py:113-115`
**Issue:** `CHECK (is_primary IN (true, false))` は PostgreSQL の `boolean` 型に対して全ての有効な値（true/false）を許すため vacuous。NOT NULL 制約が実質的な NULL 拒否を担う（C16 注記済み）。この CHECK 制約は semantically 意味がない（boolean NULL を拒否したい場合は NOT NULL で十分）。

ただし「二重防御」という設計意図は理解できる（NOT NULL だけでは将来 ALTER で外された時の fallback）。`tests/db/test_is_primary_flag.py::test_is_primary_check_constraint` で CHECK 制約の存在を検証しているため削除すると該当テストが RED になる。

**Fix:** そのまま維持する（C16 注記通り二重防御）。追加修正不要。COMMENT ON COLUMN に「実質的な NULL 拒否は NOT NULL 制約が担う・CHECK は意味論的に冗長だが二重防御として保持」と既明記のため。

### WR-06: segment 評価の `seg_df` が lightgbm のみ（catboost の segment 安定性が未評価）

**File:** `scripts/run_evaluation.py:863-870`
**Issue:** `evaluate_integrated` の segment 評価は `main_pred_lightgbm` の test split のみを使用する。catboost が lightgbm より segment 安定性で優れる可能性を評価できない。D-04 事前登録では「Calibration 重視」で LightGBM を主モデルに選定したため実害はないが・SC#3「segment 別安定性評価」は本来両モデルで実施すべき。

実レポートでは LightGBM の segment のみ記録され・CatBoost の segment 安定性（例: 副因 C「高確率域 miscalibration」の segment 別確認）が抜け落ちている。`reports/06-evaluation.md` の bin 単調性 WARN 指標セクションでは両モデルの spearman_corr が併記されているため・単調性については両モデル比較可能だが・segment 別曲線/ scalar は LightGBM のみ。

**Fix:** （Phase 6 完了後の改善案）`seg_df` を両モデルでループ評価し `segment_summary` を `{axis: {lightgbm: {...}, catboost: {...}}}` 構造に拡張する。または少なくとも MD レポートに「CatBoost segment 評価は Phase 8 で追加予定」と明記する。

## Info

### IN-01: `reports/06-evaluation.md` の float 表示精度（6桁）で LightGBM/CatBoost 差が丸められる

**File:** `scripts/run_evaluation.py:1005` / `src/model/evaluator.py:160`
**Issue:** `_df_to_markdown_table` は `f"{v:.6f}"` で6桁表示。LightGBM brier=0.152216 と CatBoost brier=0.154529 の差は0.0023で6桁表示で十分識別可能。`calibration_max_dev` で LightGBM=0.230769 と CatBoost=0.257893 も表示上は明確。JSON 側は `0.23076923076923073` 等の高精度で保存されているため監査性は担保されている。MD の丸めは見やすさのため妥当。

**Fix:** なし（現状で妥当）。

### IN-02: `_compute_quantile_max_dev` と `_compute_mce` の命名類似（実装は分離されている）

**File:** `src/model/evaluator.py:506-523` / `557-594`
**Issue:** `_compute_quantile_max_dev`（ガードなし worst-case・strategy=quantile）と `_compute_mce`（ガード付き worst-case・strategy=quantile デフォルト）は名前が類似し混同しやすい。docstring で明確化されている（REVIEW C5）・test 16 で別実装性を検証済み。METRIC_COLUMNS_EXTENDED でも別列（`quantile_max_dev` と `mce`）。

**Fix:** なし（docstring + test で十分明確化されている）。

### IN-03: `run_apply_schema.py` の `--sql-file` 引数が未使用（ハードコード順序）

**File:** `scripts/run_apply_schema.py:160-167, 183-186`
**Issue:** `--sql-file` 引数（デフォルト `scripts/apply_schema.sql`）を読込むが・実際の `apply()` 関数は `sql_text` 引数を使わず `schema_module.APPLY_ORDER` と各定数をハードコード参照する。`--sql-file` の中身は無視される silent no-op（`sql_text = args.sql_file.read_text(encoding="utf-8")` で読込むが `apply()` に渡した後 `apply` 内では参照しない）。機能的には問題ない（schema.py が単一ソース）が・CLI 契約違反。

**Fix:** `--sql-file` 引数を削除するか、`apply()` で `sql_text` を実際に使用する（ファイルから読込んだ SQL を実行する）。

### IN-04: `evaluate_integrated` の try/except で segment 評価例外を広範 catch（silent 化リスク）

**File:** `scripts/run_evaluation.py:884-886`
**Issue:** `evaluate_all_segments` が例外を送出した場合 `except Exception as e: logger.warning(...)` で WARN skip し `segment_summary = {"error": str(e)}` を設定。広範 `Exception` catch は意図しないバグ（例: KeyError・TypeError・AttributeError）も silent にする可能性がある。

**Fix:** より狭い例外（`ValueError, KeyError`）に絞るか・例外種別によらず `segment_summary["error"]` を MD/JSON の目立つセクションに表示する。現状では MD の segment サマリで「segment 評価: {error}」と表示されるため発見可能。

---

## 前回指摘に対する判断（意図的に未変更）

### WR-05 (set_primary_model tz strip): 却下維持（妥当）
`_canonicalize_as_of_datetime` は tz 正規化しないが・CLI は `--as-of-datetime` required で ISO8601 文字列を明示的に渡すため問題ない。Z 付き ISO8601 で WHERE が不一致になる場合は REVIEW HIGH#7 post-condition（0行 UPDATE → RuntimeError）が fail-loud で検出するため silent no-op にはならない。本レビューの WR-04 は予防的 defense-in-depth 提案（機能的には既存判断で問題なし）。

### WR-10 (D-08 tiebreak 5%閾値): 却下維持（妥当）
`build_recommended_primary_model` は回収率が異なれば（差の大小に関わらず）回収率の大小で勝敗を決める。5%未満の僅差は `tiebreak_applied` フラグ（接戦だった旨の注記）だけで次基準へは飛ばさない。docstring（`run_evaluation.py:656-660`）で「回収率が第1基準として勝敗を決める・差の大小関わらず」と明記されており誤読防止済み。

---

_Reviewed: 2026-06-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
