# 競馬予測AI 要件定義書

版数: v1.3  
作成日: 2026-06-16  
対象: JRA競馬向け 複勝払戻対象確率・期待値判定AI  
ステータス: Phase 1実装着手可のレビュー版。レビュー段階ではMarkdownのみ作成し、Word版は要件確定時に作成する。

本書は、M2 Pro MacBook、Parallels Desktop上のWindows VM、EveryDB2、Mac側PostgreSQLを前提とした競馬予測AIの要件を定義する。v1.3では、v1.2レビューで実装前の微修正として推奨された **sales_start_entry_countの取得・復元方針、払戻テーブル優先ラベル、返還時effective_stake、同着処理、市場ベースライン解釈、sum(p)分布チェック** を追記した。

---

## 改訂履歴

| 版数 | 日付 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-06-16 | 初版。ヒアリング結果を統合し、詳細版の要件定義書として作成。 |
| v1.1 | 2026-06-16 | レビュー反映版。複勝ラベル、予測タイミング、EV計算、取消・競走中止、race_id単位バックテスト、2015年開始データのウォームアップ、クラス正規化、カテゴリ・欠損仕様を追加。 |
| v1.2 | 2026-06-16 | 再レビュー反映版。発売開始時点基準の複勝ラベル、払戻テーブル突合、オッズ時点固定、仮想購入ルール、as-of特徴量管理、推奨ランク初期式、Calibration受入基準、ベースラインモデルを追加。レビュー段階ではMarkdownのみ出力する方針に変更。 |
| v1.3 | 2026-06-16 | v1.2追加レビュー反映版。sales_start_entry_count取得・復元方針、払戻テーブル優先ラベル、同着処理、返還時effective_stake、市場ベースライン解釈、sum(p)分布チェックを追記。Phase 1実装着手可のレビュー版。 |

---

## 目次

- 1. プロジェクト概要
- 2. 背景・設計思想
- 3. 前提条件とスコープ
- 4. v1.3での重要改訂点
- 5. システム構成
- 6. データ要件
- 7. 初期モデル対象レース
- 8. 予測対象・馬券種・Phase定義
- 9. 予測タイミング・利用可能データ
- 10. 複勝ラベル生成・検証仕様
- 11. EV計算・オッズ時点・仮想購入仕様
- 12. DB・ETL・分析エンジン方針
- 13. 特徴量生成・as-of管理
- 14. モデル設計・ベースライン・カテゴリ仕様
- 15. 評価指標・バックテスト要件
- 16. 画面・CSV出力要件
- 17. 開発環境・プロジェクト構成
- 18. Phase構成・ロードマップ
- 19. 非機能要件
- 20. リスクと対策
- 21. 未確定事項・将来検討事項
- 22. 参考情報

---

# 1. プロジェクト概要

## 1.1 目的

本プロジェクトの目的は、JRA競馬データを用いて、各出走馬の **複勝払戻対象確率** を推定し、取得時点の市場オッズと比較することで、複勝期待値が高い馬を抽出する競馬予測AIを構築することである。

内部的な主要予測値は `p_fukusho_hit` とする。これは単純な「3着以内確率」ではなく、JRAの複勝発売・払戻ルールに基づく **複勝払戻対象になる確率** と定義する。

本システムは、穴馬の1着予測を主目的としない。主目的は、過小評価されている馬の複勝払戻対象入り可能性を検出し、複勝・ワイド・将来的な三連複へ段階的に拡張できる基盤を作ることである。

## 1.2 Phase 1のゴール

Phase 1では、実馬券購入ではなく、以下の実装検証をゴールとする。

- 更新済みEveryDB2由来データの品質確認
- normalized層の初期ETL
- 出馬表・馬番・枠番確定後の複勝基礎モデル
- `p_fukusho_hit` の算出
- オッズ取得後の `EV_lower` / `EV_upper` 算出
- 固定ルールによる仮想購入バックテスト
- Streamlit最小画面
- CSV出力
- race_id単位・時系列順のバックテスト

## 1.3 成功基準

Phase 1では、以下を満たすことを成功基準とする。

1. 複勝ラベルが発売開始時点の複勝払戻対象数および払戻テーブルと整合していること。
2. 出馬表・馬番・枠番確定後に利用可能なデータのみで `p_fukusho_hit` を算出できること。
3. オッズ取得時点を固定してEVおよび推奨ランクを再現できること。
4. 仮想購入ルールが明文化され、回収率・損益・最大ドローダウンが再現可能であること。
5. バックテストにおいて、同一 `race_id` がtrain/testにまたがらないこと。
6. モデル出力確率がベースラインを上回る、または改善余地を定量評価できること。

---

# 2. 背景・設計思想

## 2.1 日本競馬向けに限定する理由

本システムはJRA競馬向けに設計する。海外競馬は開催体系、馬券種、オッズ形成、控除率、データ構造、馬場・クラス体系が異なるため、Phase 1では対象外とする。

海外研究や一般的な機械学習手法は、確率校正、時系列検証、カテゴリ特徴量処理、リーク防止など、日本競馬にも転用可能なものに限って採用する。

## 2.2 予測思想

本システムは「的中しそうな馬」を単純に選ぶのではなく、以下の構造を採用する。

```text
AI推定確率 p_fukusho_hit
  ×
取得時点の複勝オッズ
  ↓
EV_lower / EV_upper
  ↓
固定ルールによる推奨判定・仮想購入検証
```

Phase 1では、モデル本体に当日オッズを特徴量として入れない。オッズは、推定確率との比較によるEV計算にのみ使用する。

## 2.3 設計上の基本方針

- まず複勝払戻対象確率を正しく推定する。
- ワイド・三連複はPhase 2以降へ回す。
- 能力予測とEV計算を分離する。
- 予測時点ごとに利用可能データを分離する。
- オッズ時点を固定し、後知恵選択を禁止する。
- バックテストはrace_id単位かつ時系列順で行う。
- データベースや分析エンジンは過度に複雑化しない。
- 実馬券購入・自動投票はスコープ外とする。

---

# 3. 前提条件とスコープ

## 3.1 プロジェクト開始前に完了している前提

以下はプロジェクト開始前にユーザー側で完了している前提とする。

- Parallels Desktop / Windows VM構築
- EveryDB2セットアップ
- JRA-VAN Data Lab.利用環境の準備
- Mac側PostgreSQLのHomebrewインストール
- EveryDB2からMac側PostgreSQLへの接続設定
- EveryDB2によるMac側PostgreSQL上へのテーブル作成
- EveryDB2による2015年1月1日以降のデータ更新実行

## 3.2 スコープ内

本プロジェクトのPhase 1スコープは以下とする。

- 更新済みPostgreSQLデータの確認
- rawデータ品質チェック
- Pythonプロジェクト構築
- normalized層の初期ETL
- 複勝ラベル生成・払戻テーブル突合
- `p_fukusho_hit` モデル用データセット作成
- 出馬表・馬番・枠番確定後モデル
- 複勝EV計算
- 推奨ランク算出
- 初回バックテスト
- Streamlit最小画面
- CSV出力
- 要件定義書作成・更新

## 3.3 スコープ外

以下はスコープ外とする。

- EveryDB2セットアップ
- Parallels Desktop / Windows VM構築
- Mac側PostgreSQLインストール
- EveryDB2からMac側PostgreSQLへの接続設定
- EveryDB2によるテーブル作成
- EveryDB2更新実行
- JRA-VAN Data Lab.契約・設定
- 実馬券購入
- 自動投票
- 自動購入ツール連携
- Phase 1でのワイド・三連複モデル実装

---

# 4. v1.3での重要改訂点

v1.3では、v1.2の実装前レビューに基づき、Phase 1実装時にブレやすい以下の仕様を追記した。

| 項目 | v1.2での対応 |
| --- | --- |
| 複勝ラベル | 最終出走頭数ではなく、発売開始時点の複勝払戻対象数と払戻テーブル突合を基準にする。 |
| 払戻テーブル突合 | 着順由来の一次ラベルと払戻テーブル由来の確定ラベルを分離する。 |
| オッズ時点 | バックテスト意思決定オッズを固定し、後から有利なオッズ時点を選ぶことを禁止する。 |
| 仮想購入ルール | 1点100円、EV条件、最低確率、最低オッズ、同一レース最大点数を明文化する。 |
| as-of管理 | `as_of_datetime`、`feature_cutoff_datetime`、`feature_availability` を導入する。 |
| Phase 1-A時点 | 曜日固定ではなく、出馬表・馬番・枠番などのデータ状態で実行条件を定義する。 |
| クラス正規化 | 文字列ではなく、競走条件コード基準で正規化する。 |
| 推奨ランク | Phase 1では未定義の予測信頼度を使わず、EV・確率・オッズ下限のみで初期ランクを定義する。 |
| Calibration | 受入基準とベースラインを追加する。 |
| Word出力 | レビュー段階ではMarkdownのみ。Word版は確定時に作成する。 |
| sales_start_entry_count | 直接項目があれば使用し、なければ出馬表と取消・競走除外発表時刻から復元し、復元不能なら未解決として学習・評価から除外する。 |
| validated label | `fukusho_hit_validated` は原則として払戻テーブル上の複勝払戻対象馬を正例とし、着順・頭数は補助情報として扱う。 |
| 返還処理 | 返還時の `effective_stake`、`refund_amount`、`payout_amount` を定義し、回収率計算の再現性を高める。 |
| 同着処理 | 同着時は払戻テーブルに存在するすべての複勝対象馬を正例にする。 |
| 市場ベースライン | 複勝オッズ逆数ベースラインは市場参考値であり、Phase 1-Aモデルとの同一情報条件比較ではないと明記する。 |
| sum(p)検査 | 平均だけでなく、中央値、標準偏差、p10、p90を確認する。 |

---

# 5. システム構成

## 5.1 全体構成

```text
Windows VM / Parallels Desktop
  └─ EveryDB2
      └─ Mac側PostgreSQLへ直接保存

Mac側
  ├─ PostgreSQL
  │   ├─ EveryDB2由来原本テーブル
  │   ├─ normalized
  │   ├─ prediction
  │   └─ backtest
  │
  ├─ Python
  │   ├─ ETL
  │   ├─ ラベル生成・払戻突合
  │   ├─ 特徴量生成
  │   ├─ モデル学習
  │   ├─ 予測実行
  │   └─ バックテスト
  │
  ├─ DuckDB
  │   └─ 必要時のみ、大量集計・Parquet分析に使用
  │
  ├─ Parquet
  │   ├─ 学習用データセット
  │   ├─ 検証用データセット
  │   └─ feature snapshot
  │
  └─ Streamlit
      └─ レース一覧、複勝確率、EV、推奨ランク表示
```

## 5.2 役割分担

| 要素 | 役割 |
| --- | --- |
| EveryDB2 | JRA-VAN Data Lab.データの取得・Mac側PostgreSQLへの保存。プロジェクト開始前に更新済み前提。 |
| PostgreSQL | 主DB。原本データ、正規化データ、予測結果、バックテスト結果を保存する。 |
| DuckDB | 常時運用DBではなく、大量集計やParquet参照が必要な場合のみ使用する分析エンジン。 |
| Parquet | 学習・検証・再現用スナップショット。 |
| Python | ETL、特徴量生成、モデル学習、予測、評価、バックテスト。 |
| Streamlit | ローカルWeb画面。 |

---

# 6. データ要件

## 6.1 データ取得期間

初期構築フェーズでは、EveryDB2によるデータ取得範囲を **2015年1月1日から現在まで** とする。

2015年1月1日以降のJRAデータは、初期フェーズにおいて全件保存対象とする。取得可能な全期間を無制限に取り込むことは初期スコープには含めない。

## 6.2 2015年開始データのウォームアップ

2015年1月1日開始データでは、2015年初期に出走する馬の過去走履歴が左側打ち切りになる。

したがって、以下の方針を採用する。

```text
データ保存対象:
  2015-01-01以降すべて

初期の学習・評価対象:
  2016年後半以降を主対象とする

2015年〜2016年前半:
  feature warm-up期間として扱う
```

ウォームアップ期間は、過去走特徴量、騎手・調教師・コース実績、馬場適性などの履歴集計を安定させるために使用する。

## 6.3 学習期間候補

保存データは2015年以降全件とするが、モデル学習では全期間を常に一律利用しない。以下の候補を比較する。

- 直近3年
- 直近5年
- 直近7年
- 直近10年
- 2019年夏季競馬以降
- 2016年後半以降全期間

## 6.4 品質チェック要件

EveryDB2更新済みデータに対して、初回に以下を確認する。

- 主要テーブルの存在
- 主要テーブル件数
- 取得データの日付範囲
- 2015年1月1日以降のデータが存在すること
- 主要項目のNULL
- 主キーまたは自然キーの重複
- 文字化け
- コード値の異常
- レース、出走馬、成績、払戻、オッズ等の主要データが取得されていること

---

# 7. 初期モデル対象レース

## 7.1 データ保存対象

以下はすべて保存対象とする。

- JRA平地競走
- JRA障害競走
- 新馬戦
- 未勝利戦
- 2歳戦
- 3歳戦
- 古馬戦
- オープン・リステッド・重賞
- 全人気帯の出走馬

## 7.2 初期モデル対象

初期モデルでは以下を対象とする。

- JRA平地競走
- 新馬戦を除くレース
- 2歳未勝利以上
- 3歳未勝利以上
- 1勝クラス以上
- オープン・リステッド・重賞
- 全人気帯
- 複勝発売対象レース

## 7.3 初期モデル除外対象

以下はデータ保存のみ行い、Phase 1モデルでは除外する。

- 障害競走
- 新馬戦
- 複勝発売なしのレース
- ラベル生成・払戻突合に失敗したレースまたは馬

## 7.4 人気帯の扱い

学習対象は全人気帯とする。穴馬だけを学習対象に絞ることはしない。

ただし、予測結果の表示や推奨候補抽出では、EVが高い馬、中穴・穴馬候補を重点的に表示する。

---

# 8. 予測対象・馬券種・Phase定義

## 8.1 主軸馬券

初期主軸は複勝とする。ワイドはPhase 2、三連複はPhase 3以降で扱う。

| Phase | 対象 | 内容 |
| --- | --- | --- |
| Phase 1 | 複勝 | `p_fukusho_hit`、EV、推奨ランク、バックテスト |
| Phase 2 | 複勝拡張・ワイド | 馬体重発表後モデル、ワイド候補、ワイドEV |
| Phase 3 | 発走直前・三連複 | 時系列オッズ、発走直前モデル、三連複候補 |

## 8.2 Phase 1-A: 出馬表・馬番・枠番確定後 複勝基礎モデル

目的は、オッズ非依存で各馬の複勝払戻対象確率 `p_fukusho_hit` を推定することである。

### 実行条件

曜日固定ではなく、以下のデータ状態で定義する。

- 出走馬が確定している
- 馬番が確定している
- 枠番が確定している
- 騎手・斤量が取得済み
- コース、距離、芝/ダート、クラス条件が取得済み
- 当日馬場・当日天候・馬体重・当日オッズは未使用

### 出力

- `race_id`
- `horse_id`
- `p_fukusho_hit`
- `prediction_version`
- `feature_snapshot_id`
- `as_of_datetime`
- `model_version`

## 8.3 Phase 1-B: オッズ取得後 EV計算

目的は、Phase 1-Aの確率に、取得時点の複勝オッズを掛けてEVを算出することである。

入力は以下とする。

- `p_fukusho_hit`
- 複勝オッズ下限
- 複勝オッズ上限
- オッズ取得時刻
- odds snapshot policy

出力は以下とする。

- `EV_lower`
- `EV_upper`
- 推奨ランク
- `odds_snapshot_at`
- `odds_snapshot_policy`

## 8.4 Phase 1-C: バックテスト

目的は、実際の払戻金に基づき、固定ルールの仮想購入成績を検証することである。

分割は `race_id` 単位かつ `race_date` / `race_start_datetime` 時系列順とする。同一 `race_id` がtrain/testにまたがることは禁止する。

---

# 9. 予測タイミング・利用可能データ

## 9.1 モデルを分ける理由

競馬データは、予測時点によって利用可能な情報が大きく変わる。出馬表・馬番・枠番確定後、開催日朝、馬体重発表後、発走直前では、使用可能なデータが異なる。

同一モデルに全情報を入れると、バックテストで未来情報リークが起こりやすい。したがって、モデルを予測タイミング別に分ける。

## 9.2 予測タイミング別モデル

| モデル | 実行条件 | 使ってよい情報 | Phase |
| --- | --- | --- | --- |
| A. 出馬表・馬番・枠番確定後モデル | 出走馬、馬番、枠番、騎手、斤量が取得済み | 出走馬、馬番、枠番、過去走、騎手、調教師、血統、コース条件 | Phase 1 |
| B. 開催日朝モデル | 当日朝の馬場・天候取得後 | A + 当日朝時点の天候・馬場状態 | Phase 2以降 |
| C. 馬体重発表後モデル | 発走約60分前以降 | B + 馬体重・馬体重増減 | Phase 2 |
| D. 発走直前モデル | 発走前の指定オッズ時点 | C + 時系列オッズ・票数変化 | Phase 3 |

## 9.3 Phase 1で使用しない情報

Phase 1-Aでは以下を使用しない。

- 当日馬場状態
- 当日天候
- 馬体重
- 馬体重増減
- 当日オッズ
- 人気集中度
- オッズ依存の荒れ指数
- 確定払戻
- 確定着順
- レース後通過順
- レース後上がり
- レース後走破タイム
- 当日レース結果由来の騎手・馬場・コース集計

---

# 10. 複勝ラベル生成・検証仕様

## 10.1 基本定義

目的変数は `fukusho_hit` とする。モデル出力は `p_fukusho_hit` とする。

`fukusho_hit` は、複勝払戻対象になった場合に1、ならなかった場合に0とする。

## 10.2 発売開始時点基準

v1.3では、複勝ラベルを最終出走頭数だけで決めない。原則として、**発売開始時点の複勝発売条件・払戻対象数** に基づいて生成する。

保持項目は以下とする。

```text
- race_id
- horse_id
- sales_start_entry_count
- final_starter_count
- fukusho_payout_places
- is_fukusho_sale_available
- fukusho_hit_raw
- fukusho_hit_validated
- label_validation_status
```

`fukusho_payout_places` は以下を基本とする。

```text
発売開始時点で8頭以上:
  3

発売開始時点で5〜7頭:
  2

発売開始時点で4頭以下:
  複勝発売なし
```

ただし、実データ上はJRA-VANの払戻・発売情報を優先する。発売開始後の取消・競走除外により最終出走頭数が変化した場合でも、最終出走頭数だけで複勝払戻対象数を確定してはならない。

## 10.3 `sales_start_entry_count` の取得・復元方針

`sales_start_entry_count` は、複勝発売条件と払戻対象数を判定するための重要項目である。取得・復元方針は以下とする。

```text
1. JRA-VAN / EveryDB2上に発売開始時点出走予定頭数を直接示す項目がある場合は、それを使用する。
2. 直接項目がない場合は、出馬表確定時点の出走予定馬一覧と、出走取消・競走除外の発表時刻を用いて復元する。
3. 復元不能な場合は label_validation_status = unresolved とし、Phase 1の学習・評価対象から除外する。
```

復元ロジックは、後続のラベル生成とバックテストに影響するため、実装時に `label_generation_version` としてバージョン管理する。

## 10.4 ラベル生成の優先順位

ラベル生成では以下の優先順位を採用する。

1. JRA-VANの払戻・発売情報
2. 発売開始時点の出走予定頭数
3. 確定成績の着順
4. 最終出走頭数

着順由来のラベルを一次ラベル `fukusho_hit_raw` とし、払戻テーブルとの突合後のラベルを `fukusho_hit_validated` とする。

`fukusho_hit_validated` は、原則として払戻テーブル上の複勝払戻対象馬を1とする。払戻テーブルが欠損または不整合の場合のみ、発売開始時点出走頭数・確定着順から補助的に復元する。補助的に復元したラベルは `label_validation_status = inferred` とし、払戻テーブル突合済みの通常ラベルとは区別する。

Phase 1の学習・評価では、原則として `fukusho_hit_validated` を使用する。ただし、`label_validation_status = unresolved` のレースまたは出走馬は、Phase 1の学習・評価対象から除外する。

## 10.5 払戻テーブル突合

ラベル生成後、以下の検査を行う。

- `fukusho_hit = 1` の馬が払戻テーブルに存在するか
- 払戻テーブルに存在する複勝対象馬が `fukusho_hit = 1` になっているか
- 同着レースで払戻対象馬数が想定より増えた場合に破綻しないか
- 取消・競走除外馬が誤って `fukusho_hit = 1` になっていないか
- 競走中止馬が誤って除外されていないか
- 複勝発売なしレースが学習・評価対象に混入していないか

同着時は、払戻テーブルに存在するすべての複勝対象馬を `fukusho_hit_validated = 1` とする。`fukusho_payout_places` の理論値より対象馬数が多い場合でも、払戻テーブルを優先し、`label_validation_status` に `dead_heat` を付与する。

検査結果は `label_validation_status` として保存する。

## 10.6 取消・競走除外・競走中止の扱い

| 区分 | 学習 | バックテスト | 扱い |
| --- | --- | --- | --- |
| 出走取消 | 予測対象外 | 仮想購入済みなら返還 | 発走前に出走しないため |
| 競走除外 | 予測対象外 | 仮想購入済みなら返還 | 発走前または発走時除外として返還対象 |
| 競走中止 | 原則含める | 不的中 | 発走後の出来事で返還対象外 |

競走中止を除外すると、実運用で発生する負けをバックテストから消すことになり、回収率が過大評価されるため禁止する。

---

# 11. EV計算・オッズ時点・仮想購入仕様

## 11.1 複勝EV計算

Phase 1では、複勝オッズの下限・上限を用いて以下を計算する。

```text
EV_lower = p_fukusho_hit × fukusho_odds_lower
EV_upper = p_fukusho_hit × fukusho_odds_upper
```

推奨判定は保守的に `EV_lower` を主基準とする。

## 11.2 バックテスト意思決定オッズ

バックテストでは、購入判断に使用するオッズ時点を検証条件として固定する。

保持項目は以下とする。

```text
- odds_snapshot_policy
- odds_snapshot_at
- odds_source_type
- odds_missing_reason
```

初期検証では以下を比較する。

- 発走30分前固定
- 発走10分前固定

候補として以下を将来比較対象にできる。

- 前日発売終了時点
- 当日朝9:30時点
- 発走60分前
- 発走30分前
- 発走10分前
- 発走5分前
- 発売締切直前

以下は禁止する。

- レース後に最も回収率が高かったオッズ時点を選ぶこと
- 最終オッズを意思決定オッズとして無条件に使うこと
- 欠損時だけ都合の良い別時点のオッズに差し替えること
- 検証後にオッズ時点を恣意的に変更すること

## 11.3 オッズ欠損時の扱い

指定した `odds_snapshot_policy` においてオッズが欠損した場合は、以下のいずれかを事前定義する。

Phase 1の初期方針は **欠損時は購入対象外** とする。

```text
odds_missing_policy:
  - no_bet: 購入対象外
  - nearest_previous: 指定時点以前の直近スナップショットを使用
  - nearest_after: 使用禁止。未来情報になる可能性が高いためPhase 1では不可
```

## 11.4 仮想購入ルール

Phase 1初期バックテストでは、以下の固定購入ルールを採用する。

```text
backtest_strategy_version:
  fukusho_ev_v1

購入単位:
  1候補100円

対象馬券:
  複勝のみ

購入条件:
  EV_lower >= 1.05
  p_fukusho_hit >= 0.15
  fukusho_odds_lower >= 1.5

同一レース制約:
  EV_lower上位2頭まで

同一馬への追加購入:
  なし

返還:
  出走取消・競走除外は返還
  競走中止は不的中
```

保持項目は以下とする。

```text
- backtest_strategy_version
- stake_per_bet
- max_bets_per_race
- selection_rule
- odds_snapshot_policy
- odds_snapshot_at
- refund_flag
- refund_amount
- payout_amount
- profit
- effective_stake
- selected_count
- effective_bet_count
- refund_count
```

## 11.5 推奨ランク初期仕様

Phase 1では、未定義の「予測信頼度」を推奨ランクに使わない。初期ランクは以下で定義する。

```text
S:
  EV_lower >= 1.20
  p_fukusho_hit >= 0.25
  fukusho_odds_lower >= 1.5

A:
  EV_lower >= 1.10
  p_fukusho_hit >= 0.20
  fukusho_odds_lower >= 1.5

B:
  EV_lower >= 1.05
  p_fukusho_hit >= 0.15

C:
  EV_lower >= 1.00

D:
  上記以外
```

予測信頼度はPhase 2以降で、分散、校正誤差、データ欠損率、過去類似サンプル数などをもとに設計する。

## 11.6 回収率計算

バックテストの回収率は表示オッズではなく、実際の払戻金を用いて計算する。返還が発生した場合でも回収率が歪まないよう、Phase 1では以下で固定する。

```text
通常購入:
  stake = 100
  refund_amount = 0
  payout_amount = 実払戻金
  profit = payout_amount - stake
  effective_stake = stake

出走取消・競走除外による返還:
  stake = 100
  refund_amount = 100
  payout_amount = 0
  profit = 0
  effective_stake = 0

競走中止:
  stake = 100
  refund_amount = 0
  payout_amount = 0
  profit = -100
  effective_stake = 100
```

回収率・件数は以下で計算する。

```text
回収率 = payout_amount合計 / effective_stake合計
損益 = payout_amount合計 + refund_amount合計 - stake合計
selected_count = 返還を含む選択数
effective_bet_count = 返還を除く実購入数
refund_count = 返還数
```

返還分は実質的な購入額から控除するため、`effective_stake = 0` とする。これにより、返還が多いレースで回収率が不自然に歪むことを防ぐ。

---

# 12. DB・ETL・分析エンジン方針

## 12.1 基本方針

主たる永続DBはMac側PostgreSQLとする。DuckDBは常時運用DBではなく、大量集計やParquet分析が必要な場合のみ使用する補助的な分析エンジンとする。

## 12.2 論理層

| 層 | 内容 |
| --- | --- |
| raw_everydb2相当 | EveryDB2由来の原本テーブル。物理的には既存テーブルをそのまま扱う。 |
| normalized | 分析用に正規化・型変換・コード変換したテーブル。 |
| label | ラベル生成・払戻テーブル突合結果。 |
| prediction | 予測結果、EV、推奨ランク。 |
| backtest | バックテスト条件、購入結果、払戻、評価指標。 |

## 12.3 クラス正規化

クラス正規化は文字列ではなく、EveryDB2 / JRA-VAN由来の競走条件コードを基準に行う。

保持項目は以下とする。

```text
source:
  - race_condition_code
  - race_condition_name_raw

normalized:
  - class_code_normalized
  - class_name_normalized
  - class_level_numeric
  - post_2019_class_system_flag
  - is_open_class
  - is_listed
  - is_grade_race
```

例:

```text
race_condition_code = 005
  2019年前: 500万下
  2019年後: 1勝クラス
  class_level_numeric = 1

race_condition_code = 010
  2019年前: 1000万下
  2019年後: 2勝クラス
  class_level_numeric = 2

race_condition_code = 016
  2019年前: 1600万下
  2019年後: 3勝クラス
  class_level_numeric = 3
```

単純な名称変換だけではなく、2019年夏季競馬以降の制度変更を示す `post_2019_class_system_flag` を保持する。

## 12.4 学習用データセット保存

学習用データセットはParquetで保存する。

ファイルには以下のメタデータを付与する。

- dataset_version
- feature_snapshot_id
- label_version
- prediction_timing
- feature_cutoff_datetime
- train_period
- validation_period
- created_at

---

# 13. 特徴量生成・as-of管理

## 13.1 as-of管理の目的

Phase 1では、特徴量生成時点のリーク防止を重視する。`race_date` の昇順だけでは不十分であり、各特徴量がどの予測時点で利用可能かを管理する。

## 13.2 必須項目

以下を保持する。

```text
- as_of_datetime
- feature_cutoff_datetime
- race_start_datetime
- feature_snapshot_id
- feature_availability_version
```

## 13.3 feature_availability定義

各特徴量に以下を付与する。

```text
- feature_name
- feature_group
- available_from_timing
- source_table
- cutoff_rule
- leakage_risk_level
```

`available_from_timing` の候補:

```text
- entry_confirmed
- post_position_confirmed
- race_day_morning
- body_weight_announced
- odds_snapshot_available
- post_race_only
```

## 13.4 Phase 1-Aの特徴量参照条件

Phase 1-Aでは以下を厳守する。

```text
参照可能な過去レース:
  対象レースの前日以前に確定済みのレース

使用禁止:
  当日レース結果
  当日馬場・天候
  馬体重
  当日オッズ
  当日ここまでの騎手成績
  当日ここまでの競馬場傾向
  当日ここまでの馬場内外傾向
```

## 13.5 Phase 1で利用可能な特徴量

Phase 1-Aで利用可能な特徴量候補:

- 出走馬ID
- 馬齢
- 性別
- 斤量
- 騎手
- 調教師
- 種牡馬
- 母父
- 競馬場
- 距離
- 芝/ダート
- 右回り/左回り
- コース条件
- クラス正規化
- 馬番
- 枠番
- 過去走着順
- 過去走タイム差
- 過去走上がり
- 過去走通過順
- 過去走距離
- 過去走馬場状態
- 過去走競馬場
- 過去走からの間隔
- 過去走成績から推定した脚質

`逃げ馬数` は、レース後通過順ではなく、過去走由来の事前推定脚質から作る場合のみ利用可能とする。

---

# 14. モデル設計・ベースライン・カテゴリ仕様

## 14.1 初期モデル

Phase 1では以下を比較する。

- LightGBM
- CatBoost
- scikit-learn系ベースライン

目的変数は `fukusho_hit_validated` とする。

## 14.2 ベースラインモデル

以下のベースラインを必ず評価する。

```text
BL-1: 頭数別一定確率
  8頭以上: 3 / 発売開始時点出走頭数
  5〜7頭: 2 / 発売開始時点出走頭数

BL-2: 人気順ベースライン
  人気順位のみで確率を推定

BL-3: 複勝オッズ逆数ベースライン
  評価比較専用。Phase 1モデル特徴量には使わない。

BL-4: ロジスティック回帰
  少数の基本特徴量のみ

BL-5: LightGBM最小特徴量版
  過去走特徴量なし、レース条件・馬情報中心
```

BL-3の複勝オッズ逆数ベースラインは、市場確率との比較用であり、Phase 1-Aモデルと同一情報条件の比較ではない。AIモデルが市場より優れているかを直接判定する目的ではなく、AI確率と市場確率の乖離がEV判定に使えるかを確認するための参考指標として扱う。

ベースラインの目的は、AIが単純モデルや市場情報に対して付加価値を持つか確認することである。

## 14.3 LightGBM仕様

- カテゴリ特徴量は `category` dtype または連番カテゴリIDで管理する。
- カテゴリIDに負値コードを使わない。負値が欠損として扱われる可能性があるためである。
- 欠損値は欠損理由を区別して管理する。
- 検証データを使ったtarget encodingは禁止する。

## 14.4 CatBoost仕様

- `cat_features` を明示する。
- 時系列順序は `race_date` / `race_start_datetime` で固定する。
- 検証データを使ったtarget encodingは禁止する。
- カテゴリ処理によるターゲットリークを防止する。

## 14.5 欠損理由

欠損は単なるNULLとしてまとめず、以下の理由を区別する。

- 未発表
- 該当なし
- データ欠落
- 初出走・履歴不足
- 集計対象不足
- 予測時点では利用不可

---

# 15. 評価指標・バックテスト要件

## 15.1 評価指標

Phase 1では以下を評価する。

- 複勝的中率
- 複勝回収率
- 損益
- 最大ドローダウン
- 購入点数
- Brier Score
- LogLoss
- Calibration Curve
- 年別安定性
- 月別安定性
- 競馬場別安定性
- 頭数別安定性
- 人気帯別安定性
- オッズ帯別安定性

## 15.2 確率品質の受入基準

初期受入基準は以下とする。

```text
- 年別Calibration Curveで極端な逆転がない
- 予測確率binごとの実測率が単調増加に近い
- LogLoss/Brier Scoreがベースラインモデルを上回る
- レース単位 sum(p_fukusho_hit) の平均が理論値から大きく外れない
```

レース単位確率合計の目安:

```text
8頭以上レース:
  平均sum(p_fukusho_hit) が 2.7〜3.3 程度

5〜7頭レース:
  平均sum(p_fukusho_hit) が 1.8〜2.2 程度
```

平均値だけでなく、以下の分布指標も確認する。

```text
- 中央値
- 標準偏差
- p10
- p90
```

8頭以上レースでは、p10〜p90が極端に広がりすぎないことを確認する。大きく外れるレース条件がある場合は、頭数、競馬場、芝/ダート、距離カテゴリ、クラス別に原因を確認する。

この基準は初期値であり、実データ検証後に調整する。

## 15.3 Calibration評価

Calibrationは以下の軸で確認する。

- 全体Calibration Curve
- 人気帯別Calibration Curve
- オッズ帯別Calibration Curve
- 競馬場別Calibration Curve
- 頭数別Calibration Curve
- 年別Calibration Curve

## 15.4 バックテスト分割

バックテストは以下を必須とする。

```text
分割単位:
  race_id単位

時系列:
  race_date / race_start_datetime 昇順

禁止:
  同一race_idのtrain/testまたぎ
  同一開催日の未来レース情報利用
  最終オッズ・確定払戻の特徴量混入
  レース後に有利なodds_snapshot_policyを選ぶこと
```

検証方式:

- rolling window
- expanding window
- fixed holdout

## 15.5 初回バックテスト候補

初回バックテストでは以下を比較する。

| 検証名 | 学習 | 検証 |
| --- | --- | --- |
| BT-1 | 2019-06〜2022 | 2023 |
| BT-2 | 2019-06〜2023 | 2024 |
| BT-3 | 2019-06〜2024 | 2025 |
| BT-4 | 直近3年 rolling | 翌年 |
| BT-5 | 直近5年 rolling | 翌年 |

各BTについて、以下の `odds_snapshot_policy` を比較する。

- 発走30分前固定
- 発走10分前固定

---

# 16. 画面・CSV出力要件

## 16.1 Phase 1画面

Streamlitの初期画面では以下を表示する。

- レース一覧
- 各馬の `p_fukusho_hit`
- 複勝オッズ下限
- 複勝オッズ上限
- `EV_lower`
- `EV_upper`
- 推奨ランク
- `odds_snapshot_policy`
- `odds_snapshot_at`
- model_version
- feature_snapshot_id
- backtest_strategy_version

Phase 1では、ワイド候補、ワイド期待値、荒れ指数、コメント生成は表示しない。これらはPhase 2以降で追加する。

## 16.2 Phase 1 CSV出力

予測CSVには以下を含める。

```text
race_id
race_date
race_start_datetime
racecourse
race_number
horse_id
horse_name
post_position
horse_number
p_fukusho_hit
fukusho_odds_lower
fukusho_odds_upper
EV_lower
EV_upper
recommend_rank
odds_snapshot_policy
odds_snapshot_at
model_version
feature_snapshot_id
prediction_created_at
```

バックテストCSVには以下を含める。

```text
backtest_id
backtest_strategy_version
train_period
validation_period
odds_snapshot_policy
race_id
horse_id
selected_flag
stake
refund_flag
payout_amount
profit
fukusho_hit_validated
recommend_rank
EV_lower
EV_upper
```

---

# 17. 開発環境・プロジェクト構成

## 17.1 開発環境

| 項目 | 採用 |
| --- | --- |
| Python環境管理 | uv |
| Python | 3.12。問題時は3.11に切替可能 |
| モデル | LightGBM、CatBoost |
| 評価・前処理 | scikit-learn |
| DB | PostgreSQL |
| 分析補助 | DuckDB。必要時のみ |
| 学習データ | Parquet |
| 画面 | Streamlit |
| コード管理 | Git |

## 17.2 プロジェクト構成

```text
project/
  README.md
  pyproject.toml
  src/
    config/
    db/
    etl/
    labels/
    features/
    models/
    prediction/
    backtest/
    evaluation/
    utils/
  scripts/
  notebooks/
  streamlit_app/
  tests/
  data/
    parquet/
  models/
  reports/
```

## 17.3 テストコード

Phase 1では以下に最低限のテストを書く。

- 複勝ラベル生成
- 払戻テーブル突合
- 出走取消・競走除外・競走中止の扱い
- オッズ時点固定
- 仮想購入ルール
- feature_cutoff_datetime
- 評価指標計算
- race_id単位分割
- クラス正規化
- カテゴリ・欠損処理

---

# 18. Phase構成・ロードマップ

## 18.1 Phase 1

Phase 1では以下を実装する。

- rawデータ品質チェック
- normalized初期ETL
- 複勝ラベル生成・払戻突合
- as-of特徴量管理
- 出馬表・馬番・枠番確定後モデル
- `p_fukusho_hit`
- EV_lower / EV_upper
- 固定仮想購入ルール
- race_id単位時系列バックテスト
- Streamlit最小画面
- CSV出力

## 18.2 Phase 2

Phase 2では以下を実装候補とする。

- 開催日朝モデル
- 馬体重発表後モデル
- ワイド候補ペア
- ワイド期待値
- 予測信頼度の定義
- Calibration改善
- Streamlit表示拡張

## 18.3 Phase 3

Phase 3では以下を実装候補とする。

- 発走直前オッズ対応
- 時系列オッズ・票数変化特徴量
- オッズ依存の市場補正モデル
- 三連複期待値モデル
- Streamlit高度化
- モデル自動更新

---

# 19. 非機能要件

## 19.1 再現性

- モデルバージョン、特徴量スナップショット、ラベル定義バージョンを保存する。
- `odds_snapshot_policy`、`backtest_strategy_version` を保存する。
- 学習用データセットはParquetで保存し、同じ条件で再学習できるようにする。
- 予測結果には生成時刻、as-of時刻、オッズ取得時刻を保存する。

## 19.2 保守性

- PostgreSQLを主DBとし、DuckDBは必要時のみ使用する。
- EveryDB2由来テーブルは原本性を保ち、直接加工しない。
- normalized以降の変換ロジックをPythonコードとして管理する。
- ラベル生成、特徴量生成、バックテスト戦略はバージョン管理する。

## 19.3 安全性

- 実馬券購入および自動投票はスコープ外とする。
- 本システムは利益を保証しない。
- 推奨ランクは参考情報であり、購入判断を強制しない。
- 回収率は過去データ上の仮想結果であり、将来成績を保証しない。

---

# 20. リスクと対策

| リスク | 影響 | 対策 |
| --- | --- | --- |
| 複勝ラベル誤定義 | 的中率・回収率・学習が歪む | 発売開始時点の複勝払戻対象数と払戻テーブル突合を必須にする。 |
| 最終出走頭数だけでラベル生成 | 発売開始後取消のケースで誤判定 | `sales_start_entry_count` と `fukusho_payout_places` を保持する。 |
| オッズ時点不明 | EV・回収率の再現性が失われる | `odds_snapshot_policy` と `odds_snapshot_at` を必須化する。 |
| 後知恵オッズ選択 | 回収率過大評価 | 発走30分前固定・10分前固定など事前定義の条件のみ使う。 |
| 仮想購入ルール未定義 | 回収率・損益が再現不能 | `backtest_strategy_version` と固定購入条件を保存する。 |
| 未来情報リーク | バックテスト過大評価 | `as_of_datetime`、`feature_cutoff_datetime`、feature_availabilityを導入する。 |
| 競走中止の除外 | 回収率過大評価 | 競走中止は出走後の不的中として扱う。 |
| 同一レースのtrain/testまたぎ | 評価の信頼性低下 | race_id単位分割を必須にする。 |
| 2015年開始による履歴不足 | 初期年の特徴量品質低下 | ウォームアップ期間を設ける。 |
| クラス制度変更 | 古いデータとの不整合 | 競走条件コード基準のクラス正規化と制度変更フラグを付与する。 |
| カテゴリ処理ミス | 過学習・リーク | LightGBM/CatBoost別のカテゴリ・欠損仕様を明文化する。 |
| Phase 1肥大化 | 実装遅延・検証不備 | Phase 1は複勝確率・EV・固定BTに限定する。 |

---

# 21. 未確定事項・将来検討事項

| 項目 | 扱い |
| --- | --- |
| EV_lower推奨閾値 | Phase 1初期値は1.05。バックテストで調整。 |
| 最低確率閾値 | Phase 1初期値は0.15。バックテストで調整。 |
| 最低オッズ下限 | Phase 1初期値は1.5。バックテストで調整。 |
| 同一レース最大購入数 | Phase 1初期値は2頭。バックテストで調整。 |
| 予測信頼度の定義 | Phase 2以降。Phase 1ランクには使わない。 |
| レース荒れ指数 | Phase 2以降。オッズ依存ならPhase 1では使わない。 |
| ワイドモデル | Phase 2。2頭ペアの同時複勝対象確率が必要。 |
| 三連複モデル | Phase 3以降。組み合わせ爆発に注意。 |
| 発走直前オッズモデル | Phase 3。取得遅延・運用制約を考慮。 |
| MLflow導入 | Phase 1安定後に検討。 |
| Optuna導入 | 特徴量・評価が安定した後に検討。 |
| Word版出力 | 要件確定時点で作成する。レビュー段階ではMarkdownのみ。 |

---

# 22. 参考情報

- JRA: 複勝式 競馬用語辞典
- JRA: 出馬表はいつごろ発表されるのですか？
- JRA: 開催日の競馬場の天候・馬場状態を知りたいのですが？
- JRA-VANヘルプセンター: 馬体重はいつ発表される？
- JRA: 競走中止となった場合の馬券の取扱い
- JRA: 具体的な払戻計算式を知りたいのですが？
- JRA: 馬券のルール
- JRA-VAN: DataLab. 会員サービス詳細仕様
- scikit-learn: TimeSeriesSplit
- JRA: 競馬のルール レースのクラス分け
- JRA-VAN Data Lab.開発者コミュニティ: 2019年夏競馬以降の競走条件変更
- JRA: 同着となった場合の払戻
- scikit-learn: Probability calibration
- scikit-learn: brier_score_loss
- LightGBM: Advanced Topics
- CatBoost: unbiased boosting with categorical features
- JRA-VAN: EveryDB2
