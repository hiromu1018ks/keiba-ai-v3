# Phase 5: EV & Backtest - Research

**Researched:** 2026-06-20
**Domain:** 複勝 EV 計算・固定オッズ時点仮想購入 backtest・返還/中止 honest 会計・BT-1..5 フル行列（PostgreSQL 15 / pandas / LightGBM 4.6 / CatBoost 1.2.10 / sklearn 1.9 / psycopg3）
**Confidence:** HIGH（実DBスキーマ・要件定義書・既存コード契約をすべて実証済み・外部ライブラリ不要）

## Summary

Phase 5 は Phase 4 のキャリブレーション済み予測 `p_fukusho_hit` を消費し、**固定 `odds_snapshot_policy`（JODDS 発走30分前/10分前）** で `EV_lower`/`EV_upper`・推奨ランクを算出、race_id-grouped 時系列で固定ルール（`fukusho_ev_v1`）の仮想購入 backtest を **BT-1..5 × {30min,10min} × {lightgbm,catboost} ≈ 20 backtest** のフル行列で実行する。返還/競走中止/dead-loss の honest 会計（§11.6）で回収率/P/L/max drawdown を算出し、**全候補を一括報告**（後知恵 winner 単独報告禁止・BACK-04）する。

最大の技術的決定点は **3 点**：

1. **オッズ時点選択のリーク防止**（D-01/D-02・EV-01/BACK-04・Core Value 直結）— JODDS `HappyoTime`(mmddHHMM) と `n_race.HassoTime`(hhmm) の差分で「発走N分前」を算出し、`merge_asof(direction='backward')` 等価の直近 snapshot 選択で未来リークを構造的に排除する。`n_jodds_tanpukuwaku_head.datakubun` で中間(`1`)/最終(`3`)/確定(`4`)/中止(`9`)を判定。特殊値（`----`/`****`/`0000`/`0999`）と snapshot 0件は `no_bet` sentinel 化（§11.3・silent fallback 禁止）。
2. **BT窓再学習ループの既存 orchestrator 拡張**（D-03）— `src/model/data.py::split_3way` は固定暦年 mask（train 2016-07〜2023 / calib 2024-01〜06 / test 2024-07〜12）をハードコードしており BT窓（BT-1 train 2019-06〜2022/test 2023 等）を表現できない。`train_calib_test_periods` パラメータを追加して BT窓ごとに train/calib/test 期間を注入する拡張が最小変更でリーク防止 guard（strict chronological / race_key disjoint）を継承できる。
3. **返還/中止 honest 会計の決定表**（D-05・BACK-02/BACK-03）— `label.fukusho_label` の既存フラグ（`is_scratch_cancel`/`is_race_cancelled`/`is_race_excluded`/`is_dead_loss`/`is_fukusho_sale_available`/`fukusho_payout_places`/`fukusho_hit_validated`）と `public.n_harai`（`FuseirituFlag2`/`HenkanFlag2`/`HenkanUma1..28`/`PayFukusyoUmaban1..5`/`PayFukusyoPay1..5`）を組み合わせ、6 シナリオ（通常/取消/除外/中止/不成立/同着）の `effective_stake`/`payout`/`profit` を決定する。実DB観測: 複勝返還 1,541件 / 不成立 0件 / 特払 0件（BACK-03 対抗的テストは合成データで全シナリオを網羅）。

**Primary recommendation:** 既存コード契約（`split_3way` の時系列 guard・`prediction_load` の staging-swap・`fukusho_label` の返還フラグ・`fetch_market_data` の JOIN PK 構造）を最大限再利用し、新規コードは（a）BT窓ヘルパ `group_split.py`・（b）JODDS 時点選択クエリ・（c）EV/rank 計算・（d）仮想購入シミュレータ・（e）返還会計決定表・（f）backtest 結果テーブル DDL + load・（g）BL-3 betting ROI の 7 ユニットに集約する。実JODDS取得は進行中（2026-06-20 時点 2015年25レース日分のみ）のため、実装・単体テスト・合成データ検証を先行し、BT期間 2019-2025 の取得完了後に実データ backtest を実行する 2 段階計画とする。

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EV-01 | `EV_lower = p × odds_lower` / `EV_upper = p × odds_upper` 算出 | §11.1 直線積・`odds_lower`=`FukuOddsLow`(JODDS)・§2 JODDS時点選択で固定 snapshot |
| EV-02 | 推奨ランク S/A/B/C/D（EV/確率/odds_lower のみ使用）算出 | §4 §11.5 初期仕様・未定義の予測信頼度不使用・S(p≥0.25)/A(p≥0.20) の確率閾値明示 |
| BACK-01 | race_id-grouped 時系列分割・BT-1..5 窓・30/10分前比較 | §5 BT窓ヘルパ（`group_split.py` 新設）・既存 `race_id_time_series_split` の guard 継承・§15.5 完全準拠 |
| BACK-02 | 固定ルール（EV≥1.05/p≥0.15/odds≥1.5/上位2頭/100円/複勝）仮想購入 | §6 仮想購入ルール `fukusho_ev_v1`・top-2 タイブレーク（§6 推奨: race_key→umaban 昇順） |
| BACK-03 | 返還 `effective_stake=0`・中止 `effective_stake=100`・回収率/P/L/max DD/件数・`backtest_strategy_version` | §3 返還会計決定表・§8 回収率計算・label フラグ + HARAI 経路の双方で検証 |
| BACK-04 | `odds_snapshot_policy` 固定（30/10分前）・後知恵オッズ選択/最終オッズ無条件/欠損時差替禁止 | §2 backward 最近接・`no_bet` sentinel・全候補一括報告（§10）・§11.2 禁止事項の構造的ブロック |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| EV 計算（p × odds） | Python 計算層 | — | 純粋関数・pandas Series演算・DB不要（メモリ内） |
| オッズ時点選択（N分前 snapshot） | PostgreSQL READ（readonly） | Python（merge_asof 等価） | JODDS/HARAI/RACE は raw 層（read-only）・snapshot 選択ロジックはPython側で backward 最近接 |
| 仮想購入ルール判定 | Python 計算層 | — | レース内 top-2 選択・pandas groupby + sort |
| 返還/中止会計 | Python 計算層（label フラグ消費） | PostgreSQL READ（HARAI 検証） | label フラグが一次ソース・HARAI は cross-check |
| BT窓 race_id 分割 | Python 計算層（`group_split.py`） | — | race_id disjoint + strict chronological guard は既存 guard が保証 |
| BT窓再学習 | Python 計算層（`orchestrator.py`） | — | LightGBM/CatBoost 学習・Parquet snapshot 入力 |
| backtest 結果永続化 | PostgreSQL WRITE（etl ロール） | — | `backtest` スキーマ・staging-swap idempotent |
| レポート出力 | ファイル（`reports/05-backtest.{md,json}`） | — | Phase 4 の `04-eval` パターン踏襲 |

## User Constraints (from CONTEXT.md)

### Locked Decisions（D-01〜D-05・計画者は代替案を探索しない）

- **D-01: `odds_snapshot_policy` に JODDS（時系列オッズ単複・`public.n_jodds_tanpuku`）採用** — 発走30分前/10分前を再現（§15.5）。`DataKubun='1'`(中間) 主使用（`3`最終/`4`確定 補助）。§11.2「最終オッズ無条件使用禁止」は発走前時点を固定 policy として事前登録することで履行（後知恵ではない）。
- **D-02: 時点選択ルール = backward 最近接** — 発走時刻-N分「以下」の直近 `HappyoTime`（`merge_asof(direction='backward')` 等価・未来リーク構造的に不可）。当該時刻以前に1件も無ければ `no_bet`（§11.3）。特殊値（`----`/`****`/`0000`/`0999`）も `no_bet`。
- **D-03: §15.5 完全準拠フル行列** — BT-1..5 × {30min,10min} × {lightgbm,catboost} ≈ 20 backtest。各 BT窓で train 期間を変えて再学習（`orchestrator.py` を BT窓で回す・固定 snapshot `postreview-v2` から race_date filter）。
- **D-04: BL-3 投資ROI比較を実装** — BL-3（確定複勝オッズ低い=人気順）で固定ルール仮想購入 → 回収率を主モデル2つと比較。BL-3 は p=1/odds で EV 自己参照=1.0 になるため EV でなく**人気順等で選ぶ**（選択ルールは研究者裁量）。
- **D-05: 返還・中止会計は Claude 裁量** — §11.6（取消/除外=返還 `effective_stake=0`・競走中止=loss `effective_stake=100`）+ JRAルール（複勝不成立=返還・特別払戻は公式に従う）+ `label.fukusho_label` フラグ + `public.n_harai` 経路で設計。

### Claude's Discretion（研究者/計画者に委ねる）

- BT窓定義の厳密適用（§15.5 train 2019-06〜 を Phase 3 D-09 の 2016H2〜 より優先）
- `category_map` の BT窓再 fit（test 窓 ID 漏洩防止・§14.3）
- calib slice の BT窓内 train 尾 carve（`max(train.race_date)<min(calib.race_date)` guard・sample<1000 は sigmoid）
- EV/ランク計算・仮想購入ルール・backtest 永続化・reports 慣例・回収率計算・`odds_snapshot_at`/`odds_source_type`/`odds_missing_reason` 保持

### Deferred Ideas (OUT OF SCOPE)

- Phase 6（Evaluation & Calibration Gates）: 確率品質受入基準のゲート検証・主モデル確定
- Phase 7（Presentation）: Streamlit 表示・OUT-02 backtest CSV 出力（Phase 5 は DB テーブル定義と書込まで）
- Phase 8（Adversarial Audit）: BACK-03 返還会計テスト・BACK-04 odds policy 固定違反検出・race_id disjoint・JODDS 時点選択 backward 原則の対抗的監査
- 発走前オッズの更なる時点比較（前日売最終/朝9:30/60分前/5分前/締切直前）

## Project Constraints (from CLAUDE.md)

- **§11.2 odds policy 固定**: レース後の有利オッズ時点選択・最終オッズ無条件使用・欠損時都合の良い時点への差し替え・検証後の恣意的変更を禁止（構造的ブロック・BACK-04）
- **§13 PIT 原則**: `merge_asof(direction='backward')` で未来リーク防止。JODDS 時点選択も同一思想（D-02）
- **リーク防止プリミティブ**: race_id-grouped split・`category_map` frozen・`cv='prefit'`（strict-later disjoint）・`has_time=True`。BT窓再学習で race_id disjoint + strict chronological を保証
- **silent fallback 禁止（D-13）**: 欠損 odds は `no_bet` sentinel・都合の良い別時点への差し替え禁止
- **「要件定義書優先」**: §15.5（2019-06〜）を Phase 3 D-09（2016H2〜）より優先
- **5層スキーマ分離**: feature=不変 Parquet・prediction/backtest=queryable Postgres（結果層）。Phase 5 は backtest 層を初めて実装
- **応答言語**: 日本語（技術用語・コード識別子は原文可）

---

## 1. JODDS 時系列オッズの固定時点選択（D-01/D-02・EV-01/BACK-04）

### 1.1 出典（実DBスキーマ実証済み）

`[VERIFIED: 実DB information_schema + EveryDB2 マニュアル 47/46/03]`

**`public.n_jodds_tanpuku`（時系列オッズ単複・14カラム）** — PK: `Year, MonthDay, JyoCD, Kaiji, Nichiji, RaceNum, HappyoTime, Umaban`（8カラム）
- `HappyoTime` varchar(8) = **mmddHHMM**（例: `01031833` = 1月3日18時33分）。中間オッズのみ設定。時系列オッズ使用時のみキー。
- `FukuOddsLow` / `FukuOddsHigh` varchar(4) = 複勝最低/最高オッズ。`0999`=99.9倍以上 / `0000`=無投票 / `----`=発売前取消 / `****`=発売後取消 / ` `(sp)=登録なし
- `TanOdds` / `TanNinki` / `FukuNinki` = 単勝オッズ/人気・複勝人気

**重要: `n_jodds_tanpuku` 本体テーブルは `DataKubun` 列を持たない**（実DB実証）。`DataKubun` は head テーブル（46）のみ。中間/最終/確定/中止の判定は head テーブル経由。

**`public.n_jodds_tanpukuwaku_head`（時系列オッズヘッダ・19カラム）** — PK: `Year, MonthDay, JyoCD, Kaiji, Nichiji, RaceNum, HappyoTime`（7カラム・馬番なし）
- `DataKubun` varchar(1): `1`=中間 / `2`=前日売最終 / `3`=最終 / `4`=確定 / `5`=確定(月曜) / `9`=レース中止 / `0`=該当レコード削除
- `FukusyoFlag` varchar(1): `0`=発売なし / `1`=発売前取消 / `3`=発売後取消 / `7`=発売あり
- `FukuChakuBaraiKey` varchar(1): `0`=複勝発売なし / `2`=2着まで払い / `3`=3着まで払い
- `TorokuTosu` / `SyussoTosu` = 登録頭数 / 出走頭数

**実DB観測値（2026-06-20・取得進行中）**:
- `n_jodds_tanpuku`: 1,708,045行・25レース日分・**2015年のみ**（BT期間 2019-2025 は未取得）
- `n_jodds_tanpukuwaku_head.datakubun` 分布: `1`(中間) 115,525 / `2`(前日売最終) 19 / `3`(最終) 763 / `4`(確定) 763・**`9`(中止) 0件**
- `FukuOddsLow` top値: `0011`(1.1倍) 48,977 / `0000`(無投票) 36,829 / 数値群

**`public.n_race`（RACE・発走時刻の正）** — `HassoTime` varchar(4) = **hhmm**（例: `0950` = 9時50分）。PK 6カラム（Year, MonthDay, JyoCD, Kaiji, Nichiji, RaceNum）。

### 1.2 時点選択ロジック（backward 最近接・未来リーク構造的に不可）

「発走N分前」の snapshot を選択するクエリ設計（`src/ev/odds_snapshot.py` に新設推奨）:

```sql
-- 発走30分前 snapshot 選択（readonly ロール・public schema）
-- HappyoTime は mmddHHMM・HassoTime は hhmm・Year+MonthDay でレース特定
WITH race_times AS (
    SELECT
        r.year, r.monthday, r.jyocd, r.kaiji, r.nichiji, r.racenum,
        r.hassotime,  -- hhmm varchar
        -- 発走時刻を HHMM 整数化（例: '0950' → 950）
        (r.hassotime::int) AS hassou_int
    FROM public.n_race r
    WHERE r.hassotime IS NOT NULL AND r.hassotime != '0000'
),
odds_at_policy AS (
    SELECT
        j.year, j.monthday, j.jyocd, j.kaiji, j.nichiji, j.racenum, j.umaban,
        j.happyotime,
        -- HappyoTime 下4桁 = HHMM（例: '01031833' → 1833）
        (RIGHT(j.happyotime, 4)::int) AS happyo_hhmm_int,
        j.fukuoddslow, j.fukuoddshigh,
        h.datakubun, h.fukusyoflag, h.fukuchakubaraikey
    FROM public.n_jodds_tanpuku j
    JOIN public.n_jodds_tanpukuwaku_head h
        ON j.year = h.year AND j.monthday = h.monthday AND j.jyocd = h.jyocd
        AND j.kaiji = h.kaiji AND j.nichiji = h.nichiji AND j.racenum = h.racenum
        AND j.happyotime = h.happyotime
    WHERE h.datakubun = '1'  -- 中間オッズのみ（D-01）
)
-- backward 最近接: 発走時刻 - N分 以下の最大 HappyoTime
SELECT o.*, r.hassotime,
       o.happyo_hhmm_int AS selected_hhmm
FROM race_times r
JOIN LATERAL (
    SELECT * FROM odds_at_policy o
    WHERE o.year = r.year AND o.monthday = r.monthday AND o.jyocd = r.jyocd
      AND o.kaiji = r.kaiji AND o.nichiji = r.nichiji AND o.racenum = r.racenum
      AND o.happyo_hhmm_int <= (r.hassou_int - %s)  -- N分前（境界日跨ぎ注意）
    ORDER BY o.happyo_hhmm_int DESC
    LIMIT 1
) o ON true;
```

**Python側 `merge_asof(direction='backward')` 等価実装**（pandas で実装する場合・推奨）:

```python
# 各レースの race_id (year-monthday-jyocd-kaiji-nichiji-racenum) 単位で
# 発走時刻 - N分 以下の直近 snapshot を選択（merge_asof 等価・未来リーク不可）
def select_odds_snapshot(
    jodds_df: pd.DataFrame,  # HappyoTime, FukuOddsLow/High, Umaban, race_key
    race_times: pd.DataFrame,  # race_key, race_start_datetime (HassoTime由来)
    policy: str,  # '30min_before' / '10min_before'
) -> pd.DataFrame:
    minutes = 30 if policy == '30min_before' else 10
    # race_id 単位で backward 最近接（by=race_key でグループ化・direction='backward'）
    jodds_sorted = jodds_df.sort_values(['race_key', 'happyo_datetime'])
    cutoff = race_times.copy()
    cutoff['cutoff_datetime'] = cutoff['race_start_datetime'] - pd.Timedelta(minutes=minutes)
    cutoff_sorted = cutoff.sort_values('race_key')
    # merge_asof は両フレームが by キーでソート済み前提・direction='backward' で未来不可
    result = pd.merge_asof(
        cutoff_sorted, jodds_sorted,
        left_on='cutoff_datetime', right_on='happyo_datetime',
        by='race_key', direction='backward',  # ← 未来リーク構造的に不可
    )
    return result
```

### 1.3 落とし穴

- **日跨ぎ**: `HassoTime` が深夜（例: `0030`）で `HassoTime - 30分` が前日になる場合、`HappyoTime` の月日部分（mmdd）が一致しなくなる。`race_start_datetime`（`race_date + HassoTime` 構築済み）を基準に `pd.Timedelta` で計算すれば自動解決。HHMM整数比較は日跨ぎで破綻するため**避ける**。
- **複数 `HappyoTime` 同時刻**: 同一レース同一HHMMに複数 snapshot は通常無いが、`ORDER BY happyo_hhmm DESC LIMIT 1` で決定論化。
- **`FukuOddsLow='0000'`(無投票)**: snapshot は存在するが発売前。これは `no_bet`（§11.3 silent fallback 禁止）。`FukusyoFlag` が `0`(発売なし)/`1`(発売前取消)/`3`(発売後取消) の場合も `no_bet`。
- **`0999`(99.9倍以上)**: 数値としては巨大だが odds としては有効（EV 計算に使用可能）。`no_bet` ではない。
- **境界値 `<=`**: 発走時刻ぴったりN分前の snapshot は含める（`<=`・以下）。`merge_asof(direction='backward')` の標準挙動と一致。

### 1.4 検証方法（単体テスト）

- `test_odds_snapshot_backward`: 合成データで「発走10:00・policy=30min」→ HappyoTime 09:25/09:31/09:35 から 09:31（最大かつ≤09:30）を選択
- `test_odds_snapshot_no_bet_empty`: snapshot 0件 → `no_bet` sentinel
- `test_odds_snapshot_special_values`: `FukuOddsLow` が `----`/`****`/`0000` → `no_bet`（`0999` は odds として使用）
- `test_odds_snapshot_future_leak`: 発走時刻より未来の HappyoTime が選択されないことを assert（backward 原則）
- `test_odds_snapshot_day_boundary`: 深夜発走レースの日跨ぎで正しい snapshot を選択

---

## 2. 返還/競走中止/dead-loss honest 会計（D-05・BACK-02/BACK-03）

### 2.1 出典

`[VERIFIED: src/etl/fukusho_label.py + EveryDB2 マニュアル 05-HARAI + 実DB label.fukusho_label]`

**`label.fukusho_label` の既存フラグ列**（Phase 2 実装済み・backtest はこれを消費）:
- `is_scratch_cancel` (bool): 出走取消（`bataijyu` sentinel）
- `is_race_cancelled` (bool): レース全体中止（`datakubun='9'）
- `is_race_excluded` (bool): 発走前除外（本DBでは0件）
- `is_dead_loss` (bool): 競走中止（発走後停止・`marker_active AND time_present`）
- `is_fukusho_sale_available` (bool): 複勝発売あり（`torokutosu>=5 AND fuseirituflag2!='1'`）
- `fukusho_payout_places` (int): HR `PayFukusyoUmaban` の実払戻馬番数（WR-04・torokutosu でなく payout_count ベース）
- `fukusho_hit_validated` (int 0/1): HR `PayFukusyoUmaban` 突合済み的中判定

**実DB観測値（label.fukusho_label 554,267行）**:
- `is_dead_loss` (競走中止): 4,506行
- `is_scratch_cancel` (出走取消): 956行
- `is_race_cancelled` (レース中止): 376行
- `is_fukusho_sale_available` (複勝発売あり): 553,891行

**`public.n_harai`（払戻・199カラム）の該当列**:
- `FuseirituFlag2` varchar(1): `0`=不成立なし / `1`=複勝不成立 → 返還
- `TokubaraiFlag2` varchar(1): `0`/`1`(複勝特払) → 払戰金は `PayFukusyoPay`
- `HenkanFlag2` varchar(1): `0`/`1`(複勝返還あり)
- `HenkanUma1..28` varchar(1) 各1文字: 返還対象馬番ビットマスク（例: 5番取消=`0000100000000000000000000000`）
- `PayFukusyoUmaban1..5` varchar(2): 複勝的中馬番（`00`=発売なし/特払/不成立）
- `PayFukusyoPay1..5` varchar(9): 複勝払戻金（100円あたり・特払/不成立の金額も入る）
- `PayFukusyoNinki1..5` varchar(2): 複勝人気順

**実DB観測値（n_harai 39,580行）**:
- `fuseirituflag2='1'` (複勝不成立): **0件**（現状）
- `henkanflag2='1'` (複勝返還): **1,541件**
- `tokubaraiflag2='1'` (複勝特払): **0件**（現状）

### 2.2 honest 会計決定表（§11.6 + §10.6 + label フラグ）

| シナリオ | 判定条件（label フラグ優先・HARAI cross-check） | `stake` | `refund_amount` | `payout_amount` | `profit` | `effective_stake` | 選択可 |
|----------|--------------------------------------------------|---------|-----------------|-----------------|----------|-------------------|--------|
| **通常的中** | `fukusho_hit_validated=1` AND NOT 取消/除外/中止/不成立 | 100 | 0 | `PayFukusyoPay`(該当馬番 slot) | payout-100 | 100 | ○ |
| **通常不的中** | `fukusho_hit_validated=0` AND NOT 取消/除外/中止/不成立 | 100 | 0 | 0 | -100 | 100 | ○ |
| **出走取消** | `is_scratch_cancel=True` | 100 | 100 | 0 | 0 | **0** | ○(購入済なら返還) |
| **競走除外** | `is_race_excluded=True` | 100 | 100 | 0 | 0 | **0** | ○(購入済なら返還) |
| **競走中止** | `is_dead_loss=True` AND `is_model_eligible=True`(§10.6 含める) | 100 | 0 | 0 | **-100** | **100** | ○(除外禁止・§10.6) |
| **複勝不成立** | `FuseirituFlag2='1'` (レース全体) | 100 | 100 | 0 | 0 | **0** | ○(購入済なら返還) |
| **レース全体中止** | `is_race_cancelled=True` (HR `datakubun='9'`) | 100 | 100 | 0 | 0 | **0** | ○(購入済なら返還) |
| **複勝発売なし** | `is_fukusho_sale_available=False` | — | — | — | — | — | ✗(選択対象外・事前filter) |
| **同着拡張** | `fukusho_payout_places > 標準`(4-5着払い) | 100 | 0 | 該当slotの`PayFukusyoPay` | payout-100 | 100 | ○(払戻テーブル優先) |
| **特別払戻** | `TokubaraiFlag2='1'` | 100 | 0 | `PayFukusyoPay`(特払金額) | payout-100 | 100 | ○(公式に従う) |

**核心ルール（§11.6）**:
- 返還（取消/除外/不成立/レース中止）は `effective_stake=0` → 回収率の分母から控除（返還多いレースで回収率が不自然に歪むのを防止）
- 競走中止（`is_dead_loss`）は `effective_stake=100` → **実運用の負けを消さない**（§10.6・回収率過大評価防止）
- 払戻金は表示オッズでなく実際の `PayFukusyoPay`（100円あたり）を使用

### 2.3 データ経路設計（label フラグ一次・HARAI cross-check）

```python
# src/ev/refund_accounting.py（新設推奨）
def determine_stake_payout(
    row: pd.Series,  # prediction + label + HARAI join 済み行
    stake_per_bet: int = 100,
) -> dict:
    """§11.6 honest 会計。label フラグ一次・HARAI PayFukusyoPay で payout 確定。"""
    # 複勝発売なしは選択対象外（事前 filter で除外済み・到達しない）
    if not row.get('is_fukusho_sale_available', False):
        return {'stake': 0, 'refund': 0, 'payout': 0, 'profit': 0, 'effective_stake': 0}

    # 返還系（effective_stake=0）
    if (row.get('is_scratch_cancel') or row.get('is_race_excluded')
            or row.get('is_race_cancelled')
            or row.get('fuseirituflag2') == '1'):  # 複勝不成立
        return {'stake': stake_per_bet, 'refund': stake_per_bet,
                'payout': 0, 'profit': 0, 'effective_stake': 0}

    # 競走中止（effective_stake=100・loss・§10.6 除外禁止）
    if row.get('is_dead_loss'):
        return {'stake': stake_per_bet, 'refund': 0,
                'payout': 0, 'profit': -stake_per_bet, 'effective_stake': stake_per_bet}

    # 通常: PayFukusyoPay で payout 確定（的中 slot の金額）
    payout = _lookup_payfukusyo_pay(row)  # umaban → PayFukusyoUmaban1..5 slot → PayFukusyoPay
    return {'stake': stake_per_bet, 'refund': 0,
            'payout': payout, 'profit': payout - stake_per_bet,
            'effective_stake': stake_per_bet}
```

`_lookup_payfukusyo_pay` は `PayFukusyoUmaban1..5` に該当 umaban があれば対応する `PayFukusyoPay1..5` を返す（同着で slot 2-5 使用）。該当なしは payout=0（不的中）。

### 2.4 落とし穴

- **`is_model_eligible` と backtest 対象の違い**: `is_model_eligible=False`（障害/新馬/発売なし）は**学習/予測対象外**だが、backtest では予測が生成されないのでそもそも選択されない。`is_dead_loss` は `is_model_eligible` の判定対象外（§10.6 含める）だが、競走中止馬は予測が生成されていれば選択対象（不的中として会計）。
- **`HenkanUma` ビットマスク vs `HenkanFlag2`**: `HenkanFlag2='1'` は「複勝返還あり」だが、個別馬の返還は `HenkanUma1..28` ビットマスク。ただし §10.6 では取消/除外は `label.is_scratch_cancel`/`is_race_excluded` で判定済み（`bataijyu` sentinel）のため、backtest 会計は `HenkanUma` を直接見なくてよい（label フラグが一次ソース）。`HenkanFlag2` はレース全体の返還有無の cross-check 用。
- **複勝不成立の払戻金**: `FuseirituFlag2='1'` の場合 `PayFukusyoPay` に不成立の金額（通常70円・控除率返還）が入る場合があるが、§11.6 では不成立=返還(`effective_stake=0`)のため `payout=0`・`refund=100` で統一（表示揺れ防止）。
- **特別払戻**: `TokubaraiFlag2='1'` は「的中馬がいないが払戻がある」（例: 全馬取消で特払70円）。§11.6 明記はないが「公式に従う」→ `PayFukusyoPay` を payout に計上。

### 2.5 検証方法（対抗的テスト・BACK-03）

合成データで全シナリオを網羅（実DBでは不成立/特払 0件のため合成必須）:
- `test_refund_normal_hit`: 通常的中 → payout=`PayFukusyoPay`, profit=payout-100
- `test_refund_normal_miss`: 通常不的中 → payout=0, profit=-100
- `test_refund_scratch_cancel`: `is_scratch_cancel` → refund=100, effective_stake=0
- `test_refund_race_excluded`: `is_race_excluded` → refund=100, effective_stake=0
- `test_refund_dead_loss`: `is_dead_loss` → profit=-100, effective_stake=100（§10.6 除外禁止）
- `test_refund_fuseiritu`: `FuseirituFlag2='1'` → refund=100, effective_stake=0
- `test_refund_race_cancelled`: `is_race_cancelled` → refund=100, effective_stake=0
- `test_refund_no_sale`: `is_fukusho_sale_available=False` → 選択対象外（stake=0）
- `test_refund_deadheat`: 同着で `PayFukusyoUmaban` slot 2-5 → 該当 slot の `PayFukusyoPay`

## 3. EV 計算・推奨ランク（EV-01/EV-02・§11.1/§11.5）

### 3.1 出典

`[CITED: docs/keiba_ai_requirements_v1.3.md §11.1/§11.5]`

**§11.1 複勝EV計算**:
```text
EV_lower = p_fukusho_hit × fukusho_odds_lower
EV_upper = p_fukusho_hit × fukusho_odds_upper
```
推奨判定は保守的に `EV_lower` を主基準。

**§11.5 推奨ランク初期仕様**（未定義の予測信頼度不使用・EV/確率/odds_lower のみ）:
```text
S: EV_lower >= 1.20 AND p_fukusho_hit >= 0.25 AND fukusho_odds_lower >= 1.5
A: EV_lower >= 1.10 AND p_fukusho_hit >= 0.20 AND fukusho_odds_lower >= 1.5
B: EV_lower >= 1.05 AND p_fukusho_hit >= 0.15
C: EV_lower >= 1.00
D: 上記以外
```

### 3.2 実装方針（純粋関数・pandas Series演算）

```python
# src/ev/ev_rank.py（新設推奨）
def compute_ev_and_rank(
    df: pd.DataFrame,  # p_fukusho_hit, fuku_odds_lower, fuku_odds_upper 列
) -> pd.DataFrame:
    """§11.1/§11.5 EV計算 + 推奨ランク（純粋関数・DB不要）。"""
    df = df.copy()
    df['EV_lower'] = df['p_fukusho_hit'] * df['fuku_odds_lower']
    df['EV_upper'] = df['p_fukusho_hit'] * df['fuku_odds_upper']
    df['recommend_rank'] = df.apply(_rank, axis=1)
    return df

def _rank(row: pd.Series) -> str:
    ev, p, ol = row['EV_lower'], row['p_fukusho_hit'], row['fuku_odds_lower']
    if ev >= 1.20 and p >= 0.25 and ol >= 1.5: return 'S'
    if ev >= 1.10 and p >= 0.20 and ol >= 1.5: return 'A'
    if ev >= 1.05 and p >= 0.15: return 'B'
    if ev >= 1.00: return 'C'
    return 'D'
```

### 3.3 落とし穴

- **`odds_lower` 欠損（`no_bet`）**: EV 計算不可 → rank='D'（選択対象外）。`compute_ev_and_rank` 呼出前に `no_bet` 行を NaN 化または除外。
- **rank 閾値の AND 条件**: S/A は EV・p・odds_lower の3条件 AND。B は EV・p の2条件（odds_lower 閾値なし）。C は EV のみ。階層的判定（上から順に最初に満たした rank）。
- **`odds_lower` は固定 snapshot の `FukuOddsLow`**: JODDS backward 最近接で選択した snapshot の値。確定オッズ（`n_odds_tanpuku`）ではない（D-01）。

### 3.4 検証方法

- `test_ev_calculation`: p=0.3, odds_lower=5.0 → EV_lower=1.5, EV_upper=*
- `test_rank_S`: EV=1.25, p=0.30, odds=2.0 → 'S'
- `test_rank_D_low_ev`: EV=0.8 → 'D'
- `test_rank_B_no_odds_threshold`: EV=1.06, p=0.16, odds=1.2 → 'B'（odds閾値なし）

---

## 4. 仮想購入ルール `fukusho_ev_v1`（BACK-01・§11.4）

### 4.1 出典

`[CITED: docs/keiba_ai_requirements_v1.3.md §11.4]`

```text
backtest_strategy_version: fukusho_ev_v1
購入単位: 1候補100円
対象馬券: 複勝のみ
購入条件:
  EV_lower >= 1.05
  p_fukusho_hit >= 0.15
  fukusho_odds_lower >= 1.5
同一レース制約: EV_lower上位2頭まで
同一馬への追加購入: なし
返還: 出走取消・競走除外は返還・競走中止は不的中
```

### 4.2 実装方針（レース内 top-2 選択）

```python
# src/ev/purchase_simulator.py（新設推奨）
def select_bets(
    df: pd.DataFrame,  # race_id, horse_id, EV_lower, p, odds_lower, rank, label flags
    *,
    strategy: str = 'fukusho_ev_v1',
    max_bets_per_race: int = 2,
    stake_per_bet: int = 100,
) -> pd.DataFrame:
    """§11.4 fukusho_ev_v1: フィルタ → レース内 top-2 選択。"""
    # 複勝発売なし・no_bet・適格性除外を事前 filter
    eligible = df[
        df['is_fukusho_sale_available']
        & df['is_model_eligible']
        & df['fuku_odds_lower'].notna()  # no_bet 除外
    ].copy()
    # 購入条件フィルタ
    eligible = eligible[
        (eligible['EV_lower'] >= 1.05)
        & (eligible['p_fukusho_hit'] >= 0.15)
        & (eligible['fuku_odds_lower'] >= 1.5)
    ]
    # レース内 top-2（EV_lower 降順・タイブレーク: race_key→umaban 昇順で安定）
    eligible = eligible.sort_values(
        ['race_key', 'EV_lower', 'umaban'], ascending=[True, False, True]
    )
    selected = (
        eligible.groupby('race_key', group_keys=False)
        .head(max_bets_per_race)  # top-2
    )
    selected['selected_flag'] = True
    selected['stake'] = stake_per_bet
    return selected
```

### 4.3 タイブレーク（Claude 裁量・推奨）

同 EV_lower 時の順位付け（§11.4 明記なし）:
- **推奨: `race_key → umaban 昇順`**（馬番の若い方を優先・決定論的・再現性保証）
- 代替案: p 高い方優先 / odds_lower 高い方優先 — いずれも決定論だが umaban 昇順が最も中立的で §19.1 再現性に有利

`sort_values(..., kind='mergesort')` で安定ソート（pandas default は quicksort・非安定）を使用し、seed 非依存の決定論化。

### 4.4 保持項目（§11.4）

```text
backtest_strategy_version, stake_per_bet, max_bets_per_race, selection_rule,
odds_snapshot_policy, odds_snapshot_at, refund_flag, refund_amount,
payout_amount, profit, effective_stake,
selected_count, effective_bet_count, refund_count
```

### 4.5 落とし穴

- **`selected_count` vs `effective_bet_count`**: selected_count=返還含む選択数・effective_bet_count=返還除く実購入数。返還馬は selected だが effective_bet ではない。
- **レース内候補 < 2**: 条件を満たす馬が1頭のみなら1頭選択（0頭なら不選択）。`head(max_bets_per_race)` で自動対応。
- **同着の的中判定**: `fukusho_hit_validated` は HR `PayFukusyoUmaban` 突合済み（同着含む）なので、仮想購入の的中判定は `fukusho_hit_validated` をそのまま使用。

### 4.6 検証方法

- `test_purchase_filter_conditions`: EV/p/odds 閾値で正しく filter
- `test_purchase_top2`: レース内3候補 → 上位2頭選択
- `test_purchase_tiebreak`: 同 EV で umaban 昇順
- `test_purchase_no_eligible`: 条件満たさず → 0選択
- `test_purchase_no_sale`: `is_fukusho_sale_available=False` → 除外

---

## 5. BT-1..5 窓ヘルパ（BACK-01・§15.5）

### 5.1 出典

`[CITED: docs/keiba_ai_requirements_v1.3.md §15.5]`

| 検証名 | 学習 | 検証 |
|--------|------|------|
| BT-1 | 2019-06〜2022 | 2023 |
| BT-2 | 2019-06〜2023 | 2024 |
| BT-3 | 2019-06〜2024 | 2025 |
| BT-4 | 直近3年 rolling | 翌年 |
| BT-5 | 直近5年 rolling | 翌年 |

各 BT について `odds_snapshot_policy`（30分前/10分前）を比較。

**§15.5 は 2019-06 開始**（Phase 3 D-09 の 2016H2〜 より後・要件正を優先・CLAUDE.md「要件定義書優先」）。

### 5.2 既存コードとの関係（重要制約）

`[VERIFIED: src/utils/group_split.py + src/model/data.py::split_3way]`

- **既存 `race_id_time_series_split`**（`group_split.py`）: expanding-window CV・`max(train)<min(test)` strict guard・race_id disjoint guard を持つが、**固定 window（BT-1..5）や rolling window を表現できない**（docstring に明記: "本関数は expanding-window のみを生成する"）。
- **既存 `split_3way`**（`data.py`）: 固定暦年 mask（train 2016-07〜2023 / calib 2024-01〜06 / test 2024-07〜12）を**ハードコード**。BT窓（train 2019-06〜2022/test 2023 等）を表現不可。

→ Phase 5 は **BT窓ヘルパを新設**（CLAUDE.md 記載の~20行）し、既存 guard ロジック（race_id disjoint + strict chronological）を継承・`split_3way` に BT窓期間を注入する拡張を行う。

### 5.3 実装方針（BT窓ヘルパ新設 + split_3way 拡張）

```python
# src/utils/group_split.py に追記
from dataclasses import dataclass

@dataclass(frozen=True)
class BTWindow:
    """§15.5 BT窓定義。train_start/train_end は train 期間・test_start/test_end は test 期間。"""
    name: str           # 'BT-1'..'BT-5'
    train_start: str    # 'YYYY-MM-DD'
    train_end: str      # 'YYYY-MM-DD'
    test_start: str     # 'YYYY-MM-DD'
    test_end: str       # 'YYYY-MM-DD'
    window_type: str    # 'expanding' / 'rolling'

# §15.5 完全準拠（2019-06 開始・要件正）
BT_WINDOWS: list[BTWindow] = [
    BTWindow('BT-1', '2019-06-01', '2022-12-31', '2023-01-01', '2023-12-31', 'expanding'),
    BTWindow('BT-2', '2019-06-01', '2023-12-31', '2024-01-01', '2024-12-31', 'expanding'),
    BTWindow('BT-3', '2019-06-01', '2024-12-31', '2025-01-01', '2025-12-31', 'expanding'),
    # BT-4/5: rolling（test 年の直近3年/5年 train）
    BTWindow('BT-4', '2021-01-01', '2023-12-31', '2024-01-01', '2024-12-31', 'rolling'),  # 例: test 2024
    BTWindow('BT-5', '2019-01-01', '2023-12-31', '2024-01-01', '2024-12-31', 'rolling'),  # 例: test 2024
]
# 注: BT-4/5 の test 年は確定後 train_start を再計算（rolling なので test 年に依存）

def get_bt_race_ids(
    races: pd.DataFrame,  # race_id, race_date, race_start_datetime
    bt: BTWindow,
) -> tuple[list[str], list[str]]:
    """BT窓の (train_race_ids, test_race_ids) を返す（race_date filter + guard）。"""
    train = races[races['race_date'].between(bt.train_start, bt.train_end)]
    test = races[races['race_date'].between(bt.test_start, bt.test_end)]
    # 既存 guard 継承: race_id disjoint + strict chronological
    train_ids = set(train['race_id']); test_ids = set(test['race_id'])
    if not train_ids.isdisjoint(test_ids):
        raise ValueError(f"{bt.name}: race_id leak across train/test")
    if train['race_start_datetime'].max() >= test['race_start_datetime'].min():
        raise ValueError(f"{bt.name}: strict chronological violated")
    return sorted(train_ids), sorted(test_ids)
```

### 5.4 落とし穴

- **§15.5 開始年 vs Phase 3 D-09**: §15.5 は 2019-06〜（要件正）・Phase 3 D-09 は 2016H2〜。**§15.5 優先**（CLAUDE.md「要件定義書優先」）。固定 snapshot `postreview-v2` は全期間 PIT-correct なので 2019-06 filter で安全に切り出せる。
- **BT-4/5 rolling の test 年**: §15.5 は「直近3年/5年 rolling・翌年」と明記だが、具体的 test 年は明記なし。BT-1..3 の test 年（2023/2024/2025）と揃えるのが自然（同一 test 年で rolling vs expanding を比較）。Planner が確定（Claude 裁量）。
- **calib slice の BT窓内 carve**: BT窓の train 期間内で calib を切る（train 尾・`max(train.race_date) < min(calib.race_date)`）。BT-1 train 2019-06〜2022 なら calib を 2022 後半等に carve。calib sample <1000 は sigmoid。

### 5.5 検証方法

- `test_bt_window_disjoint`: 各 BT窓で train/test race_id が disjoint
- `test_bt_window_chronological`: `max(train.race_date) < min(test.race_date)`
- `test_bt_window_2019_start`: BT-1..3 train_start = '2019-06-01'（§15.5・D-09 でなく）
- `test_bt_window_rolling`: BT-4/5 の train_start が test 年から3年/5年前

---

## 6. BT窓再学習ループ（D-03）

### 6.1 出典

`[VERIFIED: src/model/orchestrator.py::train_and_predict + src/model/data.py::split_3way]`

**制約**: `train_and_predict` は内部で `split_3way` を呼び、固定暦年 mask（train 2016-07〜2023 / calib 2024-01〜06 / test 2024-07〜12）で分割する。BT窓（BT-1 train 2019-06〜2022/test 2023 等）を直接指定できない。

### 6.2 実装方針（split_3way に BT窓期間を注入）

**最小変更案**: `split_3way` に `train_calib_test_periods` パラメータを追加（既存ハードコードをデフォルト値として保持・後方互換）:

```python
# src/model/data.py::split_3way 拡張（後方互換）
def split_3way(
    frame: pd.DataFrame,
    *,
    periods: dict[str, tuple[str, str]] | None = None,  # 新規・None なら既存ハードコード
) -> dict[str, pd.DataFrame]:
    """D-02b 推奨案（periods=None）または BT窓（periods 指定）で分割。"""
    if periods is None:
        # 既存ハードコード（後方互換・Phase 4 はこちらを使用）
        periods = {
            'train': ('2016-07-01', '2023-12-31'),
            'calib': ('2024-01-01', '2024-06-30'),
            'test': ('2024-07-01', '2024-12-31'),
        }
    train = frame[frame['race_date'].between(*periods['train'])].copy()
    calib = frame[frame['race_date'].between(*periods['calib'])].copy()
    test = frame[frame['race_date'].between(*periods['test'])].copy()
    # 既存 guard 継承: strict chronological + race_key disjoint（ValueError）
    ...
```

**BT窓再学習ループ**（`scripts/run_backtest.py` 新設）:

```python
from src.model.orchestrator import train_and_predict
from src.model.data import split_3way
from src.utils.group_split import BT_WINDOWS

for bt in BT_WINDOWS:
    for model_type in ['lightgbm', 'catboost']:
        # calib slice を BT窓 train 尾から carve（Claude 裁量）
        # 例: BT-1 train 2019-06〜2022 → calib 2022-07〜2022-12 / test 2023
        calib_start, calib_end = _carve_calib_from_train_tail(bt)  # train 尾の ~20%
        periods = {
            'train': (bt.train_start, _calib_start_minus_1day(calib_start)),
            'calib': (calib_start, calib_end),
            'test': (bt.test_start, bt.test_end),
        }
        # train_and_predict に periods を注入（split_3way 拡張経由）
        result = train_and_predict(
            feature_df,  # postreview-v2 から race_date filter 済み全体
            model_type=model_type,
            feature_snapshot_id='20260620-1a-postreview-v2',
            split_periods=periods,  # 新規パラメータ
        )
        # result['pred_df'] に BT窓 test 予測
```

### 6.3 category_map の BT窓再 fit（§14.3・Claude 裁量）

`[CITED: CLAUDE.md §14.3 "連番カテゴリID"]`

Phase 3 固定 map（全期間 train 2016-2023 fit）は参考。BT窓ごとに train 窓のみで `fit_category_map` を再 fit するのがリーク防止上 正しい方向（test 窓 ID の train 漏洩防止・§14.3）。

```python
# BT窓 train 行のみで category_map 再 fit
train_rows = feature_df[feature_df['race_date'].between(bt.train_start, calib_end)]
cat_map = fit_category_map(train_rows, cols=HIGH_CARD_CODE_COLS)  # train 窓のみ
# test 行に apply（未知 ID は __UNSEEN__ sentinel）
```

### 6.4 落とし穴

- **calib slice の strict-later guard**: `max(train.race_date) < min(calib.race_date)` を `split_3way` 拡張が継承。BT窓 calib が train と重複すると `ValueError`（構造的ブロック）。
- **calib sample <1000**: BT窓 train 期間が短い（BT-1 train 3.5年）と calib sample が減る。`calibrate_model` の isotonic/sigmoid 切替（sample<1000 → sigmoid）が自動対応（既存ロジック）。
- **bit-identical 再現性（SC#4）**: BT窓再学習でも固定 seed=42・thread count=1・固定 `as_of_datetime` を維持（`FIXED_REPRODUCE_TS`）。ただし BT窓ごとに `as_of_datetime` を変えると provenance が変わるため、`backtest_strategy_version` で BT窓を識別。
- **計算量**: 2モデル × 5窓 = 10 学習・各 BT窓 test 予測再生成。実行時間大（D-03 受容）。20 backtest（2policy × 2model × 5窓）の集計は予測生成後にメモリ内で高速。

### 6.5 検証方法

- `test_split_3way_periods_injection`: `periods` 指定で BT窓分割・guard 継承
- `test_split_3way_backward_compat`: `periods=None` で既存ハードコード（Phase 4 回帰防止）
- `test_bt_retrain_category_map`: BT窓 train のみで fit・test 窓 ID が train に無い場合は `__UNSEEN__`

## 7. backtest 結果永続化

### 7.1 出典

`[CITED: docs/keiba_ai_requirements_v1.3.md §16.2 OUT-02 + VERIFIED: src/db/schema.py + src/db/prediction_load.py]`

**§16.2 backtest CSV schema**（OUT-02・Phase 7 CSV 出力だが DB テーブル設計の参考）:
```text
backtest_id, backtest_strategy_version, train_period, validation_period,
odds_snapshot_policy, race_id, horse_id, selected_flag, stake, refund_flag,
payout_amount, profit, fukusho_hit_validated, recommend_rank, EV_lower, EV_upper
```

### 7.2 既存コード契約（再利用ポイント）

`[VERIFIED: src/db/prediction_load.py + src/db/schema.py + src/config/settings.py + src/db/connection.py]`

- **`prediction_load.py::_idempotent_load_prediction`**: model_version スコープ staging-swap（DELETE WHERE model_type+model_version → INSERT・他 model_version 行は保持）。backtest 書込の直接の参考。**backtest は backtest_id スコープ置換**（backtest_id = BT窓+policy+model_type の複合キー）で採用。
- **`schema.py`**: `SCHEMAS = [...,"backtest"]`（CREATE SCHEMA のみ・テーブル DDL/GRANT 無し）。backtest テーブル DDL 新設 + GRANT 拡張必要。
- **`connection.py`**: etl ロール search_path に `backtest` 未設定 → 拡張必要（`settings.db_schema_prediction` の後に `db_schema_backtest` 追加）。
- **`settings.py`**: `db_schema_backtest` 未定義 → 追加必要。

### 7.3 実装方針

**① settings.py 拡張**:
```python
db_schema_backtest: str = "backtest"  # 新規・db_schema_prediction と対称
```

**② connection.py 拡張**（etl search_path に backtest 追加）:
```python
search_path = (
    f"{settings.db_schema_label},"
    f"{settings.db_schema_prediction},"
    f"{settings.db_schema_backtest},"  # 新規
    f"{settings.db_schema_normalized},public"
)
```

**③ schema.py 新設**（backtest テーブル DDL + GRANT）:
```python
BACKTEST_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS backtest.fukusho_backtest (
    -- provenance（§19.1 再現性・NOT NULL）
    backtest_id varchar(64) NOT NULL,  -- {bt_name}-{policy}-{model_type} 例: BT-1-30min-lightgbm
    backtest_strategy_version varchar(32) NOT NULL,  -- 'fukusho_ev_v1'
    odds_snapshot_policy varchar(16) NOT NULL,  -- '30min_before'/'10min_before'
    train_period_start date NOT NULL,
    train_period_end date NOT NULL,
    test_period_start date NOT NULL,
    test_period_end date NOT NULL,
    model_type varchar(16) NOT NULL,
    model_version varchar(64) NOT NULL,
    feature_snapshot_id varchar(64) NOT NULL,
    -- PK RACE_KEY (7カラム・prediction と同一)
    year int, jyocd varchar(2), kaiji int, nichiji varchar(2),
    racenum int, umaban int, kettonum int,
    -- 選択・会計
    selected_flag boolean NOT NULL,
    stake int NOT NULL,  -- 0 or 100
    refund_flag boolean NOT NULL,
    refund_amount int NOT NULL,
    payout_amount int NOT NULL,
    profit int NOT NULL,
    effective_stake int NOT NULL,
    -- 的中・rank・EV
    fukusho_hit_validated int,
    recommend_rank varchar(2),
    EV_lower double precision,
    EV_upper double precision,
    -- odds provenance（§11.2 保持項目）
    odds_snapshot_at timestamp,
    odds_source_type varchar(16),  -- 'jodds_tanpuku'
    odds_missing_reason varchar(32),  -- 'no_bet_empty'/'special_value'/NULL
    -- 補助
    race_date date,
    PRIMARY KEY (backtest_id, year, jyocd, kaiji, nichiji, racenum, umaban, kettonum),
    CONSTRAINT backtest_model_type_domain CHECK (model_type IN ('lightgbm','catboost','bl3')),
    CONSTRAINT backtest_strategy_domain CHECK (backtest_strategy_version = 'fukusho_ev_v1')
);
"""
# GRANT_READER_SQL / GRANT_ETL_SQL に backtest スキーマ USAGE+SELECT / USAGE+CREATE+書込 を追加
# APPLY_ORDER に ("backtest_table", BACKTEST_TABLE_DDL) を grant_reader 直前に挿入
```

**④ backtest_load.py 新設**（`prediction_load.py` パターン踏襲・backtest_id スコープ置換）:
```python
def load_backtest(write_cur, backtest_df, *, reader_role=None) -> str:
    """backtest_id スコープ staging-swap idempotent load（prediction_load パターン）。
    同一 backtest_id の行のみ DELETE → INSERT・他 backtest_id 行は保持。
    """
    # _idempotent_load_prediction と同一構造・backtest_id スコープ
    ...
```

### 7.4 落とし穴

- **`backtest_id` 一意性**: `{bt_name}-{policy}-{model_type}`（例: `BT-1-30min_before-lightgbm`）。20 backtest で20種。PK に含めて他 backtest_id 行を保持。
- **BL-3 の model_type**: BL-3 backtest は `model_type='bl3'` で区別（CHECK 制約に `bl3` 追加・上記 DDL に反映済み）。BL-3 は model_version なし（確定オッズ固定ルール）→ `model_version='bl3_market_v1'` 等の sentinel。
- **APPLY_ORDER 挿入位置**: `backtest_table` DDL は `grant_reader` の直前（CREATE SCHEMA で backtest スキーマ作成済み・GRANT が GRANT SELECT ON ALL TABLES で本テーブルを拾えるように）。

### 7.5 検証方法

- `test_backtest_load_idempotent`: 2回連続実行で checksum bit-identical
- `test_backtest_load_scoped_swap`: backtest_id A 書込後 B 書込で A が残る
- `test_backtest_schema_apply`: `apply_schema` で backtest スキーマ + テーブル + GRANT が作成される

---

## 8. 回収率/P/L/max drawdown 計算（§11.6）

### 8.1 出典

`[CITED: docs/keiba_ai_requirements_v1.3.md §11.6]`

```text
回収率 = payout_amount合計 / effective_stake合計
損益 = payout_amount合計 + refund_amount合計 - stake合計
selected_count = 返還を含む選択数
effective_bet_count = 返還を除く実購入数
refund_count = 返還数
```

### 8.2 実装方針

```python
# src/ev/metrics.py（新設推奨）
def compute_backtest_metrics(df: pd.DataFrame) -> dict:
    """§11.6 回収率/P/L/max drawdown。race_date 昇順で累積。"""
    total_payout = df['payout_amount'].sum()
    total_effective_stake = df['effective_stake'].sum()
    total_stake = df['stake'].sum()
    total_refund = df['refund_amount'].sum()

    recovery_rate = total_payout / total_effective_stake if total_effective_stake > 0 else 0.0
    profit_loss = total_payout + total_refund - total_stake

    # max drawdown: race_date 昇順の累積 profit の最大下落幅
    df_sorted = df.sort_values(['race_date', 'race_key', 'umaban'])
    cumulative = df_sorted['profit'].cumsum()
    running_max = cumulative.cummax()
    drawdown = running_max - cumulative
    max_drawdown = int(drawdown.max())

    return {
        'recovery_rate': recovery_rate,
        'profit_loss': int(profit_loss),
        'max_drawdown': max_drawdown,
        'selected_count': int(len(df)),
        'effective_bet_count': int((df['effective_stake'] > 0).sum()),
        'refund_count': int(df['refund_flag'].sum()),
        'hit_count': int(df['fukusho_hit_validated'].sum()),
    }
```

### 8.3 落とし穴

- **`effective_stake` 合計 0**: 全件返還（極端ケース）→ 回収率 0.0 で定義（ゼロ除算回避）。
- **max drawdown の時系列順**: `race_date` 昇順（同日内は race_key→umaban）。累積 profit のピークからの最大下落。
- **`PayFukusyoPay` は 100円あたり**: stake=100 との比率が直接回収率。表示オッズでなく実際払戻金（§11.6）。

### 8.4 検証方法

- `test_metrics_recovery_rate`: payout=150, effective_stake=100 → 1.5
- `test_metrics_refund_excluded`: 返還马 effective_stake=0 → 分母から控除
- `test_metrics_max_drawdown`: 累積 [100, 200, 50, 150] → max DD=150（200→50）
- `test_metrics_counts`: selected/effective_bet/refund 件数

---

## 9. BL-3 投資ROI比較（D-04・MODL-02・Phase 4 D-07）

### 9.1 出典

`[CITED: 04-CONTEXT.md D-07 + src/model/baseline.py]`

Phase 4 D-07: 「betting ROI 比較（固定 snapshot の投資戦略としての BL-3）は Phase 5」。BL-3 は p=1/odds で EV 自己参照=1.0 になるため EV でなく**人気順等で選ぶ**（D-04・Claude 裁量）。

### 9.2 実装方針

BL-3 は「確定複勝オッズが低い=人気順」で固定ルール仮想購入:
```python
# src/ev/bl3_betting.py（新設推奨）
def select_bl3_bets(
    market_df: pd.DataFrame,  # fetch_market_data 出力・fukuoddslow, ninki, race_key
    *,
    max_bets_per_race: int = 2,
    stake_per_bet: int = 100,
) -> pd.DataFrame:
    """BL-3: 確定複勝オッズ低い順（=人気順）で top-2 選択。EV でなく odds 昇順。"""
    eligible = market_df[
        market_df['is_fukusho_sale_available']
        & market_df['fukuoddslow'].notna()
        & (market_df['fukuoddslow'] > 0)
    ].copy()
    # 確定複勝オッズ昇順（低い=人気が高い）で top-2
    eligible = eligible.sort_values(['race_key', 'fukuoddslow', 'umaban'], ascending=[True, True, True])
    selected = eligible.groupby('race_key', group_keys=False).head(max_bets_per_race)
    selected['selected_flag'] = True
    selected['stake'] = stake_per_bet
    selected['model_type'] = 'bl3'
    return selected
```

**`fetch_market_data`**（`baseline.py` 既存）を再利用: `n_odds_tanpuku.fukuoddslow` × `n_uma_race.ninki` JOIN（6列 PK + umaban）。BL-3 は確定オッズ（`n_odds_tanpuku`・`datakubun` 最終確定）を使用。JODDS ではない（BL-3 は §14.2 市場参照ベンチマーク・確定値）。

### 9.3 落とし穴

- **BL-3 と主モデルの情報条件の違い**: BL-3 は確定オッズ（レース後）・主モデルは odds-free feature（レース前）。§14.2 明記の通り「同一情報条件の比較ではない」。比較表に `bl3_comparison_caveat` で明示（Phase 4 の `baseline.py::BL3_COMPARISON_CAVEAT` 定数を再利用）。
- **BL-3 の odds_snapshot_policy**: BL-3 は確定オッズ固定（JODDS 時点非依存）。`odds_snapshot_policy='confirmed'` sentinel で区別。20 backtest 行列には含まれず・別途5窓（BT-1..5）×1 = 5 backtest（確定オッズは policy 1種）。
- **選択ルールの決定論**: `fukuoddslow` 昇順・タイブレーク `umaban` 昇順（主モデルと対称）。

### 9.4 検証方法

- `test_bl3_select_top2_low_odds`: オッズ昇順で top-2
- `test_bl3_no_ev`: BL-3 は EV 計算しない（p=1/odds で EV=1.0 自己参照・比較無意味）
- `test_bl3_caveat`: 比較表に §14.2 caveat が付与される

---

## 10. 再現性と全候補一括報告（BACK-04・§19.1）

### 10.1 出典

`[CITED: docs/keiba_ai_requirements_v1.3.md §11.2/§19.1 + VERIFIED: reports/04-eval.{md,json}]`

**§11.2 禁止事項**（構造的ブロック）:
- レース後に最も回収率が高かったオッズ時点を選ぶこと
- 最終オッズを意思決定オッズとして無条件に使うこと
- 欠損時だけ都合の良い別時点のオッズに差し替えること
- 検証後にオッズ時点を恣意的に変更すること

**§19.1 再現性**: `backtest_strategy_version`・`odds_snapshot_policy`・snapshot policy の保存。

### 10.2 全候補一括報告（後知恵禁止）

20 backtest（5窓 × 2policy × 2model）+ 5 BL-3 backtest を**全件報告**。winner 単独報告禁止:

```python
# scripts/run_backtest.py の報告生成（reports/05-backtest.{md,json}）
def generate_report(all_backtests: list[dict]) -> None:
    """全候補を一括報告・winner 単独報告禁止（BACK-04）。"""
    # 20 + 5 = 25 backtest を backtest_id でソート・全件テーブル出力
    # 勝者強調・ランキングは提示するが「この1つだけ採用」は提示しない
    # 主モデル確定は Phase 6（D-03/D-04・事前登録基準）
```

### 10.3 reports/05-backtest.{md,json} 出力構造（Phase 4 `04-eval` パターン踏襲）

```markdown
# Phase 5 Backtest Report (BACK-01..04 / §15.5 / §19.1)

## フル行列 backtest 結果（25 backtest）

| backtest_id | bt_name | odds_policy | model_type | recovery_rate | P/L | max_DD | selected | effective_bet | refund | hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BT-1-30min_before-lightgbm | BT-1 | 30min_before | lightgbm | 0.95 | -1200 | 3500 | 245 | 240 | 5 | 0.32 |
| BT-1-30min_before-catboost | BT-1 | 30min_before | catboost | ... | ... | ... | ... | ... | ... | ... |
| ...（20行）... |
| BT-1-confirmed-bl3 | BT-1 | confirmed | bl3 | ... | ... | ... | ... | ... | ... | ... |
| ...（5行）... |

## §11.2 odds policy 固定の履行確認（BACK-04 構造的ブロック）

- 全 backtest で odds_snapshot_policy は事前登録（30min_before/10min_before/confirmed）・レース後変更なし
- 欠損 odds は no_bet sentinel・別時点への差し替えなし
- 後知恵 winner 単独報告なし（全25候補を一括提示）

## 注記

- BL-3: 確定オッズ由来（§14.2 同一情報条件ではない・market reference only）
- 主モデル確定は Phase 6（D-03/D-04 事前登録基準: Calibration 重視）
- 実JODDS取得進行中・本報告は [取得完了版 / 合成データ版]
```

### 10.4 落とし穴

- **winner バイアス**: 回収率最高の backtest_id を「推奨」として強調すると後知恵選択になる。全件提示・Phase 6 で事前登録基準（D-04 Calibration 重視）で確定。
- **`backtest_strategy_version` stamp**: 全行に `'fukusho_ev_v1'`（§11.4 固定ルール）。戦略を変える場合は別 version（`fukusho_ev_v2` 等）。

### 10.5 検証方法

- `test_report_all_candidates`: 25 backtest 全件が報告に含まれる
- `test_report_no_winner_override`: winner 単独報告ロジックが存在しない
- `test_report_strategy_version`: 全行 `backtest_strategy_version='fukusho_ev_v1'`

## Validation Architecture

> `workflow.nyquist_validation: true`（.planning/config.json 確認済み）→ 本セクション必須。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0（既存・`pyproject.toml [tool.pytest.ini_options]` testpaths=["tests"]） |
| Config file | `pyproject.toml`（addopts="-ra"・markers 定義済み） |
| Quick run command | `uv run pytest tests/ev/ tests/utils/test_group_split.py -x -q` |
| Full suite command | `uv run pytest -q`（既存 26 ファイル・262 tests green・Phase 4 完了時） |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EV-01 | EV_lower/EV_upper 計算 | unit | `uv run pytest tests/ev/test_ev_rank.py::test_ev_calculation -x` | ❌ Wave 0 |
| EV-02 | 推奨ランク S/A/B/C/D | unit | `uv run pytest tests/ev/test_ev_rank.py::test_rank_S -x` | ❌ Wave 0 |
| BACK-01 | race_id-grouped split + BT窓 | unit | `uv run pytest tests/utils/test_group_split.py::test_bt_window_disjoint -x` | ❌ Wave 0 |
| BACK-02 | 仮想購入ルール fukusho_ev_v1 | unit | `uv run pytest tests/ev/test_purchase_simulator.py::test_purchase_top2 -x` | ❌ Wave 0 |
| BACK-03 | 返還会計（6シナリオ） | unit | `uv run pytest tests/ev/test_refund_accounting.py::test_refund_dead_loss -x` | ❌ Wave 0 |
| BACK-03 | odds 時点選択 backward | unit | `uv run pytest tests/ev/test_odds_snapshot.py::test_odds_snapshot_future_leak -x` | ❌ Wave 0 |
| BACK-04 | odds policy 固定・no_bet | unit | `uv run pytest tests/ev/test_odds_snapshot.py::test_odds_snapshot_no_bet_empty -x` | ❌ Wave 0 |
| BACK-03 | staging-swap idempotent | integration | `uv run pytest tests/db/test_backtest_load.py::test_backtest_load_idempotent -x` | ❌ Wave 0 |
| §11.6 | 回収率/max drawdown | unit | `uv run pytest tests/ev/test_metrics.py::test_metrics_recovery_rate -x` | ❌ Wave 0 |
| D-03 | BT窓再学習ループ | integration | `uv run pytest tests/model/test_orchestrator_bt.py::test_split_3way_periods_injection -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit**: `uv run pytest tests/ev/ tests/utils/test_group_split.py -x -q`（新規モジュールの unit test・<30秒）
- **Per wave merge**: `uv run pytest -q`（フル suite・Phase 4 完了時 262 tests green）
- **Phase gate**: フル suite green + BACK-03 対抗的テスト（6シナリオ stake/payout assert）全 green で `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/ev/__init__.py`・`tests/ev/conftest.py` — 合成データ fixtures（label flags + HARAI + JODDS mock）
- [ ] `tests/ev/test_odds_snapshot.py` — covers EV-01/BACK-04（backward/no_bet/special_values/day_boundary/future_leak）
- [ ] `tests/ev/test_refund_accounting.py` — covers BACK-03（6シナリオ: normal/scratch/excluded/dead_loss/fuseiritu/race_cancelled/no_sale/deadheat）
- [ ] `tests/ev/test_ev_rank.py` — covers EV-01/EV-02
- [ ] `tests/ev/test_purchase_simulator.py` — covers BACK-02（filter/top2/tiebreak/no_eligible/no_sale）
- [ ] `tests/ev/test_metrics.py` — covers §11.6（recovery_rate/max_drawdown/counts）
- [ ] `tests/utils/test_group_split.py` — covers BACK-01（BT窓ヘルパ新設分・既存 test_group_split.py に追記）
- [ ] `tests/db/test_backtest_load.py` — covers 永続化（staging-swap idempotent・scoped swap）
- [ ] `tests/model/test_orchestrator_bt.py` — covers D-03（split_3way periods injection・後方互換）

**合成データ設計指針**（実JODDS未完でも検証可能）:
- JODDS mock: `HappyoTime`(mmddHHMM) 複数 snapshot・`FukuOddsLow` 正常値/特殊値（`----`/`****`/`0000`/`0999`）混在
- HARAI mock: `FuseirituFlag2`/`HenkanFlag2`/`PayFukusyoUmaban1..5`/`PayFukusyoPay1..5` 各シナリオ
- label mock: `is_scratch_cancel`/`is_dead_loss`/`is_race_cancelled`/`is_fukusho_sale_available` 各シナリオ
- prediction mock: p_fukusho_hit + race_key + PK 7カラム

*(Framework install 不要・既存 pytest 9.1.0 + KEIBA_SKIP_DB_TESTS パターンで DB テスト制御)*

---

## ファイル変更マップ（pattern-mapper 用）

### 新規ファイル

| File | 役割 | 主要関数/クラス |
|------|------|-----------------|
| `src/ev/__init__.py` | EV/backtest モジュール | — |
| `src/ev/odds_snapshot.py` | JODDS 時点選択（D-01/D-02） | `select_odds_snapshot(jodds_df, race_times, policy)` |
| `src/ev/refund_accounting.py` | 返還/中止会計決定表（D-05/BACK-03） | `determine_stake_payout(row)` |
| `src/ev/ev_rank.py` | EV計算・推奨ランク（EV-01/02） | `compute_ev_and_rank(df)` |
| `src/ev/purchase_simulator.py` | 仮想購入ルール fukusho_ev_v1（BACK-02） | `select_bets(df)` |
| `src/ev/metrics.py` | 回収率/P/L/max DD（§11.6） | `compute_backtest_metrics(df)` |
| `src/ev/bl3_betting.py` | BL-3 投資ROI（D-04） | `select_bl3_bets(market_df)` |
| `src/db/backtest_load.py` | backtest 結果永続化（staging-swap） | `load_backtest(write_cur, df)` |
| `scripts/run_backtest.py` | BT窓再学習 + フル行列 backtest 実行 | `main()` |
| `tests/ev/conftest.py` | 合成データ fixtures | — |
| `tests/ev/test_*.py` | 上記 6 ユニットの unit test | — |
| `tests/db/test_backtest_load.py` | staging-swap idempotent | — |
| `tests/model/test_orchestrator_bt.py` | BT窓 periods injection | — |

### 変更ファイル

| File | 変更内容 | 影響範囲 |
|------|----------|----------|
| `src/utils/group_split.py` | `BTWindow` dataclass + `BT_WINDOWS` + `get_bt_race_ids` 追記 | 新規追加・既存 `race_id_time_series_split` は変更なし |
| `src/model/data.py` | `split_3way` に `periods` パラメータ追加（後方互換・`None` で既存ハードコード） | `split_3way` シグネチャ拡張・既存呼出元（orchestrator/run_train_predict）は影響なし |
| `src/model/orchestrator.py` | `train_and_predict` に `split_periods` パラメータ追加（`split_3way` へ伝播） | 新規パラメータ・既定値 `None` で後方互換 |
| `src/db/schema.py` | `BACKTEST_TABLE_DDL` 新設 + GRANT_READER/GRANT_ETL に backtest スキーマ追加 + APPLY_ORDER 挿入 | 新規 DDL・既存 PREDICTION_TABLE_DDL は変更なし |
| `src/config/settings.py` | `db_schema_backtest: str = "backtest"` 追加 | 新規フィールド・既定値 |
| `src/db/connection.py` | etl search_path に `settings.db_schema_backtest` 追加 | 1行追加 |
| `reports/05-backtest.{md,json}` | 新規生成（Phase 4 `04-eval` パターン） | 新規 |

### 再利用（変更なし）

| File | 再利用ポイント |
|------|----------------|
| `src/etl/fukusho_label.py` | label フラグ（`is_scratch_cancel` 等）を READ で消費・変更なし |
| `src/db/prediction_load.py` | staging-swap idempotent パターンを `backtest_load.py` が踏襲・変更なし |
| `src/model/baseline.py::fetch_market_data` | BL-3 市場データ取得（`n_odds_tanpuku` JOIN）・変更なし |
| `src/model/predict.py::PREDICTION_COLUMNS/MODEL_TYPE_TO_SHORT` | 予測の model_type 区別・変更なし |

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 時系列オッズ時点選択 | 手作り時刻比較ループ | `pandas.merge_asof(direction='backward')` | 既存 PIT プリミティブ・未来リーク構造的に不可・sort 前提の guard 内蔵 |
| race_id-grouped 時系列分割 | 手作り group-by + filter | `src/utils/group_split.py` の既存 guard + BT窓ヘルパ新設 | race_id disjoint + strict chronological は既存 ValueError guard が保証 |
| staging-swap idempotent load | 手作り TRUNCATE+INSERT | `src/db/prediction_load.py` パターン（backtest_id スコープ） | advisory lock・rowcount verify・checksum・他 version 行保持済み |
| 返還/中止判定 | HARAI ビットマスク直接解析 | `label.fukusho_label` の既存フラグ（`is_scratch_cancel` 等） | Phase 2 で HR 突合済み・backtest は label を一次ソース・HARAI は cross-check |
| BT窓 race_id 分割 | 手作り date filter | `get_bt_race_ids`（`group_split.py` 新設） | guard 継承・§15.5 完全準拠 |
| 回収率計算 | 手作り集計 | `compute_backtest_metrics`（`metrics.py` 新設） | §11.6 effective_stake 分母控除・max drawdown 時系列順 |

**Key insight:** Phase 5 のリーク防止（BACK-04 odds policy 固定・race_id disjoint・返還 honest 会計）はすべて既存プリミティブ（`merge_asof`・`group_split` guard・label フラグ・staging-swap）の組み合わせで実現できる。新規アルゴリズムは EV/rank 計算（純粋関数）と BT窓ヘルパ（date filter + guard）のみ。

---

## Common Pitfalls

### Pitfall 1: JODDS `HappyoTime` と `HassoTime` の日跨ぎ
**What goes wrong:** `HassoTime` が深夜（例: `0030`）で `HassoTime - 30分` が前日になると、HHMM 整数比較が破綻する。
**Why it happens:** `HappyoTime` は mmddHHMM・`HassoTime` は hhmm・日付境界をまたぐと月日部分が一致しない。
**How to avoid:** `race_start_datetime`（`race_date + HassoTime` 構築済み）を基準に `pd.Timedelta(minutes=N)` で計算。HHMM 整数比較は使わない。
**Warning signs:** 日跨ぎレースで snapshot が選択されない（`no_bet` 多発）。

### Pitfall 2: `n_jodds_tanpuku` 本体に `DataKubun` がない
**What goes wrong:** `n_jodds_tanpuku` に `DataKubun` 列が無い（実DB実証）ため、中間/最終/確定判定に head テーブル JOIN が必要。
**Why it happens:** EveryDB2 の正仕様（47 には DataKubun 無・46 head のみ）。
**How to avoid:** `n_jodds_tanpukuwaku_head` と PK（Year,MonthDay,JyoCD,Kaiji,Nichiji,RaceNum,HappyoTime）で JOIN して `DataKubun` を取得。
**Warning signs:** `DataKubun='1'`(中間) で filter せずに確定オッズが混入（D-01 違反）。

### Pitfall 3: `split_3way` ハードコードで BT窓が表現できない
**What goes wrong:** `split_3way` は固定暦年 mask（train 2016-07〜2023 / test 2024-07〜12）で BT窓（train 2019-06〜2022/test 2023 等）を表現できない。
**Why it happens:** Phase 4 で val 2024 固定で実装された。
**How to avoid:** `split_3way` に `periods` パラメータを追加（後方互換・`None` で既存ハードコード）。
**Warning signs:** BT窓 test 2023 予測が生成されない（Phase 4 の val 2024 予渓が再利用される）。

### Pitfall 4: 競走中止を backtest から除外すると回収率が過大評価
**What goes wrong:** `is_dead_loss` 馬を除外すると実運用の負けが消える（§10.6 禁止）。
**Why it happens:** 中止馬は `fukusho_hit_validated=0` なので「不的中として計上すればよい」と誤解しがちだが、予測対象から外すと消失。
**How to avoid:** `is_dead_loss` は `is_model_eligible` の判定対象外（§10.6 含める）・予測が生成されていれば選択対象（不的中・`effective_stake=100`）。
**Warning signs:** 回収率が異常に高い（中止馬の損失が抜ける）。

### Pitfall 5: 返還馬の `effective_stake=0` 忘れで回収率が歪む
**What goes wrong:** 返還馬を `effective_stake=100` で計上すると分母が膨らみ回収率が過小評価。
**Why it happens:** §11.6 の `effective_stake=0` ルールを見落とす。
**How to avoid:** 決定表（§2.2）に従い取消/除外/不成立/レース中止は `effective_stake=0`。
**Warning signs:** 返還多いレースで回収率が不自然に下がる。

### Pitfall 6: 後知恵 winner 単独報告
**What goes wrong:** 回収率最高の backtest_id を「推奨」として強調すると後知恵選択（§11.2 禁止）。
**Why it happens:** 報告を読む側が「最高スコア=採用」と解釈する。
**How to avoid:** 全25候補を一括提示・主モデル確定は Phase 6（D-04 事前登録基準: Calibration 重視）。
**Warning signs:** 報告に「推奨: BT-X-policy-model」の記述。

---

## Package Legitimacy Audit

> 本フェーズは**外部パッケージを新規インストールしない**。既存スタック（LightGBM 4.6.0 / CatBoost 1.2.10 / scikit-learn 1.9.0 / pandas 3.0.3 / psycopg3 3.3.4 / mlxtend 0.25.0 / pyarrow 24.0.0）のみ使用。PyPI 新規依存なし。

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none new) | — | — | — | — | — | 本フェーズは既存スタックのみ・新規インストールなし |

**Packages removed due to [SLOP] verdict:** なし（新規パッケージなし）
**Packages flagged as suspicious [SUS]:** なし

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 15 | DB永続化（backtest スキーマ） | ✓ | 15.18 (Homebrew) | — |
| Python 3.12 | 実行環境 | ✓ | 3.12.13 | 3.11 fallback (§17.1) |
| LightGBM | BT窓再学習（lightgbm） | ✓ | 4.6.0 | — |
| CatBoost | BT窓再学習（catboost） | ✓ | 1.2.10 | — |
| scikit-learn | CalibratedClassifierCV 再利用 | ✓ | 1.9.0 | — |
| pandas | merge_asof / groupby | ✓ | 3.0.3 | — |
| psycopg3 | DB READ/WRITE | ✓ | 3.3.4 | — |
| mlxtend | GroupTimeSeriesSplit（既存 re-export） | ✓ | 0.25.0 | — |
| pyarrow | Parquet snapshot 読込 | ✓ | 24.0.0 | — |
| `public.n_jodds_tanpuku` | JODDS 時点選択（D-01） | ✓（取得進行中）| 2015年25レース日分のみ | 合成データで検証先行・BT期間2019-2025取得完了後に実データ |
| `public.n_jodds_tanpukuwaku_head` | DataKubun 判定 | ✓ | 同上 | 同上 |
| `public.n_harai` | 返還/払戻額（D-05） | ✓ | 39,580行 | — |
| `public.n_race` | HassoTime（発走時刻） | ✓ | 全期間 | — |
| `label.fukusho_label` | 返還フラグ・的中判定 | ✓ | 554,267行 | — |
| `prediction.fukusho_prediction` | Phase 4 予渓（val 2024） | ✓ | 22,213行/モデル | BT窓 test 2023/2025 は再学習で生成 |
| `snapshots/feature_matrix_20260620-1a-postreview-v2.parquet` | BT窓 race_date filter 元 | ✓ | 554,267行 | — |

**Missing dependencies with no fallback:** なし
**Missing dependencies with fallback:** JODDS 実データは BT期間 2019-2025 が未取得（2015年25レース日分のみ）→ 合成データで単体テスト・実データ backtest は取得完了後（2段階計画）

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 確定オッズ固定 backtest | JODDS 発走前時点固定（30/10分前）| Phase 5 D-01 | EV 計算が実運用（発走前判断）に整合・後知恵排除 |
| race_id-grouped なし | race_id disjoint + strict chronological | Phase 1 D-17 / 既存 group_split | 同一レースの train/test またぎリーク構造的防止 |
| 返還を無視 | `effective_stake` honest 会計 | §11.6 v1.3 | 回収率の歪み防止（返還多いレースで過大評価） |

**Deprecated/outdated:**
- 確定オッズのみ backtest: D-01 で JODDS 発走前時点に移行（確定オッズは BL-3 のみ・§14.2 市場参照）
- Phase 4 固定窓（val 2024）: D-03 で BT窓再学習フル行列に移行

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | JODDS 取得が BT期間 2019-2025 で完了する（過去遡取可能・ユーザー判断）| §1/Environment | backtest 実行が block・合成データ検証のみで Phase 5 完了扱いになる |
| A2 | BT-4/5 の test 年を BT-1..3 と揃える（2024）| §5 | rolling vs expanding の比較が BT-1..3 と対称でなくなる（Claude 裁量・planner 確定） |
| A3 | BL-3 選択ルール = 確定複勝オッズ昇順 top-2 | §9 | D-04「人気順等」の具体的ルール・別ルール（ninki 昇順等）でも可（Claude 裁量） |
| A4 | 仮想購入タイブレーク = umaban 昇順 | §4 | 同 EV 時の順位付け・別ルール（p 高い方等）でも可（Claude 裁量・決定論維持） |
| A5 | `split_3way` 拡張が orchestrator/run_train_predict の後方互換を維持 | §6 | Phase 4 回帰（SC#4 bit-identical 等）・`periods=None` デフォルトで防ぐ |
| A6 | `HenkanUma` ビットマスクを直接見なくてよい（label フラグが一次） | §2 | 個別馬返還の取りこぼし・label の `is_scratch_cancel`/`is_race_excluded` が同等情報（HR `bataijyu` sentinel 由来） |

---

## Open Questions

1. **JODDS 取得完了タイミング**
   - What we know: 2026-06-20 開始・2015年25レース日分取得済み・過去遡取進行中
   - What's unclear: BT期間 2019-2025 の完了時期
   - Recommendation: Phase 5 実装（コード・単体テスト・合成データ）を先行・取得完了後に実データ backtest 実行の 2 段階計画（planner が実行計画に反映）

2. **BT-4/5 rolling の test 年**
   - What we know: §15.5 は「直近3年/5年 rolling・翌年」・具体 test 年は明記なし
   - What's unclear: BT-1..3 の test 年（2023/2024/2025）と揃えるか別途
   - Recommendation: 揮える（同一 test 年で rolling vs expanding 比較が対称）・planner 確定

---

## Security Domain

> `security_enforcement` は config.json に明示的に `false` が無いため有効（absent = enabled）。本フェーズは DB READ/WRITE・SQL クエリ・計算ロジックが中心。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (ローカル DB・既存 psycopg3 認証) |
| V3 Session Management | no | — |
| V4 Access Control | yes | 既存2ロール（readonly/etl）・raw read-only REVOKE・backtest スキーマ GRANT 拡張 |
| V5 Input Validation | yes | BT窓期間文字列の検証・odds 特殊値 sentinel 化・`no_bet` で silent fallback 禁止 |
| V6 Cryptography | no | — (機密性の高い計算なし) |
| V8 Information Disclosure | yes | 既存 DSN masked logging・backtest 結果に秘匿情報なし |

### Known Threat Patterns for PostgreSQL + pandas backtest stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection（JODDS/HARAI クエリ） | Tampering | psycopg3 parameterized queries（既存パターン・`%s` placeholder） |
| 後知恵オッズ選択（リーク） | Information Disclosure | `merge_asof(direction='backward')` 固定・`odds_snapshot_policy` 事前登録・§11.2 構造的ブロック |
| race_id train/test またぎ（リーク） | Information Disclosure | 既存 `group_split` guard（race_id disjoint + strict chronological・ValueError） |
| 返還马の回収率歪み | Tampering | §11.6 `effective_stake=0`・決定表（§2.2） |

---

## Sources

### Primary (HIGH confidence)
- `docs/keiba_ai_requirements_v1.3.md` §11.1-11.6 / §15.4-15.5 / §16.2 / §19.1 / §10.6 — EV計算・オッズ時点・仮想購入・推奨ランク・回収率・BT窓・CSV schema・再現性・中止扱い
- `docs/everydb2/47-JODDS_TANPUKU.md` — 時系列オッズ単複スキーマ（HappyoTime/FukuOddsLow/High/特殊値）
- `docs/everydb2/46-JODDS_TANPUKUWAKU_HEAD.md` — DataKubun/FukusyoFlag/FukuChakuBaraiKey
- `docs/everydb2/05-HARAI.md` — FuseirituFlag2/HenkanFlag2/HenkanUma1..28/PayFukusyoUmaban1..5/PayFukusyoPay1..5
- `docs/everydb2/03-RACE.md` — HassoTime（発走時刻）
- 実DB `information_schema.columns`（n_jodds_tanpuku/n_jodds_tanpukuwaku_head/n_race/n_harai/label.fukusho_label/prediction.fukusho_prediction）— スキーマ実証
- 実DB `pg_stat_user_tables`（JODDS 1,708,045行・HARAI 39,580行・返還1,541件・中止4,506件）— 件数実証
- `src/model/orchestrator.py` / `src/model/data.py::split_3way` / `src/model/predict.py` / `src/db/prediction_load.py` / `src/db/schema.py` / `src/db/connection.py` / `src/config/settings.py` / `src/model/baseline.py` / `src/etl/fukusho_label.py` / `src/utils/group_split.py` — 既存コード契約

### Secondary (MEDIUM confidence)
- `reports/04-eval.{md,json}` — Phase 4 レポートパターン（md+json・比較表・D-04 事前登録明記）
- `.planning/phases/04-model-prediction/04-CONTEXT.md` D-03/D-07/D-08 — 両モデル backtest・BL-3 betting ROI・確定オッズ源
- `.planning/phases/03-as-of-features-snapshots/03-CONTEXT.md` D-09 — train 2016H2〜（§15.5 の 2019-06〜 が優先）

### Tertiary (LOW confidence)
- なし（全要件・スキーマ・コード契約を実証済み）

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 既存スタックのみ・新規パッケージなし・全バージョン実証（LightGBM 4.6.0 / CatBoost 1.2.10 / sklearn 1.9.0 / pandas 3.0.3 / psycopg3 3.3.4 / mlxtend 0.25.0）
- Architecture: HIGH — 既存コード契約（split_3way/prediction_load/group_split/label flags）を実証・拡張点（BT窓 periods/backtest DDL）は既存パターンの踏襲
- Pitfalls: HIGH — 実DB観測（DataKubun列無し/返還1,541件/中止4,506件）とコード契約（split_3way ハードコード）を実証・落とし穴を実データで確認
- JODDS 実データ backtest: MEDIUM — 取得進行中（2015年のみ）・合成データで検証先行・BT期間完了後に実データ検証必要

**Research date:** 2026-06-20
**Valid until:** 2026-07-20（30日・JODDS取得進行で実データ状況が変化する可能性あり）
