---
phase: 08-adversarial-audit-suite
reviewed: 2026-06-25T00:00:00Z
depth: deep
files_reviewed: 9
files_reviewed_list:
  - src/audit/__init__.py
  - src/audit/report.py
  - scripts/run_reproducibility_smoke.py
  - tests/audit/__init__.py
  - tests/audit/conftest.py
  - tests/audit/test_audit_features.py
  - tests/audit/test_audit_label.py
  - tests/audit/test_audit_split.py
  - tests/audit/test_audit_ui_csv.py
findings:
  critical: 3
  warning: 7
  info: 5
  total: 15
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-06-25
**Depth:** deep
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 08 は **Adversarial Audit Suite** — テストがリーク/欠陥を本当に捕捉できるか (false-pass 回避) がコア価値。deep cross-file 解析の結果、**3 件の Critical** を含む 15 件の指摘を抽出した。

最も重大な問題は **adversarial テスト群が「guard 無効化でリークを混入させる」という自己目的化要件を実際には満たしていない** 点。`test_audit_features.py` の「リーク注入」は guard を `<=` に緩めるのでなく・データの `as_of_datetime` を偽装するだけ・`test_audit_label.py` の end-to-end は mock cursor の magic-proxy 挙動に偶然依存する・`test_audit_ui_csv.py` のキーワード集合は本番 guard と乖離している。これらは「SC#2 adversarial 三ケースが GREEN」を満たすが・guard を削除/破壊しても通る可能性が高い・すなわち adversarial テストの**存在意義自体が侵食**されている。

`src/audit/report.py` は DRY・presence assert・atomic write と設計は堅牢だが・テスト結果数値 (`passed=499`) をソースコードに hardcode し・実行時に検証しない点が D-04「フルスイート GREEN 証明」の趣旨を損なう。`scripts/run_reproducibility_smoke.py` は薄く清潔だが・subprocess 失敗時の stdout/stderr 欠落と・N=1 の比較戦略に warning 級の改善余地がある。

## Critical Issues

### CR-01: `test_audit_features.py` の「リーク注入」は guard を無効化せず・データ偽装のみ (false-pass の構造的リスク・adversarial 存在意義の毀損)

**File:** `tests/audit/test_audit_features.py:69-129`
**Issue:**

テスト docstring (L42-49) は「(3) 意図的 T+1 リーク注入（guard monkeypatch で ``<`` → ``<=`` に緩める）」と宣言する。しかし実際の `_leaky_build_rolling_features` (L76-96) は guard を **一切** 無効化しない。代わりに `history` の `previous_day` 行の `as_of_datetime` を `obs_cutoff - pd.Timedelta(seconds=1)` に **偽装** して strict `<` を素通りさせる経路をとる (L85-91)。本体の guard コード (`src/features/rolling.py:235-237`) は両経路で同一の `expanded["as_of_datetime"] < expanded["feature_cutoff_datetime"]` である。

これは **adversarial テストの存在意義を毀損** する:
- docstring が宣言する「guard を無効化するとリーク混入」が成立しない。仮に guard が壊れていても・`history_clean` の `previous_day` 行は依然 `as_of == cutoff` であり・step (2)/(4) の baseline は何も検出しない。
- step (5) の「検証力証明」も guard ではなくデータ偽装で成立しているため・guard が削除されても step (5) は GREEN のまま (test が「guard が効いている」ことを証明しない)。
- 機能テスト `tests/features/test_pit_cutoff.py::test_cutoff_excludes_previous_day_race_strict_less_than` (L44-55) は同一ロジック (previous_day の除外) を検証済み。本 adversarial テストは「5 段階鋳型適用」の体裁をとるが・実質は機能テストの重複に過ぎない。

5 段階鋳型 (`test_no_target_encoding_leak` L277-486 構造) の要件は「guard monkeypatch で本物の guard コードを改変し・それで混入すること」・すなわち *guard そのもの* にリークを注入できること。現状は「guard を素通りするデータを作る」ことしか検証しておらず・guard が未来のリファクタで silent に壊れても SC#2 ケース1 は GREEN を返す。

**Fix:**

guard を本当に無効化する monkeypatch 経路に書き換える:
```python
import src.features.rolling as rolling_mod
from unittest.mock import patch

# guard を <= に緩めた複製を注入
def _leaky_prefilter(expanded: pd.DataFrame) -> pd.DataFrame:
    return expanded[expanded["as_of_datetime"] <= expanded["feature_cutoff_datetime"]].copy()

with patch.object(rolling_mod, "_CUTOFF_PREFILTER", _leaky_prefilter):  # または該当行の関数化
    result_leaked = rolling_mod.build_rolling_features(obs, history_clean)
mean_leaked = float(result_leaked.iloc[0]["rolling_kakuteijyuni_mean_5"])
assert abs(mean_leaked - 18.0) < 1e-6, "guard 無効化で previous_day (66) が混入するはず"
```
`src/features/rolling.py:235-237` の strict `<` filter をモジュール private helper に切り出し・それを patch することで「guard そのものの無効化」を検証する。これが真の adversarial (T-08-01 mitigate) である。

---

### CR-02: `test_audit_label.py` の「cursor ベース end-to-end」は mock cursor の magic-proxy 挙動に偶然依存 (false-pass・SC#2 ケース2 の検証力欠如)

**File:** `tests/audit/test_audit_label.py:79, 105-109`
**Issue:**

テスト docstring (L72) は「cursor ベース end-to-end で ``reconcile_against_payout(cur)["verdict"] == "fail"`` を検証」と宣言し・「注入経路が本番 cursor path を通る」と主張する。しかし mock cursor `_mock_cursor` (L30-56) は `fetchone` のみを設定し・**未知の SELECT 全てに `(0,)` を返す** (L51-52)。

本番 `reconcile_against_payout` (`src/etl/label_reconcile.py:953-996`) は BLOCK 6 検査 + INFO 2 検査 + `_compute_race_level_agreement` を順次実行する。内 `_compute_race_level_agreement` (L727-) は `cur.fetchall()` を呼ぶが・mock は `fetchall` を設定しない (`MagicMock` の default 戻り値 = `MagicMock()` instance)。結果として `for year, jyocd, ... in label_rows:` の unpack で例外が raise され・本番 `except Exception` (L980) に捕捉される。`_compute_race_level_agreement` は空行 path (L782-788: agreement_pct=100.0, total_held_out=0) を辿ることで辛うじて verdict 計算まで到達するが・これは mock の偶然の振舞いに依存する。

実際の挙動を検証 (`uv run python` で再現): mock cursor は `fetchall` default で MagicMock を返し・for-loop unpack で `TypeError`/`ValueError` が raise されるが・`except Exception` (L980) で捕捉される。**verdict='fail' が返るのは・payout_recall.passed=False が BLOCK 集計で正しく伝播するから** という点では正しいが・「本番 cursor path 経由」ではない。mock cursor の (0,) fallback は・他の BLOCK 検査 (`_check_payout_precision` 等) がデフォルトで passed=True を返すことを保証するだけで・それらの SQL 実行を検証していない。

adversarial 存在意義の観点で: もし `_check_payout_recall` の本番 SQL が未来のリファクタで壊れても (例: `l.fukusho_hit_validated = 0` が別のカラムに rename される)・mock cursor の `fetch_map` key `fukusho_hit_validated = 0` (L79) が SQL 内にマッチしなくなり・fallback `(0,)` が返る → `passed=True` → **verdict='pass' になるはずが・本番 SQL は壊れている**。すなわち・mock cursor は「注入した条件」の SQL 文字列が *本番 SQL に現れる* ことを一切検証しない。文字列の drift を検出する回帰テストが別途必要。

**Fix:**

(1) mock cursor に `fetchall` も安全な空リスト `[]` を返すよう明示設定する (magic-proxy 依存の排除):
```python
def _mock_cursor(fetch_map: dict[str, object]) -> MagicMock:
    cur = MagicMock()
    cur._fetch_map = fetch_map
    cur.fetchall.return_value = []   # ← 追加: _compute_race_level_agreement の空行 path を保証
    # ... 既存の execute / fetchone ...
```
(2) 注入キーが本番 SQL に実際に現れることを assert する回帰 test を追加:
```python
# 注入前・_check_payout_recall の本番 SQL が fetch_map key を含むことを確認
import src.etl.label_reconcile as lr
import inspect
recall_sql = inspect.getsource(lr._check_payout_recall)
assert "fukusho_hit_validated = 0" in recall_sql, (
    "_check_payout_recall の SQL から 'fukusho_hit_validated = 0' が消失・mock 注入が dead path 化"
)
```

---

### CR-03: `test_audit_ui_csv.py` の `_WRITE_DDL_KEYWORDS` が本番 guard と異なり「同一覆盖力」主張が誤实

**File:** `tests/audit/test_audit_ui_csv.py:45-53, 83-86`
**Issue:**

`_WRITE_DDL_KEYWORDS` は bare キーワード (`"insert"`, `"update"`, `"delete"`, `"truncate"`, `"create"`, `"drop"`, `"alter"`) を使用する。docstring (L83-86) は「analog ``tests/ui/test_readonly_guarantee.py`` の書き込み/DDL 検出と同一の覆盖力を持つ」と宣言する。

しかし本番 `tests/ui/test_readonly_guarantee.py:38-46` の `_WRITE_DDL_KEYWORDS` は複合キーワード (`"insert into"`, `"update "` (末尾スペース), `"delete from"`, `"truncate "`, `"create table"`, `"drop table"`, `"alter table"`) である。両者は**同一の覆盖力を持たない**:

| ケース | 本番 guard | audit test |
|---|---|---|
| `UPDATE x SET` | hit (`"update "` match) | hit (`"update"` + word-boundary) |
| `SELECT * FROM updates` | miss (no `"update "`) | hit (`"update"` word-boundary 検出) |
| `DELETE` 単独 | miss (本番は `"delete from"`) | hit |
| `DELETE FROM x` | hit | hit |

adversarial テストの「注入を確実に検出」意図としては bare の方が広いが・docstring が「同一覆盖力」と虚偽宣言している点と・本番 guard が通す `DELETE` 単独を audit が fail させる設計差が・ユーザーが「D-06 を通るなら本番 guard も通る」と誤推論するリスクを生む。さらに・本番 guard が通す SQL が audit test で fail した場合・開発者はどちらを直すべきか迷う (実害は無いが・「同一」主張が trust barrier を下げる)。

さらに悪いことに・audit test の step (4) (L141-155) は本番 `src/ui/` に対して bare キーワードを適用し GREEN を主張するが・これは「本番 guard のキーワード集合」とは異なる。すなわち audit test が GREEN でも本番 guard が RED になるケース (`UPDATE` 単独を含む SQL 等) を検出できない。

**Fix:**

(1) docstring の「同一覆盖力」主張を削除し・差異を明記:
```python
# docstring L83-86 を修正:
# 本テストの _WRITE_DDL_KEYWORDS は bare キーワード採用で本番 guard
# (tests/ui/test_readonly_guarantee.py) より広い。adversarial 注入検出を優先するため・
# 本番 guard との完全一致は意図しない (本番 guard は誤検知回避で複合キーワード)。
```
(2) より望ましいのは本番 guard のキーワード定数を `tests/ui/test_readonly_guarantee.py` から import して使い・「同一キーワード」で注入検出と GREEN 保証の両立を図ること。bare を使う意図 (注入確実検出) は・step (1)-(3) の dummy file 注入に限定し・step (4) の本番 src/ui 検査は本番 guard と同一キーワードを使うべき。

---

## Warnings

### WR-01: `src/audit/report.py` がテスト結果数値 (`passed=499`) を hardcode・実行時に検証しない

**File:** `src/audit/report.py:277-279, 291-298`
**Issue:**

`generate_audit_report` は `"checkpoint 08-03 実績: 499 passed / 1 skipped"` と `"full_suite_result": {"passed": 499, "skipped": 1, "failed": 0}` をソースに固定値で埋め込む。これは D-04「フルスイート GREEN 証明」の趣旨を損なう:
- レポート生成時点で実際に pytest を実行しないため・値が drift しても silent に古い数値を主張し続ける。
- 499 が减少しても (例: 新バグで 490 passed に)・レポートは依然「499 passed / failed 0」を宣言する。これは CLAUDE.md「リーク防止と再現性だけは守らなければならない」の対極・**silent 隠蔽** 構造。
- D-04「チェックポイント 08-03 で人間承認」と分離しているとの docstring 弁明があるが・report.py を CLI 実行 (`__main__` L343) したときに古い数値が再生されるリスクは残る。

**Fix:**

`generate_audit_report` 呼出時に pytest を実行して数値を動的取得するか・数値を外部引数として受け取る (現状は外部から与えられない):
```python
def generate_audit_report(
    *,
    output_dir: str | Path = "reports",
    full_suite_result: dict | None = None,   # ← 追加: 呼出元が pytest 結果を注入
) -> tuple[Path, Path]:
    fsr = full_suite_result or _read_latest_checkpoint()  # 08-03-SUMMARY.md 等から parse
    ...
```
少なくとも・hardcode 値の隣に「検証日時: 2026-06-XX・verify 08-03 checkpoint 時点」を明示し・report が動的検証しないことを開示すべき。

---

### WR-02: `src/audit/report.py` の presence assert が header_line 抽出を `AUDIT_SURFACE_COLUMNS[0] in line` に依存 (fragile)

**File:** `src/audit/report.py:308-313`
**Issue:**

presence assert は md から header 行を抽出する際・`line.startswith("| ") and AUDIT_SURFACE_COLUMNS[0] in line` を使う (`AUDIT_SURFACE_COLUMNS[0]` = `"surface"`)。これは:
- `"surface"` が evidence 列の文章内 (例: `"fukusho_label ... surface ..."`) に現れた場合・最初に hit した行が header でない可能性がある。
- 現状 SURFACE_ROWS の evidence 文字列に `"surface"` は含まれないため hit しないが・将来 evidence が拡張されたときに silent に誤行を拾う。

**Fix:**

header 行は `md_payload` 生成時に marker を付けて保持し・検索ではなく変数参照する:
```python
md_header_line = header  # _format_surface_table_md 内で生成した header 変数
# md_payload 構築後に md_header_line を直接 assert する
for col in AUDIT_SURFACE_COLUMNS:
    assert col in md_header_line, ...
```

---

### WR-03: `scripts/run_reproducibility_smoke.py` が subprocess 失敗時の stdout/stderr を破棄 (debug 性低下)

**File:** `scripts/run_reproducibility_smoke.py:103-109`
**Issue:**

`subprocess.run(cmd)` は `capture_output` 指定がなく・pytest の出力は親プロセスの stdout/stderr に直接継承される。CI 環境で出力が buffer overflow / truncate する場合・どのテストが fail したか分からなくなる。`logger.error("FAIL: %s (returncode=%s)", desc, result.returncode)` は returncode しか出さない。

**Fix:**

`capture_output=True` + 失敗時の stderr dump:
```python
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    logger.error("FAIL: %s (returncode=%s)", desc, result.returncode)
    logger.error("stdout:\n%s", result.stdout[-2000:])
    logger.error("stderr:\n%s", result.stderr[-2000:])
    return 1
```

---

### WR-04: `scripts/run_reproducibility_smoke.py` が SC#3 を「合成データ bit-identical」1 test のみで証明 (再現性 smoke として弱い)

**File:** `scripts/run_reproducibility_smoke.py:49-64`
**Issue:**

SC#3 の設計意図 (docstring L8-17) は「固定 seed で合成データの bit-identical 再現性を確認する薄い orchestrator」だが・実際に実行するのは:
- step 1: `tests/model/test_calibrator.py::test_reproduce_bit_identical` (calibrator のみ・N=1)
- step 2: `tests/audit/` (SC#2 adversarial・再現性ではなく注入検出)

NC-03 comment (L19-22) は「trainer bit-identical 群は現状 0 件のため除外」と説明するが・これは SC#3 の検証力が薄弱であることをむしろ露呈する。calibrator 1 関数の bit-identical だけでは「フルパイプラインの再現性 smoke」を名乗るには弱く・ユーザーが「SC#3 = full pipeline reproducibility 済み」と誤推論するリスクがある。

ファイル名 (`run_reproducibility_smoke.py`) と docstring のスコープ主張 (「SC#3 合成層」) は・実体 (calibrator N=1 + SC#2) に比べて過大。

**Fix:**

(1) ファイル名・docstring を実体に合わせて縮退: `run_calibrator_bit_identical_smoke.py` 等に rename・または docstring で「現状 calibrator のみ・trainer 追加予定」と冒頭で明示。
(2) step 1 に `test_reproduce_bit_identical` 以外にも `tests/model/` 配下の bit-identical 系 test を collect して実行する動的拡張を検討 (`-k "reproduce or bit_identical"` を step 定義に入れる等)。

---

### WR-05: `tests/audit/conftest.py` の fixtures/builders (`_build_label_row`, `_build_payout_row`, `_build_history_row`, `audit_mock_cursor`) が未使用 (dead code)

**File:** `tests/audit/conftest.py:27, 51, 74, 117`
**Issue:**

`grep -rn "_build_label_row\|_build_payout_row\|_build_history_row\|audit_mock_cursor" tests/` の結果・これら 4 シンボルは `conftest.py` 内の定義と docstring 言及のみで・**どの test ファイルからも import/use されていない** (実際の audit test は `tests/features/conftest.py::_build_adversarial_rolling_rows` 等を使う)。

Phase 08 が「Plan 08-01 で SC#2 adversarial 3 ケース」を作った際・本来これらの builder を使う意図だったが・最終的に features/test_label_reconcile 側の builder を再利用したため dead に残ったと思われる。`audit_mock_cursor` に至っては `tests/audit/test_audit_label.py` が独自に `_mock_cursor` を定義しており・完全に重複 dead code。

**Fix:**

未使用 builder 3 つ + `audit_mock_cursor` fixture を削除する。または・docstring に「将来の Task 拡張用・現在未使用」と明示して残す (推奨されない・conftest の軽量化が test 収集速度と可読性に効く)。

---

### WR-06: `test_audit_split.py::test_fold_race_id_shared_detected_and_raises` は既存 test の機械的複製 (D-04 重複)

**File:** `tests/audit/test_audit_split.py:26-89`
**Issue:**

docstring (L8-15, 92-97) 自ら「既存 ``tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak`` と同一注入パターン」と認める。実体も BTWindow `train_end == test_start` で R2 を共有させ・`ValueError(match='race_id')` を検証する・完全な機械的複製。

SC#2「3 ケース独立 adversarial」の体裁要件のために作られた再定式化だが・adversarial としての新規検証力はゼロ。機能テストと等価のテストを「adversarial」ラベルで増やすことは・test suite の保守コストを増やし・将来一方だけ直す際のもう一方の stale 化リスクを生む。

**Fix:**

(i) 本 test を削除し・`tests/utils/test_group_split.py::test_get_bt_race_ids_raises_on_leak` を SC_CORRESPONDENCE の evidence として直接参照する。または (ii) SC#2 ケース3 を別の注入経路 (例: `race_id` は disjoint だが `race_start_datetime` が等値タイスタンプで跨ぐ HIGH #2 ケース) に差し替えて真に独立した検証力を持たせる。

---

### WR-07: `test_audit_ui_csv.py::test_reproducibility_stamp_missing_detected` が presence assert の tautology を内包 (検証力制限)

**File:** `tests/audit/test_audit_ui_csv.py:180-203, 215-246`
**Issue:**

step (2) L185-186 は `for stamp in REPRODUCIBILITY_STAMPS: assert stamp in REPRODUCIBILITY_STAMPS` という完全な tautology を持ち・comment にも「tautology guard・定数が tuple なので常に GREEN」と書かれている。これは削除すべき dead assert。

step (3)/(4) の `_verify_degraded_tuple_fails_presence_assert` (L215-246) は sentinel `"__MISSING_SENTINEL__"` が container に存在しないことで AssertionError を期待するが・これは「presence assert が要素非存在を検出できること」の検証であり・**presence assert そのものの検証力** を証明するわけではない (presence assert の実装は test 内に無く・本番 `tests/ui/test_csv_columns.py` にある)。すなわち・本番 presence assert の実装が壊れても本 test は通る可能性がある。

**Fix:**

(1) L185-186 の tautology assert を削除。
(2) 本番 `tests/ui/test_csv_columns.py::test_prediction_csv_has_all_stamps` の presence assert ロジックを helper として切り出して import し・それを本 test でも使うことで・本番ロジックの破壊を検出可能にする。

---

## Info

### IN-01: `src/audit/report.py` が `report.md` 内の「476 テスト」(L177) と「499 passed」(L277, 296) の数値矛盾を内包

**File:** `src/audit/report.py:177, 277, 296`
**Issue:**

SC#1 coverage 行 (L177) は「既存476テストで COVERED」と書くが・直後の D-04 証明 (L277, L296 JSON) は「499 passed / 1 skipped」と書く。499 - 1 = 498 ≠ 476。差分 22 件が何かに言及されず・読者は「SC#1 = 476・D-04 = 499」の乖離に気づいても説明がない。

**Fix:**

「SC#1 既存機能テスト 476 件 + SC#2/3 audit・calibrator 追加分 = 499」のように内訳を明示するか・同一数値に揃える。

---

### IN-02: `src/audit/report.py` の `reports/` 書込が「既定の出力ディレクトリ」に依存 (cwd 依存)

**File:** `src/audit/report.py:237, 257-259`
**Issue:**

`generate_audit_report(output_dir="reports")` の default は cwd 相対パス。CLI 実行 (`__main__` L343) 時・実行 cwd に依存して `reports/08-audit.{md,json}` が作られる。CI や異なるディレクトリからの実行で出力先が変わる。`__file__` 基準の repo root 解決 (`scripts/run_reproducibility_smoke.py:34` のパターン) と一貫しない。

**Fix:**

default を `_REPO_ROOT / "reports"` にするか・output_dir を必須引数にする。

---

### IN-03: `tests/audit/test_audit_label.py` の mock cursor が `fetchall` を未設定 (CR-02 と関連)

**File:** `tests/audit/test_audit_label.py:30-56`
**Issue:**

`_mock_cursor` は `execute` と `fetchone` のみを side_effect で設定し・`fetchall` は `MagicMock` default のまま。`reconcile_against_payout` 内の `_compute_race_level_agreement` が `fetchall` を呼ぶと MagicMock が返り・`for ... in label_rows:` で例外が raise される (CR-02 参照)。この暗黙依存は test の可搬性を下げる。

**Fix:**

明示的に `cur.fetchall.return_value = []` を設定し・空行 path を保証する (CR-02 fix と同一)。

---

### IN-04: `tests/audit/test_audit_features.py` L72 の `import` が関数内 (PEP 8 違反・test 可読性低下)

**File:** `tests/audit/test_audit_features.py:72`
**Issue:**

`import src.features.rolling as rolling_mod` が関数内 import。monkeypatch 意図なら理解できるが・本テストでは monkeypatch に使われておらず (CR-01 参照)・単に convention に従っていないだけ。

**Fix:**

module top に import を移動。

---

### IN-05: `tests/audit/test_audit_label.py` の `# noqa: ANN002` が不要 (型 hint 付与可能)

**File:** `tests/audit/test_audit_label.py:40, 48`
**Issue:**

`def _execute(sql: str, *args, **kwargs):` と `for key, val in cur._fetch_map.items():` に `# noqa: ANN002` / `# noqa: SLF001` 等の ignore marker が付くが・`*args, **kwargs` には `Any` 型 hint を付与できる。また `cur._fetch_map` への private access は mock 実装のため許容するにしても・marker が過剰。

**Fix:**

`*args: Any, **kwargs: Any` で ANN001/ANN002 を解消。SLF001 は mock 実装なので残す。

---

## Cross-File Analysis

### Import Graph (verified)

- `src/audit/report.py` → `src/model/artifact.py::_atomic_write_text` (verified・L59-69 で atomic write 定義)
- `tests/audit/test_audit_features.py` → `src.features.rolling.build_rolling_features` (verified・L112 build_rolling_features) + `tests.features.conftest._build_adversarial_rolling_rows / _build_race_obs_row` (verified・conftest L66, L37)
- `tests/audit/test_audit_label.py` → `src.etl.label_reconcile._check_payout_recall / reconcile_against_payout` (verified) + `src.etl.quality_gate.CheckResult` (verified)
- `tests/audit/test_audit_split.py` → `src.utils.group_split.BTWindow / get_bt_race_ids` (verified)
- `tests/audit/test_audit_ui_csv.py` → `src.ui.csv_columns.PREDICTION_CSV_COLUMNS / REPRODUCIBILITY_STAMPS` (verified)
- `tests/audit/conftest.py` → どの test からも参照されない (WR-05)

### 共有 fixtures の test-isolation

- `audit_mock_cursor` (function scope) は未使用・state mutation リスクなし (WR-05)
- module-scoped fixture は存在しない・全て function scope・test isolation は保たれる
- ただし `test_audit_label.py` の `_mock_cursor` は module-level helper だが stateless・cross-test mutation 無し

### Reproducibility smoke の決定論性

- `scripts/run_reproducibility_smoke.py` は datetime/seed を使わず・subprocess の returncode のみで判定・決定論的
- `src/audit/report.py` の JSON 出力は `sort_keys=True, ensure_ascii=False` で byte-reproducible (verified L300-302)
- `_atomic_write_text` で partial-failure 抑止 (verified)

---

_Reviewed: 2026-06-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
