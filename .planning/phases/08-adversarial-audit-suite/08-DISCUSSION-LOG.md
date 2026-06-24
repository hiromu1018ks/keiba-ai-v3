# Phase 8: Adversarial Audit Suite - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 8-Adversarial Audit Suite
**Areas discussed:** 統合成果物の形, 注入テスト深度, 再現性スモーク(SC#3), DB必須とゲート証憑, honest既知限界, UI/CSV対抗的監査

---

## 統合成果物の形

| Option | Description | Selected |
|--------|-------------|----------|
| 両方(レポート＋新規テスト) | `reports/08-audit.{md,json}`（サーフェス別カバレッジマップ・SC対応表）で既存476テストを集約可視化 ＋ ギャップを `tests/audit/` 新設で補完 | ✓ |
| 監査レポート集約のみ | 既存テストは十分。`reports/08-audit` で集約・可視化のみ。新規テストは SC#2 必須3ケースのみ最小補完 | |
| 新規テスト新設のみ | `tests/audit/` に専用統合 adversarial テストを新設、既存はそのまま。レポート生成は最小 | |

**User's choice:** 両方(推奨)
**Notes:** SC#1/#2 のほぼ全サーフェスは既存476テストで既カバー。Phase 8 の付加価値は「一枚の監査レポートに集約可視化し、真のギャップを注入型 adversarial で補完すること」。TEST-01「対抗的監査テストを含む」に最適合。

---

## 注入テスト深度

| Option | Description | Selected |
|--------|-------------|----------|
| SC#2必須3ケース中心 | lookahead注入検出 / payout正欠損検出 / fold の train/test race_id共有検出 を独立 adversarial として確保。既存476が functional 検証を担い、注入型は3つを代表とする | ✓ |
| 全サーフェスに注入展開 | SC#1 の8+リークサーフェス全てに「リーク注入→fail」メタテストを体系展開。最も厳密だが工数大・重複リスク | |
| Claude判断(ギャップ分析次第) | researcher が既存テストの adversarial カバーを棚卸しし、真のギャップだけ補完 | |

**User's choice:** SC#2必須3ケース中心(推奨)
**Notes:** `test_no_target_encoding_leak`（Phase 4・注入で DEMONSTRABLY fail 実証）が再利用パターン。3ケースは `test_pit_cutoff` / `test_label_reconcile` / `test_group_split` に近接——researcher が重複を避け真のギャップだけ新設。

---

## 再現性スモーク(SC#3)

| Option | Description | Selected |
|--------|-------------|----------|
| 既存CLI+pytestを束ねる | `scripts/run_reproducibility_smoke.py` で `run_train_predict --check-reproduce`＋bit-identical pytest＋backtest/eval を orchestrate。新規 runner なし・重複回避 | ✓ |
| 新規統合smoke runner | snapshot→...→eval を一本化した新規 runner。stamped snapshot からフル再生。最も完全だが工数大・Phase 4 SC#4 と重複 | |
| Claude判断 | researcher が既存 check-reproduce/E2E smoke カバーを棚卸し、足りない段階だけ補う | |

**User's choice:** 既存CLI+pytestを束ねる(推奨)
**Notes:** Phase 4 SC#4 が既に bit-identical を確立済み。新規重厚 runner は重複し keep it simple に反する。薄い orchestrate スクリプトで SC#3 を満たす。

---

## DB必須とゲート証憑

| Option | Description | Selected |
|--------|-------------|----------|
| unset全実行+監査レポート | Phase 4 踏襲。`KEIBA_SKIP_DB_TESTS` unset で全 `requires_db` 実行し GREEN 証明。`reports/08-audit.{md,json}` を出荷ゲート証憑として生成 | ✓ |
| CI(DB不要)+手動live-DB分離 | CI は DB 不要層を自動実行、live-DB 全実行は checkpoint:human-verify 手動層に分離 | |
| Claude判断 | researcher がテスト実行環境（CI 有無・live-DB 接続前提）を棚卸しし判断 | |

**User's choice:** unset全実行+監査レポート(推奨)
**Notes:** Phase 4 で 38 requires_db 全実行・262 passed の先例。memory `phase7-ui-live-db-bugs`（live-DB でしか発覚しない bug）に整合。個人開発ローカル（PostgreSQL 15.18 Homebrew）。

---

## honest既知限界の可視化

| Option | Description | Selected |
|--------|-------------|----------|
| 含める | `reports/08-audit` に "Known Limitations" セクションで既知限界（回収率~0.65天井・odds JODDS再検証subject・Calibration BL劣位）を隠さず明示 | ✓ |
| 含めない | 監査レポートは GREEN/カバレッジのみ。限界は既存 reports/05・06・04-eval 記載済みなので重複回避 | |
| Claude判断 | researcher が既存 reports 記載状況を棚卸しし統合要否を判断 | |

**User's choice:** 含める(推奨)
**Notes:** "Looks Done But Isn't" ゲートの核心。機能テストでは表現できない「概念的正直さ」を監査レポートで担保。Core Value（過大表示回避・実馬券購入しない個人分析）に整合。memory `fukusho-recovery-070-structural-ceiling` に整合。

---

## UI/CSV対抗的監査（Phase 7 Deferred 継承）

| Option | Description | Selected |
|--------|-------------|----------|
| 含める | 07-CONTEXT Deferred「UI/CSV の read-only 保証・再現性スタンプ inline 検出」を `tests/audit/` に追加。TEST-01「対抗的監査テストを含む」に合致 | ✓ |
| 含めない | ROADMAP SC#1-#3 は UI/CSV 監査を明示せず。read-only は GRANT 担保済み・スタンプ inline は Phase 7 実装済みなので最小限 | |
| Claude判断 | researcher が Phase 7 実装と Phase 8 SC の重複を棚卸しし判断 | |

**User's choice:** 含める(推奨)
**Notes:** 07-CONTEXT が明示的に Phase 8 に委ねた項目。memory `phase7-ui-live-db-bugs`（live-DB 必須 bug）への対処も兼ねる。SC#1 明示リスト外だが 07-CONTEXT Deferred と TEST-01 包括表現でスコープ内。

---

## Claude's Discretion

- `tests/audit/` の内部ファイル構成（サーフェス別分割 vs 単一）・各 adversarial テストの注入手法（合成 DataFrame で T+1 データ混入等）
- サーフェス別カバレッジマップの機械化（pytest `--collect-only` + marker vs 手動 SC↔テスト対応表）
- adversarial 3ケースと既存テスト（`test_pit_cutoff`/`test_label_reconcile`/`test_group_split`）の重複回避判定（researcher 棚卸し次第）
- 再現性スモークの対象データ規模（合成 vs stamped snapshot 縮小サンプル）
- CI 統合の要否（個人開発ローカル・config に CI 設定なし・Phase 8 では最小限）

## Deferred Ideas

- CI 環境での自動テスト実行（PHASE2 / OPS-01・02）— GitHub Actions 等・push hook・pre-commit 連携
- MLflow/Optuna 連携テスト基盤（OPS-01/02・§21 defer）
- より広範な mutation testing / property-based testing（`hypothesis` 等）の全サーフェス展開 — 現状は SC#2 の3ケース中心
- フルパイプライン end-to-end runner の完全一本化 — Phase 4 SC#4 と重複するため見送り

### Reviewed Todos (not folded)
- `phase3-advisory-hardening.md` — Phase 3.1 で解決済み・Phase 8 と無関係（keyword "phase" の偶発一致）
