# GitHubアップロード手順

## 1. GitHubリポジトリの作成

1. [GitHub](https://github.com)にログイン
2. 右上の「+」→「New repository」をクリック
3. リポジトリ名を入力（例：`image-syncer`）
4. 「Public」または「Private」を選択
5. 「Create repository」をクリック

## 2. ローカルリポジトリの初期化とアップロード

```bash
# Gitリポジトリを初期化
git init

# ファイルをステージング
git add .

# 初回コミット
git commit -m "Initial commit: iOS Photos風PWAアプリ"

# GitHubリポジトリをリモートに追加（YOUR_USERNAMEとREPO_NAMEを変更）
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# メインブランチにプッシュ
git branch -M main
git push -u origin main
```

## 3. 別のパソコンでのセットアップ

### 3.1 リポジトリのクローン
```bash
git clone https://github.com/YOUR_USERNAME/REPO_NAME.git
cd REPO_NAME
```

### 3.2 自動セットアップスクリプトの実行
```bash
# セットアップスクリプトを実行
./setup.sh
```

### 3.3 手動セットアップ（スクリプトが使えない場合）
```bash
# Python仮想環境の作成
python3 -m venv .venv

# 仮想環境の有効化
source .venv/bin/activate  # Linux/Mac
# または
.venv\Scripts\activate  # Windows

# 依存関係のインストール
pip install -r requirements.txt

# 環境変数ファイルの作成
cp .env.example .env

# シークレットキーの生成
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"

# 生成されたキーを.envファイルに設定
nano .env  # または好きなエディタで編集
```

### 3.4 アプリケーションの起動
```bash
# 仮想環境を有効化（まだの場合）
source .venv/bin/activate

# アプリケーション起動
python app.py
```

### 3.5 アクセス
ブラウザで http://localhost:5000 にアクセス

## 4. 必要な追加ソフトウェア

### FFmpeg（動画サムネイル生成用）

#### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install ffmpeg
```

#### macOS:
```bash
brew install ffmpeg
```

#### Windows:
1. [FFmpeg公式サイト](https://ffmpeg.org/download.html)からダウンロード
2. PATHに追加

## 5. 設定ファイル

### .env ファイルの編集
```bash
nano .env
```

以下を設定：
- `SECRET_KEY`: セキュアなランダム文字列
- `ADMIN_USERNAME`: 管理者ユーザー名
- `ADMIN_PASSWORD`: 管理者パスワード

## 6. よくある問題と解決方法

### Python3が見つからない
- Ubuntu/Debian: `sudo apt install python3 python3-pip python3-venv`
- macOS: `brew install python3`
- Windows: [Python公式サイト](https://python.org)からダウンロード

### 権限エラー
```bash
chmod 755 storage/
chmod 755 storage/thumbnails/
```

### ポートが使用中
```bash
# 別のポートで起動（app.pyを編集）
app.run(host='0.0.0.0', port=5001, debug=True)
```

## 7. 本番環境での注意

1. **DEBUG無効化**: `app.py`の`debug=False`に変更
2. **HTTPS使用**: nginxやCloudflare等でSSL設定
3. **強力なパスワード**: 複雑なパスワードに変更
4. **定期バックアップ**: データベースとstorageディレクトリ
5. **ファイアウォール**: 必要なポートのみ開放

## 8. 更新の取得

```bash
# 最新の変更を取得
git pull origin main

# 依存関係の更新
source .venv/bin/activate
pip install -r requirements.txt --upgrade
```
