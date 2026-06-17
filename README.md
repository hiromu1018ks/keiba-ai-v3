# Keiba AI v3

JRA競馬データを用いて、各出走馬の**複勝払戻対象確率 `p_fukusho_hit`** をリークなく推定し、固定オッズ時点の EV で過小評価されている馬を検出する予測AI基盤。能力予測と EV 計算を分離し、race_id 単位・時系列順の再現可能なバックテストで有効性を定量評価する。

## セットアップ

```bash
# .env を .env.example を元に作成（DB 認証情報を記入・commit しない）
cp .env.example .env

# 依存関係のインストール（byte 再現性・§19.1）
uv sync --frozen

# テスト実行（PostgreSQL everydb2 が必要）
uv run pytest tests/ -v

# 5層スキーマ適用（raw REVOKE + ETL ロール CREATE）
uv run python scripts/run_apply_schema.py
```

## 主要ドキュメント

- 要件定義書: `docs/keiba_ai_requirements_v1.3.md`
- Phase 計画: `.planning/phases/01-trust-foundation/`
- 技術スタック・リーク防止設定: `CLAUDE.md`
