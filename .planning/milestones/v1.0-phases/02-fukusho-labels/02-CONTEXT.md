# Phase 2: Fukusho Labels - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning

<domain>
## Phase Boundary

予測目標の**唯一の真実の情報源**である `fukusho_hit_validated` を生成すること。具体的には：

1. **2層ラベル生成（LABEL-01）** — 着順由来の一次ラベル `fukusho_hit_raw`（`n_uma_race.SE.KakuteiJyuni`）と、払戻テーブル(HR)突合後の確定ラベル `fukusho_hit_validated`（`n_harai.HR.PayFukusyoUmaban1..5`）を生成。全行に `label_validation_status` ∈ {`validated`, `inferred`, `dead_heat`, `unresolved`} を付与
2. **`sales_start_entry_count` 取得・復元（LABEL-02 / §10.2-10.3）** — 発売開始時点ベース。直接項目がなければ出馬表確定時出走予定 + 取消/除外発表時刻から復元、不能は `unresolved` で学習除外
3. **払戻テーブル突合（LABEL-03 / §10.5 / SC#2）** — `>99.9%` 整合ゲート。対象馬の存在/過不足・同着・取消除外馬の誤正例・中止馬の扱い・複勝発売なし混入を検査
4. **同着・取消/除外・競走中止の扱い（LABEL-04 / §10.6）** — 同着=払戻テーブル全対象馬を正例(`dead_heat`)、取消/除外=予測対象外（返還は Phase 5）、競走中止=学習に含めて `fukusho_hit=0`

Build-Order DAG の step 3（ラベル生成）。**ラベルは予測目標の正＝リーク防止と同等の聖域。** Phase 1 基盤（5層スキーマ・normalized ETL・リーク防止プリミティブ）の上に乗る。モデル/特徴量/EV/バックテスト実装は明示的に後続フェーズ。

</domain>

<decisions>
## Implementation Decisions

### sales_start_entry_count 復元と inferred/unresolved 境界（LABEL-02 / §10.2-10.3）
- **D-01: ハイブリッド復元方針** — 復元対象を「ラベル境界そのもの」と「補助メタデータ」に分け、厳格さを段階的に変える：
  - **厳格（学習除外の対象）:** `fukusho_payout_places`（複勝払戻対象数 8頭以上→3 / 5-7頭→2 / 4頭以下→複勝発売なし）を確定する頭数判定。これは `fukusho_hit_validated` の境界そのものなので、HR の発売/払戻情報（`PayFukusyoUmaban` / `FuseirituFlag2`）か、取消/除外発表時刻からの**確実な復元**のみで確定する。曖昧な場合は `label_validation_status = unresolved` として学習/評価対象から除外（§10.3）
  - **寛容（inferred で保持）:** `sales_start_entry_count` そのもの（補助メタデータ・適格性フィルタ用）。直接項目がなければ `TorokuTosu`（HR 登録頭数＝出馬表発表時）等を代理値とし `inferred` で保持。件数ロスを避けつつ不確実性を明示
  - **根拠:** Core Value（ラベル正確性＝リーク防止と同等の聖域）＋ Phase 1 D-01（hybrid gate）＋ D-13（silent fallback 禁止）。ラベル境界には純度を、補助情報には寛容さを振り分ける

### 払戻テーブル突合ゲート（LABEL-03 / §10.5 / SC#2）
- **D-02: Phase 1 hybrid gate 踏襲** — `>99.9%` 達成後の残り `<0.1%` と不整合レースを、Phase 1 D-01 と同じ構造/量化の2段階で扱う：
  - **構造的不整合 = ブロック（`unresolved` で学習除外）:** 払戻テーブル欠損・対象馬数の理論値違反・取消/除外馬の誤正例・競走中止馬の誤除外・複勝発売なしレースの混入（§10.5 の6検査のうち「ラベル境界を壊す」もの）
  - **量的ドリフト = 参考レポート:** 件数の不一致等（下流は動くが品質要注意）
  - **実装:** Phase 1 の `quality_gate.py` の `CheckResult` dataclass + BLOCK/INFO 分離パターンを再利用（後述 code_context）。研究者が §10.5 の6検査項目を構造/量化に分類して計画化
  - **根拠:** ラベル誤りは Phase 3-6 下流へ直結するため、構造的欠陥は聖域として止める。EveryDB2 既知のデータ揺れで過剰 FAIL しない点は Phase 1 D-01 と一貫

### ラベル生成スコープ（§7.2 / §7.3）
- **D-03: 全件網羅＋除外旗** — 保存済み**全レース/全馬**にラベル行を生成し、`label_validation_status` に加えて `is_model_eligible` フラグ（bool）で §7.2 適格性を明示する：
  - `is_model_eligible = False`: 障害競走 / 新馬戦 / 複勝発売なし / ラベル生成/突合失敗（`unresolved`）/ §7.2 のクラス条件（2歳未勝利以上・1勝クラス以上等）非充足
  - `is_model_eligible = True`: §7.2 対象かつ `label_validation_status ∈ {validated, inferred, dead_heat}`
  - 下流（Phase 3 features / Phase 4 model / Phase 5 backtest）は `is_model_eligible` でフィルタ
  - **根拠:** §7.3 は障害/新馬/複勝発売なしを「データ保存のみ・モデル除外」と規定＝データには存在しラベル付きで保持すべき。Phase 8 対抗的監査（除外境界の監査）・将来 v2 の対象拡張・Core Value の再現性（同じデータ→同じラベル、除外理由が透明）に合致。同データスキャンで低コスト

### 状況系エッジの分類（LABEL-04 / §10.6）
- **D-04: 観測事実ベース分類** — 固定4値 status（`validated`/`inferred`/`dead_heat`/`unresolved`）＋ `is_model_eligible` 旗への写像は、HR/SE の**観測事実のみ**で行い、推測しない（D-13 整合）：
  - **複勝不成立**（HR `FuseirituFlag2=1`）= `unresolved` / `is_model_eligible=False`（複勝 outcome が確定しない）
  - **レース全体中止**（HR/SE `DataKubun=9`）= 全馬 `unresolved` / `is_model_eligible=False`
  - **複勝特払**（HR `TokubaraiFlag2=1`）= 払戻テーブルに複勝対象馬が存在すれば正当な正例 `validated`（払戻金額は参考）。対象馬なき場合は `unresolved`
  - **同着** = 払戻テーブル（`PayFukusyoUmaban1..5`、最大5スロット）に存在する全対象馬を正例、理論対象数超過でも払戻テーブル優先で `dead_heat`（§10.5）
  - **馬個別競走中止** = 学習に含めて `fukusho_hit=0`（§10.6・除外禁止）。取消/除外とは SE のマーカーで識別（後述 specifics）
  - **取消/除外**（HR `HenkanUma1..28`=発売後取消返還馬番、SE `BaTaijyu=000` 等）= 予測対象外（`is_model_eligible=False`）。返還処理自体は Phase 5
  - **根拠:** §10.4「払戻テーブル優先」＋観測事実のみ（推測なし）。特払は実在中なら正当 outcome なので過剰除外しない。不成立/全体中止は outcome 非確定なので除外

### Claude's Discretion（研究者/計画者に委ねる）
- **成績レコードの権威:** SE/HR は1レースに複数 `DataKubun` レコード（木曜出走馬名表/金土出馬表/速報/月曜確定）を持つ。ラベル原料を「月曜確定成績（HR `DataKubun=2`/SE `DataKubun=7`）のみ（純度優先）」か「最新利用可・速報は `inferred`（直近性優先）」かは、研究者が実データのレコード可用性を確認の上決定。指針: バックテスト対象の歴史レースは原則すべて月曜確定が入手可能 → `validated`。速報しかないレース（極めて新しい）は `inferred` で保持可
- **`>99.9%` ゲートの試験設計:** held-out サンプル（時系列ホールドアウト/層化/ランダム）と「agreement」の定義（レース単位の馬集合完全一致か、正例の precision/recall か）。SC#2 の検証可能性に関わる。計画者が設計、§10.5 の6検査に対応させる
- **`sales_start_entry_count` の具体復元ロジック:** どのカラム/タイムスタンプ組合せで「発売開始時点頭数」を復元するか。**STATE.md が research flag として明示** → 実 EveryDB2/JRA-VAN カラムの精査が必須。`TorokuTosu`(HR 登録頭数)・取消/除外発表時刻列の存在と粒度を確認
- **§10.5 の6検査の構造/量化分類:** D-02 に基づき各検査を構造(ブロック)/量化(レポート)に分類する具体対応表
- **ラベルテーブル/カラム具体設計:** `label` スキーマ配下のテーブル名・カラム構成。§10.2 の保持項目リスト（race_id/horse_id/sales_start_entry_count/final_starter_count/fukusho_payout_places/is_fukusho_sale_available/fukusho_hit_raw/fukusho_hit_validated/label_validation_status）＋ D-03 の `is_model_eligible` を網羅。`label_generation_version`（§10.3）の採番方式も計画で確定
- **n_harai(HR)・n_hyosu(成績) の取り扱い:** Phase 1 は `normalized.n_race`/`n_uma_race` のみ正規化済み。HR/HYOSU は raw（`public.n_harai` 等・raw_everydb2 VIEW 経由で読取可能）のまま。label ETL が raw を明示キャスト付きで直読みするか、Phase 2 で先に `normalized.n_harai` を作るかは計画決定（Phase 1 D-08 の psycopg3+Python 明示 ETL パターンに従う）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 要件・仕様（正）
- `docs/keiba_ai_requirements_v1.3.md` §10.1-10.6 — 複勝ラベル生成・検証仕様（基本定義/発売開始時点基準/`sales_start_entry_count` 取得復元/ラベル優先順位/払戻突合/取消除外中止）。LABEL-01..04 の直接根拠
- `docs/keiba_ai_requirements_v1.3.md` §7.2-7.3 — 初期モデル対象/除外対象（障害/新馬/複勝発売なし）。D-03 の `is_model_eligible` 判定基準
- `docs/keiba_ai_requirements_v1.3.md` §11.1-11.2 — EV計算/オッズ時点（Phase 5 用だが、取消/除外の返還・競走中止の扱い §10.6 と連動）。Phase 2 はラベル/flag のみ付与し EV・返還計算は扱わない

### EveryDB2 公式マニュアル（実データ依存の正・ユーザー提供）
- `docs/everydb2/05-HARAI.md` — 払戻（HR, 199フィールド）。**Phase 2 の主たる突合情報源。** `PayFukusyoUmaban1..5`（複勝的中馬番・同着で最大5スロット）/ `DataKubun`（9=レース中止/2=月曜確定/1=速報）/ `FuseirituFlag2`（複勝不成立）/ `TokubaraiFlag2`（複勝特払）/ `HenkanFlag2`+`HenkanUma1..28`（複勝返還/返還馬番）/ `TorokuTosu`（登録頭数）/ `SyussoTosu`（出走頭数）
- `docs/everydb2/04-UMA_RACE.md` — 出走馬（SE, 73フィールド）。`KakuteiJyuni`（確定着順・`fukusho_hit_raw` 原料）/ `NyusenJyuni`（入線順位）/ `BaTaijyu=000`（出走取消マーカー）/ `HaronTimeL3/L4=999`・`TimeDIFN=9999`（取消/除外/発走除外/競走中止マーカー）/ `DataKubun`（複数レコード・9=レース中止）
- `docs/everydb2/INDEX.md` — 全59テーブル＋RecordSpec。`n_harai`/`n_hyosu` 等の raw テーブル名特定に使用
- `docs/everydb2/CODE.md` — ⚠ スクレイピング不完全（Phase 1 D-10）。コード表参照のみ、補完必須

### プロジェクト計画・状態
- `.planning/ROADMAP.md` — Phase 2 成功基準#1-#4、8フェーズ strict DAG。Phase 2 = long pole・`>99.9%` ハードゲート
- `.planning/REQUIREMENTS.md` — LABEL-01/02/03/04（Phase 2 割当）、全25要件トレーサビリティ
- `.planning/STATE.md` — **Blockers/Concerns に「Phase 2 research flag: `sales_start_entry_count` 復元ロジックと払戻テーブル schema は実カラム調査が必要」を明示** → `/gsd-plan-phase --research-phase 2` を想定
- `.planning/PROJECT.md` — Core Value、Key Decisions（複勝ラベル=発売開始時点ベース＋払戻優先）、Out of Scope

### 前フェーズ成果（引き継ぎ決定の正）
- `.planning/phases/01-trust-foundation/01-CONTEXT.md` — **D-01（hybrid gate）/ D-05（5層スキーマ）/ D-06（raw read-only 二重保護）/ D-07（config YAML Git 管理）/ D-08（psycopg3+Python 明示 ETL）/ D-13（未知コード厳格エラー・silent fallback 禁止）** が Phase 2 の直接の前提
- `.planning/phases/01-trust-foundation/01-VERIFICATION.md` — Phase 1 実装内容（normalized.n_race=39593行 / 5層スキーマ / REVOKE 実効性実証 / 76テスト green）。`n_odds_tanpuku`=単複共用（`n_odds_fukusho` 非存在）確定事項
- `.planning/research/SUMMARY.md` — Build-Order DAG、Phase 2 位置づけ
- `.planning/research/PITFALLS.md` — "Looks Done But Isn't" チェックリスト（ラベル/突合系の落とし穴）
- `CLAUDE.md` — 技術スタック・リーク防止設定・Postgres↔Parquet↔DuckDB interop（プロジェクト指示として权威）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/etl/quality_gate.py`** — `CheckResult` dataclass + `run_quality_gate(cur)` + BLOCK/INFO 分離。**D-02 の払戻突合ゲートの直接の雛形。** verdict 集計（`all(r.passed for r in results if r.severity=="block")`）パターンを複勝ラベル突合に再利用
- **`src/etl/normalize.py`** — `staging-table-swap` による idempotent load（`_idempotent_load`）＋ `_JRA_FILTER`（`jyocd BETWEEN '01' AND '10'`・Pitfall 2 JRA 限定）＋ 全 varchar 明示キャスト（`pd.to_numeric(errors="coerce")`）。label ETL も同じパターンで `label` スキーマへ idempotent 書込
- **`src/db/connection.py`** — `make_pool(role='readonly'/'etl')` ＋ `readonly_cursor` / `write_cursor`。2ロール DSN。label ETL は `role='etl'`（search_path=label）で書込、`role='readonly'` で raw/normalized 読込
- **`src/etl/raw_fingerprint.py`** — raw read-only 集計 helper パターン（UPDATE/DELETE 発行なし）。HR/SE 読込時の参照
- **`src/config/*.yaml` + loader** — `class_normalization.yaml`/`code_tables.yaml` の YAML→dataclass 読込パターン（D-07）。`label_generation_version` や status 分類ルールの静的正として `src/config/` 配下に配置可能
- **`src/utils/`（pit_join/group_split/category_map/calibrator）** — Phase 1 bootstrap 済み。**Phase 2（モデル前）では直接使用しない**が、Phase 3/4 が本格消費

### Established Patterns
- **5層スキーマ（Phase 1 D-05 / `src/db/schema.py`）:** `raw_everydb2`/`normalized`/`label`/`prediction`/`backtest`。label 層は `label` スキーマのみに書く。Phase 1 で `label` スキーマは CREATE 済み（空）
- **psycopg3 + pandas 明示 ETL（D-08）:** DuckDB は大量集計時のみ補助。型/コード変換ロジックは可読・テスト可能に
- **hybrid gate（D-01）:** 構造的欠陥=ブロック（pytest/CI fail）、量的異常=参考レポート。D-02 がこれを踏襲
- **raw read-only（D-06）:** REVOKE + raw_fingerprint の二重保護。label ETL も raw/normalized から SELECT のみ
- **silent fallback 禁止（D-13）:** 未知/解決不能は明示的に status/flag で隔離（`unresolved` / `is_model_eligible=False`）。見せかけの通過を許さない
- **権限:** ETL ロールは Phase 1 01-03 で `normalized` に `USAGE+CREATE` 付与済み。**`label` スキーマへの `USAGE+CREATE` GRANT 拡張が必要**（計画で `apply_schema.sql`/GRANT を更新）

### Integration Points
- **READ（readonly/raw_everydb2 VIEW 経由）:**
  - `normalized.n_race`（レース級・クラス・除外判定用 race-level カラム・`class_code_normalized` 等）
  - `normalized.n_uma_race`（SE: 着順/取消/除外/中止マーカー・馬番/血統）
  - `public.n_harai` / `raw_everydb2.n_harai`（HR: 払戻/返還/不成立/特払/DataKubun）— **raw のまま・normalized 未実施**
  - `public.n_hyosu` / `raw_everydb2.n_hyosu`（成績系）— 必要に応じて（実データで SE との役割分担を確認）
- **WRITE（ETL ロール・search_path=label）:**
  - `label.<fukusho_label テーブル>`（新規・Phase 1 で `label` スキーマ作成済み・空）。§10.2 保持項目 + `is_model_eligible`（D-03）
- **CONSUMED BY（下流フェーズ）:**
  - Phase 3（features）・Phase 4（model）: `fukusho_hit_validated` を目的変数、`label_validation_status`/`is_model_eligible` でフィルタ
  - Phase 5（backtest）: 取消/除外フラグ（返還 `effective_stake=0`）・競走中止（`effective_stake=100`）判定に HR `HenkanUma`/SE マーカーを使用
  - Phase 8（adversarial audit）: D-02 突合ゲート・D-04 エッジ分類の対抗的監査テスト

</code_context>

<specifics>
## Specific Ideas

- **複勝的中馬番は HR `PayFukusyoUmaban1..5`（最大5スロット＝同着3頭までの拡張対応）。** 通常2-3頭だが同着で増加。理論払戻対象数（2 or 3）を超える場合も**払戻テーブル優先**で全頭を正例とし `dead_heat` 付与（§10.5・D-04）。`00`=発売なし/特払/不成立
- **HR/SE `DataKubun=9` は「レース全体中止」**（発走後の天候等による全レース中止）＝全馬 `unresolved`/除外。**馬個別の競走中止とは別物**（馬個別中止は SE の着順/タイムマーカーで識別・学習に残して0）
- **取消/除外/発走除外/競走中止の識別（D-04 観測事実ベース）:** SE `BaTaijyu=000`=出走取消、`HaronTimeL3/L4=999` & `TimeDIFN=9999`=取消/競走除外/発走除外/競走中止の共通マーカー。HR `HenkanUma1..28`=発売後取消（返還対象馬番）。これらの組合せで「取消/除外（予測対象外・返還）」と「競走中止（学習0）」を識別。**研究者が実データで正確な識別条件を確定**
- **`n_odds_tanpuku` が単複共用**（`n_odds_fukusho` は非存在・Phase 1 確定事項）。オッズは Phase 2 では未使用（EV層は Phase 5）
- **Phase 1 で normalized 化済みなのは `n_race`/`n_uma_race` のみ。** `n_harai`(HR)・`n_hyosu` は raw 品質ゲート対象だが normalized 未実施。label ETL が raw 直読み（明示キャスト付き）するか、先に `normalized.n_harai` を作るかは Claude's Discretion（計画決定）
- **ラベルは予測目標の正であり、リーク防止と同等の聖域。** 突合ゲート通過率・`unresolved`/`inferred`/`dead_heat` の割合はレポートとして可視化し、`label_generation_version` でバージョン管理（§10.3・§19.1 再現性）

</specifics>

<deferred>
## Deferred Ideas

- **Phase 3:** `feature_availability` registry の本格運用（Phase 1-A allowlist test 含む）・PIT feature builder・Parquet snapshot（§12.4 メタデータ）。Phase 2 はラベル層のみ
- **Phase 4:** `fukusho_hit_validated` を目的変数に Phase 1-A モデル学習・`p_fukusho_hit` 算出。Phase 2 はラベル生成のみ
- **Phase 5:** 取消/除外の返還処理（`effective_stake=0`）・競走中止の `effective_stake=100`（§10.6・BACK-03）。固定ルール仮想購入シミュレータ。Phase 2 は status/flag のみ付与し、返還・損益計算は扱わない
- **Phase 8:** D-02 突合ゲート・D-04 エッジ分類・`sales_start_entry_count` 復元に対する対抗的監査テスト（TEST-01）。Phase 2 で実装するゲート/分類が監査対象
- **v2（将来マイルストーン）:** 障害競走・新馬戦のモデル対象化。Phase 2 では `is_model_eligible=False` でラベル付き保持のみ（§7.3「データ保存のみ」）。再実行なしで対象追加できるよう D-03 全件網羅が土台

None — discussion stayed within phase scope

</deferred>

---

*Phase: 2-Fukusho Labels*
*Context gathered: 2026-06-17*
