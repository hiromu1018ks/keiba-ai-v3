---
resolves_phase: 3.1
created: 2026-06-19
type: hardening
source: [03-VERIFICATION.md, 03-REVIEW.md]
title: "Phase 03 advisory 4件 hardening — Phase 3.1 に統合"
---

# Phase 03 advisory hardening（Phase 3.1 統合）

Phase 03 gap-closure（03-05）後の code review（03-REVIEW.md）で発見された advisory 4件。
verifier は「現 SC 非破壊・Phase 4 学習前 hardening 推奨」と判定（03-VERIFICATION.md `status: passed`・`advisories:` セクション）。
operator 指示により **Phase 3.1（Timediff/Babacd Restoration）に統合**して修正する。両者とも `builder.py` / `rolling.py` / `run_feature_build.py` を触るため、同ファイル編集時に併せて対処する。

Core Value（リーク防止・再現性）の defense-in-depth 強化が目的。Phase 3 の「passed」判定を覆すものではない。

## 修正対象

### WR-01' — silent no-filter fallback（リーク防御・defense-in-depth）
- 場所: `src/features/builder.py:353-354`
- 問題: `else: pit_filtered_style = expanded_style`（`as_of_datetime` 不在時に無 filter）。将来の refactor / 合成 history 直接 inject で silent に未来レースが推定脚質に混入する余地。WR-01 must_have は live path で成立しているが、到達不能分岐が残存。
- 修正: `as_of_datetime` 不在時に fail-loud（`ValueError`）。WR-01 must_have の完全化。
- テスト: `as_of_datetime` 列を持たない frame で `ValueError` を assert。

### WR-02 — `_fetch` 系 `except Exception`→空 DataFrame（silent NaN 化）
- 場所: `src/features/builder.py:455-457, 485-487`（`_fetch_feature_sources` / `_fetch_history`）
- 問題: `except Exception` で空 DataFrame を返す。DB 障害時に空/全 NaN snapshot を SHA256 付きで書き出す（CR-01 silent-NaN と同根）。
- 修正: `except` で空 DF を返さず fail-loud（raise / ログ）。または空 DF を返す場合でも呼び出し側で検知して fail。
- テスト: DB 障害シミュレートで raise/検知を assert。

### CR-01(new) — manifest→persist 順序依存（再現性 defense-in-depth）
- 場所: `scripts/run_feature_build.py:206-228`
- 問題: manifest 書き出し（L206・SHA256 含む）が `persist_category_maps`（L228）より先。persist 失敗時に SHA256 一致の「完成済」manifest が残り、category map artifact 欠損の再現性破壊状態が完成する。`category_map_artifact` が相対パス（`snapshots/category_map_*.json`）で CWD 依存。
- 修正: persist を manifest 書き出しより先に実行。永続化直後に存在確認（`assert exists`）。manifest の `category_map_artifact` を repo-root 相対で正規化。
- テスト: persist 失敗シミュレートで manifest が書かれないことを assert。

### WR-03 — rolling `groupby().apply` pandas 3.x 非推奨（byte-repro 維持）
- 場所: `src/features/rolling.py:236-240`
- 問題: `groupby().apply(lambda)` が pandas 3.x で非推奨。pandas upgrade 時に SHA256 drift（SC#3 byte-reproducibility 破壊）。同一プロセス・同一 pandas では検出不可。
- 修正: vectorized 形（`groupby().transform` / 明示的ループ）に置換。現 snapshot と同一 SHA256 を維持。
- テスト: rolling 再計算で SHA256 一致を assert（既存 byte-repro test 拡張）。

## 備考

- Phase 3.1 の主目的（`rolling_timediff_*` / `rolling_babacd_*` 計6 feature 復元）と併せて実施。
- 03-05 の end-to-end regression guard（`test_no_registered_feature_column_all_nan_end_to_end`）が silent empty feature の再発を検出するため、6 feature 再登録後も parity が機械保証される。
- 修正後、03-VERIFICATION.md の `advisories:` 4件を resolved に更新する（Phase 3.1 完了時）。
