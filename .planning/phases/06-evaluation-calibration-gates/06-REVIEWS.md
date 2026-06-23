---
phase: 06
reviewers: [codex, claude]
reviewed_at: 2026-06-23T05:29:42Z
plans_reviewed:
  - 06-01-PLAN.md
  - 06-02-PLAN.md
  - 06-03-PLAN.md
  - 06-04-PLAN.md
  - 06-05-PLAN.md
cycle: 1
---

# Cross-AI Plan Review — Phase 6 (Evaluation & Calibration Gates)

> 初回レビューサイクル。Codex（OpenAI）と Claude（Anthropic・別セッション）の2システムが独立に同一プロンプト（PROJECT.md / ROADMAP / CONTEXT.md / RESEARCH.md / 5つの PLAN.md）をレビュー。下記は各レビューの原文と、共通懸念のコンセンサスサマリ。深刻度（HIGH/MEDIUM/LOW）は各レビュアーの判定をそのまま掲載。

---

## Codex Review

### Summary

全体として、Phase 6 の計画は Core Value（リーク防止・再現性）を強く意識しており、Wave 分割、D-04 事前登録指標の不変維持、D-01/D-02/D-03 の hybrid gate、segment 安定性、`is_primary` の provenance 設計までかなり具体化されています。特に「評価専用フェーズ」としてモデル再学習・予測再生成を避ける方針は妥当です。一方で、計画内にいくつか重大な矛盾があります。最大の懸念は、Wave 1 の依存関係が自己矛盾していること、`check_acceptance_gate` の D-02 実装が「baselines 全敗 + sum(p) 著乖離」の AND 条件ではなく OR 条件になっていること、Plan 06-01 の DB カラム確認テストが欠損時に PASS する設計で D-12 の前提検証として弱いことです。これらを直さないと、SC#2/SC#3 の達成判定が実際より甘くなるリスクがあります。

### Strengths

- Phase 6 を評価専用に限定し、Phase 4 SC#4 bit-identical を壊さない方針が一貫している。
- D-04 の `calibration_max_dev` 不変維持と、quantile/ECE/MCE の併記追加が明確に分離されている。
- `y_pred==1.0`、single-class、quantile duplicate edges、MIN_BIN_COUNT など既知エッジケースをテスト対象に含めている。
- `is_primary` を行削除ではなくフラグ更新にし、両モデル行を保持する設計は再現性・監査性に合う。
- `selection_reason` / `tiebreak_applied` をレポートに残す設計は、後知恵すり替えリスクの低減に有効。
- Plotly HTML と JSON の二重成果物は、Phase 7 の Streamlit 消費と単体確認の両方に対応している。
- `reports/06-evaluation.json` を `sort_keys=True` で byte-reproducible にする方針は良い。
- BLOCK と WARN の分離は、Core Value と D-03 の「曖昧基準を過機械化しない」に整合している。

### Concerns

- **HIGH — D-02 の BLOCK 条件が AND ではなく OR 実装になっている。**
  仕様では「baselines 全敗 + sum(p) 著乖離」の両方を満たす構造的破綻が BLOCK ですが、Plan 06-02 の `check_acceptance_gate` は baselines 全敗だけ、または sum(p) violation だけで `block_triggered=True` にしています。これはユーザー決定 D-02 と矛盾します。

- **HIGH — Plan 06-03 は Plan 06-02 の関数に依存しているのに、Wave 1 並列可能とされている。**
  06-03 は `_compute_calibration_curve_bins`, `_compute_ece`, `_compute_mce` を import する前提です。これらは 06-02 で追加されるため、06-03 は 06-02 完了後にすべきです。ROADMAP の「02/03 並列可能」と PLAN の実装内容が食い違っています。

- **HIGH — Plan 06-01 の segment 軸確認テストが、欠損時に PASS する設計になっている。**
  `ninki` / `fukuoddslower` などが欠損しても「WARN メッセージ付き PASS」とされており、Open Question #1 の解決になりません。D-12「6軸全て生成」の前提検証なら、代替カラムを確定できない場合は fail-loud すべきです。

- **HIGH — `is_primary` migration の CHECK 制約テストが PostgreSQL boolean 型と噛み合っていない。**
  `is_primary=2` の INSERT は CHECK 以前に型変換で失敗します。また boolean は基本的に true/false/null しか取れないため `CHECK (is_primary IN (true, false))` は NULL を許す限り実質的な価値が薄いです。`NOT NULL DEFAULT false` にするか、NULL 許容の意図を明文化すべきです。

- **HIGH — Plan 06-04 の `set_primary_model` は選定対象が 0 行でも成功してしまう。**
  `UPDATE ... true` の affected rows が 0 でも検知しない計画です。model_version や `as_of_datetime` 指定ミスで全行 false になり、主モデルなしの状態を作るリスクがあります。これは Phase 7 表示と D-09 に直結します。

- **HIGH — Plan 06-05 の実行順で、BLOCK 発火時に report が残らない可能性がある。**
  `check_acceptance_gate` 後に RuntimeError を投げる設計ですが、fail-loud は良い一方、原因確認用の `reports/06-evaluation.{md,json}` が出力されない可能性があります。BLOCK 時も最低限の gate report は atomic write してから raise する方が運用上安全です。

- **MEDIUM — `calibration_max_dev_report_value_match` が reports/04-eval.json 自身の値を読み、その同じ値と比較するだけなら回帰固定にならない。**
  計画文では「reports/04-eval.json を直接読込して assert」とありますが、固定リテラル値と比較しなければ意味が薄いです。compute 再計算値との一致を検証するなら入力データも必要です。

- **MEDIUM — `quantile_max_dev` と `mce` が同一値として二重定義されている。**
  D-05 の「quantile max_dev + ECE + MCE」は理解できますが、計画では `quantile_max_dev = _compute_mce(strategy='quantile')`、`mce` も quantile default になっており、列が重複指標になります。MCE を uniform guarded にするのか、quantile MCE と明記するのか定義を固定すべきです。

- **MEDIUM — `compute_metrics` の既存出力拡張が downstream の `METRIC_COLUMNS` / `build_comparison_table` と整合するか曖昧。**
  `METRIC_COLUMNS_EXTENDED` を追加する一方、既存 `build_comparison_table` は変更しないと書かれている箇所があります。Plan 06-05 で比較表に新指標を入れるなら、どの関数が拡張列を使うか明確にすべきです。

- **MEDIUM — `sum(p)` violation_rate 閾値 0.30 の根拠が弱い。**
  安全網としては理解できますが、受け入れ基準に直結する定数です。`constants` と notes に根拠、対象 bucket、`>` か `>=` を明記し、テスト名と実装表現を一致させる必要があります。

- **MEDIUM — タイブレーク規則が「省略時は自動適用」と「省略時は is_primary 更新スキップ」で揺れている。**
  D-08 は決定的タイブレークで1つ選ぶ方針ですが、Plan 06-05 では `--primary-model` 省略時は reports のみ生成を推奨しています。人間判断優先ならそれで良いですが、D-08 の発火条件と CLI 挙動を再整理すべきです。

- **MEDIUM — `as_of_datetime` スコープが文字列/ timestamp の厳密性に触れられていない。**
  `set_primary_model` の WHERE 条件に使うため、timezone・microsecond・文字列表現差で 0 行更新になるリスクがあります。DB 型に合わせた parse と canonical format が必要です。

- **MEDIUM — JOIN 契約が race_id ではなく 7カラム race_key で、重複検知はあるが train/test race_id またぎ禁止の再検証が薄い。**
  Phase 6 は評価専用とはいえ、§8.4 の聖域に近いので `split` ごとの `race_id`/race_key disjoint 確認を gate report に含めるとより堅いです。

- **MEDIUM — Segment 評価で欠損軸を WARN skip すると SC#3 達成が曖昧になる。**
  欠損時も 6軸キーを空 dict で返すと、成果物上は「生成された」ように見えます。D-12 は全6軸なので、欠損軸は Phase 6 完了条件では fail または human-blocking にすべきです。

- **MEDIUM — Plotly HTML 12ファイル、合計 ~18MB の肥大を受容しているが、テストで `>1_000_000 bytes` を要求するのは脆い。**
  Plotly のバージョンや出力設定でサイズが変動します。自己完結性は `"Plotly.newPlot"` や include script の存在で検証する方が安定します。

- **MEDIUM — `test_is_primary_default_false` が live DB の既存行すべて false を仮定しており、再実行性に弱い。**
  一度 Plan 06-05 で主モデル確定した後は true 行が存在するため、このテストは失敗します。テスト専用スコープの synthetic rows で検証すべきです。

- **LOW — `scipy` を推移依存前提にしている。**
  実際には sklearn 依存で入る可能性が高いですが、直接 import するなら明示依存にする方が lockfile の意図が明確です。

- **LOW — `tests/model/__init__.py` / `tests/db/__init__.py` の必要性が薄い。**
  害は小さいですが、既存 tests 構成に package marker が不要なら追加しない方がメタデータ churn を抑えられます。

- **LOW — `Reports` を plan 実装の files_modified に含めているが、実データ依存成果物は環境差が出やすい。**
  `reports/06-*` をコミット対象にするのか、生成物として扱うのかを明確にした方が良いです。

### Suggestions

- `check_acceptance_gate` の BLOCK 判定を D-02 通りに修正する。
  `baselines_all_lose AND sum_p_structural_violation` の組み合わせでのみ `BLOCK`、片方だけなら `WARN` にする。

- Wave 構成を修正する。
  06-03 は 06-02 に依存させるか、06-03 側で 06-02 の未実装関数に依存しない contract stub 方式に変える。現計画なら Wave 1 は 06-02、Wave 2 は 06-03 + 06-04、Wave 3 は 06-05 が自然です。

- Plan 06-01 の segment カラム確認は欠損時に fail-loud へ変更する。
  代替カラムを発見できた場合のみ PASS、未解決なら FAIL または checkpoint:human-verify にしてください。

- `set_primary_model` に rowcount 検証を入れる。
  選定モデル更新が 0 行なら RuntimeError、対象スコープに複数 model_type がない場合も RuntimeError、更新後に `true` が選定モデルのみであることを検証すると安全です。

- `is_primary` は `boolean NOT NULL DEFAULT false` を推奨する。
  予測生成時に DataFrame では `None` でも、load 時に false に正規化すれば DB 状態が単純になります。

- `as_of_datetime` は CLI で parse して DB 型に合わせる。
  ISO8601 文字列をそのまま WHERE に渡すのではなく、timezone と precision を canonical 化してください。

- `quantile_max_dev` / `ece` / `mce` の定義表を PLAN に追加する。
  例: `quantile_max_dev = quantile bins + guarded max dev`, `ece_quantile = quantile bins weighted avg`, `mce_uniform_guarded` など、列名と strategy を一致させる。

- BLOCK 時も最小 report を出力してから RuntimeError にする。
  CI では fail しつつ、`block_reasons`、対象 model、sum(p) violation_rate を artifact に残せます。

- `reports/04-eval.json` 固定値テストは、固定リテラル比較または再計算比較にする。
  JSON を読んで同じ JSON の値と比べるだけのテストは削除した方が良いです。

- Segment HTML は必要なら `include_plotlyjs="directory"` や代表軸のみ self-contained を検討する。
  D-10 が self-contained を絶対要求していないなら、12ファイルで plotly.js 重複を避けられます。要求するなら現状のままでよいですが、サイズテストは緩めるべきです。

- acceptance report に race_key/race_id split integrity を入れる。
  Phase 6 が評価専用でも、§8.4 の「race_id train/test またぎ禁止」は SC#2 より上位の信頼条件なので、少なくとも検査結果を `gate_result.reproducibility_checks` に含めるとよいです。

- `--primary-model` 省略時の挙動を明文化する。
  推奨は「省略時は report only、DB 更新なし」。D-08 タイブレークは report 内の `recommended_primary_model` として算出し、人間が明示指定した時だけ `is_primary` 更新が安全です。

### Risk Assessment

**全体リスク: MEDIUM-HIGH**

設計思想とテスト観点はかなり良く、リーク防止・再現性・事前登録指標不変への意識も高いです。ただし、現在の PLAN のまま実装すると、D-02 BLOCK 条件の誤実装、06-02/06-03 依存順序の破綻、segment 軸欠損を PASS してしまう問題により、Phase 6 の達成判定が仕様より甘くなる可能性があります。これらは実装前に PLAN 修正で解消可能です。上記 HIGH concern を直せば、リスクは MEDIUM まで下げられます。

---

## Claude Review

### Summary

本計画は、Phase 4/5 の stamped 成果物を消費する評価専用フェーズとして、**リーク防止・再現性の聖域（T-04-24 事前登録指標不変・Phase 4 SC#4 bit-identical 維持・model_version scoped UPDATE による silent 履歴破壊防止）を正しく遵守**しており、設計思想は堅牢です。既存の `_compute_calibration_max_dev_guarded` の純 NumPy binning パターン・staging-swap idiom・hybrid gate・md/json 分離を直接拡張する方針は、実装リスクを大きく下げています。一方で、**実行順序に直結する3つのHIGH課題**（06-03 の依存宣言漏れ・人気帯/オッズ帯のバケット化欠落・ninki/odds データ経路の誤認）と、**SC#3 の達成性を脅かす データ経路問題**、**SUM_P_BLOCK_THRESHOLD=0.30 の経験的根拠欠如**が未解決です。これらはいずれも「設計の方向」ではなく「PLAN の精度・実装仕様の確定不足」に起因するもので、実行前に修正すれば本フェーズの品質はHIGH水準に到達可能です。

### Strengths

- **Core Value の遵守が明示的**: 評価専用フェーズ（READ-only + `is_primary` UPDATE のみ・モデル再学習/再予測なし）で Phase 4 SC#4 bit-identical を維持。T-04-24 後知恵すり替え防止を `test_calibration_max_dev_report_value_match` で固定化する設計は本プロジェクトの聖域に直結。
- **既存パターンの最大限再利用**: binning 契約固定・純 NumPy bit-identical・staging-swap idempotent・md/json 分離・atomic write の全てが既存コードに確立済み。PATTERNS.md の analog 探索（11/11 strong match）は説得力がある。
- **Pitfall 網羅性**: Pitfall 1（quantile 重複 edge・`np.unique`）・Pitfall 2（y_pred==1.0 clip）・Pitfall 4（3ファイル連鎖・`test_prediction_columns_matches_ddl` で機械検証）は実データベースの落とし穴を的確に捕捉。
- **hybrid gate の継承**: D-01/D-02/D-03 を Phase 1/2 の構造的 BLOCK + 量的 WARN パターンの延長に置き、曖昧基準の過機械化を回避。`check_acceptance_gate` の `block_reasons` リスト戻しで監査性も担保。
- **silent 履歴破壊の構造的防止**: `set_primary_model` が model_type+model_version+feature_snapshot_id+as_of_datetime スコープでフラグのみ UPDATE（DELETE しない・両モデル保持）。T-06-11 と `test_set_primary_model_both_models_retained` で二重防御。
- **人間判断経路の明文化**: D-07 主モデル選定を checkpoint:human-verify + `--primary-model` + `selection_reason` 記録で後知恵排除（T-06-10/T-06-13）。Phase 8 対抗的監査への引き継ぎも明示。

### Concerns

#### HIGH

- **C1 [依存順序] 06-03 の `depends_on` が 06-02 を欠く（Wave 1 並列宣言と矛盾）** — `segment_eval.py` は `from src.model.evaluator import _compute_calibration_curve_bins, _compute_ece, _compute_mce` するが、これらは Plan 06-02 が追加するシンボル。06-03 frontmatter は `depends_on: [06-01]` のみで、ROADMAP は「Wave 1・02/03 は並列可能」と宣言。ところが 06-03 Task 1 の read_first 自身が「本 task は Plan 06-02 完了後実行・import 依存」と明記。宣言（deps/wave）と実体（import 依存）が矛盾しており、wave-parallel executor が 06-03 を先に走らせると `test_segment_eval.py` の collection 時点で ImportError。**正式依存は `depends_on: [06-01, 06-02]`・Wave 構成は 06-02→06-03 の直列（または 06-02 完了後の 06-03）に修正必須。**

- **C2 [目標達成性/スコープ] 人気帯・オッズ帯のバケット化関数が存在しない** — SC#3/§15.3/EVAL-03 は「per-**人気帯**・per-**オッズ帯**」を要求。RESEARCH Pattern 2 の `SEGMENT_AXES` は `_ninki_band(df["ninki"])`/`_odds_band(df["fukuoddslower"])` の banding lambda を想定していたが、Plan 06-03 の `SEGMENT_AXES` は `"ninki": "ninki"` / `"odds_band": "fukuoddslower"` と**生値に直結**し、`evaluate_all_segments` 内にも banding 関数がない。`fukuoddslower`（連続 float）を生値で `np.unique` すると数百〜数千の segment に分裂し MIN_BIN_COUNT=30 でほぼ全滅、`ninki`（1-18）も希薄化する。**「帯（band）」要件が履行されず SC#3 部分達成にとどまる。** `_ninki_band`（1-3/4-6/7-9/10+ 等）・`_odds_band`（1.0-2.9/3.0-4.9/5.0-9.9/10+ 等）の定義と適用が必須。

- **C3 [目標達成性/データ経路] ninki/fukuoddslower のデータソース誤認（label に無い可能性大）** — CONTEXT/RESEARCH は segment 軸が「label.fukusho_label + prediction.fukusho_prediction の JOIN で揃う」とするが、実データ経路では `run_train_predict.py::_compute_baselines`/`run_backtest.py` は ninki/fukuoddslow を `fetch_market_data(cur)`（market/n_odds_tanpuku 由来）から取得しており、label JOIN では無い。加えて `PREDICTION_COLUMNS`（実契約）には entry_count も ninki/odds も無い（CONTEXT Integration Points の「prediction に entry_count」は不正確）。**label.fukusho_label にこれら列が無ければ、06-01 Task 2 のテストは WARN-skip し、人気帯/オッズ帯が silent に欠落**する。segment_eval は `fetch_market_data` を市場データソースとして明示的に JOIN する経路設計が必要。

- **C4 [受け入れ基準/目標達成性] SUM_P_BLOCK_THRESHOLD=0.30 の経験的根拠が検証されていない** — RESEARCH は「現データで violation_rate ほぼ 0%・発火しない安全網」と前提するが、(a) `check_sum_p_distribution` は Phase 4 で**一度も呼ばれておらず** reports/04-eval.json に violation_rate は存在しない（実測値ゼロ）、(b) reports/04-eval.json の sum_p_p10=1.93 / p90=4.15（LightGBM・全レース混合分布）はバケット毎の violation_rate が 0% に近いことを全く保証しない。**Plan 06-05 が初めて violation_rate を計算するため、0.30 が実際の分布に対して偽陽性 BLOCK を出すか否かは未検証。** もし large バケットの実 violation_rate が 0.30 を超えると、正常モデルで RuntimeError（出荷停止）が発生する。

#### MEDIUM

- **C5 [過剰設計/定義一致性] `quantile_max_dev` と `mce` が同一定義（冗長）** — Plan 06-02 Task 1 および RESEARCH Code Examples で `quantile_max_dev = mce  # 同一（MCE と定義一致）`。D-05 は「quantile max_dev + ECE + MCE」の3指標を想定するが、実装は ECE と (MCE≡quantile_max_dev) の2値しか産出しない。METRIC_COLUMNS_EXTENDED に同名義で2列並ぶのは Phase 7 表示/Phase 8 監査で混乱の元。quantile_max_dev を *ガードなし* quantile max|dev|（事前登録 calibration_max_dev との対比）として差別化するか、alias として削除すべき。

- **C6 [再現性/整合性] reports/04-eval.json が現 evaluator.py に対して stale** — 現 `evaluator.py` の `METRIC_COLUMNS`/`compute_metrics` は `calibration_max_dev_guarded` を吐く（9列）が、reports/04-eval.json の `constants.METRIC_COLUMNS` は8列・`metrics.lightgbm` に `calibration_max_dev_guarded` が無い。Plan 06-01 の回帰テストは unguarded 値（0.23077 等）を assert するのでテストは通るが、Plan 06-05 が「D-04 事前登録素材」として読み込む JSON に guarded 列が無い。Wave 0 で reports/04-eval.json を再生成するか、欠損キーの扱いを明示すべき。

- **C7 [受け入れ基準の曖昧さ] `--primary-model` 省略時の挙動が自己矛盾し D-08 タイブレークが未実装** — parse_args help は「省略時は D-08 タイブレーク規則適用」、Step 5 は「省略時は is_primary 更新スキップ・reports のみ生成」と矛盾。加えて D-08 タイブレーク規則をコード化する `apply_tiebreak()` 関係の task がどの PLAN にも無い。結果、タイブレークは「適用される」と書かれるが実装されない dead-spec。省略時は「reports のみ（is_primary 更新スキップ）」に統一し、タイブレークは人間が `--primary-model` で指定する際の*判断補助資料*（reports に優先順位表を提示するのみ）に位置付けるべき。

- **C8 [目標達成性/曖昧さ] SC#1 の model-level 指標の集計規則が未定義** — reports/05-backtest.json の回収率/損益/maxDD/的中率は backtest_id（5窓 × 2 policy × model）単位。SC#1 は「開発者が評価スイートを実行し 複勝的中率/回収率/損益/maxDD/購入点数 を受け取る」と単数形を想定。主モデル比較表に「どの backtest 行（または窓×policy の集計＝平均？優位 policy？合算？）」を載せるかの規則が無く、run_evaluation.py の統合設計が確定しない。

- **C9 [依存順序/制御フロー] Step 3（gate）と Step 4（segments）の順序依存が脆い** — `yearly_inversion_warn`（Step 3 の gate_result に含む）は year 軸 segment 評価（Step 4）の出力を必要。Plan は「Step 6 出力直前に gate_result に merge」と指示するが、BLOCK 発火（RuntimeError）を segment 評価の*前*にするか*後*にするか・BLOCK 時に reports/06-* を書くか否かが未規定。BLOCK→即 RuntimeError だと reports/06-segments/ が未生成の中途状態になり得る。

- **C10 [エッジケース/テスト堅牢性] `test_is_primary_default_false` が global DB 状態を前提** — 既存行（本番 22,213×2 行含む）の is_primary=false を assert するが、Plan 06-04 Task 3 checkpoint 完了後に再実行すると本番の primary 行（true）で失敗する。テストは test 挿入行に scope すべき。

- **C11 [エラーハンドリング] `set_primary_model` の silent no-op リスク** — スコープ条件 `feature_snapshot_id = %s AND as_of_datetime = %s` は stored as_of_datetime（Phase 4 FIXED_REPRODUCE_TS）と*完全一致*が必要。タイムゾーン/マイクロ秒のズレで 0 行 UPDATE となり、reset/true とも silent no-op。production 経路に affected-row 検証（「当該スコープで is_primary=true が1 model_type のみ」等の post-condition assert）が無い。

- **C12 [エッジケース] segment_eval の race_date dtype 未正規化** — `evaluate_all_segments` は `df["race_date"].dt.year/.dt.month` で year/month 軸を導出するが、prediction テーブルの race_date は `date` 型で pandas 読込時に Python date object になる可能性があり、`.dt` accessor で AttributeError。run_backtest `_filter_label_by_period` の `pd.to_datetime(errors="coerce")` 正規化パターンを segment_eval にも明示適用すべき。

- **C13 [パフォーマンス/スコープ] Plotly 自己完結 HTML が reports/ に ~21MB 肥大** — `include_plotlyjs=True` で各 HTML に ~3.5MB の plotly.js が埋込まれ ×6 軸 ≈ 21MB。reports/ が Git 管理されている現状（04-eval/05-backtest は tracked）では、生成物 HTML の Git 格納は不適切。`reports/06-segments/*.html` の .gitignore 指定（models/ と同様）または plotly.js 共有化の決定が未記載。

- **C14 [再現性] guarded 値の回帰ピン留めがない** — Plan 06-02 は `_compute_calibration_max_dev_guarded` を新 helper 経由にリファクタすることを許容するが、test_compute_metrics_uniform_max_dev_unchanged / test_calibration_max_dev_report_value_match は *unguarded* 値（0.23077/0.25789）のみ pin。guarded 値（LightGBM 0.0987）を固定するテストが無く、リファクタ時の境界処理差分が silent に漂う可能性。

#### LOW

- **C15 [目標達成性] SC#2「beat the baselines」が gate で検証されない** — BLOCK 条件1は「全 baselines に劣る（max 比）」極端例のみ捕捉。「baselines を上回る」（SC#2 文面）は WARN/人間判定。D-01 の意図的設計だが SC#2 原文との gap を注記すべき（現データでは LightGBM は全 BL を上回るため実害なし）。
- **C16 [過剰設計] is_primary の CHECK 制約が vacuous** — `CHECK (is_primary IN (true,false))` は boolean 型に対し実質無意味（NULL は CHECK 通過）。NOT NULL を意図するなら明示、さもなくば削除。
- **C17 [スコープ] 2つの checkpoint が重複** — 06-04 Task 3（機構承認）は reports/06-evaluation.md 未生成の段階で「主モデル候補を判断」を求め、06-05 Task 2（実際の選定）と重複。06-04 は「機構の unit test GREEN と model_version scoped UPDATE の確認」に縮小可。
- **C18 [Wave 構成] 06-04 の Wave 2 配置が保守的** — is_primary migration（schema/predict/prediction_load）は 06-02/06-03 にコード依存せず、Wave 1 で 06-02 と並列可能。Wave 全体のクリティカルパス短縮の余地。
- **C19 [設計] tdd="true" の flag misuse** — Plan 06-01 は Phase 4 既存契約の characterization test（即 GREEN）であって RED-first の古典 TDD ではない。フラグ表現と実態の不一致（動作への影響は軽微）。

### Suggestions

1. **【C1・最優先】依存グラフ修正** — 06-03 の `depends_on` を `[06-01, 06-02]` に変更し、ROADMAP Wave 1 を「06-02 完了後に 06-03（06-02 と files_modified 衝突なし・直列実行可）」に修正。executor が wave 宣言を信頼して並列起動しても import 破綻しないよう、宣言を正とする。

2. **【C2/C3・SC#3 達成の鍵】人気帯・オッズ帯のバンド化とデータソース確定** — (a) `_ninki_band`/`_odds_band` の離散化関数を 06-03 に実装し SEGMENT_AXES の値を band 適用済み列名に、(b) 06-01 Task 2 で label.fukusho_label のカラムを実 DB 確認し、ninki/fukuoddslow が無ければ segment_eval の入力 df 構築で `fetch_market_data` を明示 JOIN する経路を 06-05 に組込む。Open Question #1 の「RESOLVED」は実コード確認前なので過早表記。

3. **【C4】SUM_P_BLOCK_THRESHOLD の経験的検証を Wave 0 に前倒し** — Wave 0（または 06-02 完了直後）で `check_sum_p_distribution` を実データに走らせ、large/small バケットの実 violation_rate を計測・記録。0.30 が実分布に対して偽陽性 BLOCK とならないか（margin を含め）を確認してから閾値を fix。初回 run の BLOCK を informational 扱いする escape-hatch（`--allow-sump-warn` 等）の検討も。

4. **【C5】`quantile_max_dev` の定義分離** — D-05 の「3指標」を尊重し、quantile_max_dev を *ガードなし*（MIN_BIN_COUNT filter 無し・事前登録 calibration_max_dev と対）に定義、MCE を guarded のまま分離。または quantile_max_dev を廃止し ECE/MCE の2指標に整理（METRIC_COLUMNS_EXTENDED も整合）。

5. **【C6】reports/04-eval.json の整合** — Wave 0 で現 evaluator.py により reports/04-eval.json を再生成（guarded 列を含む9列化）し、06-01 回帰テストと 06-05 入力の両方を整合させる。再生成は D-04 事前登録値（unguarded 0.23077 等）を変えないことを test で担保。

6. **【C7】主モデル確定フローの単純化** — `--primary-model` 省略時は「reports のみ生成・is_primary 更新スキップ」に統一。D-08 タイブレークは*自動適用せず*、reports に優先順位表（backtest 回収率→計算コスト→Brier→LogLoss→AUC）を提示して人間判断を支援する資料と割り切る。タイブレーク自動関数の実装 task は削除。

7. **【C8】SC#1 model-level 集計規則の明記** — 主モデル比較表の backtest 指標を「優位 policy の代表窓」または「5窓×2policy の重み付き平均」のいずれかに固定し、reports/06-evaluation.md に集計方法を注記。

8. **【C9】BLOCK 制御フローの確定** — gate 判定を segment 評価の*後*に実行し、BLOCK 時も（segments 含む）reports/06-evaluation.{md,json} を書き出した上で RuntimeError、と明記。例外メッセージに block_reasons を含める（PATTERNS 実装例通り）。

9. **【C10/C11/C12/C14】テスト・実装の防御追加** — `test_is_primary_default_false` を test 挿入行に scope・`set_primary_model` に post-condition assert（当該スコープで is_primary=true が1件以上・model_type 単位で一意）・`evaluate_all_segments` に `pd.to_datetime(race_date)` 正規化・guarded 値（0.0987）の回帰 pin をそれぞれ追加。

10. **【C13】Plotly HTML の格納方針** — `reports/06-segments/*.html` を .gitignore 対象（JSON のみ tracked・Phase 7 Streamlit は JSON 消費）とするか、plotly.js を1ファイル共有参照化するかを決定し PLAN に明記。

### Risk Assessment

**全体リスクレベル: MEDIUM**

**正当化:** リーク防止・再現性（本プロジェクトの Core Value）に対する設計は HIGH 水準で、T-04-24・SC#4 bit-identical・model_version scoped UPDATE・事前登録指標不変の各聖域は計画で正しく守られています。脅威は設計思想ではなく**PLAN の宣言精度と実装仕様の未確定**に集中しています。なかでも C1（06-03 の依存宣言漏れ・Wave 並列宣言との矛盾）は wave-parallel executor の下で即座に ImportError を引き起こす実行阻害級のバグ、C2/C3（人気帯/オッズ帯のバケット化欠落・データソース誤認）は SC#3/EVAL-03 の達成を根本で損なう仕様欠陥、C4（SUM_P_BLOCK_THRESHOLD の経験的根拠欠如）は正常モデルの偽陽性「出荷停止」リスクを抱えます。これら3つの HIGH はいずれも PLAN 修正（依存グラフ・バンド関数・データ経路・閾値検証）で解決可能であり、再設計を要しないため全体を HIGH でなく MEDIUM と評価します。MEDIUM 群（C5〜C14）は受け入れ基準の曖昧さ・テスト堅牢性・エッジケースの仕上げであり、実行中のラウンドトリップで発見・修正可能です。実行前に C1〜C4 を修正すれば、本フェーズは高品質で完了可能です。

---

## Consensus Summary

### Agreed Strengths (2+ reviewers)

- **Core Value 聖域の遵守** — 両者とも、評価専用フェーズ（モデル再学習/再予測なし）・Phase 4 SC#4 bit-identical 維持・D-04 事前登録指標不変（T-04-24 回避）・model_version scoped UPDATE による silent 履歴破壊防止を、設計思想として高く評価。
- **既存パターンの再利用** — binning 契約固定・純 NumPy bit-identical・staging-swap idempotent・hybrid gate・md/json 分離・atomic write など既存コード契約を直接拡張する方針が堅牢と一致して評価。
- **hybrid gate と監査性** — D-01/D-02 構造的 BLOCK と D-03 曖昧 WARN の分離・`block_reasons` リスト戻し・`selection_reason`/`tiebreak_applied` 記録で過機械化回避と後知恵排除を両立する設計を両者が明示的に肯定。

### Agreed Concerns (2+ reviewers — highest priority)

1. **【HIGH・実行阻害】06-03 の `depends_on` が 06-02 を欠く（Wave 1 並列宣言との矛盾）** — Codex と Claude の両者が「HIGH」と判定。`segment_eval.py` は 06-02 が追加する `_compute_calibration_curve_bins/_compute_ece/_compute_mce` を import するが、frontmatter は `depends_on: [06-01]` のみで ROADMAP は「Wave 1・02/03 並列可能」を宣言。06-03 自身の read_first も「06-02 完了後実行・import 依存」と明記し宣言が自己矛盾。wave-parallel executor が 06-03 を先に起動すると `test_segment_eval.py` collection 時点で ImportError。**修正:** 06-03 の `depends_on` を `[06-01, 06-02]` に変更し、Wave 構成を 06-02 → 06-03 の直列（files_modified 衝突なし・直列実行可）に修正。

2. **【HIGH・目標達成】segment 軸確認テストが fail-loud でない（Open Question #1 未解決）** — Codex は「HIGH」、Claude は C3 で「label に列が無ければ WARN-skip し silent 欠落」と指摘。Plan 06-01 Task 2 は `ninki`/`fukuoddslower` 欠損時「WARN メッセージ付き PASS」とし、Open Question #1 を解決したとするが、代替カラムを確定できなければ D-12「6軸全て生成」の前提検証にならない。**修正:** 欠損時は fail-loud（または checkpoint:human-verify）に変更し、データソース（label vs `fetch_market_data`）を確定してから「RESOLVED」表記。

3. **【HIGH・目標達成】segment「帯（band）」要件の未履行（人気帯/オッズ帯）** — Claude C2 が「HIGH」と詳細指摘。SC#3/§15.3/EVAL-03 は「per-**人気帯**・per-**オッズ帯**」を要求するが、Plan 06-03 の `SEGMENT_AXES` は `"ninki": "ninki"` / `"odds_band": "fukuoddslower"` と生値に直結し、banding 関数が存在しない。`fukuoddslower`（連続 float）を生値で分割すると数百〜数千の segment に分裂し MIN_BIN_COUNT=30 でほぼ全滅。Codex も MEDIUM「欠損軸 WARN skip で SC#3 達成が曖昧」と指摘。**修正:** `_ninki_band`/`_odds_band` 離散化関数を 06-03 に追加実装し SEGMENT_AXES の値を band 適用済み列名に。

4. **【HIGH・受け入れ基準】SUM_P_BLOCK_THRESHOLD=0.30 の経験的根拠欠如** — Claude C4 が「HIGH」、Codex は MEDIUM で「閾値の根拠が弱い」と指摘。`check_sum_p_distribution` は Phase 4 で一度も呼ばれず reports/04-eval.json に violation_rate 実測値が無い。0.30 が実分布に対して偽陽性 BLOCK（正常モデルで RuntimeError＝出荷停止）を出すか未検証。**修正:** Wave 0 または 06-02 完了直後に実データで violation_rate を計測・記録し、0.30 が安全網として妥当か検証してから fix。

5. **【HIGH・目標達成・制御フロー】BLOCK 発火時の report 残存フロー未規定** — Codex は「HIGH」、Claude は C9 で MEDIUM 指摘。`check_acceptance_gate` 後の RuntimeError 設計で、`reports/06-evaluation.{md,json}` が生成されない可能性。BLOCK 時も block_reasons を含む最小レポートを atomic write してから raise すべき。**修正:** gate 判定を segment 評価後に実行し、BLOCK 時も reports を書き出してから RuntimeError（例外メッセージに block_reasons 含む）。

6. **【HIGH・目標達成】`set_primary_model` の silent no-op / rowcount 検証欠如** — Codex は「HIGH（0 行 UPDATE を検知しない）」、Claude は C11 で MEDIUM「silent no-op リスク」を指摘。model_version や `as_of_datetime`（timezone/microsecond ズレ）で 0 行 UPDATE となり主モデルなし状態になるリスク。Phase 7 表示と D-09 に直結。**修正:** post-condition assert（当該スコープで is_primary=true が1 model_type のみ・0 行なら RuntimeError）を追加。

7. **【HIGH・型設計】is_primary の NULL 許容/CHECK 制約の意図不明** — Codex は「HIGH」、Claude は C16 で LOW「CHECK が vacuous」と指摘。`CHECK (is_primary IN (true,false))` は boolean 型に対し NULL を許す限り実質無意味。`is_primary=2` の INSERT テストは CHECK 以前に型変換で失敗。**修正:** `boolean NOT NULL DEFAULT false` を明示し load 時に false 正規化、または NULL 許容の意図を明文化。

### Divergent Views (where reviewers disagreed — worth investigating)

- **全体リスク評価**: Codex は「MEDIUM-HIGH」・Claude は「MEDIUM」。差は主に D-02 BLOCK 条件の AND/OR 実装（Codex のみ HIGH 判定）と quantile_max_dev/MCE 冗長性（両者とも指摘するが Codex は MEDIUM・Claude は C5 MEDIUM で一致）に対する重み付け。Claude は「再設計不要・PLAN 修正で解決」と評価し MEDIUM に抑えた。この差は BLOCK 条件解釈の確定次第で縮まる。
- **D-02 BLOCK 条件の AND/OR**: Codex のみ「AND ではなく OR 実装の疑い（HIGH）」を指摘。Claude は D-02 の仕様（両方満たす構造的破綻）を前提にしつつも、実装の AND/OR には言及せず。Plan 06-02 Task 2 の記述（`block_reasons に ... を追加`・`gate_verdict は block_reasons が空なら WARN・非空なら BLOCK`）を厳密に読むと、baselines 全敗と sum(p) 著乖離はそれぞれ独立して block_reasons に追加され得る（= OR 挙動）。CONTEXT.md D-02 原文「＋（両方）」との整合性を実装で確定する必要がある。Claude レビューはこの点を見落とした可能性があるため、再レビューで確認推奨。

---

## Verification Coverage (source-grounding)

本レビューは以下のソースファイルを根拠とする:

- `/Users/hart/develop/keiba-ai-v3/.planning/PROJECT.md`（最初80行・Core Value・技術スタック制約）
- `/Users/hart/develop/keiba-ai-v3/.planning/ROADMAP.md`（Phase 6 セクション・SC#1/2/3・Plans/Wave 構成）
- `/Users/hart/develop/keiba-ai-v3/.planning/phases/06-evaluation-calibration-gates/06-CONTEXT.md`（D-01〜D-12 決定・Open Question・deferred）
- `/Users/hart/develop/keiba-ai-v3/.planning/phases/06-evaluation-calibration-gates/06-RESEARCH.md`（Pattern 1-4・Pitfall 1-6・Code Examples・Open Questions RESOLVED 表記）
- `/Users/hart/develop/keiba-ai-v3/.planning/phases/06-evaluation-calibration-gates/06-01-PLAN.md` 〜 `06-05-PLAN.md`（5つの PLAN 全文）
- `/Users/hart/develop/keiba-ai-v3/.planning/phases/06-evaluation-calibration-gates/06-VALIDATION.md`（Wave 0 必須項目）
- `/Users/hart/develop/keiba-ai-v3/.planning/phases/06-evaluation-calibration-gates/06-DISCUSSION-LOG.md`（Q1-Q3 のユーザー選択履歴）

レビュー実行コマンド:
- `cat /tmp/gsd-review-prompt-6.md | codex exec --ephemeral --dangerously-bypass-hook-trust --skip-git-repo-check -`
- `cat /tmp/gsd-review-prompt-6.md | claude -p -`

### Symbol verification (authority: grep)

Phase 6 plans extend Phase 4 `src/model/evaluator.py`. Verified cited existing symbols against source declarations; symbols declared under each plan's produced-artifacts list are excluded (this phase creates them, not references to existing code).

**VERIFIED** (existing symbol → declaration site):
- `check_sum_p_distribution` → `src/model/evaluator.py:343`（06-01/06-02 参照）
- `build_comparison_table` → `src/model/evaluator.py:418`（06-02/06-05 参照）
- `_compute_calibration_max_dev` / `_compute_calibration_max_dev_guarded` → `src/model/evaluator.py:228` / `:259`（06-01/06-02 参照）
- `compute_metrics` → `src/model/evaluator.py:148`
- `write_eval_report` → `src/model/evaluator.py:461`
- `evaluate_all_models` → `src/model/evaluator.py:552`

**Excluded from verification (produced by this phase — not references to existing code):**
- 06-02 産出: `check_acceptance_gate`, `compute_monotonicity_warn`, `quantile_max_dev`, `ece`, `mce`, `_compute_calibration_curve_bins`, `_compute_ece`, `_compute_mce`
- 06-03 産出: `segment_eval.py` モジュール + 追加予定 `_ninki_band`/`_odds_band`（review HIGH#4 で新規追加）
- 06-04 産出: `set_primary_model`（migration 範囲）
- 06-05 産出: `run_evaluation.py` CLI

**UNCHECKABLE under grep authority**（INFO・非ブロック）:
- 全参照の signature/overload 適合性 — grep では signature をassert できない → UNCHECKABLE
- `src/db/schema.py` のテーブル/カラム実体（`is_primary`, `model_version`, prediction 行）— 06-04 produced-artifact / migration 範囲で宣言、load 時正規化はテスト経由で担保、grep 非対象

**hardBlock: なし**（grep authority は hard-block 不可・LSP/SCIP 専用）。サンプル参照範囲で hallucinated な既存シンボルは検出されず。完全 LSP 検証は `intel.enabled`（SCIP/LSP authority）有効時に推奨。
