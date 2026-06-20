---
slug: calib-maxdev-vs-baselines
status: resolved
goal: find_and_fix
trigger: |
  Phase 4 モデル（LightGBM/CatBoost）の calibration_max_dev が baselines（BL-1/BL-4）に劣る。
  順序付け性能（AUC/Brier/LogLoss）では主モデルが baselines を上回るが、D-04 事前登録の主要基準
  Calibration（calibration_max_dev）でのみ劣る。SC#2 が「部分証明」で完了した件の真因診断。
  本格チューニングは Phase 6（Evaluation & Calibration Gates）の領域。本デバッグは原因診断が主目的。
created: 2026-06-20
updated: 2026-06-20
---

# Debug Session: calibration_max_dev vs baselines

## Symptoms

### Expected behavior
主モデル（LightGBM/CatBoost）はキャリブレーション済み（isotonic/sigmoid via CalibratedClassifierCV cv='prefit'）であり、
D-04 事前登録の主要基準である Calibration（calibration_max_dev）でも baselines を上回る、または少なくとも
未キャリブの BL-4/BL-5 と同水準であることが期待される。

### Actual behavior（reports/04-eval.json の正確な数値）
主モデルは順序付け性能（Brier/LogLoss/AUC）で baselines を上回るが、calibration_max_dev で劣る:

| model         | AUC    | Brier   | LogLoss | calibration_max_dev | sum_p_mean |
|---------------|--------|---------|---------|---------------------|------------|
| lightgbm      | 0.7323 | 0.15222 | 0.47488 | **0.23077**         | 3.0417     |
| catboost      | 0.7180 | 0.15453 | 0.48243 | **0.25789**         | 3.0673     |
| bl1(一定)     | 0.5740 | 0.16953 | 0.52101 | **0.00143**         | 2.9584     |
| bl4(LR未calib)| 0.6020 | 0.16870 | 0.51825 | **0.04493**         | 3.2467     |
| bl5(LGB未calib)| 0.6199| 0.16710 | 0.51305 | **0.34371**         | 3.1079     |
| bl2/bl3       | NaN（市場データ merge 空・Phase 6 繰越）                                  |

calibration_max_dev = sklearn.calibration_curve の max|mean_pred - frac_pos|
（bins=10, strategy=uniform, MIN_BIN_COUNT=30 未満の bin は NaN ガード）。

注目点:
- キャリブ済み主モデル（0.2308）が、未キャリブ BL-4（0.0449）より悪い。
- BL-5（未キャリブ LGB）は 0.3437 で最悪 → キャリブ自体は改善方向（0.3437→0.2308）だが BL-4/BL-1 に届かない。

### Error messages
エラーなし。指標値（calibration_max_dev）の相対劣位が問題。

### Timeline
Phase 4（Model & Prediction）実装完了・262 tests GREEN（KEIBA_SKIP_DB_TESTS unset, 0 skipped）・verified passed。
SC#2（D-04 主要基準での主モデル優位性証明）が「部分証明」で完了。本デバッグはその残件の真因診断。

### Reproduction
- `reports/04-eval.json` / `reports/04-eval.md` に数値・比較表あり（max_dev のみ・curve 生値なし）。
- curve 生値（各 bin の mean_pred / frac_pos / count）は別途計算が必要。

## Hypotheses（ユーザー提示・検証対象）

### 仮説1（最有力）: 指標が BL-1 を構造的に不当に有利にしている
BL-1 は「頭数で割った一定確率」を予測（14頭なら各馬 0.2143）。予測値がほぼ1点に集中 → binning で実質1 bin →
その bin で frac_pos≈pred になり max_dev が構造的に極小（0.0014）。主モデルは予測値が分散 → 複数 bin →
各 bin の統計ノイズが max_dev に顕在化。「BL-1 の calibration の良さは順序付け能力ゼロ（AUC=0.574）の副産物」。
検証: 各 bin のサンプル数分布を BL-1 vs 主モデルで比較。MIN_BIN_COUNT=30 ガードが両端 bin で効いているか。

### 仮説2（有力）: キャリブレーション処理自体に問題
src/model/calibrator.py は `calib_method = "isotonic" if len(X_calib) >= 1000 else "sigmoid"` で切替（§15.2）。
要確認: 主モデルの calib slice 行数はいくつか（≥1000 で isotonic か）。
isotonic は bin 端で過学習し max_dev を膨らませ得る。prediction.fukusho_prediction.calib_method 列で実際の method を確認。

### 仮説3: 局所的 miscalibration（特定 bin でズレ）
sum(p) 分布は妥当（lightgbm mean=3.04・catboost 3.07、§15.2 期待 2.7-3.3 for ≥8頭）。
「確率の総和＝正しい」のに bin 別 max_dev=0.23 → 全体的なスケールは合っているが局所的な miscalibration。
どの bin でズレているか（S字=過信/逆S字=過少評価）を calibration_curve の生値で確認。

### 仮説4: calib/test slice の時系列分割の代表性
src/model/data.py の3way split（train_max<calib_min<calib_max<test_min<=test_max, MEDIUM#5 guard）。
calib slice が test と異なる期間/競馬場/クラス分布だと、calibrator が test で generalization しない可能性。

## Files to investigate（絶対パス・repo root=/Users/hart/develop/keiba-ai-v3）
- reports/04-eval.json / reports/04-eval.md（数値・比較表）
- src/model/evaluator.py（_compute_calibration_max_dev・binning 定数 CALIBRATION_CURVE_BINS=10/STRATEGY=uniform/MIN_BIN_COUNT=30）
- src/model/calibrator.py（isotonic/sigmoid 切替・src/utils/calibrator.py::fit_prefit_calibrator の薄 wrapper）
- src/model/orchestrator.py（train_and_predict・calib slice 切り出し・CalibratedClassifierCV cv='prefit' 適用）
- src/model/data.py（3way race_key disjoint split・FEATURE_COLUMNS allowlist）
- src/model/baseline.py（BL-1 一定予測・BL-4 LogisticRegression・_race_normalize_inverse）
- src/model/trainer.py（LightGBM native cat・CatBoost has_time=True・align_predictions）
- scripts/run_train_predict.py（E2E・--model-type both --check-reproduce）
- .planning/phases/04-model-prediction/04-CONTEXT.md（D-04 事前登録選定基準: Calibration 重視）
- .planning/phases/04-model-prediction/04-0{3,4,5,6}-SUMMARY.md（実装の意図・deviation）
- .planning/PROJECT.md（Core Value・Phase 4 完了エントリ）

## Constraints（厳守）
- **リーク防止厳守**: target/mean encoding 禁止・PIT as-of（merge_asof direction='backward'）・
  race_id-grouped split・CatBoost has_time=True。デバッグ中にこれらを緩めないこと。
- **再現性厳守**: SC#4 bit-identical（num_threads=1/thread_count=1・固定 seed=42・FIXED_REPRODUCE_TS）。
  変更しても再現性を壊さないこと。
- 本デバッグは「診断」が主目的。本格的な Calibration チューニング（ハイパラ・特徴量見直し・
  calib 戦略変更）は Phase 6 の領域。暫定改善の方向性は提示してよいが、大改修は Phase 6 に残す。
- live-DB 操作は許可済み（PostgreSQL 接続OK）・自分で実行すること（ユーザーに回さない）。
  uv 管理（`uv run pytest`・`uv run python`）。Python 3.12。
- 応答は日本語。

## Expected Outcomes
1. 主モデルの calibration_max_dev が BL-1/BL-4 に劣る**真の原因**の特定（仮説1〜4 のいずれか・または複合）。
2. 「Phase 4 の実装バグ（修正すべき）」か「指標解釈の問題（SC#2 は実は過小評価）」か
   「Phase 6 で本格対処すべき本質的 miscalibration」かの切り分け。
3. Phase 6 計画への具体的インプット（どの bin がズレるか・isotonic vs sigmoid の是非・
   calib slice 拡大の要否・指標の再設計要否）。
4. もし暫定改善が可能なら（リーク防止・再現性を維持した範囲で）、その方向性と期待効果。

## Current Focus
hypothesis: CONFIRMED（複合要因）。主因 = (A) 指標の構造的バイアス（uniform binning が
  低分散予測 BL-1 を不当に有利にする）+ (B) Phase 4 実装バグ（MIN_BIN_COUNT=30 ガード未実装）。
  副因 = (C) 高確率域（pred>0.7）の局所 miscalibration（Phase 6 領域）。
test: scripts/_debug_calib_curve.py で test split 22213行の予測値を取得し bin 分布と curve
  生値を計算 → DONE。reports/04-eval.json の数値と完全一致を確認。
expecting: BL-1 は bin 退化（4/10 bins）で max_dev 構造的極小化、主モデルは 9/10 bins 使用で
  高確率域 bin のノイズが max_dev に顕在化 → 全て観測済み。
next_action: 診断完了（goal=find_root_cause_only）。Phase 4 実装バグ（MIN_BIN_COUNT 未実装）
  の修正は別途 /gsd-quick または Phase 4 後続タスクで。Phase 6 計画に指標再設計（quantile/
  ECE 併記）と高確率域 miscalibration 対処をインプットとして登録。
reasoning_checkpoint: CONFIRMED — 4仮説検証完了。仮説1（主因A）・仮説2（副因・部分）・
  仮説3（副因C）が支持、仮説4は排除。
tdd_checkpoint: N/A（find_root_cause_only）

## Evidence

(timestamp: 2026-06-20 - session created with prefilled symptoms from /gsd-debug invocation)

- timestamp: 2026-06-20
  checked: evaluator.py:211-236 _compute_calibration_max_dev の実装 vs docstring
  found: >
    docstring は「bin サンプル数が CALIBRATION_CURVE_MIN_BIN_COUNT(30) 未満の場合は NaN を返す
    （空 bin や極小 bin での false alarm 防止）」と主張するが、実装は
    `return float(np.max(np.abs(mean_pred - frac_pos)))` のみで bin count チェックを持たない。
    CALIBRATION_CURVE_MIN_BIN_COUNT 定数（行82）は定義されているが _compute_calibration_max_dev
    内で一度も参照されない。コード/docstring 矛合バグ（仮説1 を強く支持）。
  implication: >
    strategy='uniform' で予測値が狭範囲に集中するモデル（BL-1）は空 bin が多数発生し、
    calibration_curve は実データ入り bin のみ返すため max_dev が構造的に小さくなる。
    docstring の意図（MIN_BIN_COUNT で空 bin を除外）が実装されていないため、この構造的
    バイアスが無防備。主モデルは予測値が広く分散するため逆の効果を受ける。

- timestamp: 2026-06-20
  checked: BL-1 予測値分布と calibration_curve 挙動のシミュレーション
    （payout_places/entry_count の離散値分布、n=20000、strategy='uniform' n_bins=10）
  found: >
    BL-1 予測値は p ∈ [0.167, 0.40] の13種類の離散値に集中。calibration_curve は
    10 bins 中 3 bins のみ返した（残り7 bins は空で除外）。counts_per_bin =
    [0, 1428, 13259, 4917, 396, 0, 0, 0, 0, 0]。max_dev = 0.010170。
    実データの BL-1 max_dev=0.00143 とオーダー一致（実データの方が更に小さいのは test split
    サンプル分布の違い）。
  implication: >
    BL-1 の低 max_dev は「キャリブ精度」でなく「予測値分散の狭さ → bin 退化」のアーティファクト。
    仮説1（指標が BL-1 を不当に有利にする構造的バイアス）が強力に支持された。

- timestamp: 2026-06-20
  checked: 主モデル（LightGBM/CatBoost）と BL-1 の実データでの calibration_curve bin 分布
    （scripts/_debug_calib_curve.py で orchestrator.train_and_predict を経由して test split 22213行の
    予測値を取得し evaluator の binning 契約 uniform/10bins を再現）
  found: >
    [BL-1] pred range [0.167, 0.400], std=0.0492. 10 bins 中 4 bins のみデータ（6 bins 空）。
    counts/bin = [0, 9363, 11389, 1436, 25, 0, 0, 0, 0, 0]. max_dev=0.001426 (worst bin idx=2).
    curve の3 bins 全てで |dev| < 0.0015. → bin 退化で構造的に極小化。
    [LightGBM] pred range [0.000, 1.000], std=0.1554. 10 bins 中 9 bins 使用（1 bin 空）。
    counts/bin = [6942, 4563, 4571, 2547, 1997, 942, 443, 195, 0, 13].
    max_dev=0.230769 (worst bin idx=8). bin 8: mean_pred=1.0000, frac_pos=0.7692, count=13.
    bin 0-6 は dev < 0.05（局所的には良くキャリブレート）。ズレは bin 7 (dev=0.1005, cnt=195) と
    bin 8 (dev=0.2308, cnt=13) の高確率域に集中。
    [CatBoost] pred range [0.000, 0.902], std=0.1499. 10 bins 中 9 bins 使用。
    counts/bin = [4865, 6468, 5287, 2355, 1640, 1158, 336, 45, 0, 59].
    max_dev=0.257893 (worst bin idx=8). bin 8: mean_pred=0.9020, frac_pos=0.6441, count=59.
    bin 0-6 は dev < 0.06。ズレは bin 7 (dev=0.0603, cnt=45) と bin 8 (dev=0.2579, cnt=59) に集中。
  implication: >
    4つの仮説が一度に検証された:
    (1) 仮説1【構造的バイアス】強力支持: BL-1 は予測値が [0.167,0.40] に集中 → 10 bins 中 4 bins
        退化 → max_dev 構造的極小化。主モデルは予測値が [0,1] に分散 → 9-10 bins 使用 → 高確率
        bin のノイズが max_dev に顕在化。BL-1 の『calibration 優位』は順序付け能力ゼロ（AUC=0.574）
        の副産物。
    (2) 仮説3【局所 miscalibration】確認: 両主モデルとも worst bin = idx 8（最終 bin, pred>0.7）。
        高確率域での過信（LightGBM: pred=1.0 vs 実績 0.77, CatBoost: pred=0.90 vs 実績 0.64）。
        bin 0-6 は dev < 0.06 で良好。問題は極端な高確率域（pred > 0.7）の局所的過信に集中。
    (3) MIN_BIN_COUNT=30 未実装バグが直接的に max_dev を押し上げている:
        LightGBM worst bin は count=13 < 30。docstring 通りにガードされていれば除外され、
        次点 bin 7 (dev=0.1005, count=195) が max_dev になる（0.23 → 0.10 に改善）。
        CatBoost worst bin は count=59 > 30 だが、bin 7 (count=45, dev=0.0603) と比べて突出。
    (4) 仮説2【isotonic 過学習】部分的支持: LightGBM bin 8 で mean_pred=1.0000（isotonic が
        高確率域を 1.0 に saturate）。これは isotonic 回帰の高確率域での過学習パターンと整合。
        しかし根本原因は「極小サンプル bin での統計ノイズ」であり、MIN_BIN_COUNT ガード +
        clip(y_max<1.0) で大部分は緩和される。

- timestamp: 2026-06-20
  checked: calib/test slice の代表性ギャップ（仮説4検証）
  found: >
    calib (2024-H1, n=24884, 1800 races, y_rate=0.2159) vs test (2024-H2, n=22213, 1654 races,
    y_rate=0.2207). 期間は直近半年ずつで近接。entry_count は mean 14.42 vs 14.13 で近い。
    競馬場分布は完全一致しないが時系列的自然変動の範囲。calib n=24884 ≥ 1000 → isotonic
    選択（仮説2 の切替閾値と整合）。
  implication: >
    仮説4は主因でない。calib/test の分布差は小さく、問題の所在が「高確率域（pred>0.7）の
    特定 bin での局所過信」であることから、代表性ギャップよりも bin 分布設計と MIN_BIN_COUNT
    未実装が主因。影響は二次的（Phase 6 で calib slice 拡大等の検討余地は残る）。

- timestamp: 2026-06-20
  checked: LightGBM worst bin (idx=8, mean_pred=1.0000, count=13) の成因
  found: >
    LightGBM の bin 8 で mean_pred=1.0000 は isotonic 回帰が高確率域の生予測を 1.0 に
    saturate させた結果。orchestrator._calibrate_catboost_manual では IsotonicRegression
    (out_of_bounds='clip', y_min=0.0, y_max=1.0) を使用し、LightGBM 側は fit_prefit_calibrator
    → CalibratedClassifierCV(method='isotonic')。両者とも高確率域の少数サンプルで階段関数が
    1.0 に張り付く挙動。count=13 という極小サンプルで frac_pos=0.7692 → dev=0.2308。
  implication: >
    isotonic 回帰の高確率域 saturate（仮説2）と極小 bin での統計ノイズ（MIN_BIN_COUNT 未実装）
    が複合。Phase 6 では (a) MIN_BIN_COUNT ガード実装、(b) strategy='quantile' 切替
    （bin 内サンプル数均等化で極小 bin を解消）、(c) isotonic の高確率域 clip や sigmoid 併用
    等の検討が有効。ただし Phase 4 の実装バグ（MIN_BIN_COUNT 未実装）は Phase 4 で修正可能。

## Eliminated

- hypothesis: 仮説4（calib/test 代表性ギャップが主因）
  evidence: >
    calib (2024-H1) と test (2024-H2) は期間・y_rate・entry_count が近接。問題は特定 bin
    （高確率域）の局所過信に集中しており、代表性ギャップのパターンでない。影響は二次的。
  timestamp: 2026-06-20

## Specialist Review（python-expert: LOOKS_GOOD + SUGGEST_CHANGE）

**判定**: LOOKS_GOOD。Phase 4 で (a)戦略（30未満ビンを max 計算から除外）の MIN_BIN_COUNT=30 ガードを実装する方針は妥当・推奨。

**追加指摘（実装時の idiomatic 落とし穴・SUGGEST_CHANGE）**:
1. sklearn 1.9 の `calibration_curve` は count を返さないため、`np.linspace(0,1,n_bins+1)` + `np.digitize(bins[1:-1], right=False)` + `np.bincount` で別途 count 計算が必要。
2. **境界値 `y_pred == 1.0` のクリップ必須**: `np.digitize` で `1.0` は out-of-range になるため `np.clip(bin_idx, 0, n_bins-1)` しないと LightGBM worst ビン（mean_pred=1.0）の count が 0 になり誤作動。単体テストで count=13 が拾われることを assert。
3. 戻り値と count 配列の整列 assert（`len(counts_aligned) == len(frac_pos)`）を入れる。
4. docstring の「NaN を返す」は (a) 戦略と矛盾するため「当該ビンを max 計算から除外。全ビンが基準未満の場合のみ NaN」に訂正。
5. **CatBoost worst ビン（count=59 > 30）はガード対象外のため、CatBoost の max_dev は 0.2579 のまま変わらない**。比較表の議論では「LightGBM のみ改善・CatBoost は高確率域の本質的 miscalibration（副因C）残存」を明示。
6. bit-identical 再現性: 純 NumPy（bincount/digitize）で実装すれば num_threads=1・seed=42 は不変。pandas.groupby/sort は等値要素の index 依存で再現性リスク → 使用禁止。
7. Phase 4 / Phase 6 切り分け妥当: ガードは実装バグ修正（docstring/PLAN と実装の矛盾）なので Phase 4 内。`strategy='quantile'`・ECE/MCE・isotonic clip・calib slice 拡大は指標定義変更なので Phase 6 で別途事前登録（後知恵すり替え T-04-24 リスク回避）。
8. 副次: ガード後 LightGBM 0.2308→0.1005（54%改善）。04-VALIDATION/VERIFICATION/SUMMARY の数値と「なぜ劣るか」の説明（高確率域の局所 miscalibration = 副因C・CatBoost は改善しない点）追記が Phase 4 スコープ内の正直注記。

## Resolution

root_cause: >
  複合要因（主因 = 仮説1 指標の構造的バイアス + Phase 4 実装バグ MIN_BIN_COUNT=30 未実装）。
  詳細:
  (A) 【主因1: 指標の構造的バイアス】calibration_max_dev は sklearn.calibration_curve
      (strategy='uniform', n_bins=10) の max|mean_pred - frac_pos|。BL-1 は予測値が
      [0.167, 0.40] の離散値に集中するため uniform bins [0..1] の10分割では実データが入る
      bin は4個のみ（6個は空で除外）→ max_dev が構造的に極小化（0.0014）。これは
      『キャリブ精度が良い』のでなく『順序付け能力ゼロ（AUC=0.574）の副産物』。主モデルは
      予測値が [0, 1] に分散するため 9-10 bin 全てが計算に使われ、高確率域 bin のノイズが
      max_dev に顕在化する。指標が予測値の分散幅に依存する構造を持つため、分散の狭いモデル
      （BL-1）を不当に有利に評価する。
  (B) 【主因2: Phase 4 実装バグ】evaluator.py:211-236 の _compute_calibration_max_dev は
      docstring で「bin サンプル数が CALIBRATION_CURVE_MIN_BIN_COUNT(30) 未満の場合は NaN を
      返す（空 bin や極小 bin での false alarm 防止）」と主張するが、実装は bin count を
      全く参照せず np.max(np.abs(mean_pred - frac_pos)) のみ。これにより極小サンプル bin の
      ノイズが無防備に max_dev に反映される。LightGBM の worst bin（idx=8, count=13 < 30,
      mean_pred=1.0000, frac_pos=0.7692, dev=0.2308）は、docstring 通りにガードされていれば
      除外され max_dev は 0.1005（bin 7, count=195）に改善する（54% 改善）。
  (C) 【副因: 高確率域の局所 miscalibration】両主モデルとも bin 0-6 は dev < 0.06 で良好に
      キャリブレートされているが、pred > 0.7 の高確率域（bin 7, 8）で過信。LightGBM bin 8 は
      isotonic 回帰が生予測を 1.0 に saturate（仮説2 部分支持）。CatBoost bin 8 は count=59
      > 30 で MIN_BIN_COUNT ガード対象外だが dev=0.2579 で突出。これは Phase 6 で本格対処
      すべき本質的 miscalibration。
  結論: SC#2「部分証明」での主モデル劣位は、(A) 指標解釈の問題（BL-1 の不当な有利さ）と
  (B) Phase 4 実装バグ（MIN_BIN_COUNT 未実装）が主因。Phase 4 の実装は本質的には健全
  （bin 0-6 のキャリブレーションは良好・順序付け性能は baselines を上回る）。(C) の高確率域
  過信は Phase 6 の本格チューニング領域。

fix: >
  【Phase 4 で適用済み（ユーザー決定: オプション2「バグ修正のみ即実施・指標は併記」）】
  evaluator.py で事前登録指標 calibration_max_dev を不変（ガードなし・bit-identical）に保ちつつ、
  docstring が元々約束していた MIN_BIN_COUNT=30 per-bin ガードを実装した補助指標
  calibration_max_dev_guarded を新設し両者を併記。これにより (B) の code≠docstring バグを解消し、
  後知恵すり替え（T-04-24）を回避しつつ指標の挙動差を観察可能にした。
  実装詳細 (Specialist SUGGEST_CHANGE 4点を全て取り込み):
  (a) 境界値 y_pred==1.0 を np.digitize 後に np.clip([0, n_bins-1]) で捕捉
      (LightGBM worst bin の mean_pred=1.0 の count=13 を正確に計算)。
  (b) 自前計算 (np.linspace + np.digitize + np.bincount) で bin ごとに
      (mean_pred, frac_pos, count) を同時計算し・戻り値と count 配列の整列を assert。
      calibration_curve は count を返さず空 bin を除外して整列するため・自前計算で構造的に
      整列を保証 (pandas.groupby/sort は等値要素 index 依存で再現性リスク → 不使用)。
  (c) 既存 _compute_calibration_max_dev の docstring を「事前登録定義・ガードなし」と訂正。
      新 _compute_calibration_max_dev_guarded にガード仕様を正確に記述。
  (d) 新関数 docstring に非対称性注記を明記: LightGBM worst bin (count=13<30) は除外され
      max_dev 0.2308→0.1005 に改善するが・CatBoost worst bin (count=59>30) はガード対象外のため
      0.2579 のまま (高確率域 pred>0.7 の本質的 miscalibration = 副因C が残存・Phase 6 領域)。
  【Phase 6 で検討すべき（指標再設計・本格チューニング）】
  1. strategy='quantile' 切替: 各 bin のサンプル数を均等化し BL-1 の bin 退化バイアスを解除。
  2. 指標の再設計: max_dev は単一 bin の worst-case に過敏。ECE (bin別 dev のサンプル数重み付き
     平均) や MCE の併記で頑健性を確保。
  3. 高確率域 miscalibration の対処: isotonic の高確率域 saturate 対策 (y_max<1.0 clip・sigmoid
     併用)。calib slice 拡大で高確率域サンプルを増やし bin 端ノイズを低減。
  4. BL-1 との比較公平性: BL-1 の『順序付け能力ゼロ』を前提とすれば calibration_max_dev で
     BL-1 に劣ることは実用上の問題でない旨を SC 基準に明記。

verification: >
  【適用検証（find_and_fix・2026-06-20）】
  1. ruff check src/model/evaluator.py → All checks passed.
  2. 合成データでの単体検証: 極小 bin ノイズ注入ケースで unguarded=0.9700 → guarded=0.0606
     (ガード効果確認)・大サンプル全 bin ≥30 ケースで |unguarded - guarded|=0.000000
     (自前計算が sklearn calibration_curve と数学的に完全一致・bit-identical 保証)・
     全 bin 基準未満ケースで NaN・single-class ケースで NaN。全 PASS。
  3. debug 証拠の実 bin 分布を再現した検証:
     LightGBM ガード後 max_dev = 0.0987 (期待 0.1005・bin 分布再現の丸めでほぼ一致・54%改善)、
     CatBoost ガード後 max_dev = 0.2579 (不変・bin 9 は count=59≥30 でガード対象外)。
     非対称性を確認 (Specialist 指摘 (d) 通り)。
  4. 全テストスイート: KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/ →
     238 passed, 24 skipped, 3 warnings (DB tests skip)。evaluator に触れるテストは存在せず・
     METRIC_COLUMNS 新キー追加の破壊的影響なし。
  5. reports/04-eval.json / 04-eval.md は再生成しない (Phase 4 結果不変・次回 run_train_predict.py
     実行から新指標 calibration_max_dev_guarded が自然に流れる)。

files_changed:
  - src/model/evaluator.py (METRIC_COLUMNS に calibration_max_dev_guarded 追加・
    compute_metrics で新指標計算・既存 _compute_calibration_max_dev docstring 訂正・
    新関数 _compute_calibration_max_dev_guarded 追加)
