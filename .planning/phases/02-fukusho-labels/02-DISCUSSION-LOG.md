# Phase 2: Fukusho Labels - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-17
**Phase:** 2-Fukusho Labels
**Areas discussed:** sales_start_entry_count 復元と inferred/unresolved 境界, 払戻テーブル突合ゲート, ラベル生成スコープ, 状況系エッジの分類

---

## 復元の厳しさ（sales_start_entry_count 復元と inferred/unresolved 境界）

| Option | Description | Selected |
|--------|-------------|----------|
| ハイブリッド | 払戻対象数 `fukusho_payout_places`（ラベル境界）は厳格、`sales_start_entry_count`（補助）は `inferred` で保持 | ✓ |
| 全面厳格 | 復元根拠が薄いものは頭数含めて全て `unresolved` で学習除外 | |
| 全面実用 | `TorokuTosu` を発売開始時点頭数の代理とし `inferred` で積極保持 | |

**User's choice:** ハイブリッド
**Notes:** ラベル境界（払戻対象数）には純度、補助メタデータには寛容さを振り分ける。Phase 1 D-01/D-13 と整合。Core Value（ラベル正確性＝リーク防止と同等の聖域）に合致。

---

## 突合ゲート哲学（>99.9% 達成後の残り <0.1% と不整合レースの扱い）

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 1 踏襲 | hybrid gate：構造的不整合=ブロック（`unresolved` で学習除外）、量的ドリフト=参考レポート。Phase 1 D-01 と一貫 | ✓ |
| 残り全件調査 | <0.1% の不一致を全て個別解決してから出荷 | |
| 自動隔離＋報告 | 不整合は自動 `unresolved` 化し割合のみレポート | |

**User's choice:** Phase 1 踏襲
**Notes:** ラベル誤りは Phase 3-6 下流へ直結するため構造的欠陥は聖域として止める。EveryDB2 既知のデータ揺れで過剰 FAIL しない点は Phase 1 D-01 と一貫。研究者が §10.5 の6検査を構造/量化に分類。

---

## ラベル生成スコープ（全件網羅 vs モデル対象のみ）

| Option | Description | Selected |
|--------|-------------|----------|
| 全件網羅＋除外旗 | 全レース/全馬にラベル行生成、`is_model_eligible` で除外セット明示 | ✓ |
| モデル対象のみ | §7.2 対象レースのみ生成 | |

**User's choice:** 全件網羅＋除外旗
**Notes:** §7.3「データ保存のみ」レースもラベル付きで保持。Phase 8 監査性・将来 v2 対象拡張・Core Value 再現性に合致。同データスキャンで低コスト。

---

## 状況系エッジの分類（固定4値 status + 除外旗への写像）

| Option | Description | Selected |
|--------|-------------|----------|
| 観測事実で分類 | 不成立/レース全体中止=`unresolved`、特払=払戻対象馬があれば `validated`、馬個別競走中止=学習0。HR/SE 観測事実のみ推測なし | ✓ |
| 保守的全除外 | 特払・不成立含め「標準的でない払戻」は全て `unresolved` | |
| 研究者に委ねる | 実データで各エッジの頻度と JRA 規則を調査の上、計画時に推奨分類を提示 | |

**User's choice:** 観測事実で分類
**Notes:** §10.4「払戻テーブル優先」＋観測事実のみ（推測なし・D-13 整合）。特払は実在中なら正当 outcome なので過剰除外しない。不成立/全体中止は outcome 非確定なので除外。

---

## Done（残りグレーエリアの扱い）

| Option | Description | Selected |
|--------|-------------|----------|
| コンテキストへ | 4領域の決定で十分。残り(E/F)は研究者/計画者に委ねて CONTEXT.md 作成 | ✓ |
| さらに深掘り | (E) 成績レコード権威 と (F) >99.9%ゲート試験設計 を深掘り | |

**User's choice:** コンテキストへ
**Notes:** 残り2候補（成績レコード権威・ゲート試験設計）は研究/計画領域寄りと判断し Claude's Discretion に委ねた。

---

## Claude's Discretion

- **成績レコードの権威:** SE/HR の複数 `DataKubun` レコード（木曜/金土/速報/月曜確定）から月曜確定のみ（`validated`）か最新利用可・速報は `inferred` か。研究者が実データの可用性で決定。指針: 歴史レースは月曜確定が原則入手可能
- **`>99.9%` ゲートの試験設計:** held-out サンプル設計と「agreement」の定義（馬集合完全一致か precision/recall か）。SC#2 検証可能性。計画者が設計
- **`sales_start_entry_count` 具体復元ロジック:** どのカラム/タイムスタンプで復元するか。STATE.md の research flag → 実カラム精査が必須
- **§10.5 の6検査の構造/量化分類:** D-02 に基づく各検査の分類対応表
- **ラベルテーブル/カラム具体設計:** §10.2 保持項目 + `is_model_eligible` の網羅・`label_generation_version` 採番方式
- **n_harai(HR)・n_hyosu(成績) の取り扱い:** raw 直読み（明示キャスト）か先に normalized 化か

## Deferred Ideas

- **Phase 3:** feature_availability registry 本格運用・PIT feature builder・Parquet snapshot。Phase 2 はラベル層のみ
- **Phase 4:** `fukusho_hit_validated` を目的変数に学習
- **Phase 5:** 取消/除外の返還（`effective_stake=0`）・競走中止の `effective_stake=100`・固定ルール仮想購入シミュレータ。Phase 2 は status/flag のみ
- **Phase 8:** D-02 突合ゲート・D-04 エッジ分類・`sales_start_entry_count` 復元への対抗的監査テスト
- **v2:** 障害/新馬のモデル対象化（Phase 2 は `is_model_eligible=False` で保持のみ）
