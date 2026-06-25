# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Leak-Free Fukusho Pipeline

**Shipped:** 2026-06-25
**Phases:** 9 (1-8 + 3.1) | **Plans:** 40 | **Tasks:** 82

### What Was Built
- **leak-free odds-free 複勝 `p_fukusho_hit` pipeline**（SC#1 Parquet-only 学習・SC#3 leak diagnostic・SC#4 bit-identical・LightGBM 4.6 + CatBoost 1.2.10）
- **複勝ラベル ETL + 払戻テーブル突合**（>99.9% 実測100%・554,267行・6 §10.5 BLOCK checks・2層 raw/validated label）
- **PIT-correct 不変 Parquet snapshot**（62 features・byte-reproducible・3者 registry parity・merge_asof backward）
- **race_id-grouped 再現可能 backtest**（25 backtest・行レベル DB 永続化 1,184,052行・返還/中止 honest 会計・固定 odds_snapshot_policy）
- **確率品質ゲート**（Brier/LogLoss/Calibration/sum(p)/segment 6軸・主モデル LightGBM 確定・gate=WARN・SC#2 達成）
- **read-only Streamlit UI**（3タブ）+ CSV（20/16列 BOM+CRLF）+ **対抗的監査**（tests/audit/・フルスイート 499 passed）

### What Worked
- GSD workflow の **strict DAG**（label→feature→model の順序保証・no model before labels locked）がリーク防止に有効だった
- **adversarial audit**（tests/audit/・5段階鋳型）が機能テストでは捕捉できない lookahead/payout/fold のリークを構造的に検出した
- debug session fukusho-recovery-070 の**科学的診断**（falsification test・ヘッドルム測定）で回収率0.65-0.70天井の ROOT CAUSE を確定（閾値 fix でなく構造的限界と結論・ Sanctuary Note で過学習聖域の文字面違反も正直記録）
- **staging-swap idempotent ETL + SHA256 byte-reproducible snapshot** で §19.1 再現性聖域を機械保証
- **live-DB 検証**（KEIBA_SKIP_DB_TESTS unset・フルスイート 499 passed）が unit test では見えない bug を暴露した（memory `phase7-ui-live-db-bugs`）

### What Was Inefficient
- `label.fukusho_label.race_date` が **3度再発**（某経路で消失・quick-260625-h1g で race_key kaiji/racenum zfill 正規化により根本根絶まで時間を要した）
- Phase 5 実データ backtest の **DB 永続化漏れ**（GAP-INT-01・`--no-write-db` で走った可能性・マイルストーン監査の統合チェッカー実DBクエリで発覚・run_backtest 再実行で解消）
- モデルの **Calibration が BL-1/BL-4 に劣る**（MODL-02 部分証明）を Phase 6 まで先送り・gate=WARN で正直記録したが改善は次マイルストーン

### Patterns Established
- **staging-table-swap**（LIKE でなく DDL 駆動・idempotent・backtest_id/model_version scoped）で silent 履歴破壊防止
- **frozen category map**（JSON・training-window-only fit・`__UNSEEN__`/`__MISSING__` sentinel）でリーク防止 + byte-repro
- **`CalibratedClassifierCV(cv='prefit')`** on strictly-later disjoint slice で時系列キャリブ
- **`merge_asof(direction='backward')`** で PIT-correct as-of join
- **adversarial 5段階鋳型**（docstring cross-reference・KEIBA_SKIP_DB_TESTS gate・fail-by-default）で false-pass 構造的排除
- **bit-identical SC#4**（固定 seed + thread count=1 + FIXED_REPRODUCE_TS）

### Key Lessons
1. **live-DB 検証は unit test で代替できない**（memory `run-authorized-ops-directly`・`feature-snapshot-regen-required`）。`KEIBA_SKIP_DB_TESTS` unset のフルスイートが本番 bug を暴露する。許可済み live-DB 操作は人手に回さず自分で実行する。
2. **監査（gsd-audit-milestone）は運用ギャップを暴露する**。GAP-INT-01（report 25行 vs DB 2行）は統合チェッカーの実DBクエリで初めて発覚・各 Phase verification の通過だけでは不十分。マイルストーン完了前に必ず監査を通す。
3. **構造的限界は要件未達でなく正直な結論**。回収率0.65-0.70天井は odds-free 1-A の構造的限界・閾値 fix でなく debug session の falsification test で「ヘッドルム無し」を確定し別計画フェーズへ委譲するのが正しい。
4. **再現性聖域（§19.1）は行レベルで守る**。report の決定論的再生成だけでは不十分・DB 永続化（`backtest.fukusho_backtest`）まで含めて「同じ条件で再現できること」を満たす。

### Cost Observations
- 期間: 2026-06-16 → 2026-06-25（9日間）
- commits: 449・plans: 40・tasks: 82
- Python LOC: 39,658（src/tests/scripts）
- Notable: 9日間で leak-free pipeline を完了・adversarial audit 499 passed で出荷品質担保・監査で発覚した GAP-INT-01 を即座に解消して passed 昇格

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | (初回) | 9 | GSD strict DAG + adversarial audit gate + live-DB フルスイート検証を確立 |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | 499 passed (live-DB フルスイート・1 skipped は Phase 6 既知) | (adversarial audit でリーク防止を構造保証・行カバレッジ計測せず) | LightGBM/CatBoost/scikit-learn/mlxtend/psycopg3/uv（要件固定 stack） |

### Top Lessons (Verified Across Milestones)

1. live-DB 検証は unit test で代替不可（v1.0 で確立・次マールストーンも維持）
2. 監査は運用ギャップを暴露する（v1.0 で GAP-INT-01 発覚・次マールストーンも完了前に監査を実施）
3. 構造的限界は正直な結論（v1.0 で回収率0.65-0.70天井・次マールストーンで戦略判断）
