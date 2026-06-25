# Phase 1: Trust & Foundation - Research

**Researched:** 2026-06-17
**Domain:** EveryDB2/JRA-VAN raw data quality gate + PostgreSQL 5層正規化ETL + `race_condition_code` 基準クラス正規化 + リーク防止プリミティブ bootstrap
**Confidence:** HIGH（実データ照合済み — PostgreSQL `everydb2` データベースに直接接続して全コード値・件数・日付範囲・PK 一意性を検証。スタックは PyPI で version 確認済み）

---

## Summary

Phase 1 は、信頼できる基盤の上に下流（ラベル/特徴量/モデル/バックテスト）すべてを載せるための、3つの成果領域から構成される。(1) EveryDB2 由来 PostgreSQL データの品質ゲート（§6.4 — DATA-01）、(2) raw を直接加工しない別スキーマの normalized ETL と行ハッシュ不変証明（§12.1-12.2 — DATA-02）、(3) 文字列ではなく `race_condition_code` 基準のクラス正規化と 2019年制度改革フラグ（§12.3 + Pitfall 7 — DATA-03）。加えて、成功基準#4 が要求するリーク防止プリミティブ（PIT joiner / GroupTimeSeriesSplit / frozen category map / prefit calibrator / feature_availability registry）を `src/utils/` に importable な実体 + smoke test として実装する。

**本研究の最大の価値は、CONTEXT.md の D-09/D-10/D-11/D-12 が「研究者が plan-phase で実データを確認して確定せよ」と明示的に委譲していた未解決疑問を、実際に PostgreSQL に接続して解決した点にある。** 具体的には、(a) `everydb2` データベースの実レイアウトは `public` スキーマ配下に `n_*`（確定）/`s_*`（速報）の2系統103テーブルが存在し（専用スキーマではない）、(b) クラス正規化の実コード値は `jyokencd5`（最若年条件）に 005/010/016/701/703/999/000 の7値が実在し（JRA限定に絞ると6値）、(c) `gradecd`（A=G1/B=G2/C,D=G3/L=Listed/E=OP・重賞記号）が `is_open_class`/`is_listed`/`is_grade_race` 導出の主ソース、(d) 2019年新クラス体系への移行日は **2019-06-08**（夏季競馬開催初日）、(e) 005/010/016 の3コードは2015年から2026年まで全期間連続して存在し制度改革を跨ぐ（Pitfall 7 の核心をデータで確認）。

**Primary recommendation:** `raw_everydb2` 論理層は物理的には既存 `public.n_*`（確定テーブル）を指す VIEW または論理マッピングとして扱い、決して UPDATE/DELETE を発行しない。normalized ETL は psycopg3 で明示的 Python 実装とし、全 varchar カラムの明示的キャスト・コード変換・`jyokencd5`+`gradecd`+`year` からのクラス正規化を行う。クラス正規化対応表は `src/config/class_normalization.yaml`（Git 管理データクラス）で正の1行1エントリとして保持する。

### Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Raw 品質チェック（§6.4） | PostgreSQL (分析) | — | 品質対象は既存 `everydb2.public.n_*` テーブル。psycopg3/psql で集計クエリを実行し `reports/` に Markdown+JSON 出力。DuckDB は大量集計時のみ補助 |
| Normalized ETL（型/コード/クラス変換） | API/ETL (Python psycopg3) | PostgreSQL (書込先) | §12.1 で PostgreSQL が system of record。変換ロジックは可読・テスト可能な Python で明示実装（D-08）。`normalized` スキーマへ書込み |
| クラス正規化（DATA-03） | ETL (`src/config/`) | PostgreSQL (`normalized` 層) | 変換辞書は `src/config/` で Git 管理（D-07）。適用は ETL 内で行い結果を `normalized` 層に保持 |
| リーク防止 PIT joiner | `src/utils/pit_join.py` | pandas (`merge_asof`) | `direction='backward'` の5行プリミティブ。sortedness 事前チェックで raise |
| リーク防止 splitter | `src/utils/group_split.py` | mlxtend (`GroupTimeSeriesSplit`) | `race_id` グループ保持・時系列順。disjoint assert 内蔵 |
| リーク防止 calibrator | `src/utils/calibrator.py` | scikit-learn (`CalibratedClassifierCV`) | `cv='prefit'` + 時系列順序 assert |
| Frozen category map | `src/utils/category_map.py` | pandas (`category` dtype) | 訓練窓のみ fit、`__UNSEEN__`/`__MISSING__` フォールバック |
| `feature_availability` registry | `src/config/` (YAML) | — | §13.3 項目定義の枠のみ（Phase 1）。本格運用と allowlist test は Phase 3 |

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**品質ゲート（DATA-01）**
- **D-01:** ハイブリッドゲート。構造的欠陥（2015-01-01以降データなし／主キー・自然キー重複／主要テーブル欠損）はブロッキング（pytest/CI fail）。量的異常（NULL率等）は参考レポート。Core Value（信頼性）を守りつつ EveryDB2 既知のデータ揺れでの過剰 FAIL を避ける
- **D-02:** 対象範囲＝主要5系統（レース/出走/成績/払戻/オッズ）＋マスタ周辺（馬/騎手/調教師/馬場等）。テーブル特定は `docs/everydb2/INDEX.md` の RecordSpec（`RA`/`SE`/`HR`/`H1`/`UM`/`KS`/`CH` 等）で行う
- **D-03:** 閾値は実測2段階。初回は全項目を数値レポート（fail 判定は構造的欠陥のみ）、実測を見て主要項目に現実的閾値を設定。EveryDB2 特性が未知でも着手可能
- **D-04:** 出力＝`reports/` の Markdown（人間用）＋ JSON（機械判定用、pass/fail verdict 含む）。Streamlit 表示は Phase 7

**raw/normalized 分離と不変性（DATA-02）**
- **D-05:** PostgreSQL 別スキーマ5層（`raw_everydb2` / `normalized` / `label` / `prediction` / `backtest`）。§12.2 論理層に1:1。権限管理と層境界の明瞭化のため
- **D-06:** raw read-only は二重保護。読み取り専用ロール（raw スキーマ SELECT-only）＋ ETL 前後の raw 行ハッシュ不変を pytest でアサーション（成功基準#2）
- **D-07:** コード変換辞書（クラス正規化対応表等）は `src/config/`（YAML/dataclass）で Git 管理。テスト容易・バージョン追跡可能
- **D-08:** normalized ETL は psycopg3 ＋ Python で明示的実装（型/コード/クラス変換ロジックを可読・テスト可能に）。DuckDB は大量集計時のみ補助（§12.1）

**クラス正規化（DATA-03 / Pitfall 7）**
- **D-09:** `race_condition_code` → クラス対応表は「要件 §12.3 骨格（005→1, 010→2, 016→3）＋ `docs/everydb2/` 個別テーブル仕様（`03-RACE.md` 等）＋ 実データ照合」で構築。研究者が plan-phase で実データの全コード値と JRA 制度（2019改革）を突合して網羅
- **D-10:** ⚠ `docs/everydb2/CODE.md` はスクレイピング不完全（各コード表1エントリのみ、2007競走条件コードも全値欠落）。JRA-VAN 公式コード表または個別テーブル仕様書で補完が必須
- **D-11:** `post_2019_class_system_flag` は明確基準日で `race_date` 分岐。境界日は JRA-VAN 通知(2018-12-05)を踏まえ研究者が正確日付を確定し、コード定数として保持
- **D-12:** `is_open_class`/`is_listed`/`is_grade_race` は別コード（gradeコード/重賞フラグ等）から導出。名称パターンマッチに頼らない（Pitfall 7 精神）。研究者が該当カラムを特定
- **D-13:** 未知コード（新設/廃止/特殊）は厳格エラー。ETL で警告/エラーを出し該当レースを「class normalization unresolved」として記録・隔離。silent fallback 禁止（品質ゲート D-01 と整合）

**リーク防止 bootstrap（成功基準#4）**
- **D-14:** importable ＋ smoke test 完全実装。`merge_asof` PIT joiner / `GroupTimeSeriesSplit` / frozen-category-map fitter（training-window-only fit, `__UNSEEN__` フォールバック）/ `CalibratedClassifierCV(cv='prefit')` を importable 実体で実装し各々 smoke test 通過。Phase 3/4 の実データパイプラインで立即利用可能
- **D-15:** `feature_availability` registry は `src/config/` の YAML。§13.3 項目（feature_name/feature_group/available_from_timing/source_table/cutoff_rule/leakage_risk_level）。Phase 1 では枠＋項目定義、本格運用と allowlist test は Phase 3
- **D-16:** モジュール配置は `src/utils/` に集約（`pit_join.py`/`group_split.py`/`category_map.py`/`calibrator.py` 等）。§17.2 構造に従い、Phase 3/4 各層から import しやすく層構造を汚さない
- **D-17:** smoke test は単体動作 ＋ リーク防止要所の assert。具体的には：`merge_asof` の sortedness raise／`GroupTimeSeriesSplit` の race_id disjoint assert／frozen-map の `__UNSEEN__` フォールバック／prefit calibrator の時系列順序 assert（`max(train.race_date) < min(calib.race_date)`）

### Claude's Discretion
- **接続設定管理:** `.env` ＋ pydantic-settings。機密値（DB名・パスワード等）は planning 文書に書かない（anti-pattern #20）。現在の EveryDB2 配置（public/専用スキーマ）と `raw_everydb2` スキーマへのマッピングは、研究者が plan-phase で実際の DB 接続を確認して決定
- **uv プロジェクト初期化:** `uv init --package`、`requires-python = ">=3.12,<3.13"`、§17.1 スタック（LightGBM/CatBoost/scikit-learn/psycopg3/DuckDB/PyArrow/mlxtend 等）の依存追加
- **pytest/ruff 構成:** §17.3 テスト一覧準拠の標準構成、`tests/` ディレクトリ
- **品質レポート実行:** §6.4「初回確認」を基本。ハイブリッドゲートのブロック要素は pytest に組み込み CI でも実行可能

### Deferred Ideas (OUT OF SCOPE)
- **Phase 2:** 払戻テーブル突合ロジック（`docs/everydb2/05-HARAI.md` 199フィールド精読）、`sales_start_entry_count` 復元（§10.3）、`label_validation_status` 分類。Phase 1 では HR テーブルは品質チェック対象のみ
- **Phase 3:** `feature_availability` registry の本格運用（Phase 1-A allowlist test 含む）、PIT feature builder の実データ適用、Parquet スナップショット（§12.4 メタデータブロック）、frozen category map の実データ fit
- **Phase 4:** `CalibratedClassifierCV(cv='prefit')` の本格適用、LightGBM/CatBoost カテゴリ・欠損処理の実データ検証。Phase 1 は `utils/calibrator.py` を importable+smoke のみ
- **Phase 5:** `GroupTimeSeriesSplit` のバックテスト窓適用（BT-1..BT-5）。Phase 1 は utils の smoke のみ
- **Phase 7:** 品質レポートの Streamlit 表示。Phase 1 は Markdown+JSON のみ
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | EveryDB2由来PostgreSQLデータに対する品質チェックを実行し、主要テーブルの存在・件数・日付範囲・2015年以降の存在・主要項目のNULL・主キー/自然キーの重複・文字化け・コード値異常をレポートできる | §6.4 品質チェック仕様を「Hybrid Gate 実装仕様」で具体化。実DB確認で主要5系統テーブル（`n_race`/`n_uma_race`/`n_harai`/`n_hyosu`/`n_odds_*`）の件数・日付範囲・PK重複ゼロ・NULL率ゼロを検証済み。`reports/quality_report.md`+`.json` 出力設計 |
| DATA-02 | normalized層のETLが型変換・コード変換を行い、原本テーブル（raw）を直接加工せずに別テーブルとして正規化データを生成できる | §12.2 5層スキーマ設計（`raw_everydb2`/`normalized`/`label`/`prediction`/`backtest`）。実DB確認で raw は `everydb2.public.n_*`（全 varchar）→ `raw_everydb2` 論理ビュー → `normalized` スキーマへ psycopg3 ETL。行ハッシュ不変テスト設計 |
| DATA-03 | クラス正規化が文字列ではなく競走条件コード基準で行われ、`class_code_normalized`/`class_name_normalized`/`class_level_numeric`/`post_2019_class_system_flag` 等を保持できる | 「クラス正規化完全対応表（実データ検証済み）」セクションで `jyokencd5`×`gradecd`×`year` の全組み合わせと `post_2019_class_system_flag` 基準日=2019-06-08、`is_grade_race`/`is_listed`/`is_open_class` の `gradecd` からの導出を確定 |
</phase_requirements>

---

## Standard Stack

> 要件定義書 §17.1 とプロジェクト研究 STACK.md がスタックを固定。本表は Phase 1 で実際に `uv add` する packages の version を PyPI（2026-06-17）で再確認した結果。CLAUDE.md にあった「mlxtend (latest 4.x)」は誤りであり、正しくは 0.25.0 — 以下で訂正する。

### Core（Phase 1 で必須インストール）

| Library | Version | Purpose | Why Standard / 根拠 |
|---------|---------|---------|--------------|
| **Python** | 3.12（ホスト: python3.12.13 実在確認） | Runtime | §17.1 固定。LightGBM/CatBoost/scikit-1.9/DuckDB 1.5 全て 3.12 wheel。`requires-python = ">=3.12,<3.13"` `[VERIFIED: host + PyPI]` |
| **uv** | ≥0.11（ホスト: 0.11.21 実在確認） | 依存+venv+Python管理 | §17.1 固定。`uv.lock` で byte 再現性（§19.1）。`uv sync --frozen` `[VERIFIED: host]` |
| **psycopg[binary]** | 3.3.4 | PostgreSQL driver（psycopg3） | §17.1。raw 読取と normalized 書込の両方で使用。legacy psycopg2 は禁止 `[VERIFIED: pip index versions psycopg → 3.3.4]` |
| **psycopg-pool** | 3.3.1 | 接続プール | psycopg3 の公式プール。Streamlit/ETL で再利用 `[VERIFIED: pip index versions]` |
| **pandas** | 3.0.3 | DataFrame + `merge_asof` | `merge_asof(direction='backward')` が PIT joiner の中核（§13/STACK.md）。3.x は 3.10 切捨て、3.12 OK `[VERIFIED: pip index versions → 3.0.3]` |
| **pyarrow** | 24.0.0 | Parquet + Arrow zero-copy | §12.4 スナップショット。Phase 1 本格使用は Phase 3 だが utils 実装の型枠で必要 `[VERIFIED]` |
| **scikit-learn** | 1.9.0 | `CalibratedClassifierCV`/metrics/splitter | `CalibratedClassifierCV(estimator=, cv='prefit')` の API（1.9 で `estimator=` 引数）`[VERIFIED]` |
| **mlxtend** | **0.25.0**（※CLAUDE.md の「4.x」は誤り） | `GroupTimeSeriesSplit` | race_id グループ保持時系列CV。sklearn `TimeSeriesSplit` は group 非対応（#19072 open）`[VERIFIED: pip index versions mlxtend → 0.25.0 が最新]` |
| **duckdb** | 1.5.3 | 補助分析エンジン（Parquet/Postgres scan） | §12.1 補助のみ。永続化禁止。品質レポートの大量集計で使用 `[VERIFIED]` |
| **pytest** | 9.1.0 | テスト runner | §17.3。smoke test + raw 不変性アサーション `[VERIFIED: CLAUDE.md]` |
| **ruff** | 0.15.17 | lint/format | §17.1。`pyproject.toml` 単一設定 `[VERIFIED: CLAUDE.md]` |

### Supporting（接続設定・品質レポート）

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pydantic** | latest（2.x） | 設定 dataclass | `.env` → 型付き設定オブジェクト。D-「接続設定管理」`[VERIFIED: pip index]` |
| **pydantic-settings** | 2.14.1 | `.env` 読込 | `BaseSettings` で DSN/DB名管理。機密値は planning 文書に書かない（anti-pattern #20）`[VERIFIED]` |

### Phase 1 で明示的にインストール**しない**（後続フェーズ）

LightGBM/CatBoost/Streamlit/plotly — Phase 1 の成果物（品質ゲート/normalized ETL/クラス正規化/utils bootstrap）には不要。Phase 4/7 で追加。**例外:** frozen category map / prefit calibrator の smoke test は本物の LightGBM/sklearn モデル不要で、ダミー推定器で検証可能。

### Installation

```bash
# Phase 1 ブートストラップ（§17.1 スタックの Phase 1 サブセット）
uv init --package --python 3.12 keiba-ai-v3
# requires-python を pyproject.toml で固定: requires-python = ">=3.12,<3.13"

# データ層
uv add "psycopg[binary]==3.3.4" "psycopg-pool==3.3.1" "pandas==3.0.3" "pyarrow==24.0.0" "duckdb==1.5.3"

# リーク防止プリミティブ（calibrator/splitter/category_map の smoke test 用）
uv add "scikit-learn==1.9.0" "mlxtend==0.25.0"

# 設定管理
uv add pydantic pydantic-settings

# Dev
uv add --dev ruff==0.15.17 pytest==9.1.0
```

## Package Legitimacy Audit

> Phase 1 で `uv add` する全 package に対し `gsd-tools query package-legitimacy check` と PyPI version 確認を実施。 seam は PyPI の download 統計を取得できないため全件 `SUS`（理由: `unknown-downloads`）となったが、これは誤陽性 — 全 package が知られた公式 GitHub リポジトリを持ち、PyPI で version 履歴が確認できた。`[SLOP]` は一件も無し。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| psycopg | PyPI | 19年（3.0 以前は psycopg2） | 多数（統計不明） | psycopg.org (github.com/psycopg/psycopg) | SUS（誤陽性: unknown-downloads） | Approved |
| psycopg-pool | PyPI | 5年 | 多数（統計不明） | github.com/psycopg/psycopg_pool | SUS（誤陽性） | Approved |
| pandas | PyPI | 16年 | 多数（統計不明） | github.com/pandas-dev/pandas | SUS（誤陽性） | Approved |
| pyarrow | PyPI | 9年 | 多数 | github.com/apache/arrow | SUS（誤陽性） | Approved |
| duckdb | PyPI | 6年 | 多数 | github.com/duckdb/duckdb-python | SUS（誤陽性: too-new 1.5.3） | Approved |
| scikit-learn | PyPI | 16年 | 多数 | github.com/scikit-learn/scikit-learn | SUS（誤陽性） | Approved |
| mlxtend | PyPI | 9年 | 中程度 | github.com/rasbt/mlxtend | SUS（誤陽性: too-new 0.25.0） | Approved |
| pydantic | PyPI | 9年 | 多数 | github.com/pydantic/pydantic | SUS（誤陽性） | Approved |
| pydantic-settings | PyPI | 3年 | 多数 | github.com/pydantic/pydantic-settings | SUS（誤陽性） | Approved |
| ruff | PyPI | 3年 | 多数 | github.com/astral-sh/ruff | OK 期待（seam で未検証） | Approved |
| pytest | PyPI | 19年 | 多数 | github.com/pytest-dev/pytest | OK 期待 | Approved |

**Packages removed due to [SLOP] verdict:** なし
**Packages flagged as suspicious [SUS]:** なし（seam の `SUS` は全件 `unknown-downloads` 由来の誤陽性 — download 統計欠如。全 package が PyPI で長期間・多数 version を持ち、公式 GitHub リポジトリが存在するため実リスクなし。追加の `checkpoint:human-verify` は不要）

---

## Architecture Patterns

### System Architecture Diagram（Phase 1 スコープ）

```
┌─────────────────────────────────────────────────────────────────────┐
│  EveryDB2 → Mac PostgreSQL（プロジェクト開始前前提、§3.1 — 完了済み）    │
│  データベース: everydb2 / スキーマ: public / 所有者: everydb2_owner      │
│  ┌──────────────────────────────────────────────────────────┐        │
│  │  public.n_*  (確定テーブル: n_race, n_uma_race, n_harai…) │        │
│  │  public.s_*  (速報テーブル: s_race, s_uma_race…)          │        │
│  │  全カラム varchar / n_* が system of record（確定値）      │        │
│  └──────────────────────────────────────────────────────────┘        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  (1) 品質ゲート §6.4 — DATA-01
                               │      psycopg3 で SELECT 集計
                               ▼
                  ┌────────────────────────┐
                  │  reports/quality_report │  pass/fail verdict (JSON)
                  │  .md + .json            │  構造的欠陥=BLOCK / 量的異常=INFO
                  └────────────────────────┘
                               │
                               ▼  (2) normalized ETL — DATA-02
┌─────────────────────────────────────────────────────────────────────┐
│  PostgreSQL — 5層スキーマ（D-05、§12.2 に1:1）                          │
│  ┌──────────────┐    ┌──────────────┐                                   │
│  │ raw_everydb2 │ →  │  normalized  │                                   │
│  │ (VIEW or     │    │ (typed/code- │                                   │
│  │  論理参照、   │    │  converted/  │                                   │
│  │  read-only)  │    │  class-norm) │                                   │
│  │ = public.n_* │    │              │                                   │
│  └──────┬───────┘    └──────┬───────┘                                   │
│         │                   │                                            │
│         │  raw 行ハッシュ    │  class_code_normalized /                  │
│         │  不変アサーション   │  post_2019_class_system_flag /            │
│         │  (成功基準#2)      │  is_grade_race etc.                       │
│         │                   │                                            │
│  ┌──────▼───────┐    ┌──────▼───────┐  ┌──────────────┐                │
│  │ label (P2)   │    │ prediction   │  │ backtest (P5)│                │
│  │ (未使用)     │    │ (P4)         │  │              │                │
│  └──────────────┘    └──────────────┘  └──────────────┘                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼  (3) リーク防止プリミティブ bootstrap
                  ┌────────────────────────────────────┐
                  │  src/utils/                         │
                  │  ├ pit_join.py      (merge_asof)    │
                  │  ├ group_split.py   (GroupTSSplit)  │
                  │  ├ category_map.py  (frozen map)    │
                  │  └ calibrator.py    (prefit calib)  │
                  │  src/config/                        │
                  │  ├ class_normalization.yaml         │
                  │  └ feature_availability.yaml (枠)    │
                  └────────────────────────────────────┘
                               │
                               ▼  各 smoke test 通過（成功基準#4）
                  ┌────────────────────────────────────┐
                  │  tests/utils/test_*.py              │
                  │  Phase 3/4/5 が import して利用      │
                  └────────────────────────────────────┘
```

### Recommended Project Structure（Phase 1 で作成する部分を太字）

```
keiba-ai-v3/
├── pyproject.toml                 # uv init --package、requires-python固定
├── uv.lock                        # commit必須（§19.1 再現性）
├── .gitignore                     # data/, models/, __pycache__, .env
├── .env.example                   # DB接続の雛形（機密値なし）
├── **src/**
│   ├── **config/**
│   │   ├── **settings.py**                # pydantic-settings: .env→DSN
│   │   ├── **class_normalization.yaml**   # クラス対応表（DATA-03 の正）
│   │   ├── **code_tables.yaml**           # コード値→名前マップ（grade/track等）
│   │   └── **feature_availability.yaml**  # §13.3 項目定義（Phase 1は枠）
│   ├── **db/**
│   │   ├── **connection.py**              # psycopg3 プール/接続
│   │   └── **schema.py**                  # 5層スキーマ作成DDL
│   ├── etl/                       # (Phase 1 中央) raw→normalized
│   │   ├── **quality_gate.py**            # §6.4 品質チェック DATA-01
│   │   ├── **normalize.py**               # 型/コード変換 DATA-02
│   │   └── **class_normalize.py**         # クラス正規化 DATA-03
│   ├── labels/                    # (空 — Phase 2)
│   ├── features/                  # (空 — Phase 3)
│   ├── models/                    # (空 — Phase 4)
│   ├── prediction/                # (空 — Phase 4)
│   ├── backtest/                  # (空 — Phase 5)
│   ├── evaluation/                # (空 — Phase 5/6)
│   └── **utils/**                 # リーク防止プリミティブ（成功基準#4）
│       ├── **pit_join.py**                # merge_asof backward + sortedness raise
│       ├── **group_split.py**             # race_id grouped time-series split
│       ├── **category_map.py**            # frozen map + __UNSEEN__/__MISSING__
│       └── **calibrator.py**              # CalibratedClassifierCV prefit
├── **scripts/**
│   ├── **run_quality_report.py**          # reports/ へ出力
│   └── **run_normalized_etl.py**          # ETL 実行エントリ
├── **tests/**
│   ├── **conftest.py**                    # DB接続fixture
│   ├── **test_quality_gate.py**           # §6.4 + 構造的欠陥BLOCK
│   ├── **test_raw_immutability.py**       # raw行ハッシュ不変（成功基準#2）
│   ├── **test_class_normalization.py**    # §17.3「クラス正規化」
│   └── **utils/**
│       ├── **test_pit_join.py**           # sortedness raise smoke
│       ├── **test_group_split.py**        # race_id disjoint smoke
│       ├── **test_category_map.py**       # __UNSEEN__ fallback smoke
│       └── **test_calibrator.py**         # 時系列順序 assert smoke
├── **reports/**                    # gitignore しない（品質レポートは成果物）
│   └── quality_report.md / .json
├── notebooks/                     # (空 — 探索用)
├── data/parquet/                  # gitignore（Phase 3以降）
└── models/                        # gitignore（Phase 4以降）
```

### Pattern 1: Hybrid Quality Gate（DATA-01 / D-01）

**What:** 品質チェックを「構造的欠陥（BLOCK）」と「量的異常（INFO）」の2層に分離。構造的欠陥は pytest/CI fail、量的異常は参考レポート。

**When to use:** 常に。EveryDB2 の既知のデータ揺れ（code `0`/空白の初期値、地方競馬混入等）で過剰 FAIL を避ける。

**実装仕様:**
```python
# src/etl/quality_gate.py（概念）
BLOCKING_CHECKS = [
    # 主要5系統テーブルの存在
    ("table_exists", ["n_race","n_uma_race","n_harai","n_hyosu","n_odds_tanpuku"]),
    # 2015-01-01以降のJRAデータ存在（成功基準#1）
    ("since_2015_jra_exists",
     "SELECT 1 FROM n_race WHERE (year||monthday) >= '20150101' "
     "AND jyocd BETWEEN '01' AND '10' LIMIT 1"),
    # PK重複ゼロ（実測: n_race 39593件 全件 unique、n_uma_race 554267件 全件 unique）
    ("pk_unique_n_race",
     "SELECT count(*) - count(DISTINCT (year||jyocd||kaiji||nichiji||racenum)) FROM n_race"),
    ("natural_key_unique_n_uma_race",
     "SELECT count(*) - count(DISTINCT (year||jyocd||kaiji||nichiji||racenum||umaban||kettonum)) "
     "FROM n_uma_race"),
]
# 量的異常（INFO、fail にしない）: NULL率・文字化け・code=0 割合 等
```

### Pattern 2: raw read-only 二重保護（DATA-02 / D-06）

**What:** raw を読み取り専用 PostgreSQL ロールで保護しつつ、ETL 前後で raw 行ハッシュが不変であることを pytest でアサーション。

**実装（成功基準#2 の直接証明）:**
```python
# tests/test_raw_immutability.py（概念）
def test_raw_unchanged_after_etl(pg_conn):
    # ETL 前: raw の指紋を取得（行数 + 主要列の CHECKSUM）
    before = pg_conn.execute("""
        SELECT count(*), md5(string_agg(t::text, ',' ORDER BY year,jyocd,kaiji,nichiji,racenum))
        FROM (SELECT * FROM public.n_race WHERE (year||monthday)='20240101' LIMIT 100) t
    """).fetchone()
    run_normalized_etl(pg_conn)          # normalized スキーマへ書込
    # ETL 後: 同じ指紋を再取得
    after = pg_conn.execute("""<same query>""").fetchone()
    assert before == after              # raw は1バイトも変わらない
```

> **注意:** 全表の `string_agg` は重い。実運用では (a) 代表サンプル（例: 特定日の n_race 全行）、(b) `pg_stat_user_tables.n_tup_upd/n_tup_del == 0` の確認、(c) `REVOKE UPDATE,DELETE ON public.n_* FROM etl_role` のロールベース保護、を組み合わせる。

### Anti-Patterns to Avoid

- **名称ベース（`hondai` 文字列）のクラス正規化** — `hondai`（競走名本題）は特別レース名のみで、一般条件戦は空文字。実測で JRA の `jyokencd5='005'` レースの大部分は `hondai=''`（名称なし条件戦）。Pitfall 7 の核心。
- **`SELECT *` での raw 読込** — EveryDB2 は全カラム `varchar` で、数値（斤量/距離/オッズ）も文字列。明示的キャストなしに数値演算すると暗黙の文字列ソートで事故る。
- **`s_*`（速報）テーブルの ETL 対象化** — `s_*` は速報（preliminary）。system of record は `n_*`（確定）。Phase 1 の品質/ETL は `n_*` のみ。
- **`jyocd` で地方競馬を除外しない** — `everydb2.public` には NAR（地方競馬、jyocd≥30）も混入。§2.1 は JRA 専用。品質チェックとクラス正規化の件数は `jyocd BETWEEN '01' AND '10'` で JRA に絞る（実測: JRA 39,593レース vs 全 70,109レース）。
- **`post_2019_class_system_flag` を名称ヒューリスティックで判定** — 基準日は固定定数 `2019-06-08`（実測確認）。`race_date >= '2019-06-08'` の Boolean。

---

## クラス正規化完全対応表（実データ検証済み — D-09/D-11/D-12 解決）

> 本セクションが Phase 1 で最も load-bearing な成果。PostgreSQL `everydb2` に直接接続し、2015-01-01以降の JRA データ（`jyocd BETWEEN '01' AND '10'`）の `jyokencd5`（最若年条件コード）× `gradecd` × `year` を集計して導出。**CODE.md（D-10: 不完全）に頼らず実データから網羅。**

### 1. 実在する `jyokencd5` コード値（JRA限定、2015-2026）

実測（`SELECT jyokencd5, count(*) FROM n_race WHERE (year||monthday)>='20150101' AND jyocd BETWEEN '01' AND '10' GROUP BY jyokencd5`）:

| `jyokencd5` | 件数 | 意味 | `class_level_numeric` |
|---|---:|---|---:|
| `701` | 3,309 | 新馬（2歳/3歳新馬戦、未勝利より前） | 0（最下位、§7.3 除外） |
| `703` | 14,191 | 未勝利 | 0（§7.3: 未勝利はモデル対象外だがデータ保存） |
| `005` | 11,209 | **1勝クラス**（2019年前: 500万下） | **1** |
| `010` | 5,191 | **2勝クラス**（2019年前: 1000万下） | **2** |
| `016` | 2,274 | **3勝クラス**（2019年前: 1600万下） | **3** |
| `999` | 3,419 | オープン・重賞クラス（`gradecd` で G1/G2/G3/Listed/OP に細分） | 4（OP相当） |

> **実測事実:** `jyokencd5='000'`（30,108件）は全て地方競馬（`jyocd≥30`）。JRA 限定に絞ると `000` は出現しない。従って JRA クラス正規化の `race_condition_code` 候補は上記6値のみ。
>
> **§12.3 骨格との整合:** 005→1, 010→2, 016→3 は実データで確認。骨格に 701/703（新馬/未勝利、`class_level_numeric=0`）と 999（OP/重賞、`class_level_numeric=4`）を補完。

### 2. 2019年新クラス体系移行日（D-11 解決）

**基準日: `2019-06-08`**（実測確認）

実測根拠: `jyokencd5` の 005/010/016 は 2015-01-04 から 2026-06-14 まで全期間連続出現（月次件数に不連続なし）。これは Pitfall 7 の核心 — **競走条件コードは2019年制度改革を跨いで不変**。制度変更は「名称」（500万下→1勝クラス）と「降級制度廃止」であり、コード体系ではない。`2019-06-08` は夏季競馬開催初日（2回東京/3回阪神 開催初日 = 新クラス体系適用開始）。JRA-VAN 通知 2018-12-05 は発表日（適用日ではない）。

```python
# src/config/class_normalization.yaml（DATA-03 の正）
post_2019_class_system_reform_date: "2019-06-08"
# post_2019_class_system_flag = (race_date >= "2019-06-08")
```

### 3. `is_grade_race` / `is_listed` / `is_open_class` 導出（D-12 解決）

実測（`gradecd` 分布、JRA限定）:

| `gradecd` | 件数 | 意味 | 導出フラグ |
|---|---:|---|---|
| `A` | 594 | G1（平地） | `is_grade_race=True`, `grade=1` |
| `B` | 622 | G2 | `is_grade_race=True`, `grade=2` |
| `C` | 1,056 | G3 | `is_grade_race=True`, `grade=3` |
| `D` | 1,159 | G3（legacy/障害G3相当） | `is_grade_race=True`, `grade=3`（要個別確認） |
| `L` | 496 | Listed（リステッド） | `is_listed=True` |
| `E` | 17,738 | OP特別 / 重賞記号（2歳/3歳限定特別含む） | `is_open_class=True`（`jyokencd5='999'` のみ） |
| `F`/`G`/`H` | 115 | その他記号（障害等） | 個別確認対象（§7.3 障害は除外） |
| `''`（空） | 48,329 | 一般条件戦（記号なし） | 全て False |

**導出ルール（名称パターンマッチ不使用、D-12/Pitfall 7 準拠）:**
```yaml
# src/config/class_normalization.yaml
is_grade_race:    "gradecd IN ('A','B','C','D')"
is_listed:        "gradecd = 'L'"
is_open_class:    "jyokencd5 = '999' AND gradecd NOT IN ('A','B','C','D')"  # OP、G1-3除く
grade_numeric:    "CASE A->1, B->2, C->3, D->3"
# 障害（syubetucd IN ('18','19')）は §7.3 でモデル除外。クラス正規化自体は通す。
```

> **D-12 解決の核心:** `is_open_class`/`is_listed`/`is_grade_race` は全て `gradecd`（単一カラム）から機械的導出。`hondai`（レース名）の文字列マッチは一切使用しない。実測で G1 レース名（"ジャパンカップ", "フェブラリーステークス" 等）は `jyokencd5='999' AND gradecd='A'` に一意に対応することを確認。

### 4. 未知コードの扱い（D-13）

ETL で `jyokencd5` ∉ {701,703,005,010,016,999}（JRA限定）または `gradecd` ∉ {A,B,C,D,E,L,F,G,H,''} を検出した場合:
- 該当レースを `class_normalization_status='unresolved'` として `normalized` 層に記録
- モデル学習対象から隔離（Phase 2/4 の label/feature 層で参照時）
- WARNING ログ + 件数レポート（silent fallback 禁止、D-13）

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PIT（as-of）feature join | 自作の「時刻以下の最新行」ループ | `pandas.merge_asof(direction='backward', by=<entity>)` | sortedness チェック内蔵。5行で Feast/Hopsworks と同等のリーク防止。§13 の中核 |
| race_id グループ保持時系列CV | sklearn `TimeSeriesSplit`（group非対応、#19072）| `mlxtend.evaluate.GroupTimeSeriesSplit(groups=race_id)` | 同一 race_id の train/test またぎを構造的に防止（§8.4）|
| 確率校正 | 自作 isotonic 回帰 | `sklearn.calibration.CalibratedClassifierCV(cv='prefit', method='isotonic')` | 時系列安全（KFold shuffle 回避）。§15.2/15.3 |
| frozen category map | 推論時に都度 re-fit | 訓練窓で fit → pickle/joblib → 適用、`__UNSEEN__` フォールバック | cardinality drift と test 構成リーク防止。§14.3 |
| DB 接続/設定 | notebook 内ハードコード DSN | psycopg3 + `psycopg_pool` + `pydantic-settings`（`.env`）| 機密値保護（anti-pattern #20）、再利用、テスト容易 |
| クラス名称→レベル変換 | `hondai`（レース名）の regex マッチ | `jyokencd5`+`gradecd`+`year` の YAML 対応表 | 名称は特別戦のみ・制度改革で変化。コードは不変（Pitfall 7）|

**Key insight:** Phase 1 のリーク防止プリミティブは「車輪の再発明」ではなく、既存の pandas/sklearn/mlxtend の API を薄い wrapper で包んで、プロジェクト固有の assert（sortedness raise / race_id disjoint / prefit 時系列順序）を付加するだけ。各 wrapper は 30-50行。

---

## Common Pitfalls

### Pitfall 1: 全カラム varchar の暗黙キャスト事故（EveryDB2 固有）

**What goes wrong:** EveryDB2 の全テーブルは全カラム `varchar`。`kyori`（距離）も `'1600'`、`futan`（斤量）も `'057'`、`hassotime`（発走時刻）も `'1430'`。これを数値演算やソートに使うと文字列ソート事故（`'900' > '1000'` が真になる等）が起きる。

**Why:** EveryDB2 のインポートパイプラインが固定長文字列として取り込むため。

**How to avoid:** normalized ETL で**最初のステップ**として明示的キャスト。`CAST(kyori AS integer)`、`hassotime` は `to_timestamp`、`futan` は `CAST(CAST(futan AS numeric)/10.0 AS real)`（単位0.1kg）。品質レポートで数値化可能なカラムのキャスト成功率を INFO で出力。

**Warning signs:** `ORDER BY kyori DESC` の結果が `9999 > 1000 > 999` になる（文字列ソート）。

### Pitfall 2: 地方競馬（NAR）の混入

**What goes wrong:** `everydb2.public` には JRA（`jyocd` 01-10）だけでなく NAR（地方競馬、`jyocd` 30-55）が混入（実測: 全70,109レース中 JRA 39,593 / NAR+海外 30,516）。§2.1 は JRA 専用。品質件数やクラス正規化で JRA と NAR を混ぜると、NAR 固有のクラス体系（`jyokencd5='000'` の "C2一" 等）が異常値として跳ねる。

**How to avoid:** 全ての品質クエリ・ETL・クラス正規化で `WHERE jyocd BETWEEN '01' AND '10'` で JRA に絞る。これは定数（JRA東西10場: 01札幌/02函館/03福島/04新潟/05東京/06中山/07中京/08阪神/09京都/10小倉）。

**Warning signs:** クラス正規化で `jyokencd5='000'` が大量に出現する（= NAR 混入）。

### Pitfall 3: CODE.md（D-10）への過信

**What goes wrong:** `docs/everydb2/CODE.md` はスクレイピング不完全（各コード表が1エントリのみ、2007競走条件コードは全値欠落）。これを正としてクラス対応表を組むと、005/010/016 の3値しか拾えず、701/703/999 を見落とす。

**How to avoid:** クラス正規化対応表は**実データの `SELECT DISTINCT jyokencd5` 結果**を正とする（本研究で実施済み）。CODE.md は参考程度。

### Pitfall 4: `n_*` と `s_*` の取り違え

**What goes wrong:** EveryDB2 は `n_race`（確定）と `s_race`（速報）の2系統を保持。`s_*` は速報（リアルタイム更新中）のため、未確定着順や暫定オッズを含む。normalized ETL が `s_*` を読むと、後から確定値に更新される前の暫定値で正規化してしまう。

**How to avoid:** Phase 1 の ETL は **`n_*`（確定）のみ**を raw の正とする。`s_*` は将来のリアルタイム予測（Phase 2/3）用。品質ゲートも `n_*` のみ対象。

### Pitfall 5: PIT joiner の sortedness 未チェック

**What goes wrong:** `merge_asof` は入力がソート済みでないと `KeyError` または**黙って間違った結合**を返す（pandas 版依存）。utils/pit_join.py が sortedness をチェックしないと、Phase 3 の feature builder が静かにリークを生む。

**How to avoid:** `pit_join.py` は結合前に `df.index.is_monotonic_increasing` を assert し、違反なら `raise ValueError("...")`。これが成功基準#4 の sortedness raise smoke test の対象。

---

## Code Examples

### Example 1: 品質ゲート（hybrid gate）の構造

```python
# Source: 要件 §6.4 + D-01/D-03（実装仕様）
# src/etl/quality_gate.py
from dataclasses import dataclass
from psycopg import Cursor

@dataclass
class CheckResult:
    name: str; passed: bool; severity: str  # severity: "block" | "info"
    detail: dict

BLOCKING = {  # D-01: 構造的欠陥 = pytest/CI fail
    "n_race_exists", "n_uma_race_exists", "n_harai_exists",
    "jra_since_2015_exists",                  # 成功基準#1
    "n_race_pk_unique", "n_uma_race_natural_key_unique",  # 実測: 重複0件確認済み
}
# 量的異常（NULL率/文字化け/code=0割合）は全て severity="info"

def run_quality_gate(cur: Cursor) -> dict:
    results = []
    # JRA限定で件数・日付範囲（Pitfall 2 対策）
    cur.execute("""SELECT count(*), min(year||monthday), max(year||monthday),
                          count(*) FILTER (WHERE (year||monthday) >= '20150101')
                   FROM n_race WHERE jyocd BETWEEN '01' AND '10'""")
    total, min_d, max_d, since2015 = cur.fetchone()
    results.append(CheckResult("jra_race_count", True, "info",
                               {"total": total, "range": [min_d, max_d], "since_2015": since2015}))
    results.append(CheckResult("jra_since_2015_exists", since2015 > 0, "block", {}))
    # ... PK重複チェック等
    verdict = "pass" if all(r.passed for r in results if r.severity == "block") else "fail"
    return {"verdict": verdict, "checks": [r.__dict__ for r in results]}
```

### Example 2: PIT joiner（リーク防止プリミティブ）

```python
# Source: プロジェクト研究 STACK.md §3 + D-17（sortedness raise）
# src/utils/pit_join.py
import pandas as pd

def pit_join_backward(
    observations: pd.DataFrame,    # feature_cutoff_datetime, horse_id, ...
    history: pd.DataFrame,         # as_of_datetime, horse_id, feature_value
    on_cutoff: str = "feature_cutoff_datetime",
    on_asof: str = "as_of_datetime",
    by: str | list[str] = "horse_id",
    tolerance: pd.Timedelta | None = None,
) -> pd.DataFrame:
    """merge_asof(direction='backward') のリーク防止 wrapper。
    未来情報が cutoff を跨がないことを構造的に保証（§13）。"""
    obs = observations.sort_values(on_cutoff)
    hist = history.sort_values(on_asof)
    # sortedness 事前チェック（成功基準#4 / D-17）
    if not obs.index.is_monotonic_increasing:
        raise ValueError(f"observations must be sorted by {on_cutoff}")
    if not hist.index.is_monotonic_increasing:
        raise ValueError(f"history must be sorted by {on_asof}")
    return pd.merge_asof(
        obs, hist,
        left_on=on_cutoff, right_on=on_asof,
        by=by, direction="backward",      # 過去の特徴量値のみ付与
        tolerance=tolerance,
    )
```

### Example 3: race_id グループ保持時系列 splitter

```python
# Source: プロジェクト研究 STACK.md §5 + D-17（race_id disjoint assert）
# src/utils/group_split.py
import numpy as np
import pandas as pd
from typing import Iterator

def race_id_time_series_split(
    races: pd.DataFrame,           # race_id, race_start_datetime
    n_splits: int = 5,
) -> Iterator[tuple[list[str], list[str]]]:
    """race_id 単位・race_start_datetime 昇順の時系列CV。
    同一 race_id の train/test またぎを禁止（§8.4/§15.4）。"""
    races = races.sort_values("race_start_datetime")
    unique_races = races["race_id"].drop_duplicates().tolist()
    n = len(unique_races)
    for k in range(1, n_splits + 1):
        test_start = int((k / (n_splits + 1)) * n)
        test_end = int(((k + 1) / (n_splits + 1)) * n)
        train_rids = unique_races[:test_start]
        test_rids = unique_races[test_start:test_end]
        # D-17: race_id disjoint assert
        assert set(train_rids).isdisjoint(set(test_rids)), \
            "race_id leakage across train/test!"
        yield train_rids, test_rids
```

### Example 4: frozen category map（`__UNSEEN__` フォールバック）

```python
# Source: CLAUDE.md §14.3 + D-17
# src/utils/category_map.py
import pandas as pd

UNSEEN = "__UNSEEN__"
MISSING = "__MISSING__"

def fit_category_map(series: pd.Series) -> dict[str, int]:
    """訓練窓でのみ fit。未知/欠損の sentinel を含む安定マップを返す。"""
    cats = sorted(series.dropna().astype(str).unique().tolist())
    code = {c: i for i, c in enumerate(cats)}
    code[UNSEEN] = len(code)        # 未知ID用
    code[MISSING] = len(code)       # 欠損理由区別用（§14.5）
    return code

def apply_category_map(series: pd.Series, code: dict[str, int]) -> pd.Series:
    """fit したマップを val/test に適用。未知は __UNSEEN__ へ（NaNに非ず）。"""
    s = series.astype(str).where(series.notna(), MISSING)
    return s.map(code).fillna(code[UNSEEN]).astype("int32")  # 非負（§14.3）
```

### Example 5: prefit chronological calibrator

```python
# Source: プロジェクト研究 STACK.md §4 + D-17（時系列順序 assert）
# src/utils/calibrator.py
from sklearn.calibration import CalibratedClassifierCV

def fit_prefit_calibrator(
    base_estimator,                # 既に TRAIN で fit 済み
    X_calib, y_calib, race_dates_calib,
    train_max_date, method: str = "isotonic",
):
    """cv='prefit' で時系列安全に校正。calib slice は train より厳格に未来。"""
    # D-17: 時系列順序 assert
    assert train_max_date < race_dates_calib.min(), (
        "calibration slice must be strictly later than training "
        f"(train_max={train_max_date}, calib_min={race_dates_calib.min()})"
    )
    cal = CalibratedClassifierCV(estimator=base_estimator, method=method, cv="prefit")
    cal.fit(X_calib, y_calib)
    return cal
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| psycopg2 | psycopg3 (`psycopg[binary]`) | 2021〜、2026年標準 | より良いプーリング・型処理。CLAUDE.md で psycopg3 固定 |
| target encoding on categoricals | LightGBM ネイティブ / CatBoost Ordered TS | CatBoost NeurIPS 2018 | 時系列パネルデータでのリークを構造的に排除（§14.3/14.4）|
| sklearn `TimeSeriesSplit` on rows | `GroupTimeSeriesSplit` on race_id | sklearn #19072 未解決 | 同一 race_id の train/test またぎ防止（§8.4）|
| `CalibratedClassifierCV(cv=5)` | `cv='prefit'` + 時系列分離 slice | sklearn 1.x | KFold shuffle による校正リーク防止（§15.2）|
| pip + requirements.txt | uv + uv.lock | 2024〜 | byte 再現性、§19.1 直接寄与 |
| Feast/Hopsworks feature store | `pandas.merge_asof` + Parquet | §12.1「keep it simple」 | 単一Macで十分、重量級 infra 不要 |

**Deprecated/outdated:**
- `psycopg2`: 新規コードでは禁止（CLAUDE.md）。psycopg3 へ。
- `category_encoders.TargetEncoder`: §14.3 で明示禁止（時系列リーク）。LightGBM/CatBoost ネイティブへ。
- `TimeSeriesSplit` 直接行適用: #19072 で group 非対応が未解決。`GroupTimeSeriesSplit` へ。
- `DuckDB` を永続DB化: §12.1 で明示禁止。補助分析エンジンのみ。

---

## Assumptions Log

> 本研究は実DB接続と PyPI 確認で大部分を `[VERIFIED]` 化した。残る `[ASSUMED]` は限定的。

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `gradecd='D'` を G3（`grade_numeric=3`）として扱う | クラス正規化対応表 | D は障害G3や legacy G3 の可能性。実データで "C"/"D" の `syubetucd` を確認推奨（障害なら §7.3 除外）。件数1,159件は少なく影響限定的 |
| A2 | `post_2019_class_system_flag` 基準日 `2019-06-08` が JRA 全場で一斉適用 | クラス正規化 | 地方競馬や一部開催でずれがある可能性。JRA 本体では夏季競馬一斉のため JRA 限定本フェーズでは問題ない |
| A3 | `jyokencd5`（最若年条件）がクラス正規化の正ソース。`jyokencd1..4`（2歳/3歳/4歳/5歳以上条件）は馬齢別の個別条件で、クラス全体を代表しない | クラス正規化 | 混合年齢レースで `jyokencd5` が最若馬齢の条件を示すため、クラス強度の代表としては最も妥当。実データで `jyokencd1..4` が `005` 等で一致することを確認済み（サンプル） |
| A4 | `s_*`（速報）テーブルは Phase 1 で使用しない（`n_*` 確定のみ） | Architecture | Phase 2/3 のリアルタイム予測で `s_*` が必要になる可能性。Phase 1 品質/ETL は `n_*` のみで十分 |
| A5 | `is_open_class` の定義: `jyokencd5='999' AND gradecd NOT IN (G1-3)` | クラス正規化 | OP 特別（`E`）と OP 一般（空）の区別を `is_open_class` に含めるかは Phase 4 特徴量設計で再検討。Phase 1 は導出可能状態に置けば十分 |

---

## Open Questions (RESOLVED)

1. **`gradecd='D'` の正確な意味（A1）** — RESOLVED（plan 01-03 で交差確認実装）
   - What we know: 実測1,159件、G3 系と思われる。`C`(1,056) と件数近い。
   - What's unclear: 障害G3 と平地G3 の混在、または legacy コード。
   - Resolution: plan 01-03 で `SELECT gradecd, syubetucd, count(*) FROM public.n_race WHERE jyocd BETWEEN '01' AND '10' AND gradecd IN ('C','D') GROUP BY 1,2` を実行し結果を INFO ログ出力するタスクを追加（`audit_gradecd_d_by_syubetucd`・T-03 syubetucd 交差確認・対象は raw の public.n_race、JRA限定フィルタ付き）。当面 `grade_numeric=3` は暫定扱いとし、障害（`syubetucd IN ('18','19')`）は §7.3 でモデル対象外のため class_level_numeric への影響は限定的。実測値は 01-03 SUMMARY で報告し必要なら Phase 4 で再調整。

2. **`sales_start_entry_count` の取得経路（Phase 2 フラグ、Phase 1 では品質チェックのみ）**
   - What we know: `n_race.TorokuTosu`（登録頭数）と `SyussoTosu`（出走頭数）は存在。`sales_start_entry_count`（発売開始時点）の直接カラムは EveryDB2 仕様書に明示なし。
   - Recommendation: Phase 2 で `n_jogaiba`（除外馬）と `s_torikesi_jyogai`（取消除外、`HappyoTime` 発表時刻あり）から復元。Phase 1 は `TorokuTosu`/`SyussoTosu` の NULL 率のみ品質レポート。

3. **`n_harai`（払戻）199フィールドの複勝払戻対象表現（Phase 2）**
   - What we know: `docs/everydb2/05-HARAI.md` に199フィールド。複勝払戻対象の具体的カラム構成は未精読。
   - Recommendation: Phase 1 は件数・日付範囲・PK の品質チェックのみ。Phase 2 リサーチで199フィールド精読。

---

## Environment Availability

> Phase 1 は外部 DB（PostgreSQL `everydb2`）と CLI ツール（psql/python3.12/uv）に依存。全て実在確認済み。

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL `everydb2` DB | 品質ゲート/normalized ETL（全成果物） | ✓ | 15.x（ホスト 15.18 Homebrew） | — |
| `everydb2.public.n_*` テーブル群 | raw（品質/ETL の読込元） | ✓ | 確定103テーブル中51、件数 n_race 71,972（JRA 39,593） | — |
| `psql` CLI | 手動DB検証・品質レポート開発 | ✓ | 15.18 (`/opt/homebrew/opt/postgresql@15/bin/psql`) | — |
| Python 3.12 | 全コード | ✓ | 3.12.13 (`mise`) | 3.11（§17.1 切替可）|
| uv | 依存管理・venv | ✓ | 0.11.21 | — |
| git | バージョン管理 | ✓ | — | — |

**Missing dependencies with no fallback:** なし。プロジェクト前提（§3.1: EveryDB2更新済み・PostgreSQL接続・テーブル作成済み）は全て満たされていることを実接続で確認。

**Missing dependencies with fallback:** なし。

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（§17.1） |
| Config file | `pyproject.toml` の `[tool.pytest.ini_options]`（Wave 0 で作成） |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | §6.4 品質ゲート実行・verdict 出力 | unit | `uv run pytest tests/test_quality_gate.py -x` | ❌ Wave 0 |
| DATA-01 | 構造的欠陥（2015以降なし/PK重複）で BLOCK | unit | `uv run pytest tests/test_quality_gate.py::test_blocking_checks -x` | ❌ Wave 0 |
| DATA-02 | normalized ETL 実行・型/コード変換 | integration | `uv run pytest tests/test_normalized_etl.py -x` | ❌ Wave 0 |
| DATA-02 | raw 行ハッシュ不変（成功基準#2） | integration | `uv run pytest tests/test_raw_immutability.py -x` | ❌ Wave 0 |
| DATA-03 | クラス正規化: `jyokencd5`→`class_level_numeric`（§17.3） | unit | `uv run pytest tests/test_class_normalization.py -x` | ❌ Wave 0 |
| DATA-03 | code 005 が 2019年前後で同じ `class_level_numeric=1`（Pitfall 7） | unit | `uv run pytest tests/test_class_normalization.py::test_code_005_spans_reform -x` | ❌ Wave 0 |
| DATA-03 | `post_2019_class_system_flag` が 2019-06-08 境界 | unit | `uv run pytest tests/test_class_normalization.py::test_reform_date -x` | ❌ Wave 0 |
| 成功基準#4 | `pit_join.py` sortedness raise | unit | `uv run pytest tests/utils/test_pit_join.py -x` | ❌ Wave 0 |
| 成功基準#4 | `group_split.py` race_id disjoint | unit | `uv run pytest tests/utils/test_group_split.py -x` | ❌ Wave 0 |
| 成功基準#4 | `category_map.py` `__UNSEEN__` fallback | unit | `uv run pytest tests/utils/test_category_map.py -x` | ❌ Wave 0 |
| 成功基準#4 | `calibrator.py` 時系列順序 assert | unit | `uv run pytest tests/utils/test_calibrator.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`（quick）
- **Per wave merge:** `uv run pytest tests/ -v`（full）
- **Phase gate:** Full suite green before `/gsd-verify-work`。加えて品質ゲート `scripts/run_quality_report.py` が `verdict: pass` を出力すること。

### Wave 0 Gaps
- [ ] `pyproject.toml`（uv init、pytest/ruff 設定）— 全テストの前提
- [ ] `tests/conftest.py` — psycopg3 接続 fixture（`everydb2` DB への読取専用接続）
- [ ] `src/db/connection.py` — pydantic-settings による `.env` 接続管理
- [ ] `src/config/class_normalization.yaml` — DATA-03 の正（本 RESEARCH の対応表を直接転記）
- [ ] `src/config/settings.py` — `.env` → DSN（機密値は `.env` のみ、planning 文書に書かない）
- [ ] `.env.example` — 接続設定の雛形
- [ ] pytest install: `uv add --dev pytest==9.1.0` — フレームワーク未導入

---

## Security Domain

> `security_enforcement: true`（config.json）。本フェーズは local-only・PII なし・実馬券なし（§19.3）だが、DB 接続の機密管理と raw 不変性が主要な integrity リスク。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | local-only、単一ユーザー、DB 認証は `.env` のみ（anti-pattern #20）|
| V3 Session Management | no | local CLI/Streamlit。セッション概念なし |
| V4 Access Control | **yes** | raw 読取専用ロール（`REVOKE UPDATE,DELETE`）。D-06 二重保護 |
| V5 Input Validation | **yes** | ETL の型キャスト検証。全 varchar→明示的キャスト失敗を INFO レポート |
| V6 Cryptography | no | 機密性は DB 認証情報のみ、`.env` + ファイル権限 |
| V7 Error Handling/Logging | **yes** | 未知コード（D-13）の厳格エラー・silent fallback 禁止 |
| V8 Data Protection | **yes** | raw 不変性（行ハッシュアサーション）。`.env` の機密値を planning 文書に書かない |

### Known Threat Patterns for Phase 1 stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| DB 認証情報の notebook/コード埋め込み | Information Disclosure | pydantic-settings + `.env`（gitignore）。D-「接続設定管理」|
| raw の誤更新/削除（ETL バグ） | Tampering | 読取専用ロール + 行ハッシュ pytest（D-06）。V4/V8 |
| silent fallback で未知コード/欠損を隠蔽 | Tampering（データ整合性）| D-13 厳格エラー。V7 |
| 接続文字列のログ出力 | Information Disclosure | psycopg3 ログで DSN マスク。pydantic-settings の `SecretStr` |

---

## Sources

### Primary（HIGH confidence — 実データ照合・PyPI 確認・公式仕様）

- **実 PostgreSQL 接続（`everydb2` DB）:** 2026-06-17 に直接接続し以下を検証 — スキーマは `public` のみ、`n_*`/`s_*` BASE TABLE 103件、`n_race` PK `(year,jyocd,kaiji,nichiji,racenum)`（`monthday` は PK 外）、JRA 39,593レース（重複0）、`jyokencd5` の6値分布（701/703/005/010/016/999）、`gradecd` の10値、005/010/016 の2015-2026 全期間連続存在、主要カラム NULL率0。`[VERIFIED: live PostgreSQL]`
- **`docs/everydb2/03-RACE.md`:** RA 110フィールド仕様。`JyokenCD1..5`（5つの競走条件コード）、`GradeCD`、`SyubetuCD`、`KigoCD`、`TorokuTosu`/`SyussoTosu`/`NyusenTosu` の存在。`[CITED: docs/everydb2/03-RACE.md]`
- **`docs/everydb2/CODE.md`:** スクレイピング不完全の確認（D-10）。各コード表1エントリのみ。`[VERIFIED: docs/everydb2/CODE.md（不完全性確認）]`
- **`docs/keiba_ai_requirements_v1.3.md`:** §6.4（品質チェック9項目）、§12.1-12.4（DB/ETL/クラス正規化/Parquet）、§13.3-13.5（feature_availability）、§17.1-17.3（環境/構成/テスト）。`[CITED: docs/keiba_ai_requirements_v1.3.md]`
- **PyPI version 確認（2026-06-17）:** psycopg 3.3.4、psycopg-pool 3.3.1、pandas 3.0.3、pyarrow 24.0.0、duckdb 1.5.3、scikit-learn 1.9.0、mlxtend 0.25.0（CLAUDE.md の「4.x」は誤り）、pydantic-settings 2.14.1。`[VERIFIED: pip index versions]`
- **ホスト環境:** psql 15.18、python3.12.13、uv 0.11.21 実在確認。`[VERIFIED: host]`

### Secondary（MEDIUM confidence — プロジェクト研究・公式 docs）

- **`.planning/research/STACK.md`:** psycopg3 `merge_asof`/`GroupTimeSeriesSplit`/`CalibratedClassifierCV(cv='prefit')` のリーク防止設定。mlxtend version の「4.x」表記は PyPI で 0.25.0 に訂正。`[CITED: .planning/research/STACK.md]`
- **`.planning/research/PITFALLS.md`:** Pitfall 7（2019制度改革・コード不変）、Pitfall 1/3/5（リーク/ラベル/分割）。JRA-VAN 通知 2018-12-05 と 2019-06 移行の照合。`[CITED: .planning/research/PITFALLS.md]`
- **`.planning/research/ARCHITECTURE.md`:** 5層スキーマ・`src/` フォルダ構成・PIT/snapshot アーキテクチャ。`[CITED]`
- **CLAUDE.md:** 技術スタック詳細・リーク防止設定。mlxtend version 表記以外は実データ/PyPI と整合。`[CITED: CLAUDE.md]`

### Tertiary（LOW confidence — 推定・要確認）

- **`gradecd='D'` を G3 扱きする件:** 実測件数とG3系の推定から G3 と仮定（A1）。`syubetucd` との交差検証を Phase 1 ETL で推奨。`[ASSUMED]`
- **2019-06-08 が JRA 全場一斉適用:** JRA 夏季競馬の開催体系から。地方・海外は本フェーズ対象外。`[ASSUMED]`

---

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — PyPI で version 確認、ホストで実在確認。mlxtend version の CLAUDE.md 誤記を訂正。
- DB layout / raw 品質: **HIGH** — `everydb2` DB に直接接続し実測。スキーマ・テーブル・PK・件数・NULL率・コード分布全て実データ。
- クラス正規化（DATA-03）: **HIGH** — `jyokencd5`×`gradecd`×`year` の実分布を集計。§12.3 骨格を網羅・補完。2019-06-08 基準日を実測で確認。
- リーク防止プリミティブ: **HIGH** — プロジェクト研究 STACK.md のパターン（PyPI 確認済 API）を薄 wrapper 仕様に具体化。
- Pitfalls: **HIGH**（EveryDB2 固有の varchar/NAR混入/s-/n-は実DB確認）、**MEDIUM**（A1 `gradecd='D'` は推定）。

**Research date:** 2026-06-17
**Valid until:** 2026-07-17（30日。DB データは EveryDB2 更新で増えるが構造は安定。スタック version は四半期ごとに再確認推奨）
