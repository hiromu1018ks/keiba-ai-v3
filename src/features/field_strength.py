# ruff: noqa: E501  (docstring / 日本語コメント行長は緩和・tests/model/test_trainer.py・speed_figure.py と同一慣例)
"""Phase 10 PLAN 01・相手強度 field_strength profile（D-06 第1段階・FEAT-02・SC#1/SC#2・D-01〜D-06）.

本 module は source race 内 opponent の能力 profile 8値（mean/median/top3_mean/top5_mean/max/sd/
valid_count/coverage）を raw_history 全行に付与する。PLAN 02（rolling.py 拡張 第2段階）が本 profile
列を入力に 21 feature を生成する。D-01 厳格版 as-of（strict ``<``）と D-04 発走馬特定
（``kakuteijyuni > 0``）を機械保証し・core value「リーク防止最優先」を最も厳格に問う。

3聖域（本 module の不変事項・adversarial テスト + AST audit で機械保証）:

1. **市場情報不使用（SAFE-01）**
   - オッズ/人気/過去人気/過去オッズ 等・市場情報 proxy は feature に一切入れない。
   - 本 module のソース上の識別子・文字列リテラルに市場情報系トークンは現れない。
   - PLAN 07 が AST audit で完全証明する（SC#4 下地）。

2. **PIT-correct 厳格版 as-of（SC#1・D-01）**
   - **opponent-vs-source gate（行レベル）**: opponent.available_at < source_race.available_at
     (strict ``<``）・source race 当日結果は混入しない（``_pit_cutoff_prefilter`` helper）。
   - **source-vs-target-cutoff gate（値レベル・CYCLE-2 HIGH-C2-1）**: 相手 ability 値は target
     observation の feature_cutoff_datetime でなく source race 自身の available_at を cutoff として
     **FULL par + variant + speed_figure pipeline を通して再計算** される。``compute_speed_figure_for_history``
     が observations= 引数で付与した obs_id 展開済み speed_figure（target cutoff に依存・各行の par/variant
     が target obs の feature_cutoff_datetime で決定）は一切再利用せず・raw history に合成 observation
     (obs_id='SOURCE_ASOF_<race_nkey>_<kettonum>'・feature_cutoff_datetime=source_race.available_at・
     CYCLE-3 MEDIUM #2 race×horse 単位・horse-level par) を渡して full pipeline を source-as-of で
     再実行する。これが行包含でなく値レベルの source-vs-target-cutoff 保証（同じ pre-source opponent
     race がどの target observation に消費されても同一 speed_figure・値の不変性）を達成する唯一の方法。
   - adversarial value-invariance test が monkeypatch で再計算 cutoff を target に差替えると
     値が変化することを検出（Cycle-1 H2 の行包含 gate は不十分と判明・10-REVIEWS.md L57-92）。

3. **byte-reproducible（§19.1）**
   - 決定論的アルゴリズム（vectorized groupby + nlargest・固定順序）で同一入力は bit-identical。
   - ``test_byte_reproducible`` が ``np.array_equal`` で実証。

CYCLE-3 MEDIUM #1（available_at 非依存）: raw_history（Step 5b 前・obs_id 未展開）には available_at
も speed_figure も存在しない（``builder.py`` L206-323 の派生列は ``race_nkey`` / ``as_of_datetime`` /
``days_since_prev`` / ``timediff`` / ``babacd`` のみ・``available_at`` は ``compute_speed_figure_for_history``
が L698 で付与）。本 module は関数内で ``available_at = pd.to_datetime(race_date)`` を導出し・
Step 5b 後汚染 history への依存経路を構造的に閉じる。

CYCLE-3 MEDIUM #3（cardinality 回避）: 全 source race の合成 obs を1連結して
``compute_speed_figure_for_history`` を呼ぶと・``speed_figure.py`` L635 の ``out.merge(obs_keys,
on='kettonum')`` が cutoff filter(L641) の前に「H の履歴行 × H を含む source race 数」の積を
materialize し・馬平均50走 × ~1万頭で2500万行超に達する。本 module は synth_obs を
per-source-race batch（``SOURCE_RACE_BATCH_SIZE``）に分割し・各バッチ毎に
``compute_speed_figure_for_history`` を呼出すことで H² 積 materialize を回避する。バッチ化が
値の不変性を損なわないことは obs_id が source×horse 毎に独立（CYCLE-3 MEDIUM #2）なことで
構造的に保証される（par/variant groupby 先頭キー obs_id・``speed_figure.py`` L402/510）。
"""

from __future__ import annotations

import logging
from typing import Any  # noqa: F401  (型ヒント用)

import pandas as pd

from src.features.availability import CUTOFF_SEMANTICS
from src.features.speed_figure import compute_speed_figure_for_history

# CR-01 (10-08 gap-closure): 空 バッチの silent data loss を logger.warning で可視化するため。
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HIGH #2 / SC#2: cutoff semantics 不変量の実行時参照（strict_less_than / Asia/Tokyo）。
# speed_figure.py L46 / rolling.py L58 と対称な単一不変量・本 module の strict < filter は
# availability.CUTOFF_SEMANTICS["pit_filter"] と同一の真の源を持つ。
# ---------------------------------------------------------------------------
assert CUTOFF_SEMANTICS["comparison_operator"] == "strict_less_than"

# ---------------------------------------------------------------------------
# D-02 事前登録定数（Open Question #1 解決）: 相手個人の rolling 能力は rolling_speed_figure_mean_5
# の1軸のみ（17倍計算量抑制・Phase 9 D-09 安定能力代表値）。
# CYCLE-2 HIGH-C2-1: この axis は入力 history の既存 speed_figure 列（obs_id 展開済み・
# target-cutoff-contaminated）から読まず・_compute_source_asof_opponent_speed_figures で
# raw history に full-pipeline を再実行して得られた source-as-of 再計算 speed_figure 値に対して
# latest-K=5 を適用する対象。
# ---------------------------------------------------------------------------
OPPONENT_ROLLING_AXIS: str = "rolling_speed_figure_mean_5"
OPPONENT_ROLLING_K: int = 5

# ---------------------------------------------------------------------------
# CYCLE-3 MEDIUM #3 (10-REVIEWS.md L223): per-source-race バッチサイズ事前登録。
# 全 source race の合成 obs を1連結して compute_speed_figure_for_history を呼ぶと・
# out.merge(obs_keys, on='kettonum') が cutoff filter 前に H² 積を materialize し
# 2500万行超に達する（馬平均50走 × ~1万頭）。本定数で分割し H² 積を回避する。
# バッチ化が値の不変性を損なわないことは obs_id が source×horse 毎に独立なことで保証。
# W-3 性能検証は PLAN 07 で production-scale smoke を追加。
# ---------------------------------------------------------------------------
SOURCE_RACE_BATCH_SIZE: int = 100


# ---------------------------------------------------------------------------
# SAFE-01 市場情報不使用: 本モジュールは市場情報 proxy（オッズ系/人気系/過去オッズ系）を一切
# 使用しない（SC#4・AST audit 対象・PLAN 07 が grep/AST で完全証明）。
# adversarial AST audit の false positive 回避のため・禁止トークンの文字列リテラルは
# 識別子・コメント・docstring のいずれにも書かないこと（別表現「市場情報」で書く）。
# ---------------------------------------------------------------------------


def _pit_cutoff_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
    """defense-in-depth pre-filter: opponent.available_at < source_race.available_at (strict <).

    opponent-vs-source gate（D-01 厳格版 as-of・行レベル）。``_opp_available_at`` 列は opponent
    過去走の available_at・``_source_available_at`` 列は source race の available_at を表す。

    本 helper に切り出した意図: adversarial test (``tests/features/test_field_strength.py``) が
    ``monkeypatch`` で本関数を ``<=`` 版に差し替え・guard 無効化で same-day opponent データ混入を
    検証できるようにするため（``speed_figure.py`` L98-118 / ``rolling.py`` L114-126 と対称）。
    filter 式は byte-identical (``<`` strict) で振舞は不変。

    Parameters
    ----------
    expanded : pd.DataFrame
        source-as-of 再計算済みの展開フレーム（``_opp_available_at`` / ``_source_available_at`` 列必須）。
        ``_opp_available_at`` = opponent 過去走の available_at（race_date 由来）・
        ``_source_available_at`` = source race の available_at（race_date 由来・CYCLE-3 MEDIUM #1）。

    Returns
    -------
    pd.DataFrame
        ``_opp_available_at < _source_available_at`` を満たす行のみの copy。
    """
    return expanded[
        expanded["_opp_available_at"] < expanded["_source_available_at"]
    ].copy()


def _topk_mean_clamped(values: pd.Series, k: int) -> float:
    """top-k mean・k = min(k, valid_opponents) でクランプ（D-05）。

    ``rolling.py`` L183-192 ``_best2_mean_of_group`` と対称・``nlargest`` で vectorized・決定論的。
    ``len(valid)==0`` は NaN（sentinel 側で扱い・silent 0 fill でない）。

    Parameters
    ----------
    values : pd.Series
        opponent ability 値（source-as-of 再計算 speed_figure 由来の rolling_speed_figure_mean_5）。
    k : int
        上位何件の平均を取るか（3 または 5・D-03 profile）。

    Returns
    -------
    float
        上位 k 件（クランプ済み）の平均。有効値0件は NaN。
    """
    valid = values.dropna()
    if len(valid) == 0:
        return float("nan")
    actual_k = min(k, len(valid))
    return float(valid.nlargest(actual_k).mean())


def _build_source_asof_observation(source_race_rows: pd.DataFrame) -> pd.DataFrame:
    """CYCLE-2 HIGH-C2-1 + CYCLE-3 MEDIUM #2: source race × opponent horse 単位の合成 observation 構築.

    入力 source_race_rows（各 source race の代表行・race_nkey/kettonum/available_at を持つ starters）
    から・``compute_speed_figure_for_history`` に渡す合成 observation DataFrame を構築する。

    出力列:
      - ``obs_id``: ``'SOURCE_ASOF_' + race_nkey + '_' + kettonum``（race×horse 単位・
        CYCLE-3 MEDIUM #2 horse-level par・target observation の obs_id と名前空間衝突しない接頭辞）
      - ``feature_cutoff_datetime``: source_race.available_at（target cutoff でない・race_date 由来・
        CYCLE-3 MEDIUM #1・これが source-vs-target-cutoff gate の本体）
      - ``kettonum``: 当該 source race の各 starter（horse と race の組毎に1行）

    この synth_obs を ``compute_speed_figure_for_history`` に渡すことで・par groupby キー(obs_id)・
    variant groupby キー(obs_id) が source race × opponent horse 毎に独立になり・各 (source race,
    horse) の par/variant/speed_figure がその source race の available_at cutoff と horse 自身の
    pre-cutoff history のみで決定される（target cutoff 非依存・値の不変性・target 経路と同 normalization）。

    Parameters
    ----------
    source_race_rows : pd.DataFrame
        各 source race の starter 行（``race_nkey`` / ``kettonum`` / ``available_at`` 列必須）。

    Returns
    -------
    pd.DataFrame
        列 = (obs_id, kettonum, feature_cutoff_datetime)。``compute_speed_figure_for_history`` の
        ``observations`` 引数にそのまま渡せる形式。
    """
    out = pd.DataFrame(
        {
            "obs_id": (
                "SOURCE_ASOF_"
                + source_race_rows["race_nkey"].astype(str)
                + "_"
                + source_race_rows["kettonum"].astype(str)
            ),
            "kettonum": source_race_rows["kettonum"].values,
            "feature_cutoff_datetime": source_race_rows["available_at"].values,
        }
    )
    return out


def _compute_source_asof_opponent_speed_figures(
    raw_history: pd.DataFrame,
    source_available_at_by_race: pd.Series,
) -> pd.DataFrame:
    """CYCLE-2 HIGH-C2-1 root-cause fix + CYCLE-3 MEDIUM #1/#3: full par+variant+speed_figure pipeline を source-as-of で再実行.

    入力の obs_id 展開済み speed_figure（target-cutoff-contaminated・``compute_speed_figure_for_history``
    が observations= 渡しで付与した値・各行が target obs の feature_cutoff_datetime に依存する
    par/variant/speed_figure を持つ）を一切再利用しない。代わりに各 source race の available_at を
    cutoff とする合成 observation（``_build_source_asof_observation``）を用い・raw_history に対し
    ``compute_speed_figure_for_history`` を呼出すことで par+variant+speed_figure の FULL pipeline を
    source-as-of cutoff で再実行する。これが値レベルの source-vs-target-cutoff 保証（値の不変性）の
    唯一の達成方法（10-REVIEWS.md L89-92, L199-205）。

    CYCLE-3 MEDIUM #1（available_at 非依存）: raw_history に available_at 列が存在しないため・
    本 helper の冒頭で ``raw_history = raw_history.assign(available_at=pd.to_datetime(race_date))``
    を導出する（``speed_figure.py`` L698 と対称・target cutoff でない race_date 由来で固定）。
    実装者が「Step 5b 後の汚染 history から available_at を取る」脆弱な修正経路を構造的に閉じる。

    CYCLE-3 MEDIUM #3（cardinality 回避・pre-merge cutoff pre-filter）: 全 source race の synth_obs
    を1連結して ``compute_speed_figure_for_history`` を1回呼ぶと・``speed_figure.py`` L635 の
    ``out.merge(obs_keys, on='kettonum')`` が cutoff filter(L641) の前に「H の履歴行 × H を含む
    source race 数」の積を materialize し・馬平均50走 × ~1万頭で2500万行超に達する。本 helper は
    synth_obs を per-source-race batch（``SOURCE_RACE_BATCH_SIZE``）に分割し・各バッチ毎に
    ``compute_speed_figure_for_history`` を呼出すことで H² 積 materialize を回避する。バッチ化が
    値の不変性を損なわないことは obs_id が source×horse 毎に独立（CYCLE-3 MEDIUM #2）なことで
    構造的に保証される（par/variant groupby 先頭キー obs_id・``speed_figure.py`` L402/510）。

    Parameters
    ----------
    raw_history : pd.DataFrame
        Step 5b 前・obs_id 未展開の生 history。必須列: kettonum/race_nkey/race_date/time/trackcd/
        jyocd/kyori/as_of_datetime（speed_figure も available_at も存在しない・CYCLE-3 MEDIUM #1）。
    source_available_at_by_race : pd.Series
        各 source race（race_nkey）の available_at（= race_date・target cutoff でない）。index=race_nkey。

    Returns
    -------
    pd.DataFrame
        source_race × opponent_kettonum × opponent_history_row の展開フレーム。各 opponent 過去走行の
        speed_figure 値が source-as-of（当該 source race の available_at cutoff）で再計算されたもの。
        列: race_nkey (synth_obs 由来) / kettonum (opponent horse) / speed_figure / available_at
        (opponent の race_date 由来) / par_sec / variant_sec 等（compute_speed_figure_for_history 出力）。
        これが値の不変性を保証された唯一の ability 値ソース。
    """
    # CYCLE-3 MEDIUM #1: raw_history に available_at を race_date から導出（Step 5b 後汚染 history 非依存）
    raw_history = raw_history.assign(
        available_at=pd.to_datetime(raw_history["race_date"])
    )

    # source_available_at_by_race から・各 source race の starter 行（race_nkey/kettonum/available_at）
    # を構築。starters 情報は呼出側が既に D-04 filter 済みの source_races を渡す設計だが・
    # 本 helper は source_available_at_by_race の index(race_nkey) と raw_history の starters から再構築する。
    # raw_history の starters (kakuteijyuni > 0) で・かつ race_nkey が source_available_at_by_race に含まれる行。
    starter_mask = raw_history["kakuteijyuni"].fillna(0) > 0
    source_race_keys = set(source_available_at_by_race.index)
    starter_in_source = raw_history[starter_mask & raw_history["race_nkey"].isin(source_race_keys)]
    # source race × starter の代表行（race_nkey/kettonum/available_at）。重複排除（同一 race × horse 複数行防止）
    source_starters = (
        starter_in_source[["race_nkey", "kettonum", "available_at"]]
        .drop_duplicates(subset=["race_nkey", "kettonum"])
        .reset_index(drop=True)
    )

    if len(source_starters) == 0:
        # CR-01 (10-08 gap-closure): source_available_at_by_race が非空なのに starters が空は
        # 「source race は存在するが全 source race が starter 不存在（kakuteijyuni > 0 の行が無い）」
        # 状態・silent empty DataFrame 返却で後段に進むことを封印する（CYCLE-2 HIGH-C2-1 値レベル PIT 保証の
        # silent fallback 経路・core value「リーク防止」の鏡像「silent fallback 禁止」違反）。
        if len(source_available_at_by_race) > 0:
            raise RuntimeError(
                f"field_strength: source race {len(source_available_at_by_race)} 件中・"
                "全 source race が starter 不存在（kakuteijyuni > 0 の行が無い）・"
                "silent data loss を検知 (CR-01 fail-loud・CYCLE-2 HIGH-C2-1)"
            )
        # source_available_at_by_race も空の場合は正当な空入力・空 DataFrame を返す
        return pd.DataFrame(columns=["race_nkey", "kettonum", "speed_figure", "available_at"])

    # CYCLE-3 MEDIUM #3: per-source-race batch で compute_speed_figure_for_history を呼出し・H² 積 materialize を回避
    batches: list[pd.DataFrame] = []
    n_empty_batches = 0  # CR-01 (10-08): 空 バッチ（synth_obs 空 or compute 結果空）を追跡
    # race_nkey 毎にグループ化し・SOURCE_RACE_BATCH_SIZE 件の race_nkey を1バッチにまとめる
    unique_source_races = list(dict.fromkeys(source_starters["race_nkey"].tolist()))
    for batch_start in range(0, len(unique_source_races), SOURCE_RACE_BATCH_SIZE):
        batch_races = unique_source_races[batch_start : batch_start + SOURCE_RACE_BATCH_SIZE]
        batch_starters = source_starters[source_starters["race_nkey"].isin(batch_races)].copy()
        # source race の available_at は source_available_at_by_race（caller が渡した source-as-of cutoff）
        # から取る（raw_history の available_at(race_date 由来) でなく・adversarial test が leaky cutoff を
        # 注入できるように public API の source_available_at_by_race を唯一の cutoff 真の源にする）。
        batch_starters["available_at"] = batch_starters["race_nkey"].map(source_available_at_by_race)
        # 合成 observation 構築（obs_id='SOURCE_ASOF_<race_nkey>_<kettonum>'・horse-level par）
        synth_obs = _build_source_asof_observation(batch_starters)
        # raw_history に full par+variant+speed_figure pipeline を source-as-of cutoff で再実行
        # compute_speed_figure_for_history は observations 経路で obs_id 展開フレームを返す
        # （speed_figure.py L624-658・各 opponent 過去走が source race の available_at cutoff で
        # PIT filter 済み・par/variant/speed_figure が source-as-of で算出される）
        recomputed = compute_speed_figure_for_history(raw_history, observations=synth_obs)
        batches.append(recomputed)
        if len(recomputed) == 0:
            n_empty_batches += 1

    if not batches:
        # 全バッチループが回らずにここに来ることは上記 len(source_starters)==0 チェックで構造的に到達不能だが・
        # 防御的に fail-loud を置く（silent empty DataFrame 返却を封印・CR-01）。
        if len(source_available_at_by_race) > 0:
            raise RuntimeError(
                f"field_strength: batches が空・source race {len(source_available_at_by_race)} 件が"
                "全て starter 不存在の疑い (CR-01 fail-loud・CYCLE-2 HIGH-C2-1・到達不能経路)"
            )
        return pd.DataFrame(columns=["race_nkey", "kettonum", "speed_figure", "available_at"])

    # CR-01 (10-08 gap-closure): 空 バッチが混在する場合は silent な source race 欠落を可視化する。
    # pd.concat は空 DataFrame を無視して結合するため・batches に空が含まれると当該 source race が
    # 暗黙に欠落する（silent data loss）。non_empty_batches のみを結合対象にし・空 バッチ数を warning で記録。
    if n_empty_batches > 0:
        logger.warning(
            "field_strength: %d / %d バッチが空（source race starter 欠損の疑い・CR-01 silent data loss 可視化）",
            n_empty_batches, len(batches),
        )
    non_empty_batches = [b for b in batches if len(b) > 0]
    if not non_empty_batches:
        # 全バッチが空（source race は存在するが全 source race の opponent 過去走が PIT filter で全欠損等）。
        # silent empty DataFrame 返却でなく fail-loud で後段に進むことを封印する。
        raise RuntimeError(
            f"field_strength: source race {len(source_available_at_by_race)} 件・"
            f"{len(batches)} バッチ全てが空（opponent 過去走が全て欠損 or PIT filter で全除外）・"
            "silent data loss を検知 (CR-01 fail-loud・CYCLE-2 HIGH-C2-1)"
        )
    result = pd.concat(non_empty_batches, ignore_index=True)
    return result


def _opponent_ability_latest_mean5(
    source_asof_speed_figures: pd.DataFrame,
    source_available_at_by_race: pd.Series,
) -> pd.DataFrame:
    """CYCLE-2 HIGH-C2-1: full-pipeline 再計算済み speed_figure から opponent 毎 latest-K=5 mean を算出.

    入力 ``_compute_source_asof_opponent_speed_figures`` の出力（source-as-of 再計算済み speed_figure 値を持つ
    展開フレーム）と source race の available_at を受け取り・各 (source_race_nkey, opponent_kettonum) について・
    opponent 過去走のうち ``opponent.available_at < source_available_at``（strict ``<``・opponent-vs-source・D-01）
    を満たす行から最新 ``OPPONENT_ROLLING_K`` (=5) 件の speed_figure 平均を計算する。

    重要: 展開フレームの ``race_nkey`` 列は opponent 過去走の race_nkey（source race でない）。source race
    情報は ``obs_id`` 列（``SOURCE_ASOF_<source_race_nkey>_<opponent_kettonum>``）に含まれるため・
    本関数は obs_id から source_race_nkey を抽出して groupby キーに使う（``speed_figure.py`` の obs_id 展開
    idiom と対称・target 経路が obs_id で集約するのと同様に source-as-of 経路も obs_id で集約する）。

    vectorized 実装（rolling.py L375-383 idiom 転用・純粋 Python ループ禁止・Pitfall 2）:
    (source_race, opponent_kettonum, opponent_available_at) をキーに sort_values DESC + groupby.head(K)
    で最新5件を取得し mean。

    値レベル lookahead 排除の2層構造:
      - layer 1: speed_figure 値自体が source-as-of で再計算済み（_compute_source_asof_opponent_speed_figures）
      - layer 2: opponent_vs_source filter で source 以後の opponent レースを行レベルで除外（本関数）
    target cutoff はいずれの layer にも現れない。

    obs_id parse 契約（WR-01・10-08 gap-closure docstring 強化）:
        obs_id 形式は ``SOURCE_ASOF_<source_race_nkey>_<opponent_kettonum>``。本関数は ``stripped = obs_id.str[len("SOURCE_ASOF_"):]`` の後に ``rsplit("_", n=1)`` で最後の ``_`` を境界として ``parts[0]`` を
        ``source_race_nkey``・``parts[1]`` を ``opponent_kettonum`` として抽出する。

        (1) **本番 ``make_race_nkey`` 形式が契約**: ``src/features/builder.py`` の ``make_race_nkey`` が生成する
        race_nkey は ``YYYYJJJKKNN`` 形式（年/場/回/日/R 番号の零埋連結）で・**アンダースコア (``_``) を含まない**。
        従って ``rsplit("_", n=1)`` は ``<source_race_nkey>`` と ``<opponent_kettonum>`` の境界（最後の ``_``）
        を正しく分離できる。本番の ``make_race_nkey`` 契約（``_`` 含まない）が保たれる限り・本 parse は安全。

        (2) **``rsplit("_", n=1)`` の安全性根拠**: ``rsplit`` を右から1回だけ実行するため・source_race_nkey 側に
        ``_`` が含まれていても全部 parts[0] 側に残る。ただし ``make_race_nkey`` が ``_`` を含まない契約のため・
        本来的な運用では parts[0] は単一の race_nkey 文字列全体になる（L341 既存コメントで配慮済み）。

        (3) **``_`` 含み race_nkey 混入時の誤抽出リスク**: 万が一・本番 ``make_race_nkey`` が ``_`` を含む形式に
        変更された場合・``rsplit`` は最後の ``_`` で分割するため parts[0] が正しくない source_race_nkey になる
        （例: race_nkey='2024010_501' の場合 obs_id='SOURCE_ASOF_2024010_501_3' で parts[0]='2024010_501'・
        parts[1]='3' は正しいが・race_nkey='202401050_1' の場合は parts[0]='202401050'・parts[1]='1' で
        kettonum まで食われる）。これは ``make_race_nkey`` 契約違反時のリスク。

        (4) **契約違反を検知する adversarial テスト**: ``tests/features/test_field_strength.py`` に
        ``_`` 含み race_nkey 形式で parse が壊れるケースを意図的に起こして検知する adversarial テスト
        が存在する。``make_race_nkey`` の ``_`` 無し契約が保たれる限り稼働環境では発火しないが・契約が壊れた
        場合に本テストが RED で気付かせる。

        **本 plan の scope（helper 大規模書き直しは backlog 化）**: ``tests/features/test_field_strength.py`` の
        ``_fs_history_row`` helper は77箇所の呼出し（17テスト関数）で ``"R1_20230610"`` 形式（``_`` 含み）の
        race_nkey を使い続ける。本番 ``make_race_nkey`` が ``_`` 無し形式である限り実害は無いが・helper 全面書き直し
        （77箇所 + 17テスト assertion）は context budget 圧迫と CYCLE-2 adversarial テスト破壊リスクから backlog 化
        （10-08-SUMMARY.md deferred セクション参照）。本 docstring + adversarial テストで契約を機械保証する。

    Parameters
    ----------
    source_asof_speed_figures : pd.DataFrame
        ``_compute_source_asof_opponent_speed_figures`` の出力。各 opponent 過去走行が source-as-of
        再計算された speed_figure 値を持つ。``obs_id``（source race × opponent horse）/ ``kettonum``
        （opponent horse）/ ``speed_figure`` / ``available_at``（opponent の race_date 由来）列必須。
    source_available_at_by_race : pd.Series
        各 source race（race_nkey）の available_at。index=race_nkey。

    Returns
    -------
    pd.DataFrame
        列: race_nkey (source race) / kettonum (opponent horse) / _opp_rolling_ability
        (= 当該 source race 時点での opponent の rolling_speed_figure_mean_5・source as-of）。
        (race_nkey, kettonum) で一意。
    """
    if len(source_asof_speed_figures) == 0:
        return pd.DataFrame(
            columns=["race_nkey", "kettonum", "_opp_rolling_ability"]
        )

    sf = source_asof_speed_figures.copy()
    # source race_nkey を obs_id から抽出（obs_id = SOURCE_ASOF_<source_race_nkey>_<opponent_kettonum>）
    # source race 情報は race_nkey 列（opponent 過去走の race_nkey）でなく obs_id に含まれる
    obs_id_str = sf["obs_id"].astype(str)
    # SOURCE_ASOF_ を strip し・最後の _<kettonum> を分離 → 中間が source_race_nkey
    stripped = obs_id_str.str[len("SOURCE_ASOF_") :]
    # rsplit で最後の _ で分割（source_race_nkey に _ が含まれる場合に備え右から1つだけ分割）
    parts = stripped.str.rsplit("_", n=1, expand=True)
    sf["_source_race_nkey"] = parts[0].values
    # opponent_kettonum は parts[1] だが・kettonum 列が既に正しい（obs_id 展開で kettonum は opponent horse）

    # source race の available_at を lookup（_source_race_nkey で結合）
    sf["_source_available_at"] = sf["_source_race_nkey"].map(source_available_at_by_race)
    # opponent 過去走の available_at を _opp_available_at に alias（_pit_cutoff_prefilter 用）
    sf["_opp_available_at"] = sf["available_at"]
    # opponent-vs-source PIT filter（D-01 厳格版 strict <）・値レベル再計算の上に行レベル gate を重畳
    # source-as-of recompute は source race の available_at cutoff で行われるため・
    # ここでの filter は source race 以後の opponent レースを明示的に除外する defense-in-depth
    # _pit_cutoff_prefilter helper を経由させることで adversarial test が monkeypatch で guard を
    # 無効化（<= に差替）し same-day opponent 混入を検出できるようにする
    eligible = _pit_cutoff_prefilter(sf)
    if len(eligible) == 0:
        return pd.DataFrame(
            columns=["race_nkey", "kettonum", "_opp_rolling_ability"]
        )

    # sort_values DESC + groupby.head(K) で最新K件（rolling.py L375-383 idiom）
    # ソートキー: (source_race, opponent_kettonum, opponent_available_at DESC) で最新5件を取得
    eligible = eligible.sort_values(
        ["_source_race_nkey", "kettonum", "available_at"],
        ascending=[True, True, False],
        kind="mergesort",
    )
    recent_k = (
        eligible.groupby(["_source_race_nkey", "kettonum"], sort=False)
        .head(OPPONENT_ROLLING_K)
    )
    # 各 (source_race_nkey, kettonum) の speed_figure mean を算出（rolling_speed_figure_mean_5 相当）
    ability = (
        recent_k.groupby(["_source_race_nkey", "kettonum"], sort=False)["speed_figure"]
        .mean()
        .reset_index()
        .rename(
            columns={
                "_source_race_nkey": "race_nkey",
                "speed_figure": "_opp_rolling_ability",
            }
        )
    )
    return ability


def compute_field_strength_profile(
    raw_history: pd.DataFrame,
    observations: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """D-06 第1段階: raw_history 全行に source race 内 opponent profile（8値）を付与.

    PIT 保証（D-01 厳格版 as-of・2層 gate）:
      - layer 1 (値レベル・CYCLE-2 HIGH-C2-1): 相手 ability 値は入力 history の obs_id 展開済み
        target-cutoff-contaminated speed_figure を一切再利用せず・raw history に obs_id='SOURCE_ASOF_
        <race_nkey>_<kettonum>'・feature_cutoff_datetime=source_race.available_at の合成 observation で
        ``compute_speed_figure_for_history`` を再実行することで full par+variant+speed_figure pipeline を
        source-as-of で再計算する。同じ pre-source opponent race がどの target observation に消費されても
        同一 speed_figure（値の不変性）が達成される。
      - layer 2 (行レベル・opponent-vs-source): ``_pit_cutoff_prefilter`` で
        ``opponent.available_at < source_race.available_at`` (strict ``<``) を満たす opponent 過去走のみで
        算出。source race 当日結果は混入しない。

    Parameters
    ----------
    raw_history : pd.DataFrame
        Step 5b 前・obs_id 未展開の生 history。必須列: kakuteijyuni/race_nkey/kettonum/race_date/time/
        trackcd/jyocd/kyori/as_of_datetime。**CYCLE-2 HIGH-C2-1**: speed_figure は必須でない（target cutoff
        で展開された汚染値でなく本関数が raw history に full-pipeline を source-as-of で再実行して算出）。
        **CYCLE-3 MEDIUM #1**: available_at も必須でない（Step 5b 前 raw_history には存在せず本関数が
        ``pd.to_datetime(race_date)`` で導出）。
    observations : pd.DataFrame, optional
        後方互換用（現在は未使用）。PLAN 01 は raw_history から全てを再計算するため・target
        observation の feature_cutoff_datetime には依存しない（CYCLE-2 HIGH-C2-1 値の不変性）。

    Returns
    -------
    pd.DataFrame
        raw_history の copy に 8 列（field_strength_mean/median/top3_mean/top5_mean/max/sd/
        valid_count/coverage）を追加した DataFrame。該当なし行は NaN（copy-not-rename・HIGH#5）。

    Raises
    ------
    ValueError
        必須列が欠損している場合（fail-loud・CYCLE-3 MEDIUM #1・10-REVIEWS.md L221）。
    RuntimeError
        raw_history が空の場合（fail-loud・WR-01 踏襲）。
    """
    # --- Step 1: 必須列検証 + 空 raw_history fail-loud ---
    # CYCLE-3 MEDIUM #1: speed_figure / available_at は必須列に含めない（raw_history には存在しない・
    # 実装者が「Step 5b 後の汚染 history から取る」脆弱な修正経路を開かないように）。
    required_cols = (
        "kakuteijyuni",
        "race_nkey",
        "kettonum",
        "race_date",
        "time",
        "trackcd",
        "jyocd",
        "kyori",
        "as_of_datetime",
    )
    missing = [c for c in required_cols if c not in raw_history.columns]
    if missing:
        raise ValueError(
            f"raw_history に必須列が欠損: {missing} (field_strength 構築・CYCLE-3 MEDIUM #1 fail-loud)"
        )
    if len(raw_history) == 0:
        raise RuntimeError(
            "field_strength: raw_history が空・silent data loss を検知 (WR-01 fail-loud)"
        )

    # --- Step 2: CYCLE-3 MEDIUM #1・available_at を race_date から導出 ---
    # raw_history の copy を取り・race_date から available_at を導出（speed_figure.py L698 と対称・
    # race_date 由来で固定・Step 5b 後汚染 history への依存経路を閉じる）。
    raw_history = raw_history.assign(
        available_at=pd.to_datetime(raw_history["race_date"])
    )

    # --- Step 3: copy-not-rename（HIGH#5）・出力フレーム準備 ---
    out = raw_history.copy()

    # --- Step 4: D-04 発走馬特定（kakuteijyuni > 0・live-DB 実証・拡張中止コード不使用） ---
    # EveryDB2 独自拡張の中止コードフィールドは意味不明（1/2=完走馬大多数・3=競走中止・4=失格）・使わない。
    # kakuteijyuni > 0 で starter を特定（未発走 kakuteijyuni=0 は除外・競走中止馬 kakuteijyuni=11-16 は含む）。
    starters_mask = raw_history["kakuteijyuni"].fillna(0) > 0
    starters = raw_history[starters_mask].copy()
    if len(starters) == 0:
        # starter がいない→全行 NaN で 8 列を追加して返す（silent fill でなく明示的 NaN）
        for col in (
            "field_strength_mean",
            "field_strength_median",
            "field_strength_top3_mean",
            "field_strength_top5_mean",
            "field_strength_max",
            "field_strength_sd",
            "field_strength_valid_count",
            "field_strength_coverage",
        ):
            out[col] = pd.Series([float("nan")] * len(out), index=out.index)
        return out

    # source race の代表行（race×horse 単位・CYCLE-3 MEDIUM #2）・available_at は race_date 由来導出列
    source_races = starters[["race_nkey", "kettonum", "available_at"]].drop_duplicates(
        subset=["race_nkey", "kettonum"]
    )
    # race_size（coverage 計算用）: starters の race_nkey group size
    race_size = starters.groupby("race_nkey", sort=False).size().to_dict()

    # --- Step 5: CYCLE-2 HIGH-C2-1 pipeline 実行 ---
    # (a) source_available_at_by_race = 各 source race の available_at（race 内で一意・race_date 由来）
    source_available_at_by_race = source_races.groupby("race_nkey", sort=False)[
        "available_at"
    ].first()

    # CR-01 (10-08 gap-closure): starters 存在 source race 数 vs source_available_at_by_race 件数の
    # fail-loud 検査。source_available_at_by_race は source_races の groupby 由来なので理論上は一致するが・
    # drop_duplicates / groupby の境界で silent data quality 低下（一部 source race の starters が欠落し
    # profile が過小評価される）を検知する（core value「リーク防止」の鏡像「silent fallback 禁止」）。
    n_source_races_from_starters = int(source_races["race_nkey"].nunique())
    n_source_races_in_cutoff = int(len(source_available_at_by_race))
    if n_source_races_from_starters != n_source_races_in_cutoff:
        raise RuntimeError(
            f"field_strength: starters 存在 source race 数 ({n_source_races_from_starters}) と "
            f"source_available_at_by_race 件数 ({n_source_races_in_cutoff}) が不一致・"
            "silent data quality 低下の疑い (CR-01 fail-loud・CYCLE-2 HIGH-C2-1)"
        )

    # (b) source-as-of full-pipeline 再計算・全 source race について source-as-of 再計算済み opponent
    #     speed_figure 値を一括取得（obs_id='SOURCE_ASOF_<race_nkey>_<kettonum>'・
    #     CYCLE-3 MEDIUM #3 per-source-race バッチ化で H² 積 materialize 回避）
    source_asof_sf = _compute_source_asof_opponent_speed_figures(
        raw_history=raw_history,
        source_available_at_by_race=source_available_at_by_race,
    )

    # (c) opponent_ability (source_race_nkey, opponent_kettonum) → rolling_speed_figure_mean_5・source as-of
    opponent_ability = _opponent_ability_latest_mean5(
        source_asof_sf, source_available_at_by_race
    )

    # --- Step 6: per-source-race batch + vectorized groupby（Pitfall 2 計算量爆発回避） ---
    # starter × starter join で「同じ source race の他の starter（opponent）」を展開・self（kettonum 同一）は除外。
    # opponent は各 source race 内の starters のみ（D-04）。
    if len(opponent_ability) == 0:
        # opponent ability が空（全 opponent に過去走なし等）→ 全行 NaN で返す
        for col in (
            "field_strength_mean",
            "field_strength_median",
            "field_strength_top3_mean",
            "field_strength_top5_mean",
            "field_strength_max",
            "field_strength_sd",
            "field_strength_valid_count",
            "field_strength_coverage",
        ):
            out[col] = pd.Series([float("nan")] * len(out), index=out.index)
        return out

    # starter × opponent_ability を race_nkey で結合（self 除外は後で mask）
    # starter 側: source_races (race_nkey, kettonum, available_at)
    # opponent 側: opponent_ability (race_nkey, kettonum, _opp_rolling_ability)
    expanded = source_races.merge(
        opponent_ability,
        on="race_nkey",
        suffixes=("", "_opp"),
        how="inner",
    )
    # 列名整理: source 側の kettonum/available_at と opponent 側の kettonum/available_at を区別
    if "kettonum_opp" in expanded.columns:
        expanded = expanded.rename(
            columns={
                "kettonum_opp": "_opp_kettonum",
            }
        )
    else:
        # merge 結果の列名確認（suffixes 指定で kettonum_opp になるはず）
        expanded["_opp_kettonum"] = expanded["kettonum_opp"] if "kettonum_opp" in expanded.columns else expanded["kettonum"]

    # self（source race の starter）と opponent を区別するため・
    # _opp_kettonum と kettonum（source starter）が異なる行のみを残す
    # opponent-vs-source PIT filter（D-01 厳格版 strict <）は _opponent_ability_latest_mean5 内で
    # _pit_cutoff_prefilter helper を経由して適用済み（adversarial test が monkeypatch で guard を無効化可能）。
    expanded = expanded[expanded["kettonum"] != expanded["_opp_kettonum"]].copy()

    if len(expanded) == 0:
        for col in (
            "field_strength_mean",
            "field_strength_median",
            "field_strength_top3_mean",
            "field_strength_top5_mean",
            "field_strength_max",
            "field_strength_sd",
            "field_strength_valid_count",
            "field_strength_coverage",
        ):
            out[col] = pd.Series([float("nan")] * len(out), index=out.index)
        return out

    # --- Step 7: D-03 profile 8値 vectorized 集約 ---
    # rolling.py L316-324 groupby.agg idiom と対称・6.7M ペアを秒単位処理。
    # 各 source starter (race_nkey, kettonum) 毎に・opponent の _opp_rolling_ability を集約。
    profile = (
        expanded.groupby(["race_nkey", "kettonum"], sort=False, dropna=False)[
            "_opp_rolling_ability"
        ]
        .agg(
            field_strength_mean="mean",
            field_strength_median="median",
            field_strength_top3_mean=lambda s: _topk_mean_clamped(s, 3),
            field_strength_top5_mean=lambda s: _topk_mean_clamped(s, 5),
            field_strength_max="max",
            field_strength_sd="std",
            field_strength_valid_count="count",
        )
        .reset_index()
    )
    # coverage = valid_count / race_size[race_nkey]（D-05 信頼度軸）
    profile["field_strength_coverage"] = profile.apply(
        lambda row: (
            float(row["field_strength_valid_count"]) / float(race_size[row["race_nkey"]])
            if row["race_nkey"] in race_size and race_size[row["race_nkey"]] > 0
            else float("nan")
        ),
        axis=1,
    )

    # --- Step 8: out に profile 8 列を merge（copy-not-rename・該当なし行は NaN） ---
    # out の race_nkey/kettonum で profile を left join・該当なし行は NaN
    profile_cols = [
        "field_strength_mean",
        "field_strength_median",
        "field_strength_top3_mean",
        "field_strength_top5_mean",
        "field_strength_max",
        "field_strength_sd",
        "field_strength_valid_count",
        "field_strength_coverage",
    ]
    # profile 側の race_nkey/kettonum は starter (kakuteijyuni > 0) のみ・
    # out 側は全行（未発走馬も含む）・未発走馬や profile 該当なし行は NaN になる
    out = out.merge(
        profile[["race_nkey", "kettonum"] + profile_cols],
        on=["race_nkey", "kettonum"],
        how="left",
    )

    # --- Step 9: 決定論的順序（§19.1 byte-reproducible） ---
    # 入力 raw_history の行順序を維持（copy-not-rename・merge の左側 out の順序を保持）
    # profile 側の groupby は sort=False・dropna=False で決定論的・merge も how='left' で左側順序保存。
    return out


__all__ = ["compute_field_strength_profile"]
