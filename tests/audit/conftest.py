# ruff: noqa: E501  (docstring / 日本語コメント行長は緩和・tests/features/conftest.py と同一慣例)
"""Phase 8 audit 共通 fixtures (REVIEW WR-05: dead code 削除)。

Phase 08 Plan 08-01 当初の意図では ``_build_label_row`` / ``_build_payout_row`` /
``_build_history_row`` の合成行 builder と ``audit_mock_cursor`` fixture を SC#2 adversarial
テスト群で使う想定だったが・最終的に ``tests/features/conftest.py`` 側の既存 builder
(``_build_adversarial_rolling_rows`` / ``_build_race_obs_row`` 等) を再利用し・``tests/audit/
test_audit_label.py`` は独自に ``_mock_cursor`` を定義したため・本 conftest 内の 4 シンボルは
全て dead code となった (Phase 08 commit 時点で grep 確認済み)。

REVIEW WR-05 対応: 未使用 4 シンボルを削除し conftest を軽量化。audit テスト群は引き続き
GREEN を維持 (conftest 依存なし)。将来 SC#2 拡張等で共通 builder が必要になった場合は・
``tests/features/conftest.py`` のパターンを直接再利用すること (重複定義避け)。

合成行は ID のみを使用し、実馬名・騎手名等の PII は含まない（T-03-03 accept 踏襲）。
DB 不要（KEIBA_SKIP_DB_TESTS=1 でも実行される・marker なし）。
"""
