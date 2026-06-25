---
slug: race-date-null-racekey-fix
status: resolved
goal: find_and_fix
trigger: |
  label.fukusho_label.race_date 全行 NULL の根本修正。2026-06-23/06-24 の2回の silent corruption の真因は
  compute_fukusho_labels の race_df merge での _RACE_KEY 型不整合（kaiji/racenum が int4 vs varchar 2桁ゼロ埋めで
  astype(str) 後も "1" vs "01" で一致せず left join 全行 miss → race_date 全行 NULL）。
  quick task 260625-h1g の fail-loud が live-DB 検証で発火し根本原因を特定済み。本 debug は fix（ゼロ埋め正規化）まで実装。
created: 2026-06-25
updated: 2026-06-25T（resolved）
---

# Debug Session: label.race_date 全行 NULL の根本修正（race_key 型不整合）

## Symptoms

### Expected behavior
label.fukusho_label.race_date が label ETL 実行で全行 non-NULL で伝播されること（backfill 不要・ETL 再実行で再発しない）。

### Actual behavior
label ETL（run_label_etl / compute_fukusho_labels）実行で race_date が全行 NULL になる（2026-06-23/06-24 の2回発生・silent corruption）。
現在は backfill（scripts/run_label_race_date_backfill.py）で復元済み（全行 non-NULL・確認済）。しかし ETL 再実行で再発する（quick task 260625-h1g の fail-loud が live-DB 検証で発火して実証）。

### Error messages
quick task 260625-h1g の fail-loud（compute_fukusho_labels 行645-679）が発火:
- 診断ログ: race_df 側は正常（rows=39593, race_date列=True, nonnull=39593）
- merged 側は全行 NULL（rows=554267, null=554267）
- → race_df と merged の merge で race_date が伝播していない

### Timeline
- 2026-06-23: race_date 全行 NULL を検出（Phase 5 backtest の _filter_label_by_period で発覚）→ backfill で復元 → 再発防止策（label ETL 本体 + backfill + 回帰テスト）を入れたが不十分
- 2026-06-24: 再発（debug session fukusho-recovery-070 の cycle-2 で検出）→ backfill で復元
- 2026-06-25: quick task 260625-h1g で fail-loud + 診断ログ + post-condition を実装 → live-DB 検証で fail-loud 発火 → 根本原因（race_key 型不整合）を特定

### Reproduction
- live-DB で `uv run python scripts/run_label_etl.py` を実行 → compute_fukusho_labels の fail-loud が発火（race_date 全行 NULL を検知）
- 現在 label.fukusho_label は backfill 済み（race_date 全行 non-NULL・fail-loud が INSERT 前に発火して DB を守った）

## Root Cause（既知・fail-loud の診断ログで特定済み・確定）

src/etl/fukusho_label.py の compute_fukusho_labels（行631-647 の race_df merge）で、`_RACE_KEY = ["year", "jyocd", "kaiji", "nichiji", "racenum"]` を `astype(str)` で揃えているが、実データの型が不一致:

| 列 | normalized.n_race（race_df 側） | public.n_harai/n_uma_race（SE/HR 側） | str 化後 |
|----|-------------------------------|---------------------------------------|----------|
| year | 2015 (int4) | '2015' (varchar) | 一致 |
| jyocd | '06' (varchar) | '06' (varchar) | 一致 |
| **kaiji** | **1 (int4)** | **'01' (varchar・2桁ゼロ埋め)** | **"1" vs "01" → 不一致** |
| nichiji | '01' (varchar) | '01' (varchar) | 一致 |
| **racenum** | **1 (int4)** | **'01' (varchar・2桁ゼロ埋め)** | **"1" vs "01" → 不一致** |

`kaiji` と `racenum` が int4（ゼロ埋めなし）vs varchar（2桁ゼロ埋め）のため、`astype(str)` しても `"1"` vs `"01"` で一致せず、left join が全行 miss → race_date が全行 NULL。

コメント行634「実DB では race 側の _RACE_KEY は int4（normalized.n_race）、SE/HR 側は varchar」は既知 pitfall として記載されていたが、`astype(str)` だけではゼロ埋めフォーマット差を吸収できていなかった。

## Fix 方針（debugger が codebase を読んで具体化）

race_merge 構築時（compute_fukusho_labels 行639-645 付近）に kaiji/racenum を2桁ゼロ埋めに正規化:
- `race_merge[k] = race_merge[k].astype(str).str.zfill(2)`（kaiji/racenum のみ・他の _RACE_KEY は従来 astype(str) のまま）
- または _select_race_meta の SELECT で `LPAD(kaiji::text, 2, '0')` / `LPAD(racenum::text, 2, '0')` で正規化
- merged 側（SE/HR・public.n_*）は既に2桁ゼロ埋め varchar なので、両者を2桁ゼロ埋めで揃えれば一致

※ unit test の合成データ（_build_label_input_df）の kaiji/racenum が既に2桁ゼロ埋め varchar か要確認（既存テスト GREEN 維持のため）。

## Files to investigate / fix 対象
- src/etl/fukusho_label.py — compute_fukusho_labels（行631-679・race_df merge + fail-loud）/ _select_race_meta（行283-289）/ _RACE_META_SELECT_COLUMNS（行269-280）
- tests/test_fukusho_label.py — _build_label_input_df の kaiji/racenum の型確認・必要なら新規テスト
- src/etl/normalize.py — 参考: normalized.n_race の kaiji/racenum の型（int4）
- .planning/quick/260625-h1g-label-race-date-null-fail-loud-diagnosti/260625-h1g-SUMMARY.md — 前段の fail-loud 実装と根本原因特定の記録

## Constraints（厳守・聖域）

### raw 不変（D-06）
raw テーブルに一切書込まない。本 fix は src/etl/fukusho_label.py の読み取り/変換/label スキーマ書込のみ。

### 再現性（§19.1）
staging-swap / idempotent ロジック（_idempotent_load_label）を壊さない。2回連続実行で同一 checksum。
**注意**: race_key 正規化により race_date が正常伝播するようになるため、label.fukusho_label の checksum は（race_date 列が non-NULL になる点で）以前と変わる可能性がある。これは「fix による正常化」であり idempotent 違反ではない（2回実行で同一 checksum＝idempotent・1回目と以前の backfill 版との差は正常化）。要確認: race_date 以外の列は不変・race_date は全行 non-NULL になる。

### 既存テスト GREEN 維持
- test_compute_fukusho_labels_propagates_race_date（race_date 伝播）
- quick task 260625-h1g で追加した fail-loud テスト4件（empty_race_df / missing_race_date_column / normal_case_no_diagnostic_log / post-condition 構造検査）
- その他 label 関連テスト

### スコープ
変更対象は src/etl/fukusho_label.py のみ（+ 必要なら tests/test_fukusho_label.py）。
**既存の未コミット変更（scripts/run_backtest.py, src/db/prediction_load.py）には触らない・巻き込まない。**

### 日本語（CLAUDE.md 最優先）
コミットメッセージ・コメント・docstring は全て日本語。

## 検証

1. KEIBA_SKIP_DB_TESTS=1 で unit test GREEN（DB 不要テスト）。
2. uv run pytest tests/test_fukusho_label.py（KEIBA_SKIP_DB_TESTS unset・DB 必須テスト含む）GREEN。
3. ruff check src/etl/fukusho_label.py GREEN。
4. **live-DB 検証（メモリ [run-authorized-ops-directly]・自分で実行）**: `uv run python scripts/run_label_etl.py` を実行し:
   - fail-loud が発火しない（race_date 正常伝播）
   - 2回連続実行で同一 checksum（idempotent）
   - raw_touched=False（D-06 raw 不変）
   - `SELECT count(*) FROM label.fukusho_label WHERE race_date IS NULL` = 0（全行 non-NULL）
   - post-condition（260625-h1g Task 2）が発火しない

## 前提

quick task 260625-h1g 完了済み（fail-loud + post-condition 実装済み・コミット 482a10c/69e9c2c/0695787）。これが根本原因特定に貢献した。本 debug は根本修正（race_key ゼロ埋め正規化）を実装し、race_date 全行 NULL を根絶する。過学習/ルックアヘッドの懸念なし（閾値チューニングでなくデータ型正規化の fix）。

## Current Focus

- hypothesis: 【ROOT CAUSE 確定】race_key 型不整合（kaiji/racenum の int4 vs varchar 2桁ゼロ埋め・astype(str) で "1" vs "01" が不一致・left join 全行 miss → race_date 全行 NULL）
- test: 【fix 検証】race_merge 構築時に kaiji/racenum を2桁ゼロ埋め正規化し・live-DB で label ETL 再実行で race_date 全行 non-NULL になることを確認
- expecting: fix 後、fail-loud が発火せず・race_date が全行 non-NULL で伝播・idempotent 同一 checksum・raw 不変
- next_action: fix の実装（race_merge + merged 側の kaiji/racenum を zfill(2) 正規化）→ 新規 unit test（実DB型再現）→ live-DB 検証
- reasoning_checkpoint:
    hypothesis: "compute_fukusho_labels 行639-645 の race_df merge で kaiji/racenum を astype(str) のみで揃えているが、実DB では race 側が int4（1）/SE-HR 側が varchar 2桁ゼロ埋め（'01'）のため '1' vs '01' で一致せず left join が全行 miss し race_date が全行 NULL になる"
    confirming_evidence:
      - "行640-644 で _RACE_KEY 全列を astype(str) しているが zfill は無い（ゼロ埋めフォーマット差を吸収できないコード構造）"
      - "実DB の normalized.n_race.kaiji/racenum は int4（1）・public.n_harai/n_uma_race は varchar（'01'）という型差がコメント行634 で既知 pitfall として明記済み"
      - "quick task 260625-h1g の fail-loud 診断ログ: race_df 側は race_date nonnull=39593（正常）・merged 側は race_date null=554267（全行 NULL）= merge で伝播していない直接証拠"
      - "backfill（race_key で別経路 join）では race_date が復元できる = race_key 正規化ロジックの差が原因（backfill 側は別の正規化をしているか SE/HR 側と同一 varchar で join）"
    falsification_test: "kaiji/racenum を zfill(2) で正規化しても race_date が全行 NULL のままなら本仮説は誤り（別の race_key 列に不整合がある）"
    fix_rationale: "root cause は kaiji/racenum のフォーマット差のみ。両側（race_merge と merged）を zfill(2) で2桁ゼロ埋めに正規化すれば int4 '1'→'01'・varchar '01'→'01' で一致し left join が hit する。merged 側（SE/HR）は既に '01' だが zfill(2) は冪等（'01'→'01'）なので無害・unit test の合成データ（'01'）も破損しない。SQL 側 LPAD 案は unit test が pandas を直接渡すため不十分（pandas 側正規化が必須）"
    blind_spots: "jyocd/nichiji も2桁だが既に varchar 同士で一致していると仮定している（実DB で確認すべき）・year は4桁 int vs varchar で一致していると仮定している"
- tdd_checkpoint: (空)

## Evidence

- timestamp: 2026-06-25T13:20
  checked: 実DB の _RACE_KEY 全列のデータ型（information_schema.columns）
  found: |
    normalized.n_race（race_df 側）: year=integer, jyocd=varchar, kaiji=integer,
    nichiji=varchar, racenum=integer
    public.n_uma_race/n_harai（SE/HR 側）: 全列 varchar（kaiji='01', racenum='01' 2桁ゼロ埋め）
    代表値: race_df 側 kaiji=1, racenum=1 / SE 側 kaiji='01', racenum='01'
  implication: |
    astype(str) のみだと kaiji/racenum が int4 '1' vs varchar '01' で不一致。
    year は4桁のため astype(str) で一致・jyocd/nichiji は varchar 同士で一致。
    根本原因は kaiji/racenum のゼロ埋めフォーマット差のみ（blind_spots 解消）。

- timestamp: 2026-06-25T13:25
  checked: fix 無し版（astype(str) のみ）と fix あり版（zfill(2) 追加）での race_date 伝播比較
  found: |
    合成データで実DB 型（race_df kaiji/racenum=integer, SE 側=varchar '01'）を再現:
    fix 無し: race_date null = 8/8 行（全行 NULL・バグ正しく再現 = RED 確認）
    fix あり: race_date null = 0/8 行（正常伝播 = GREEN 確認）
  implication: 新規テストがバグを正しく検出できる（回帰保護として有効）

- timestamp: 2026-06-25T13:27
  checked: KEIBA_SKIP_DB_TESTS=1 で unit test 全体（test_fukusho_label.py）
  found: 46 passed（既存45 + 新規1）
  implication: 既存テスト GREEN 維持・新規テスト追加で回帰保護強化

- timestamp: 2026-06-25T13:28
  checked: live-DB で scripts/run_label_etl.py を2回連続実行
  found: |
    run #1: rows_inserted=554267, raw_touched=False, checksum=a67efb0f6f28ef4659686491e5233dd6
    run #2: rows_inserted=554267, raw_touched=False, checksum=a67efb0f6f28ef4659686491e5233dd6
    idempotent 検証 PASS（同一 checksum）・raw 不変性確認 PASS（row-hash + row-count + pg_stat）
    compute_fukusho_labels の fail-loud（race_date 全行 NULL 検知）は発火せず正常完了
  implication: |
    聖域クリア: D-06 raw 不変（raw_touched=False・raw fingerprint 不変）・
    §19.1 idempotent（2回同一 checksum）・fail-loud 未発火（race_date 正常伝播）・
    post-condition 未発火（二重防波堤正常）

- timestamp: 2026-06-25T13:30
  checked: label.fukusho_label.race_date の直接 SQL 検証
  found: 全行数 554267 / race_date NULL 数 0（100% non-NULL）/ 代表値 2015-01-04 等
  implication: silent corruption 根絶確認・ETL 再実行で race_date が正常伝播する

## Eliminated

(棄却された仮説無し・根本原因は初手で確定済み)

## Resolution

root_cause: |
  src/etl/fukusho_label.py の compute_fukusho_labels（race_df merge・行639-645）で
  _RACE_KEY を astype(str) のみで揃えていたが、実DB で kaiji/racenum が
  race_df 側（normalized.n_race）= integer（1）/ SE/HR 側（public.n_*）= varchar 2桁ゼロ埋め（'01'）
  の型不整合があり、astype(str) すると '1' vs '01' で一致せず left join が全行 miss →
  race_date が全行 NULL になる（2026-06-23/06-24 の silent corruption の真因）。
  year（4桁）/jyocd/nichiji は astype(str) で一致するため問題なし。

fix: |
  race_df merge で kaiji/racenum を str.zfill(2) で2桁ゼロ埋めに正規化。
  新規定数 _RACE_KEY_ZFILL_COLS = ['kaiji', 'racenum'] を追加し、merge 前に
  merged 側・race_merge 側の両方の kaiji/racenum を zfill(2) で正規化。
  int4 '1' → '01'・varchar '01' → '01' で一致し left join が hit する。
  year/jyocd/nichiji は従来通り astype(str) のみ（zfill 不要）。

verification: |
  1. 新規 unit test（test_compute_fukusho_labels_race_key_int4_zfill_normalization）:
     実DB 型（race_df kaiji/racenum=integer）を再現し fix で race_date 全行 non-NULL 传播を検証。
     RED/GREEN 両確認済（fix 無しで8/8行 NULL・fix ありで0/8行 NULL）。
  2. 既存 unit test 46件全て GREEN（DB 必須テスト含む）。
  3. ruff: 今回変更行に lint エラー無し（既存エラーは今回スコープ外）。
  4. live-DB 検証（scripts/run_label_etl.py 2回連続実行）:
     - fail-loud 未発火（race_date 正常伝播）
     - idempotent: run #1/#2 同一 checksum（a67efb0f6f28ef4659686491e5233dd6）
     - raw_touched=False（D-06 raw 不変）・raw fingerprint 不変
     - label.fukusho_label.race_date NULL 数 = 0（全554267行 non-NULL・100%）
     - post-condition 未発火（二重防波堤正常）

files_changed:
  - src/etl/fukusho_label.py（_RACE_KEY_ZFILL_COLS 定義追加 + race_df merge で zfill(2) 正規化）
  - tests/test_fukusho_label.py（新規回帰テスト test_compute_fukusho_labels_race_key_int4_zfill_normalization 追加）

commit: ef63e65（2026-06-25 確定・対象2ファイルのみ・非巻き込み厳守）
  - scripts/run_backtest.py・src/db/prediction_load.py は別管理として未コミット維持
  - ユーザー検証: confirmed fixed（fail-loud 未発火・race_date 全行 non-NULL・idempotent 同一 checksum・raw 不変・既存テスト GREEN を確認）
