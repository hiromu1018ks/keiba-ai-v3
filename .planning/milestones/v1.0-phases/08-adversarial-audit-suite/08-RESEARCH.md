# Phase 8: Adversarial Audit Suite - Research

**Researched:** 2026-06-24
**Domain:** テスト統合・対抗的監査（adversarial audit）・リーク防止テストスイート集約・再現性スモーク統合（TEST-01 / SC#1・SC#2・SC#3）
**Confidence:** HIGH

## Summary

Phase 8 は新機能を構築しない特殊フェーズである。Phase 1-7 で蓄積した `tests/` 配下 **49ファイル・491テスト（KEIBA_SKIP_DB_TESTS=1 収集時）・476+ テスト関数** が、SC#1 の8リークサーフェスと SC#2 の3注入ケースのほぼ全てを**個別機能テストとして既カバー**している。Phase 8 の付加価値は三つ:(1) これらを一枚の監査レポート `reports/08-audit.{md,json}` に**集約・可視化**し「どこが検証済みか」を明示する、(2) SC#2 が要求する「リークを注入すると fail する」**独立 adversarial（注入型メタ）テスト**を `tests/audit/` に新設し、機能テストでは拾えない静かな故障モードを補完する、(3) 既存の再現性インフラ（`run_train_predict --check-reproduce` + `test_reproduce_bit_identical` + `run_backtest --check-reproduce`）を束ねる**薄い smoke スクリプト**で SC#3 を単一エントリで証明する。

既存テストの棚卸しの結果、**SC#2 の3ケースは全て既存テストで近接カバーされているが、SC#2 が要求する「注入すると fail する独立 adversarial」の形式では未確立**である。`test_no_target_encoding_leak`（Phase 4・意図的リーク注入で DEMONSTRABLY fail を実証）が再利用すべき鋳型である。SC#2 の3ケース（lookahead 注入 / payout 正欠損 / fold race_id 共有）をそれぞれ `tests/audit/` に独立 adversarial テストとして新設する際、既存機能テストとの重複を避け「注入→fail のメタ検証」に特化する必要がある。特に fold 共有検出は `test_group_split.py::test_get_bt_race_ids_raises_on_leak` が既に注入→raise パターンを実現しているため、adversarial 新設の付加価値を慎重に設計する。

**Primary recommendation:** D-01..D-06 の全決定に従い、(a) `tests/audit/` に SC#2 の3ケース + UI/CSV 監査（D-06）を新設、(b) `reports/08-audit.{md,json}` でサーフェス別カバレッジマップ + SC#1/#2/#3 対応表 + Known Limitations を生成（手動対応表ベース・pytest `--collect-only` 補助）、(c) `scripts/run_reproducibility_smoke.py` で既存 CLI/pytest を orchestrate、(d) KEIBA_SKIP_DB_TESTS unset でフル GREEN を証明する。外部パッケージインストールなし・新規予測ロジックなし・read-only 監査層のみ。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| リークサーフェス別テスト集約・可視化 | Test / Audit 層 | — | `reports/08-audit.{md,json}` が全491テストを8サーフェスにマッピング。新規ロジック不要・集約層のみ。 |
| SC#2 adversarial（注入型）テスト | Test / Audit 層 | — | `tests/audit/` が合成データでリークを注入し fail を実証。DB 不要・純粋関数ベース。機能テスト（`tests/`）とは独立層。 |
| 再現性スモーク統合（SC#3） | Orchestration 層 | Test 層 | `scripts/run_reproducibility_smoke.py` が既存 CLI（`run_train_predict --check-reproduce` / `run_backtest --check-reproduce`）+ pytest を束ねる薄い orchestrator。新規フルパイプライン runner は作らない（D-03）。 |
| KEIBA_SKIP_DB_TESTS unset 全実行ゲート（SC#1 GREEN） | Test 実行層 | — | live PostgreSQL（everydb2）の全 `requires_db` テストを含むフルスイート実行。CI 統合は最小限（個人開発ローカル）。 |
| Known Limitations 可視化（D-05） | Report 層 | — | `reports/08-audit` の "Known Limitations" セクション。機能テストでは表現できない概念的正直さ（回収率天井・Calibration劣位・odds再検証未完）。 |
| UI/CSV 対抗的監査（D-06） | Test / Audit 層 | UI 層（read-only 監査対象） | `tests/audit/test_audit_ui_csv.py` が `src/ui/` と `scripts/run_export_*.py` を AST/構造検査。Phase 7 が明示的に本フェーズに委譲。 |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 統合成果物の形（TEST-01 / SC#1・SC#2）
- **D-01: 両方（監査レポート集約可視化 ＋ 新規 adversarial テスト新設）** — `reports/08-audit.{md,json}`（サーフェス別カバレッジマップ・SC#1/#2/#3 対応表）で既存476テストを集約・可視化し、真のギャップ（SC#2 注入ケース等・UI/CSV 監査）は `tests/audit/` に新設して補完する。「どこカバー済み／どこに注入テストを足すか」を明示でき、TEST-01「リーク防止の対抗的監査テストを含む」に最適合。ユーザー選択: 両方。（監査レポート集約のみ / 新規テスト新設のみ は却下）

#### 対抗的（注入型）テストの深度（SC#2）
- **D-02: SC#2 必須3ケース中心** — SC#2 が明示する3ケース（**lookahead 注入検出** / **payout 払戻対象正の馬のラベル欠損検出** / **fold の train/test が `race_id` を共有する検出**）を、それぞれ**リークを注入すると fail する独立 adversarial テスト**として確保する。既存476テストが各サーフェスの functional 検証を担い、注入型（mutation/injection style）はこの3つを代表とする。`test_no_target_encoding_leak`（Phase 4・意図的リーク注入で DEMONSTRABLY fail を実証済み）が再利用すべきパターン。ユーザー選択: SC#2必須3ケース中心。（全8サーフェス展開 / Claude判断 は却下）

#### 再現性スモーク（SC#3）
- **D-03: 既存 CLI＋pytest を束ねる統合スクリプト** — `run_train_predict --check-reproduce`（Phase 4 SC#4 bit-identical）＋ 既存 bit-identical pytest 群 ＋ backtest/eval 再現確認を、`scripts/run_reproducibility_smoke.py`（or Make ターゲット）で orchestrate し、SC#3「snapshot→train→predict→backtest→eval の固定 seed 再現」を単一エントリポイントで確認する。新規のフルパイプライン runner は作らず既存資産を活用（重複回避・keep it simple）。ユーザー選択: 既存CLI+pytestを束ねる。（新規統合smoke runner / Claude判断 は却下）

#### DB 必須テストと出荷ゲート証憑（SC#1 GREEN 証明）
- **D-04: KEIBA_SKIP_DB_TESTS unset 全実行 ＋ reports/08-audit 生成** — Phase 4 踏襲。`KEIBA_SKIP_DB_TESTS` を unset し、live PostgreSQL（everydb2）の全 `requires_db` テストを含むフルスイートを実行して GREEN を証明する。`reports/08-audit.{md,json}`（サーフェス別 GREEN/カバレッジ・SC#1/#2/#3 対応表・Known Limitations）を v1 出荷ゲートの証憑として生成する。memory `phase7-ui-live-db-bugs`（live-DB でしか発覚しない bug あり・unit test の SKIP では検出不可）に整合。ユーザー選択: unset全実行+監査レポート。（CI(DB不要)+手動live-DB分離 / Claude判断 は却下）

#### honest 既知限界の可視化（"Looks Done But Isn't" ゲートの核心）
- **D-05: Known Limitations セクションで既知限界を明示** — `reports/08-audit` に "Known Limitations" セクションを設け、**回収率~0.65 天井（odds-free 1-A の構造的限界・閾値では改善しない）**・**Phase 5 odds の JODDS取得完了後の再検証 subject**・**Phase 4 SC#2 で主モデルが Calibration において BL-1/BL-4 に劣位** を隠さず明示する。本プロジェクトの Core Value（過大表示回避・honest 評価・実馬券購入しない個人分析）に整合。memory `fukusho-recovery-070-structural-ceiling` に整合。ユーザー選択: 含める。（含めない / Claude判断 は却下）

#### Phase 7 継承の UI/CSV 対抗的監査（TEST-01）
- **D-06: Phase 8 スコープに含める** — 07-CONTEXT が Deferred した「UI/CSV の read-only 保証（書き込み経路不存在）・再現性スタンプ inline 検出（スタンプ欠落検出）」の対抗的監査テストを `tests/audit/` に追加する。TEST-01「対抗的監査テストを含む」に合致・Phase 7 が明示的に本フェーズに委ねた項目。SC#1 の明示サーフェスリストには現れないが、07-CONTEXT Deferred と TEST-01 の包括表現でスコープ内。memory `phase7-ui-live-db-bugs`（live-DB 必須 bug）への対処も兼ねる。ユーザー選択: 含める。（含めない / Claude判断 は却下）

### Claude's Discretion（研究者/計画者に委ねる）
- **`tests/audit/` の内部構成** — ファイル分割単位（サーフェス別 `test_audit_label.py` / `test_audit_features.py` / `test_audit_split.py` / `test_audit_odds.py` / `test_audit_ui_csv.py` 等 vs 単一ファイル）・各 adversarial テストの注入手法（合成 DataFrame で T+1 データを混入等）は planner/researcher が決定。`test_no_target_encoding_leak` の既存パターンを踏襲。
- **サーフェス別カバレッジマップの機械化** — `reports/08-audit.json` を pytest 収集から自動生成するか（`--collect-only` + marker 設備）、手動で SC↔テスト対応表を保守するか。既存の md+json 分離 reports 慣例に従う。
- **adversarial 3ケースの「既存テストとの棲み分け」** — `test_pit_cutoff` / `test_label_reconcile` / `test_group_split` に既に同等の注入ケースが存在する場合は重複を避け、真のギャップだけ新設するか否か（researcher の棚卸し結果次第）。
- **再現性スモークの対象データ規模** — `run_reproducibility_smoke.py` を合成データで回すか、stamped snapshot の縮小サンプルで回すか（live-DB 全量は重い）。Phase 4 SC#4 の合成データ bit-identical 手法を参考。
- **CI 統合の要否** — config.json に CI 設定なし。個人開発ローカル（PostgreSQL 15.18 Homebrew）。pre-commit / push hook で DB 不要層だけ回す等は Phase 8 では最小限（D-04 の unset 全実行が主）。将来の PHASE2/OPS で拡張。

### Deferred Ideas (OUT OF SCOPE)
- **CI 環境での自動テスト実行（PHASE2 / OPS-01・02）** — GitHub Actions 等 CI での DB 不要層自動実行・push hook・pre-commit 連携。Phase 8 は個人開発ローカルの unset 全実行（D-04）が主。CI 統合は将来フェーズ。
- **MLflow/Optuna 連携のテスト基盤（OPS-01/02・§21 defer）** — モデル管理・ハイパラ最適化の回帰テスト。Phase 1 安定後・将来 PHASE2+。
- **より広範な mutation testing / property-based testing 導入** — D-02 の注入型 adversarial を全サーフェスに一般化・`hypothesis` 等の property-based testing。現状は SC#2 の3ケース中心（D-02）。徹底度を上げる場合は将来フェーズで評価。
- **フルパイプライン end-to-end runner の一本化** — D-03 は既存資産を束ねる薄いスクリプト。snapshot→...→eval を完全一本化した重厚 runner は、Phase 4 SC#4 と重複するため見送り。需要が出れば将来。
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-01 | 複勝ラベル生成・払戻テーブル突合・出走取消/競走除外/競走中止の扱い・オッズ時点固定・仮想購入ルール・`feature_cutoff_datetime`・評価指標計算・`race_id`単位分割・クラス正規化・カテゴリ/欠損処理 に対するテストを実装できる（リーク防止の対抗的監査テストを含む） | SC#1 の8サーフェスは既存491テストで個別機能テストとしてカバー済み（§"SC#1 サーフェス別既存テストマッピング"参照）。SC#2 の3注入ケース + UI/CSV 監査を `tests/audit/` に新設し「対抗的監査テストを含む」を満たす。SC#3 は既存 CLI orchestrate で再現性証明。`reports/08-audit.{md,json}` が出荷ゲート証憠。 |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.1.0（既存 pin） | テスト実行・収集・marker | 要件 §17.3 既存。`requires_db` marker 登録済み（pyproject.toml L45-46）。`testpaths=["tests"]`・`addopts="-ra"`。Phase 8 は新規依存なし・既存 pytest 資産を活用。 [VERIFIED: pyproject.toml L43-46] |
| pandas | 3.0.3（既存 pin） | 合成 DataFrame 構築（adversarial テスト用） | 既存 `tests/features/conftest.py` の `_build_adversarial_rolling_rows` / `_build_two_observation_rolling_rows` パターン再利用。 [VERIFIED: tests/features/conftest.py] |
| NumPy | (transitive) | `np.array_equal` bit-identical 検証 | SC#3 再現性スモークの中核検証プリミティブ。 [VERIFIED: tests/model/test_calibrator.py L155 `np.array_equal(proba1, proba2)`] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| mlxtend | latest 4.x（既存 pin） | `GroupTimeSeriesSplit` 検証補助 | SC#2「fold race_id 共有検出」adversarial で group-aware 分割の等価性検証。既存 `test_group_split.py::test_bt_window_equivalent_to_group_ts_split` が参照。 [VERIFIED: tests/utils/test_group_split.py L254] |
| ruff | 0.15.17（既存 pin） | lint/format | 新規 `tests/audit/` ファイルの lint。 [VERIFIED: CLAUDE.md Recommended Stack] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 手動 SC↔テスト対応表（reports/08-audit.json） | pytest `--collect-only` + marker 自動生成 | 自動生成は実態との乖離リスクあり（marker 未付与テストが漏れる）。手動対応表を正とし・`--collect-only` は sanity check 補助に使う（Claude's Discretion・本研究の推奨）。 [ASSUMED — planner が最終判断] |
| 合成データ adversarial テスト | stamped snapshot 縮小サンプル | 合成データは注入制御が容易・DB 不要・高速。snapshot 縮小サンプルは実データ代表性が高いが live-DB 必須・重い。SC#2 の注入型は合成データが適する（D-02）。再現性スモークは既存の合成データ bit-identical 手法（Phase 4 SC#4）を踏襲。 [VERIFIED: test_no_target_encoding_leak は合成データベース] |

**Installation:**
```bash
# Phase 8 は新規パッケージインストールなし。既存 pyproject.toml の依存（pytest 9.1.0 / pandas 3.0.3 / mlxtend / ruff）のみで完結。
uv sync --frozen
```

**Version verification:** 既存パッケージのみのため追加検証不要。全て Phase 1-7 で pinned 済み。

## Package Legitimacy Audit

> Phase 8 は外部パッケージをインストールしない（既存 pytest/pandas/mlxtend/ruff のみ）。Package Legitimacy Gate は該当なし。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none — 既存依存のみ) | — | — | — | — | — | N/A |

**Packages removed due to [SLOP] verdict:** なし（インストール対象なし）。
**Packages flagged as suspicious [SUS]:** なし。

*Phase 8 はテスト・監査・統合層のみで、新規外部依存を導入しない。*

## Architecture Patterns

### System Architecture Diagram

```
                         Phase 8: Adversarial Audit Suite データフロー
                         
  [tests/ 既存491テスト]                    [SC#2 注入型 adversarial 新設]
  ├ test_fukusho_label (LABEL)             ├ tests/audit/test_audit_label.py
  ├ test_label_reconcile (LABEL)           │   └ payout正欠損注入 → fail実証
  ├ test_refund_accounting (EV)            ├ tests/audit/test_audit_features.py
  ├ test_odds_snapshot (EV)                │   └ lookahead(T+1)注入 → fail実証
  ├ test_purchase_simulator (EV)           ├ tests/audit/test_audit_split.py
  ├ test_pit_cutoff (FEAT)                 │   └ fold race_id共有注入 → fail実証
  ├ test_rolling (FEAT・cross-obs)         └ tests/audit/test_audit_ui_csv.py
  ├ test_group_split (BACK)                    └ UI書込経路注入 / スタンプ欠落検出
  ├ test_class_normalization (DATA)             │
  ├ test_allowlist (FEAT)                       │ 合成データ (DB不要)
  ├ test_trainer (MODL・target enc)             │
  └ test_readonly_guarantee (UI/Phase7)         ▼
         │                                 [pytest --collect-only]
         │                                  └ SC↔テスト対応表 (sanity check)
         ▼                                       │
  [reports/08-audit.{md,json}]  ◄────────────────┘
  ├ サーフェス別カバレッジマップ (SC#1 #1-#8)
  ├ SC#1/#2/#3 対応表
  ├ Known Limitations (D-05)
  │   ├ 回収率天井 ~0.65-0.70 (LightGBM 0.7022)
  │   ├ Calibration BL劣位 (LGB 0.2308 vs BL-1 0.0014)
  │   └ odds JODDS再検証 subject
  └ フル GREEN 証明 (D-04)
         
  [SC#3 再現性スモーク]
  scripts/run_reproducibility_smoke.py (薄い orchestrator)
  ├ run_train_predict --check-reproduce (seed=42 bit-identical)
  ├ test_reproduce_bit_identical (calibrator)
  ├ run_backtest --check-reproduce --synthetic (合成BT窓)
  └ run_evaluation (reports/06-evaluation 再現)
         │
         ▼
  [KEIBA_SKIP_DB_TESTS unset 全実行]
  └ 全 requires_db テスト含むフルスイート GREEN 証明 (SC#1)
      └ reports/08-audit に出荷ゲート証憠として記録
```

### Recommended Project Structure
```
tests/
├── audit/                          # 【新規】SC#2 adversarial + D-06 UI/CSV 監査
│   ├── __init__.py
│   ├── conftest.py                 # 合成 DataFrame 注入ヘルパー（共通）
│   ├── test_audit_label.py         # SC#2: payout正欠損注入 → fail 実証
│   ├── test_audit_features.py      # SC#2: lookahead(T+1)注入 → fail 実証
│   ├── test_audit_split.py         # SC#2: fold race_id共有注入 → fail 実証
│   └── test_audit_ui_csv.py        # D-06: UI書込経路 / スタンプ欠落検出
├── (既存49ファイルは変更なし)
scripts/
├── run_reproducibility_smoke.py    # 【新規】SC#3: 既存CLI/pytestをorchestrate
reports/
├── 08-audit.md                     # 【新規】監査レポート（人間確認用）
└── 08-audit.json                   # 【新規】監査レポート（機械消費用・byte-reproducible）
src/
└── audit/                          # 【新規・薄い層】reports/08-audit 生成ロジック
    ├── __init__.py
    └── report.py                   # md+json 分離生成（src/ev/report.py DRY再利用）
```

### Pattern 1: 注入型 adversarial（mutation/injection）テストの鋳型（D-02）
**What:** 合成データに意図的にリークを注入し、検出器（テスト対象）がそれを fail（raise/assert失敗）として捕捉することを実証するメタテスト。機能テスト（「正しく処理される」検証）とは独立に「リークがあれば検出される」ことを証明する。
**When to use:** SC#2 の3ケース（lookahead/payout正欠損/fold共有）。`test_no_target_encoding_leak`（Phase 4）が確立済みの鋳型。
**Example:**
```python
# Source: tests/model/test_trainer.py::test_no_target_encoding_leak (L277-486)
# 鋳型の構造:
# (1) 合成データ構築（制御可能な seed・race_key 単位時系列分割）
# (2) 通常経路（リークなし）でベースライン予測を取得
# (3) 意図的リーク注入（例: 未来行の label 平均を feature に混入）
# (4) リーク注入版で予測が threshold を超える（=リークがあれば検出される）ことを assert
# (5) 対比: リークなし版がリーク注入版より低いことを assert（検証力証明）

# SC#2 lookahead 注入の適用例（test_audit_features.py）:
def test_lookahead_injection_detected_and_fails():
    """SC#2: feature 値が T+1 データを使用すると検出されて fail する（注入型 adversarial）。
    
    合成 history で T+1 の race 結果を T の feature に混入し・
    build_rolling_features がそれを除外しない場合 → assert が fail することを実証。
    （test_pit_cutoff は「正しく除外される」機能テスト・本テストは「除外されないとfail」メタ検証）
    """
    # (1) 正常 history: eligible 3行のみ (kakuteijyuni=1,2,3)
    history_clean = _build_adversarial_rolling_rows(obs_race_date="2023-06-04")
    obs = pd.DataFrame([_build_race_obs_row("2023A0610-R1", 1001, "2023-06-04")])
    result_clean = builder.build_rolling_features(obs, history_clean)
    # ベースライン: mean=2.0 (eligible 3行のみ)
    assert abs(result_clean.iloc[0]["rolling_kakuteijyuni_mean_5"] - 2.0) < 1e-9
    
    # (2) リーク注入: PIT guard を monkeypatch で無効化（strict < を <= に緩める）
    #     または history の as_of を cutoff 以降に偽装
    history_leaked = history_clean.copy()
    # previous_day 行の as_of を cutoff 直前に偽装（本来除外されるべきが混入）
    # ...注入ロジック...
    
    # (3) guard が有効なら混入を検出 → 正しい結果（mean=2.0）
    #     guard が無効なら混入 → 間違った結果（mean != 2.0）→ 以下の assert が fail
    result_leaked = builder.build_rolling_features(obs, history_leaked)
    assert abs(result_leaked.iloc[0]["rolling_kakuteijyuni_mean_5"] - 2.0) < 1e-9, (
        "lookahead 注入が検出されず T+1 データが混入（SC#2 adversarial fail）"
    )
```

### Pattern 2: md+json 分離 reports 生成（D-01/D-04/D-05）
**What:** `src/ev/report.py` の DRY パターンを再利用。`REPORT_COLUMNS` 定数で列定義を外部化し、Markdown（人間確認）と JSON（byte-reproducible・`sort_keys=True`）を分離出力。presence assert（LOW-05）で md 列ヘッダと json キーの 1:1 を機械検証。
**When to use:** `reports/08-audit.{md,json}` 生成。
**Example:**
```python
# Source: src/ev/report.py L41-53 (REPORT_COLUMNS) + L176-274 (generate_report)
# 再利用パターン:
AUDIT_SURFACE_COLUMNS = (
    "surface",          # サーフェス名（fukusho_label / payout_reconcile / ...）
    "sc_id",            # SC#1/#2/#3 のどれに対応
    "existing_tests",   # 既存テストファイル・関数
    "adversarial_test", # tests/audit/ の新設テスト（あれば）
    "status",           # COVERED / ADVERSARIAL / GAP
    "evidence",         # GREEN 証明の根拠
)
# json は sort_keys=True・ensure_ascii=False で byte-reproducible
# _atomic_write_text で原子的書込（src/model/artifact.py 再利用）
```

### Pattern 3: 既存 CLI orchestrate（薄いスクリプト・D-03）
**What:** 新規フルパイプライン runner を作らず、既存の `scripts/run_*.py` CLI と pytest を subprocess または import で束ねる薄い orchestrator。
**When to use:** `scripts/run_reproducibility_smoke.py`（SC#3）。
**Example:**
```python
# Source: scripts/run_train_predict.py L125-127 (--check-reproduce flag) +
#         src/model/orchestrator.py::_assert_deterministic (bit-identical)
# scripts/run_reproducibility_smoke.py の構造（薄い orchestrator）:
import subprocess, sys
def main():
    steps = [
        # (1) Phase 4 SC#4: 両モデル bit-identical
        ["uv", "run", "python", "scripts/run_train_predict.py",
         "--check-reproduce", "--no-write-db"],
        # (2) calibrator bit-identical pytest
        ["uv", "run", "pytest", "tests/model/test_calibrator.py::test_reproduce_bit_identical", "-q"],
        # (3) backtest --check-reproduce --synthetic (合成BT窓)
        ["uv", "run", "python", "scripts/run_backtest.py",
         "--synthetic", "--bt-filter", "BT-1", "--check-reproduce", "--no-write-db"],
        # (4) audit adversarial テスト群
        ["uv", "run", "pytest", "tests/audit/", "-q"],
    ]
    for cmd in steps:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"FAIL: {' '.join(cmd)}", file=sys.stderr)
            return 1
    print("SC#3 reproducibility smoke: ALL PASS")
    return 0
```

### Anti-Patterns to Avoid
- **新規フルパイプライン runner の作成:** Phase 4 SC#4 が既に bit-identical を確立済み。重複は keep it simple に反する（D-03 明示却下）。既存 CLI を束ねる薄いスクリプトのみ。
- **既存機能テストの大量書き直し:** SC#1 の8サーフェスは既存491テストでカバー済み。Phase 8 は「集約可視化 + 真のギャップ（SC#2 注入型）の補完」のみ。functional テストを書き直さない。
- **adversarial テストと機能テストの重複:** `test_pit_cutoff`（機能: 正しく除外される）と `test_audit_features`（adversarial: 注入するとfail）は異なる検証対象。同じ合成データでも assert の意図が違う。planner は docstring で「メタ検証」であることを明記し重複回避を文書化する。
- **監査レポートのカバレッジマップを実態と乖離させる:** `--collect-only` 自動生成のみだと marker 未付与テストが漏れる。手動対応表を正とし・自動収集は sanity check 補助。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 再現性 bit-identical 検証 | 新規 bit-identical フレームワーク | `run_train_predict --check-reproduce` + `test_reproduce_bit_identical` | Phase 4 SC#4 が seed=42 + num_threads=1 + FIXED_REPRODUCE_TS で確立済み。 [VERIFIED: scripts/run_train_predict.py L257-278] |
| reports md+json 生成 | 新規レポート生成ロジック | `src/ev/report.py::generate_report` パターン（REPORT_COLUMNS + _atomic_write_text + sort_keys） | Phase 5 で DRY 確立済み。presence assert（LOW-05）も再利用可能。 [VERIFIED: src/ev/report.py L41-274] |
| 合成 DataFrame 注入ヘルパー | 新規合成データビルダー | `tests/features/conftest.py::_build_adversarial_rolling_rows` / `_build_two_observation_rolling_rows` | Phase 3 CYCLE-2 で確立済みの adversarial rolling builder。 [VERIFIED: tests/features/conftest.py L66-140] |
| group-aware 時系列分割検証 | 新規 splitter 検証 | `mlxtend.GroupTimeSeriesSplit` + `test_group_split.py::test_bt_window_equivalent_to_group_ts_split` | Phase 5 MEDIUM-01a で等価性立証済み。 [VERIFIED: tests/utils/test_group_split.py L247-292] |
| UI read-only 保証検証 | 新規 AST 検査器 | `tests/ui/test_readonly_guarantee.py::_extract_sql_literals` | Phase 7 で AST による SQL 文字列リテラル検査を確立済み（D-06 の基盤）。 [VERIFIED: tests/ui/test_readonly_guarantee.py L42-65] |

**Key insight:** Phase 8 の全成果物（adversarial テスト・監査レポート・再現性スモーク）は、Phase 1-7 で確立されたパターン・ヘルパー・インフラの**組み合わせと集約**で実現できる。新規の「仕組み」を発明しない。

## SC#1 サーフェス別既存テストマッピング（棚卸し結果・最重要）

> 以下は `tests/` 配下491テストを SC#1 の8サーフェスにマッピングした結果。各サーフェスが「既存テストでカバー済み（COVERED）」「adversarial 注入ケースとして独立存在（ADVERSARIAL）」「真のギャップ（GAP）」のどれかを判定する。

| # | SC#1 サーフェス | 既存テスト（COVERED） | adversarial 注入ケース | SC#2 対応 | 判定 |
|---|----------------|----------------------|----------------------|-----------|------|
| 1 | fukusho label generation | `tests/test_fukusho_label.py`（40関数: raw/validated drift・dead_heat・scratch・dead_loss・race_cancelled・fuseiritu・tokubarai・model_eligible・payout_places 等） | — | — | COVERED（機能テスト充実） |
| 2 | payout-table reconciliation | `tests/test_label_reconcile.py`（18テスト: precision/recall NULL-safe・dead_heat WR-01・scratch raw marker・dead_loss obstacle・no_sale・drift INFO・>99.9% agreement[requires_db]） | — | SC#2 ケース2（payout正欠損）に近接 | COVERED（機能）+ GAP（注入型 adversarial 未確立） |
| 3 | 取消/除外/競走中止 handling | `tests/test_fukusho_label.py`（scratch_cancel_excluded・dead_loss_in_training・dead_loss_obstacle_excluded・race_cancelled）+ `tests/ev/test_refund_accounting.py`（11シナリオ: normal/miss/scratch/excluded/dead_loss/fuseiritu/cancelled/no_sale/deadheat/tokubarai） | — | — | COVERED（6シナリオ決定表×refund accounting） |
| 4 | fixed-odds-snapshot enforcement（hindsight rejected） | `tests/ev/test_odds_snapshot.py`（11テスト: backward・no_bet・special_values・0999・**future_leak**・day_boundary・datakubun・snake_case・multi_horse・fukusyoflag・multi_race） | `test_odds_snapshot_future_leak`（未来HappyoTime選択されない）は注入ケースに近接 | — | COVERED（future_leak で後知恵注入検出を実質カバー） |
| 5 | virtual-purchase rules | `tests/ev/test_purchase_simulator.py`（7テスト: filter_conditions・top2・tiebreak・no_eligible・no_sale・no_bet・stable_mergesort） | — | — | COVERED |
| 6 | feature_cutoff_datetime enforcement | `tests/features/test_pit_cutoff.py`（6テスト: same_day_excluded・previous_day_strict・future_excluded・sort_values・cutoff_race_date_minus_1・metadata）+ `tests/features/test_rolling.py::test_two_observation_window_is_per_observation_not_per_horse`（CYCLE-2 cross-obs adversarial）+ `test_history_pre_filtered_strict_less_than_cutoff` | `test_pit_cutoff`（機能: 正しく除外）+ `test_rolling::test_two_observation`（cross-obs adversarial・実質注入ケース） | SC#2 ケース1（lookahead注入）に近接 | COVERED（機能+cross-obs adversarial）+ GAP（「注入するとfail」独立メタテスト未確立） |
| 7 | race_id-unit split disjointness | `tests/utils/test_group_split.py`（10テスト: race_id_disjoint・strict_chronological・equal_timestamp_raises・n_splits・missing_columns・assert_replaced_by_raise・mlxtend_exposed・BT窓 disjoint/chronological/2019-06/rolling/**raises_on_leak**・equivalent_to_group_ts_split） | `test_get_bt_race_ids_raises_on_leak`（意図的にtrain/testがrace_id共有するBTWindow→ValueError）は注入→raiseパターンを実現 | SC#2 ケース3（fold共有検出） | COVERED（機能）+ **実質ADVERSARIAL**（raises_on_leak が注入→fail を既に実現） |
| 8 | class normalization（2019 reform continuity） | `tests/test_class_normalization.py`（12テスト: module_loads・signature・**code_005_spans_reform**・reform_boundary・grade_a_g1/listed/general・unresolved_jyokencd5/gradecd・add_columns・audit_gradecd_d_by_syubetucd[+requires_db]） | — | — | COVERED（code_005_spans_reform で改革前後連続性検証） |
| (補) | categorical/missing handling（no target enc, no NaN→-1） | `tests/model/test_trainer.py`（6テスト: **lightgbm_nonneg_codes**・**catboost_has_time**・catboost_predict_row_order・**no_target_encoding_leak**・eval_set_disjoint・**no_target_encoding_imports**） | `test_no_target_encoding_leak`（**意図的リーク注入で DEMONSTRABLY fail**・SC#2 鋳型そのもの） | SC#2 鋳型 | COVERED + **ADVERSARIAL確立済み**（target encoding 注入→fail） |

### SC#2 の3ケース vs 既存テストの正確な境界（adversarial 新設の要否）

| SC#2 ケース | 既存最近接テスト | 既存の性質 | adversarial 新設の要否と付加価値 |
|-------------|----------------|-----------|--------------------------------|
| **1. lookahead 注入検出**（T の feature が T+1 使用） | `test_pit_cutoff`（機能: 正しく除外される）+ `test_rolling::test_two_observation`（cross-obs: horse-grouped では fail・obs_id-keyed のみ GREEN） | 機能テスト（正しさ検証）+ cross-obs 構造診断 | **新設推奨**。既存は「正しく除外される」を検証するが、「guard を無効化すると混入する（=リークがあれば検出される）」のメタ検証が未確立。`test_no_target_encoding_leak` の注入→fail 鋳型を PIT cutoff に適用。付加価値: guard の有効性を独立証明。 |
| **2. payout 正欠損検出**（payout 正の馬が label に無い） | `test_label_reconcile::test_check_payout_recall`（機能: mock で count>0→passed=False） | 機能テスト（mock cursor で検査ロジック検証） | **新設推奨**。既存は mock cursor で `_check_payout_recall` のロジックを検証するが、「実際に payout 正の馬を label から欠落させて reconcile が passed=False を返す」の end-to-end 注入検証が未確立。付加価値: 合成 DataFrame で label と payout テーブルの不整合を注入し、reconcile_against_payout が verdict='fail' を返すことを実証。 |
| **3. fold race_id 共有検出** | `test_group_split::test_get_bt_race_ids_raises_on_leak`（注入: train_end==test_start で R2 を共有→ValueError）+ `test_equal_timestamp_races_do_not_cross`（注入: 等値timestamp→ValueError） | **実質 adversarial**（意図的に共有する BTWindow を注入→raise） | **新設の付加価値は限定的**。既存テストが「注入→fail（raise）」パターンを既に実現。ただし SC#2 が「a fold whose train/test share a race_id is detected」を明示するため、`tests/audit/test_audit_split.py` で SC#2 専用の独立 adversarial として再定式化し、docstring で SC#2 対応を明示することが推奨（重複回避のため既存テストへの cross-reference を含む）。 |

### D-06 UI/CSV 対抗的監査の既存資産と新設範囲

| D-06 項目 | 既存テスト（Phase 7） | 新設範囲（tests/audit/） |
|-----------|---------------------|------------------------|
| UI read-only 保証（書き込み経路不存在） | `tests/ui/test_readonly_guarantee.py`（AST で SQL 文字列リテラルの INSERT/UPDATE/DELETE/TRUNCATE/CREATE/DROP/ALTER 検出）+ `test_loaders_readonly.py::test_loaders_has_no_write_ddl_sql` | 既存で大部分カバー。adversarial 新設は「書き込み SQL を注入すると検出される」メタ検証（例: 一時的に INSERT を含むダミーファイルを配置→AST 検査が fail することを実証）。 |
| 再現性スタンプ inline 検出（スタンプ欠落検出） | `tests/ui/test_csv_columns.py::test_prediction_csv_has_all_stamps`（presence assert: odds_snapshot_policy/odds_snapshot_at/model_version/feature_snapshot_id/backtest_strategy_version の5スタンプ） | 既存で CSV スタンプ存在はカバー。adversarial 新設は「スタンプを欠落させると fail する」メタ検証（例: PREDICTION_CSV_COLUMNS から1スタンプを除く→presence assert が fail）。 |
| live-DB 必須 bug 検出（memory phase7-ui-live-db-bugs） | `test_streamlit_api_usage.py::test_app_has_syspath_guard_for_streamlit_run` + `test_loaders_readonly.py::test_loaders_uses_parameterized_queries` | D-04 の unset 全実行で live-DB テストが実行されることで検出。adversarial 新設は「sys.path ガード欠落時の検出」「SQL 引用符不正時の検出」のメタ検証。 |

## Common Pitfalls

### Pitfall 1: adversarial テストと機能テストの重複（見かけ上の冗長）
**What goes wrong:** `tests/audit/test_audit_features.py` の lookahead 注入テストが、`test_pit_cutoff.py` の機能テストと同じ合成データ・同じ assert を使うため、レビューで「重複・削除すべき」と指摘される。
**Why it happens:** 両者は同じリークサーフェス（PIT cutoff）を扱うため、合成データが似る。しかし検証の**意図**が異なる（機能: 正しく処理される / adversarial: guard を無効化すると fail する）。
**How to avoid:** docstring で「本テストは SC#2 adversarial（注入型メタ検証）であり・`test_pit_cutoff`（機能テスト）とは独立層」と明記。既存テストへの cross-reference を含む。注入手法（guard の monkeypatch 無効化・偽装 as_of 等）を機能テストと明確に変える。
**Warning signs:** レビューで「このテストは test_pit_cutoff と同じでは？」と指摘されたら docstring を強化。

### Pitfall 2: KEIBA_SKIP_DB_TESTS が unset でないと見えない live-DB bug
**What goes wrong:** `KEIBA_SKIP_DB_TESTS=1`（開発時の一時回避）で全 requires_db テストが skip されるため、live-DB でしか発覚しない bug（sys.path ガード・SQL 引用符・Streamlit deprecation 等・memory `phase7-ui-live-db-bugs`）が検出されないまま「GREEN」と誤認される。
**Why it happens:** conftest.py の `pytest_collection_modifyitems` が `KEIBA_SKIP_DB_TESTS=1` の時のみ requires_db marker を skip する設計。CI では unset だが、個人開発ローカルで開発中は set していることが多い。
**How to avoid:** D-04 の unset 全実行ゲートを**必ず最後に実行**し、reports/08-audit に「KEIBA_SKIP_DB_TESTS unset・全 requires_db 実行・0 skipped」を証明として記録。conftest.py の skip policy は「fail-by-default unless KEIBA_SKIP_DB_TESTS=1」（unset で Settings validation error で fail）のため、unset 実行で確実に live-DB テストが走る。
**Warning signs:** 監査レポートの skipped count が 0 でない→unset されていない。

### Pitfall 3: 監査レポートのカバレッジマップが実態と乖離
**What goes wrong:** `reports/08-audit.json` のサーフェス→テスト対応表が、実際のテストファイルと不一致（テスト追加・リネーム時の更新漏れ）。「カバー済み」と記載されているが実テストが存在しない・または逆。
**Why it happens:** 手動対応表の保守コスト。`--collect-only` 自動生成は marker 未付与テストを漏らす。
**How to avoid:** 手動対応表を正としつつ、`pytest --collect-only -q` の出力で「対応表に記載されたテスト関数が実際に存在するか」の sanity check を `reports/08-audit` 生成スクリプトに組み込む。存在しないテスト関数を参照していたら生成エラー。
**Warning signs:** 対応表のテスト関数名が `--collect-only` に無い→乖離。

### Pitfall 4: 再現性スモークが重い（live-DB 全量）
**What goes wrong:** `run_reproducibility_smoke.py` が live-DB 全量の snapshot 読込・学習・backtest を実行するため、実行時間が数十分〜数時間になり、反復実行が困難。
**Why it happens:** stamped snapshot は実データ（~55万行）。bit-identical 検証は同じデータで2回実行するため倍。
**How to avoid:** D-03 の「既存 CLI を束ねる」に従い、合成データ（`--synthetic`）モードをデフォルトとする。Phase 4 SC#4 の合成データ bit-identical 手法（`_assert_deterministic`）は `--no-write-db` で高速実行可能。live-DB 全量は checkpoint:human-verify で別途実行。Claude's Discretion で合成データを推奨。
**Warning signs:** smoke 実行が10分超→合成データモードに切り替え。

## Code Examples

### SC#2 ケース2: payout 正欠損注入 adversarial（test_audit_label.py）
```python
# Source: 新規設計・tests/test_label_reconcile.py の mock cursor パターン + 
#         tests/ev/conftest.py の make_harai_mock/make_label_mock 再利用
# 「実際に payout 正の馬を label から欠落させて reconcile が verdict='fail' を返す」を実証

def test_payout_positive_missing_from_labels_detected():
    """SC#2 adversarial: 払戻テーブルで複勝対象(正)の馬が label.fukusho_hit_validated に
    欠落している場合・reconcile_against_payout が verdict='fail' を返すことを実証。
    
    既存 test_check_payout_recall は mock cursor で _check_payout_recall ロジックを検証するが、
    本テストは合成 label/payout DataFrame で「正の馬の欠落」を直接注入し end-to-end で fail を実証。
    """
    from tests.ev.conftest import make_harai_mock, make_label_mock
    # payout 正の馬 = umaban=3,5,7 (make_harai_mock normal_hit)
    harai = make_harai_mock("normal_hit")
    # label から umaban=7（3着・payout正）を欠落させる注入
    labels_all_positive = [make_label_mock("normal_hit").assign(umaban=u) for u in [3, 5, 7]]
    labels_missing = [make_label_mock("normal_hit").assign(umaban=u) for u in [3, 5]]  # 7が欠落
    
    # reconcile が欠落を検出 → recall check が passed=False → verdict='fail'
    # （実装は reconcile_against_payout の合成 DataFrame インターフェースに依存）
    # ...注入と assert...
```

### SC#3 再現性スモーク（run_reproducibility_smoke.py の核心）
```python
# Source: scripts/run_train_predict.py L257-278 (--check-reproduce) +
#         src/model/orchestrator.py::_assert_deterministic (bit-identical)
# SC#4 の bit-identical を SC#3 の「フルパイプライン再現」に拡張適用

def run_reproducibility_smoke() -> int:
    """SC#3: snapshot→train→predict→backtest→eval が固定 seed で同一結果を再現することを確認。
    
    Phase 4 SC#4 の bit-identical インフラ（seed=42 + num_threads=1 + FIXED_REPRODUCE_TS）を
    orchestrate する薄いスクリプト。新規フルパイプライン runner は作らない（D-03）。
    """
    import subprocess
    steps = [
        # (1) Phase 4 SC#4: 両モデル bit-identical（合成データ・--no-write-db で高速）
        (["uv", "run", "python", "scripts/run_train_predict.py",
          "--check-reproduce", "--no-write-db"], "SC#4 bit-identical (train/predict)"),
        # (2) calibrator bit-identical pytest
        (["uv", "run", "pytest", "tests/model/test_calibrator.py::test_reproduce_bit_identical", "-q"],
         "calibrator bit-identical"),
        # (3) backtest --check-reproduce --synthetic（合成BT窓・決定論的）
        (["uv", "run", "python", "scripts/run_backtest.py",
          "--synthetic", "--bt-filter", "BT-1", "--check-reproduce", "--no-write-db"],
         "backtest bit-identical"),
        # (4) audit adversarial テスト群（SC#2 注入ケース全て GREEN）
        (["uv", "run", "pytest", "tests/audit/", "-q"], "SC#2 adversarial tests"),
    ]
    for cmd, desc in steps:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"FAIL: {desc}", file=sys.stderr)
            return 1
        print(f"PASS: {desc}")
    print("SC#3 reproducibility smoke: ALL PASS")
    return 0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 個別テストで各サーフェスを検証（Phase 1-7） | 監査レポートで集約可視化 + adversarial 補完（Phase 8） | Phase 8 | 「どこカバー済みか」が一枚で分かる。「Looks Done But Isn't」の検出。 |
| `run_train_predict --check-reproduce` 単体（Phase 4 SC#4） | フルパイプライン再現性 smoke（Phase 8 SC#3） | Phase 8 | train/predict のみ→snapshot→...→eval の全段階再現証明。 |
| Known Limitations が各 phase report に散在 | `reports/08-audit` の "Known Limitations" に集約（D-05） | Phase 8 | 回収率天井・Calibration劣位・odds再検証未完が一枚で分かる。honest 出荷判定。 |

**Deprecated/outdated:**
- なし（Phase 8 は新規アプローチの導入であり、既存手法の廃止ではない）

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `reports/08-audit.json` のサーフェス→テスト対応表は手動対応表を正とし・`--collect-only` は sanity check 補助 | Standard Stack / Architecture Patterns | marker 未付与テストが漏れる可能性。自動生成に変更する場合は marker 設備の拡張が必要。 |
| A2 | 再現性スモーク `run_reproducibility_smoke.py` は合成データ（`--synthetic`）をデフォルトとする | Architecture Patterns / Pitfall 4 | live-DB 全量は checkpoint:human-verify で別途実行。合成データ代表性に懸念がある場合は stamped snapshot 縮小サンプルを検討。 |
| A3 | SC#2 ケース3（fold共有）は既存 `test_get_bt_race_ids_raises_on_leak` が注入→fail を実現済みのため、adversarial 新設の付加価値は限定的 | SC#2 棚卸し表 | planner が重複と判断し新設をスキップした場合、SC#2 の「3ケースそれぞれ独立 adversarial」要件を満たさない可能性。SC#2 専用 docstring で再定式化することを推奨。 |
| A4 | `src/audit/report.py` を新設し `src/ev/report.py` の DRY パターンを再利用する | Architecture Patterns | reports/ 生成ロジックを scripts/ に直接書く選択肢もある。規模が小さい場合は scripts/ 直書きでも可（planner 判断）。 |
| A5 | D-06 UI 監査の「書き込み SQL 注入で fail」メタ検証は、一時的に INSERT を含むダミー .py を tmp_path に配置して AST 検査が fail することを実証する | D-06 棚卸し表 | AST 検査の対象ディレクトリ（`src/ui/`）を tmp_path に差し替える必要があり、実装の複雑さが増す。既存 `test_readonly_guarantee` の拡張で十分な場合は新設不要。 |

## Open Questions

1. **adversarial 3ケースの「既存テストとの棲み分け」の最終判定（Claude's Discretion）**
   - What we know: SC#2 ケース3（fold共有）は既存 `test_get_bt_race_ids_raises_on_leak` が注入→raise を実現済み。ケース1・2は機能テストが近接するが「注入するとfail」メタ検証は未確立。
   - What's unclear: ケース3を新設するか、既存テストへの cross-reference のみで SC#2 要件を満たすか。
   - Recommendation: SC#2 が「それぞれ独立 adversarial テストとして確保する」を明示するため、3ケース全て `tests/audit/` に新設し docstring で既存テストへの cross-reference を含む。ケース3は既存パターンの再定式化（SC#2 専用 docstring）。

2. **再現性スモークの live-DB 実行要否（Claude's Discretion）**
   - What we know: 合成データ（`--synthetic`）で bit-identical は証明可能（Phase 4 SC#4 実績）。live-DB 全量は重い。
   - What's unclear: SC#3「フルパイプライン再現」に live-DB 実データの再現性証明が含まれるか。
   - Recommendation: 合成データをデフォルトとし（D-03 の keep it simple）、live-DB 全量の再現性は Phase 4 SC#4 の既存実績（262 passed・bit-identical PASS）で代用。reports/08-audit に「合成データ smoke GREEN + Phase 4 SC#4 live-DB bit-identical 既証明」と記録。

3. **監査レポートの CI 統合（Deferred）**
   - What we know: config.json に CI 設定なし。個人開発ローカル。
   - What's unclear: 将来の PHASE2/OPS で CI 統合する際の拡張点。
   - Recommendation: Phase 8 では CI 統合は最小限（D-04 の unset 全実行が主）。将来拡張の前提として `reports/08-audit.json` を機械消費可能な構造にする。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (everydb2) | D-04 unset 全実行ゲート（SC#1 GREEN） | ✓ | 15.18 (Homebrew) | —（必須・BLOCK項） |
| Python 3.12 | 全テスト実行 | ✓ | 3.12.13 | 3.11 (§17.1 fallback) |
| uv | テスト実行・スクリプト実行 | ✓ | ≥0.11 (host has 0.11.21) | — |
| pytest | 全テスト実行 | ✓ | 9.1.0 | — |
| live-DB 接続（.env） | requires_db テスト（14ファイル） | 要確認（.env 設定） | — | KEIBA_SKIP_DB_TESTS=1 で skip（但し SC#1 GREEN 証明には unset 必須） |

**Missing dependencies with no fallback:**
- なし（PostgreSQL 15.18 + Python 3.12.13 + uv 0.11.21 は host で確認済み）。

**Missing dependencies with fallback:**
- live-DB 接続: `.env` 未設定の場合、`KEIBA_SKIP_DB_TESTS=1` で DB 不要テストのみ実行可能。但し SC#1 GREEN 証明（D-04）には `.env` 設定 + unset が必須。planner は checkpoint:human-verify で live-DB 実行を確認。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（既存 pin） |
| Config file | pyproject.toml `[tool.pytest.ini_options]`（L43-46: testpaths=["tests"]・addopts="-ra"・markers=["requires_db: ..."]） |
| Quick run command | `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q`（491テスト・DB 不要層・~30秒） |
| Full suite command | `uv run pytest -q`（KEIBA_SKIP_DB_TESTS unset・全 requires_db 含む・要 live-DB） |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 (SC#1 #1 label) | fukusho label generation が正しい | unit | `uv run pytest tests/test_fukusho_label.py -q` | ✅ 既存 |
| TEST-01 (SC#1 #2 payout) | payout-table reconciliation >99.9% | unit + integration(requires_db) | `uv run pytest tests/test_label_reconcile.py -q` | ✅ 既存 |
| TEST-01 (SC#1 #3 取消除外中止) | 取消/除外/競走中止 handling | unit | `uv run pytest tests/ev/test_refund_accounting.py tests/test_fukusho_label.py -q -k "scratch or dead_loss or cancelled or excluded"` | ✅ 既存 |
| TEST-01 (SC#1 #4 odds snapshot) | fixed-odds-snapshot enforcement | unit | `uv run pytest tests/ev/test_odds_snapshot.py -q` | ✅ 既存 |
| TEST-01 (SC#1 #5 virtual purchase) | virtual-purchase rules | unit | `uv run pytest tests/ev/test_purchase_simulator.py -q` | ✅ 既存 |
| TEST-01 (SC#1 #6 cutoff) | feature_cutoff_datetime enforcement | unit | `uv run pytest tests/features/test_pit_cutoff.py tests/features/test_rolling.py -q` | ✅ 既存 |
| TEST-01 (SC#1 #7 split) | race_id-unit split disjointness | unit | `uv run pytest tests/utils/test_group_split.py -q` | ✅ 既存 |
| TEST-01 (SC#1 #8 class) | class normalization 2019 reform | unit + integration(requires_db) | `uv run pytest tests/test_class_normalization.py -q` | ✅ 既存 |
| TEST-01 (SC#1 cat/missing) | categorical/missing handling | unit | `uv run pytest tests/model/test_trainer.py -q` | ✅ 既存 |
| TEST-01 (SC#2 lookahead) | lookahead 注入検出 adversarial | unit（合成データ） | `uv run pytest tests/audit/test_audit_features.py -q` | ❌ Wave 1 新設 |
| TEST-01 (SC#2 payout正欠損) | payout 正欠損検出 adversarial | unit（合成データ） | `uv run pytest tests/audit/test_audit_label.py -q` | ❌ Wave 1 新設 |
| TEST-01 (SC#2 fold共有) | fold race_id 共有検出 adversarial | unit（合成データ） | `uv run pytest tests/audit/test_audit_split.py -q` | ❌ Wave 1 新設 |
| TEST-01 (D-06 UI/CSV) | UI read-only / スタンプ inline adversarial | unit | `uv run pytest tests/audit/test_audit_ui_csv.py -q` | ❌ Wave 1 新設 |
| TEST-01 (SC#3 再現性) | フルパイプライン固定 seed 再現 | smoke (subprocess orchestrate) | `uv run python scripts/run_reproducibility_smoke.py` | ❌ Wave 2 新設 |
| TEST-01 (SC#1 GREEN) | KEIBA_SKIP_DB_TESTS unset 全実行 | integration (live-DB) | `uv run pytest -q`（unset・checkpoint:human-verify） | ✅（既存テスト実行・新設なし） |

### Sampling Rate
- **Per task commit:** `KEIBA_SKIP_DB_TESTS=1 uv run pytest tests/audit/ -q`（新設 adversarial のみ・高速）
- **Per wave merge:** `KEIBA_SKIP_DB_TESTS=1 uv run pytest -q`（DB 不要層フル）
- **Phase gate:** `uv run pytest -q`（KEIBA_SKIP_DB_TESTS unset・全 requires_db 含む・live-DB 必須） + `scripts/run_reproducibility_smoke.py` GREEN

### Wave 0 Gaps
- [ ] `tests/audit/__init__.py` — 新規パッケージ
- [ ] `tests/audit/conftest.py` — 合成 DataFrame 注入ヘルパー（`tests/features/conftest.py` パターン再利用）
- [ ] `tests/audit/test_audit_label.py` — SC#2 ケース2（payout 正欠損注入）
- [ ] `tests/audit/test_audit_features.py` — SC#2 ケース1（lookahead 注入）
- [ ] `tests/audit/test_audit_split.py` — SC#2 ケース3（fold 共有注入）
- [ ] `tests/audit/test_audit_ui_csv.py` — D-06（UI 書込経路 / スタンプ欠落検出）
- [ ] `scripts/run_reproducibility_smoke.py` — SC#3 orchestrate
- [ ] `src/audit/report.py`（or scripts/ 直書き） — `reports/08-audit.{md,json}` 生成

*(既存491テストは Wave 0 対象外・変更なし)*

## Security Domain

> config.json `security_enforcement: true`・`security_asvs_level: 1`。Phase 8 はテスト・監査層（read-only・外部入力なし）だが、セキュリティドメインを記載する。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 8 は認証なし（ローカル実行） |
| V3 Session Management | no | Phase 8 はセッションなし |
| V4 Access Control | yes（read-only 監査） | `tests/audit/test_audit_ui_csv.py` が `src/ui/` の read-only 保証（書き込み経路不存在）を AST で検証。既存 `test_readonly_guarantee.py` の拡張。 |
| V5 Input Validation | yes（合成データ注入） | adversarial テストの合成 DataFrame は制御された入力（seed 固定・PII なし）。実データ入力なし。 |
| V6 Cryptography | no | Phase 8 は暗号操作なし |
| V7 Error Handling | yes（fail-loud） | adversarial テストは「リーク注入時に fail（raise/assert失敗）する」ことを検証。silent failure の検出が目的。 |
| V9 Communications | no | Phase 8 は外部通信なし（ローカル PostgreSQL のみ） |
| V14 Configuration | yes | `KEIBA_SKIP_DB_TESTS` unset 全実行が「設定ミスで GREEN が未検証のまま通る」を防止（conftest.py fail-by-default policy）。 |

### Known Threat Patterns for Test/Audit Layer

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| テストが silent skip で GREEN と誤認 | Repudiation | `KEIBA_SKIP_DB_TESTS` unset で全 requires_db 実行（D-04）。conftest.py は fail-by-default（unset で Settings validation error）。 |
| 監査レポートが実態と乖離（カバレッジ虚偽） | Tampering | `--collect-only` で対応表の sanity check。手動対応表を正。 |
| adversarial テストが false-pass（リーク注入でも fail しない） | Tampering | `test_no_target_encoding_leak` の注入→fail 実証パターンを踏襲。threshold assert で検証力を証明。 |
| UI/CSV に書き込み経路が混入（read-only 違反） | Elevation of Privilege | AST で SQL 文字列リテラルの INSERT/UPDATE/DELETE/TRUNCATE/CREATE/DROP/ALTER を検出（既存 `test_readonly_guarantee.py`）。 |
| 再現性スタンプ欠落（§19.1 聖域違反） | Tampering | presence assert で5スタンプ（odds_snapshot_policy/odds_snapshot_at/model_version/feature_snapshot_id/backtest_strategy_version）の存在を検証（既存 `test_csv_columns.py`）。 |

## Sources

### Primary (HIGH confidence・コードベース直接精査)
- `tests/conftest.py` — KEIBA_SKIP_DB_TESTS skipif 機構・fail-by-default policy・requires_db marker [VERIFIED: L56-84]
- `pyproject.toml` L43-46 — `[tool.pytest.ini_options]` testpaths/addopts/markers [VERIFIED]
- `tests/model/test_trainer.py::test_no_target_encoding_leak` — SC#2 adversarial 鋳型（意図的リーク注入で DEMONSTRABLY fail・L277-486） [VERIFIED]
- `tests/features/test_pit_cutoff.py` — SC#1 #6 cutoff enforcement 機能テスト（6テスト） [VERIFIED]
- `tests/features/test_rolling.py::test_two_observation_window_is_per_observation_not_per_horse` — CYCLE-2 cross-obs adversarial [VERIFIED]
- `tests/test_label_reconcile.py` — SC#1 #2 payout reconciliation（18テスト・>99.9% agreement[requires_db]） [VERIFIED]
- `tests/utils/test_group_split.py` — SC#1 #7 race_id split（10テスト・raises_on_leak で注入→raise 実現） [VERIFIED]
- `tests/ev/test_odds_snapshot.py::test_odds_snapshot_future_leak` — SC#1 #4 odds snapshot 後知恵注入検出 [VERIFIED]
- `tests/ev/test_refund_accounting.py` — SC#1 #3 取消除外中止（11シナリオ決定表） [VERIFIED]
- `tests/features/test_allowlist.py` — SC#1 #6 allowlist enforcement（banned timing feature 検出） [VERIFIED]
- `tests/test_class_normalization.py::test_code_005_spans_reform` — SC#1 #8 2019 reform 連続性 [VERIFIED]
- `tests/ui/test_readonly_guarantee.py` — D-06 UI read-only AST 検査（Phase 7 既存） [VERIFIED]
- `tests/ui/test_csv_columns.py::test_prediction_csv_has_all_stamps` — D-06 スタンプ presence assert [VERIFIED]
- `src/ev/report.py` — md+json 分離 reports DRY パターン（REPORT_COLUMNS・generate_report・_atomic_write_text） [VERIFIED: L41-274]
- `scripts/run_train_predict.py` L257-278 — SC#4 `--check-reproduce` bit-identical（seed=42 + FIXED_REPRODUCE_TS） [VERIFIED]
- `src/model/orchestrator.py` L88, L765 — FIXED_REPRODUCE_TS 定数・_assert_deterministic [VERIFIED]
- `tests/model/test_calibrator.py::test_reproduce_bit_identical` L137-175 — calibrator bit-identical pytest [VERIFIED]
- `tests/ev/test_run_backtest_e2e.py::test_check_reproduce_smoke` — backtest --check-reproduce smoke [VERIFIED]
- `reports/06-evaluation.json` — Known Limitations 数値根拠（回収率 LightGBM 0.7022/CatBoost 0.6808・calibration_max_dev LGB 0.2308 vs BL-1 0.0014） [VERIFIED]
- `reports/04-eval.json` — BL 比較表（Calibration 劣位の数値根拠） [VERIFIED]

### Secondary (MEDIUM confidence)
- `.planning/phases/07-presentation/07-CONTEXT.md` — D-06 Deferred（UI/CSV 監査の Phase 8 委譲） [CITED: L137-139]
- `.planning/phases/04-model-prediction/04-CONTEXT.md` — D-02/D-03/D-04 先例（SC#3 対抗的構造診断・SC#4 bit-identical・KEIBA_SKIP_DB_TESTS unset 最終ゲート 262 passed） [CITED]
- memory `phase7-ui-live-db-bugs` — live-DB でしか発覚しない bug（sys.path ガード・SQL 引用符・Streamlit deprecation） [CITED]
- memory `fukusho-recovery-070-structural-ceiling` — 回収率~0.65天井は odds-free 1-A の構造的限界 [CITED]

### Tertiary (LOW confidence)
- なし（全てコードベース直接精査または既存成果物から確認）

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 既存パッケージのみ・新規インストールなし・pyproject.toml で pin 確認済み
- Architecture: HIGH — src/ev/report.py の DRY パターン・test_no_target_encoding_leak の鋳型・run_train_predict --check-reproduce の既存インフラを全て直接精査
- Pitfalls: HIGH — 既存テストとの重複リスク・KEIBA_SKIP_DB_TESTS の skip 挙動・監査レポート乖離リスクを conftest.py と既存テスト構造から特定
- SC#1/#2 マッピング: HIGH — 491テストを8サーフェス+SC#2 3ケースに全てマッピング・各テスト関数の検証意図を直接確認
- Known Limitations 数値: HIGH — reports/06-evaluation.json と reports/04-eval.json から回収率・Calibration の正確な数値を確認

**Research date:** 2026-06-24
**Valid until:** 2026-07-24（安定フェーズ・外部ライブラリ依存なし・30日）

## RESEARCH COMPLETE
