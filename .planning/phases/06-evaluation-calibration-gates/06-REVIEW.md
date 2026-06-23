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
  critical: 4
  warning: 11
  info: 6
  total: 21
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-06-24
**Depth:** deep
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Phase 6（評価 / キャリブレーション / 受入ゲート層）を deep depth でレビューした。
`evaluator.py` / `segment_eval.py` の binning 契約の一元化・bit-identical 保証、
staging-swap idempotent load、CHECK 制約+NOT NULL による is_primary migration、
PSQL identifier quote を通じた SQL injection 防御など、坚强に設計された部分が多い。

しかし §8.4（race_id disjoint 聖域）の検査が実運用データで vacuous になる重大な不整合
（`n_train_races=0` で "N/A" に落ちる）や、`reports/06-evaluation.json` の注記文言が
`threshold_appropriate=False` の実データと直接矛盾する問題、`hit_rate` 集約が
SC#1/EVAL-01 で要求される正しい的中率（分母 = 仮想購買馬数）でなく代表窓単純平均に
なっている点など、**聖域（再現性・リーク防止・監査性）に関わる BLOCKER が4件**見つかった。
加えて、`_fetch_market_data` の `race_keys` フィルタが無視され market 全件 SELECT になる
性能・正確性リスク、二重 JOIN による segment 軸補完のフォールバック欠陥など WARNING 11件。

最優先で対応すべきは CR-01〜CR-04（実データ上の §8.4 検査回避・矛盾文言・
`hit_rate` 集約定義・`_compute_ece` の定義逸脱）。

## Critical Issues

### CR-01: §8.4 race_id split disjoint 検査が実データで vacuous ("N/A") に陥る聖域回避

**File:** `scripts/run_evaluation.py:285-304`, `reports/06-evaluation.json`
**Issue:**
`_fetch_split_integrity_df` は `prediction.fukusho_prediction WHERE split IN ('train','val','test')`
を SELECT するが、実際の `reports/06-evaluation.json` を見ると:

```
"reproducibility_checks": {
  "n_test_races": 1654,
  "n_train_races": 0,
  "race_id_split_disjoint": "N/A",
  "split_diagnostic_note": "split データ不足（train または test が空）・Phase 4 GroupTimeSeriesSplit 担保・REVIEW N3 cycle-3 vacuous check 回避"
}
```

`n_train_races=0` のため `check_race_id_split_disjoint` は "N/A" を返し、
§8.4「同一 race_id が train/test をまたがない」の聖域検証が**実質何も検査していない状態**
で report に記録されている。これは `reports/06-evaluation.md` の"race_id split integrity
（§8.4 聖域）"セクションが読者に聖域が確認されたと誤認させる監査性違反（T-06-04/T-06-05）。
REVIEW N3 の「vacuous check 回避」ロジック自体はtest-only 読込を防ぐ目的だったが、
**train/val 行が DB に入っていない場合には同じ vacuous 状態になる本質的穴**が残っている。

Phase 4 で生成された prediction の `split` 列が実際に train/val 行を含んでいない
（test のみ INSERT されている）可能性があり、これは Phase 4 の予測永続化が
test split しか DB に書いていない設計に起因する。Phase 6 の聖域検査は
その前提に依存しているため、predction テーブルが test-only の場合には
**検査自体が不能化**する。

**Fix:**
1. `main()` で `n_train_races == 0` の場合は RuntimeError で fail-loud にする
   （聖域が検査不能なら出荷停止すべき）:
```python
# Step 2-4 完了後、REPORT 生成 *前* に聖域検査の実効性を検証
rep = result["gate_result"].get("reproducibility_checks", {})
if rep.get("race_id_split_disjoint") == "N/A":
    logger.error(
        "race_id split integrity 検査が vacuous (N/A): "
        "prediction.fukusho_prediction に train/val split 行が存在しない・"
        "§8.4 聖域検査が実質機能していない"
    )
    raise RuntimeError(
        "race_id_split_disjoint=N/A: §8.4 聖域検査不能。"
        "Phase 4 で train/val split の予測も永続化するか、"
        "feature snapshot 側から race_key を再構築して検証すること"
    )
```
2. または `_fetch_split_integrity_df` を feature snapshot / label テーブル側の
   split 情報から race_key を再構築する経路に切り替える（prediction テーブルへの
   依存をやめる）。

### CR-02: `notes.sum_p_threshold_rationale` 文言が `threshold_appropriate=False` の実データと矛盾

**File:** `scripts/run_evaluation.py:1099-1104`, `reports/06-evaluation.json`
**Issue:**
`generate_evaluation_reports` は固定テキストで注記を埋める:

```python
"sum_p_threshold_rationale": (
    f"SUM_P_BLOCK_THRESHOLD={SUM_P_BLOCK_THRESHOLD} は仮置き・"
    "現データ violation_rate 実測で偽陽性 BLOCK を出さないか検証済み"
    f"（threshold_appropriate={sum_p_measurement['threshold_appropriate']}）"
),
```

しかし `reports/06-evaluation.json` の実データは:

```json
"sum_p_measurement": {
  "large_violation_rate": 0.7139272271016311,
  "small_violation_rate": 0.7666666666666667,
  "threshold_appropriate": false
}
```

`threshold_appropriate=False`（= 閾値 0.30 を現データが超過し偽陽性 BLOCK リスクあり）
にも関わらず、注記は「偽陽性 BLOCK を出さないか検証済み」と宣言している。
これは §19.1 監査性の観点で**読者に誤った結論（閾値が適切である）を与える**
情報開示違反。同じレポートの `sum_p_measurement.diagnostic_note` は
「閾値 0.30 を超過・閾値調整を検討」と正しく出ているため、レポート内で
注記が相互矛盾している。md 側（line 83）も同一の矛盾文言を含む。

**Fix:**
`threshold_appropriate` の値で分岐して注記を切り替える:

```python
if sum_p_measurement['threshold_appropriate']:
    rationale = (
        f"SUM_P_BLOCK_THRESHOLD={SUM_P_BLOCK_THRESHOLD} は仮置き・"
        "現データ violation_rate 実測で偽陽性 BLOCK を出さないことを確認済み"
        f"（threshold_appropriate=True）"
    )
else:
    rationale = (
        f"SUM_P_BLOCK_THRESHOLD={SUM_P_BLOCK_THRESHOLD} が現データの "
        f"violation_rate (large={large_rate:.1%}, small={small_rate:.1%}) より低く・"
        "偽陽性 BLOCK になりうる。閾値の引き上げ（0.30→0.80 等）を検討するか・"
        "sum(p) 診断の前提（独立二値確率で厳密合計でない）を注記に明記すること"
        f"（threshold_appropriate=False）"
    )
```

### CR-03: `hit_rate` 集約が SC#1/EVAL-01 の正しい複勝的中率（分母=仮想購買馬数）でない

**File:** `scripts/run_evaluation.py:543`, `reports/06-evaluation.json`
**Issue:**
`aggregate_backtest_for_model` は:

```python
# SC#1/EVAL-01 複勝的中率: representatives の hit_rate 単純平均
hit_rate = sum(float(r.get("hit_rate", 0.0)) for r in representatives) / n
```

と、各 backtest 窓の代表 policy の `hit_rate` を**単純平均**している。しかし
正しい複勝的中率は「全仮想購買馬のうち複勝払戻対象に入った馬の割合」であり、
分母は `effective_bet`（実際に購買が成立した馬数）の総和、分子は的中本数の
総和でなければならない:

```
hit_rate_correct = sum(命中本数 for 窓) / sum(effective_bet for 窓)
```

レースあたり購買馬数にバラツキがある場合、単純平均は正しい的中率と一致しない
（例: 窓 A が 1000 件中 100 的中=10%、窓 B が 100 件中 5 的中=5% の場合、
正解は 105/1100≈9.5%、本実装は (10+5)/2=7.5%）。

`reports/06-evaluation.json` の `backtest_summary.by_model.lightgbm.hit_rate=0.0918748369`
は「5窓の代表 policy の hit_rate 単純平均」であり、SC#1/EVAL-01 の受入基準として
提示する数値としては不正確。test (`test_run_evaluation_backtest_integration`) は
synthetic fixture で `hit_rate=0.09` の均一データを使っているためこの bug を検知しない。

**Fix:**
`src/ev/metrics.py` で計算済みの hit 本数と effective_bet を `reports/05-backtest.json`
から取得し、重み付き平均を計算する。もし `05-backtest.json` の各行に hit 本数
（`hits` / `n_hits`）が無ければ、それを先に Phase 5 側で永続化する:

```python
# 正しい重み付け平均（分母 = 全代表窓の effective_bet 総和）
total_effective_bet = sum(int(r.get("effective_bet", 0)) for r in representatives)
total_hits = sum(int(r.get("hits", 0)) for r in representatives)  # 05-backtest.json 側で hits 列を追加
if total_effective_bet > 0:
    hit_rate = total_hits / total_effective_bet
else:
    hit_rate = 0.0
```

### CR-04: `_compute_ece` が「空 bin のみなら NaN」と仕様書の一方で、single-bin 退化時にゼロ割れ未防護の経路あり

**File:** `src/model/evaluator.py:512-540`
**Issue:**
`_compute_ece` は:

```python
n_total = float(len(y_pred))
devs = np.abs(bins["frac_pos"] - bins["mean_pred"])
return float(np.sum(bins["counts"] / n_total * devs))
```

`_compute_calibration_curve_bins` は空 bin を除外した non-empty bin のみ返すため、
`n_total = len(y_pred)` は全サンプル数（空 bin 含む前の総数）だが、
`bins["counts"]` は non-empty bin のみ。これ自体は正しい（ECE = Σ n_m/N × |dev|）。

しかし `_compute_calibration_curve_bins` の `strategy='quantile'` で
`np.unique(np.quantile(...))` が単一の edge を返した場合、`n_bins_actual = 0` に
なり空配列を返す経路がある（line 442-449）。その場合 `_compute_ece` は
`len(bins["counts"]) == 0` で NaN を返す（line 536-537）。

問題は、**`_compute_ece` の docstring は「single-class の場合は定義不可・NaN」と
書いているが single-bin（non-empty bin が1つだけ・全予測値が同値）の場合も
NaN になる**点。single-bin の場合は frac_pos=mean_pred=全体の positive rate に
なり ECE=0 と定義できるはずだが、現実装は空配列を返すため ECE=NaN になる。
これは segment 評価で BL-1 のような極端な離散値（4種類のみ）を含む segment で
ECE が全て NaN になるという silent な情報欠損を生む（reports/06-evaluation.json の
`segment_summary.entry_count.6.0` の scalar が全て null になる経路の1つ）。

加えて、`_compute_ece` は docstring に「Naeini 2015・重み付け平均」と書きつつ、
test_evaluator.py の `test_ece_weighted_average` で ECE=0.2 を期待する手計算と
`abs(ece_miscal - 0.2) < 0.02` しか検証しておらず、bit-identical 性が担保されて
いない（0.02 の許容差は大きすぎ）。

**Fix:**
single-bin の場合も ECE を計算する（non-empty bin が1つなら frac_pos と mean_pred
は共に全体平均になり dev=0、ECE=0）:

```python
def _compute_ece(y_true, y_pred, *, strategy="quantile", n_bins=CALIBRATION_CURVE_BINS):
    if len(np.unique(y_true)) < 2:
        return float("nan")
    bins = _compute_calibration_curve_bins(y_true, y_pred, strategy=strategy, n_bins=n_bins)
    if len(bins["counts"]) == 0:
        return float("nan")
    # single-bin の場合は frac_pos==mean_pred になり ECE=0
    if len(bins["counts"]) == 1:
        return 0.0  # または float(np.abs(bins["frac_pos"][0] - bins["mean_pred"][0]))
    n_total = float(len(y_pred))
    devs = np.abs(bins["frac_pos"] - bins["mean_pred"])
    return float(np.sum(bins["counts"] / n_total * devs))
```

## Warnings

### WR-01: `_fetch_market_data` に渡した `race_keys` が無視され market 全件 SELECT になる

**File:** `scripts/run_evaluation.py:261-282, 1290-1295`
**Issue:**
`main()` は `race_keys_for_market = prediction_df["race_key"].dropna().unique().tolist()`
を計算して `_fetch_market_data(cur, race_keys=race_keys_for_market)` を呼ぶが、
`_fetch_market_data` の実装は:

```python
def _fetch_market_data(cur, race_keys=None):
    from src.model.baseline import fetch_market_data
    df = fetch_market_data(cur, race_keys=None)  # race_keys 未実装のため無視
```

`fetch_market_data(cur, race_keys=None)` は全件 SELECT になる（WHERE 句無し）。
`raw_everydb2.n_odds_tanpuku` は JRA 全レース × 全馬の複勝オッズで数百万行に達する
可能性があり、本番実行時のメモリ膨張・実行時間悪化のリスク。docstring にも
「race_keys 未実装のため無視」と書かれており、呼出側が意図せず全件ロードしている。

**Fix:**
`fetch_market_data` に `race_keys` IN-clause フィルタを実装するか、`year` 引数で
対象年を絞る（prediction の `year` 列から動的に取得）:

```python
# 最低限の対策: year で絞る
years = sorted(prediction_df["year"].unique().tolist())
market_dfs = []
for y in years:
    market_dfs.append(fetch_market_data(cur, year=int(y)))
market_df = pd.concat(market_dfs, ignore_index=True)
```

### WR-02: `_enrich_prediction_with_segments` と `_merge_prediction_with_label` の二重 JOIN 構造で market_df が `evaluate_integrated` に伝播しない

**File:** `scripts/run_evaluation.py:312-371, 691-909, 1302`
**Issue:**
`main()` のフロー:

1. `_fetch_prediction_test_df` → prediction_df（segment 軸なし）
2. `_fetch_label_df` → label_df
3. `_fetch_market_data` → market_df
4. `_enrich_prediction_with_segments(prediction_df, label_df, market_df)` →
   segment 軸付き prediction_df（label/market 両方から ninki/fukuoddslower を JOIN）
5. `evaluate_integrated(prediction_df=...)` を呼出 → 内部で `_merge_prediction_with_label(prediction_df, label_df)` を呼ぶ

しかし `evaluate_integrated` に `market_df` は渡っておらず、`_merge_prediction_with_label`
が segment 軸不足を検出した場合の market 由来フォールバック経路が存在しない。
合成テスト（`test_run_evaluation.py`）は `_make_synthetic_eval_inputs` で
元から segment 軸を含む prediction_df を作るため、この経路の欠陥を検知しない。
本番で prediction に ninki/fukuoddslower が付与されなかった場合
（例: market JOIN が空だった）、segment 評価が WARN skip になり SC#3 履行不能に
silent に陥るリスク。

**Fix:**
`evaluate_integrated` に `market_df` 引数を追加し、`_merge_prediction_with_label`
内で segment 軸不足時に market JOIN を試行するフォールバックを実装する。
または `_enrich_prediction_with_segments` の戻り値を検査し、segment 軸が
付与されなかった場合は RuntimeError で fail-loud にする:

```python
# main() 内・_enrich_prediction_with_segments 後
required_seg_cols = ["ninki", "fukuoddslower", "entry_count", "jyocd", "race_date"]
missing_seg = [c for c in required_seg_cols if c not in prediction_df.columns or prediction_df[c].isna().all()]
if missing_seg:
    raise RuntimeError(
        f"segment 軸が prediction_df に付与されなかった: missing={missing_seg}. "
        "label.fukusho_label / market データ JOIN の経路確認が必要"
    )
```

### WR-03: `_fetch_split_integrity_df` の `DISTINCT` で race_key が潰れても race_id の重複は検出できるが、split 毎の件数確認が不十分

**File:** `scripts/run_evaluation.py:285-304`
**Issue:**
`_fetch_split_integrity_df` は `DISTINCT year, jyocd, kaiji, nichiji, racenum, split`
を SELECT するが、これは race 単位の split 帰属を検出できる。しかし:
- 同一 race が train にも test にも INSERT されている場合、`DISTINCT` で
  同一 (race_key, split='train') と (race_key, split='test') の2行が残り、
  `check_race_id_split_disjoint` の `train_races & test_races` で検出可能
- だが prediction.fukusho_prediction 側で split ラベル付けミス
  （例: 同一 race の馬毎に別 split を振る）は race_key 単位の DISTINCT で
  潰れるため検出できない

より堅牢な検証は「馬単位 (race_key, umaban) で GROUP BY race_key, split を取り
1 race が複数 split にまたがる race_key を抽出」すること。

**Fix:**
`_fetch_split_integrity_df` を馬単位 SELECT に変更し、
`check_race_id_split_disjoint` で「1 race 内の split 一意性」も検証する:

```sql
SELECT year, jyocd, kaiji, nichiji, racenum, umaban, split
FROM prediction.fukusho_prediction
WHERE feature_snapshot_id = %s AND split IN ('train', 'val', 'test')
```

`check_race_id_split_disjoint` 内で `race_key → set(splits)` を作り、
複数 split を持つ race_key があれば RuntimeError（馬単位の split 帰属性違反）。

### WR-04: `aggregate_backtest_for_model` の `profit_loss` 切捨て除算で端数が累積誤差になる

**File:** `scripts/run_evaluation.py:538`
**Issue:**
```python
profit_loss = sum(int(r.get("P/L", 0)) for r in representatives) // n
```

`// n`（切捨て除算）で代表窓の平均 P/L を計算している。例えば
3窓で P/L = [-100, -101, -102] の場合、和は -303、`//3` で -101 になるが
正しい平均は -101.0（整数化すると -101）。結果は一致するが、P/L が負の場合
Python の `//` は負の無限大方向に切り捨てる（-303 // 3 = -101、正しい）。
しかし P/L = [-100, -101, -103] の場合は -304 // 3 = -102（真値 -101.33）で
1 単位の誤差。これは `reports/06-evaluation.json` の `profit_loss` が
実データと一致しない監査性リスク（§19.1）。

`recovery_rate` は浮動小数で計算しているのに `profit_loss` だけ整数除算なのも一貫性がない。

**Fix:**
```python
profit_loss = sum(int(r.get("P/L", 0)) for r in representatives) / n  # float
# または
profit_loss = round(sum(int(r.get("P/L", 0)) for r in representatives) / n)
```

### WR-05: `set_primary_model` post-condition で `as_of_datetime` timezone 不一致による silent no-op リスク

**File:** `src/db/prediction_load.py:419-440, 494-557`
**Issue:**
`_canonicalize_as_of_datetime` は ISO8601 文字列 → `pd.Timestamp(...).to_pydatetime()`
で変換する。`pd.Timestamp("2026-06-20T00:00:00Z")` は timezone-aware datetime を返す。
一方 DB の `as_of_datetime timestamp`（naive timestamp）に格納されている場合、
WHERE 句での一致が tz-aware vs tz-naive で失敗する可能性がある。
test `test_canonicalize_as_of_datetime_accepts_str_datetime_timestamp` は
naive な `datetime(2026,6,23,12,0,0)` で assertion しているが、Z 付き ISO8601
（`"2026-06-20T00:00:00Z"`）を渡した場合は tzinfo=UTC が付く。

`reports/06-evaluation.json` の `primary_model.as_of_datetime` は
`"2026-06-20T20:13:33.368966"`（naive・Z 無し）で格納されている。CLI から
`--as-of-datetime 2026-06-20T20:13:33.368966Z`（Z 付き）を渡すと、
`pd.Timestamp(...).to_pydatetime()` は tzinfo=UTC を付け、DB の naive timestamp
とは一致しなくなり `set_primary_model` の Step 2 が 0 行 UPDATE で RuntimeError。
これは REVIEW HIGH#7 が防ごうとしていた silent no-op の再発経路。

**Fix:**
`_canonicalize_as_of_datetime` で tzinfo を常に stripping する（DB が naive の場合）:

```python
def _canonicalize_as_of_datetime(as_of_datetime: Any) -> datetime:
    if isinstance(as_of_datetime, datetime):
        dt = as_of_datetime
    elif isinstance(as_of_datetime, pd.Timestamp):
        dt = as_of_datetime.to_pydatetime()
    elif isinstance(as_of_datetime, str):
        dt = pd.Timestamp(as_of_datetime).to_pydatetime()
    else:
        raise TypeError(...)
    # DB 側が naive timestamp の場合は UTC tzinfo を除去（REVIEW HIGH#7 二重防御）
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt
```

### WR-06: `evaluator._df_to_markdown_table` が `pd.NA` を `nan` 文字列で出力し Markdown が人間に読めない

**File:** `src/model/evaluator.py:141-164`, `reports/06-evaluation.md:48-54`
**Issue:**
`_df_to_markdown_table` は `pd.isna(v)` の場合 `"nan"` を cell 値にする。
`reports/06-evaluation.md` の主モデル比較表を見ると、BL-2/BL-3 行や baselines の
`bt_*` 列が全て `nan` で埋まり、人間が読むレポートとして視認性が悪い
（JSON 側は null なので問題ないが md は nan）。
更に `float(v):.6f` でフォーマットするため、大きな数値（例: 回収率 0.702153）
も6桁固定になり、読みにくい。

**Fix:**
md 用フォーマットを JSON と同様に null 化（`"nan"` → `"-"`）し、
数値は意味のある桁数に丸める:

```python
if isinstance(v, float):
    if pd.isna(v):
        cells.append("-")
    elif abs(v) < 1:
        cells.append(f"{v:.4f}")  # 確率・率
    else:
        cells.append(f"{v:.1f}")  # P/L 等の整数値
```

### WR-07: `evaluate_all_segments` で `np.array([pd.isna(v) for v in seg_arr], dtype=bool)` が非 scalar 値で TypeError

**File:** `src/model/segment_eval.py:219`
**Issue:**
```python
nan_mask = np.array([pd.isna(v) for v in seg_arr], dtype=bool)
```

`seg_arr = np.asarray(segment_values, dtype=object)` で object 配列を回すが、
seg_val が list や dict のような非 scalar の場合 `pd.isna(v)` は配列を返し
`bool()` で曖昧度エラーになる。現実のデータでは segment_values は文字列 or int なので
発火しないが、防御的でない。特に `entry_count` 軸で `np.float64` の NaN が
入った場合の挙動も標準パスと一貫性を確認すべき。

**Fix:**
`pd.isna` を scalar 強制で使う:

```python
def _is_scalar_nan(v) -> bool:
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False

nan_mask = np.array([_is_scalar_nan(v) for v in seg_arr], dtype=bool)
```

### WR-08: `evaluate_segment_axis` で single-class segment の scalar が NaN になるが、`_compute_ece`/`_compute_mce` が呼ばれない経路があり結果の一貫性が崩れる

**File:** `src/model/segment_eval.py:251-268`
**Issue:**
`evaluate_segment_axis` は:

```python
if len(np.unique(y_t_seg)) < 2:
    ece_q = float("nan")
    ece_u = float("nan")
    mce_g = float("nan")
    max_dev_g = float("nan")
else:
    ece_q = float(_compute_ece(...))
    ...
    max_dev_g = float(_compute_calibration_max_dev_guarded(...))
```

この single-class 分岐は正しいが、curve の方は single-class でも
`_compute_calibration_curve_bins` を呼んでおり、bins が1つだけ返る場合に
mean_pred/frac_pos が1要素の list になる。scalar NaN と curve リストの
整合性が取れず、`reports/06-segments/*.json` の一部 segment で scalar が null
なのに curve が空でないリスト、という不整合が生じうる。

**Fix:**
single-class の場合は curve も空リストに統一する:

```python
if len(np.unique(y_t_seg)) < 2:
    mean_pred_list = []
    frac_pos_list = []
    count_list = []
    ece_q = ece_u = mce_g = max_dev_g = float("nan")
else:
    bins = _compute_calibration_curve_bins(...)
    ...
```

### WR-09: `_merge_prediction_with_label` で `fukusho_hit_validated.fillna(fukusho_hit)` が valid 値の上書きを許す

**File:** `scripts/run_evaluation.py:413-414`
**Issue:**
```python
if "fukusho_hit_validated" in merged.columns and "fukusho_hit" in merged.columns:
    merged["fukusho_hit"] = merged["fukusho_hit_validated"].fillna(merged["fukusho_hit"])
```

意図は「fukusho_hit_validated を正とし、欠損時は fukusho_hit で補完」。
しかし `fillna` は validated 列が NaN の位置だけ fukusho_hit で埋めるため、
**validated が NaN だが fukusho_hit に誤った値（0/1）が入っている場合は
誤った値が残る**。label 側の validated=True/False/NaN の3状態を正しく扱えていない。
特に `fukusho_hit_validated` が validation 未実施で NaN の場合、
元の `fukusho_hit`（推定値）が正として採用され、§15.1 の評価が推定ラベルで
実行される silent リスク。

**Fix:**
`fukusho_hit_validated` が NaN の行は評価対象外にするか、明示的に記録する:

```python
if "fukusho_hit_validated" in merged.columns:
    unvalidated_mask = merged["fukusho_hit_validated"].isna()
    if unvalidated_mask.any():
        logger.warning(
            "fukusho_hit_validated が %d 行 NaN・これらは評価の真ラベルとして信頼性低",
            int(unvalidated_mask.sum())
        )
    merged["fukusho_hit"] = merged["fukusho_hit_validated"]
```

### WR-10: `build_recommended_primary_model` の tiebreak[1] で 5% 未満の僅差を「tiebreak 発火」とするが、その後の tiebreak[2] に進まない

**File:** `scripts/run_evaluation.py:622-650`
**Issue:**
```python
if _recovery(a) != _recovery(b):
    winner = a if _recovery(a) > _recovery(b) else b
    reason = ...
    if abs(_recovery(a) - _recovery(b)) < 0.05:
        tiebreak_applied = "backtest_recovery_rate"
    return {...}
```

`_recovery(a) != _recovery(b)` の場合、僅差（<0.05）でも recovery_rate の大小で
winner を決定して return する。D-08 の意図は「5% 未満の僅差は同点と見なし、
次の tiebreak（compute_cost_lightgbm_first）に進む」はずだが、現実装は
僅差でも recovery_rate で勝者を決めてしまう。これは D-08 タイブレーク順序の
誤実装。`reports/06-evaluation.json` の LightGBM vs CatBoost の recovery_rate
差は 0.7022-0.6808=0.0214（<5%）で、本来なら tiebreak[2] の LightGBM 優先に
進むべきだが、現実装は tiebreak[1] で LightGBM を選んでいる（結果は同じだが
理由の記録が D-08 と矛盾）。

**Fix:**
5% 未満の僅差は同点扱いで tiebreak[2] に進む:

```python
if abs(_recovery(a) - _recovery(b)) >= 0.05:
    winner = a if _recovery(a) > _recovery(b) else b
    return {
        "model_type": winner,
        "selection_reason": f"D-08 tiebreak[1] backtest_recovery_rate: {winner} ...",
        "tiebreak_applied": "backtest_recovery_rate",
        "priority_order": list(TIEBREAK_PRIORITY_ORDER),
    }
# 5% 未満の僅差は同点扱い → tiebreak[2] へ
```

### WR-11: `reports/06-evaluation.md` の segment サマリの segments 表示が最初の5件切捨てで全体が分からない

**File:** `scripts/run_evaluation.py:1218-1226`
**Issue:**
```python
md_lines.append(
    f"| {axis} | {data.get('n_segments', 0)} | "
    f"{', '.join(segs[:5])}{'...' if len(segs) > 5 else ''} |\n"
)
```

`entry_count` 軸は13 segment あるが md では最初の5件しか表示されない。
`n_segments=13` と書いてあっても何が含まれているか人間には分からず、
監査性が不十分（§19.1）。JSON 側は全 segment を含むので md の短縮は許容できるが、
少なくとも axis 毎に別行か YAML block 形式で全 segment を出すべき。

**Fix:**
md では改行区切りで全 segment を表示:

```python
md_lines.append(
    f"| {axis} | {data.get('n_segments', 0)} | "
    f"{', '.join(segs)} |\n"
)
```

## Info

### IN-01: `evaluator.py` の `_df_to_markdown_table` と `run_evaluation.py` の `_df_to_markdown_table` が重複実装

**File:** `src/model/evaluator.py:141-164`, `scripts/run_evaluation.py:951-971`
**Issue:**
同一ロジックの `_df_to_markdown_table` が2箇所に定義されている。
共通ユーティリティ（`src/model/artifact.py` 等）に切り出すべき。

**Fix:** 共通ヘルパに統合。

### IN-02: `_sanitize_nan_to_null` が segment_eval.py と run_evaluation.py で重複実装

**File:** `src/model/segment_eval.py:94-112`, `scripts/run_evaluation.py:929-948`
**Issue:**
同一関数が2箇所に定義。`src/model/artifact.py` 等に統合すべき。

**Fix:** 共通ヘルパに切り出し。

### IN-03: `_build_comparison_table_with_backmetrictable` は DEPRECATED alias だが実コード参照が残る可能性

**File:** `scripts/run_evaluation.py:1252-1254`
**Issue:**
typo 付きの DEPRECATED alias。呼出元が無いか grep 確認推奨。テストでも
使われていないため削除可能。

**Fix:** 削除。

### IN-04: `evaluator.compute_metrics` の `race_keys=None` 時 sum_p が NaN になるが、segment 評価では race_key 無しで計算する箇所がある

**File:** `src/model/evaluator.py:223`, `src/model/segment_eval.py:166-285`
**Issue:**
`evaluate_segment_axis` は `race_keys` を `compute_metrics` に渡さないため、
segment 毎の sum_p 統計が計算されない。これは仕様（segment は calibration curve 中心）
だが、segment 毎の sum_p 適合度検査ができないと §15.3 の segment 別品質検査が不完全。

**Fix:** 仕様注記に明記するか、オプションで sum_p も segment 計算する拡張。

### IN-05: `reports/06-evaluation.md` の注記セクションがN行に1行の長文で読みにくい

**File:** `reports/06-evaluation.md:84`
**Issue:**
`SC2_BLOCK_SYMMETRY_NOTE` が1行に長文で md 上折り返しが効かない。
md の場合は適度に改行を入れるか、箇条書きに展開すべき。

**Fix:** md 用にフォーマット済みテキストを生成する。

### IN-06: `tests/model/test_run_evaluation.py` の synthetic fixture が BL-3 を含まず、SC#2 対称性検査が不完全

**File:** `tests/model/test_run_evaluation.py:113-127`
**Issue:**
`_make_synthetic_eval_inputs` の metrics_04 は lightgbm/catboost/bl1/bl4/bl5 のみで
bl2/bl3 を含まない。SC#2「beat all baselines」の対称性検査は BL-3（市場暗示確率）を
含めてこそ意味があるため、テストカバレッジが不十分。

**Fix:** bl2/bl3 も synthetic metrics に追加する。

---

_Reviewed: 2026-06-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
