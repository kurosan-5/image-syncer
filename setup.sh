#!/bin/bash

# Image Syncer セットアップスクリプト
echo "======================================"
echo "  Image Syncer セットアップスクリプト"
echo "======================================"

# Python3のチェック
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3がインストールされていません"
    echo "   Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "   macOS: brew install python3"
    exit 1
fi

echo "✅ Python3が見つかりました: $(python3 --version)"


# 仮想環境の作成
echo "🔧 Python仮想環境を作成中..."
python3 -m venv .venv

# 仮想環境の有効化
echo "🔧 仮想環境を有効化中..."
source .venv/bin/activate

# FFmpegのチェック
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpegがインストールされていません"
    echo "   Ubuntu/Debian: sudo apt install ffmpeg"
    echo "   macOS: brew install ffmpeg"
    echo "   Windows: https://ffmpeg.org/download.html からダウンロード"
    read -p "継続しますか？ (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ FFmpegが見つかりました: $(ffmpeg -version 2>&1 | head -n1)"
fi

# 依存関係のインストール
echo "📦 依存関係をインストール中..."
pip install --upgrade pip
pip install -r requirements.txt

# .envファイルの設定
if [ ! -f .env ]; then
    echo "🔧 環境変数ファイルを作成中..."
    cp .env.example .env
    
    # シークレットキーの生成
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    # .envファイルを更新
    sed -i "s/your-very-long-random-secret-key-here/$SECRET_KEY/" .env
    
    echo "✅ .envファイルが作成されました"
    echo "📝 以下の設定を確認して、必要に応じて変更してください："
    echo "   - ADMIN_USERNAME (現在: admin)"
    echo "   - ADMIN_PASSWORD (現在: secret)"
    echo ""
    echo "💡 パスワードを変更するには："
    echo "   nano .env"
else
    echo "✅ .envファイルが既に存在します"
fi

# ストレージディレクトリの作成
echo "📁 ストレージディレクトリを確認中..."
mkdir -p storage/thumbnails

echo ""
echo "🎉 セットアップが完了しました！"
echo ""
echo "📋 次のステップ："
echo "1. .envファイルを編集してパスワードを変更"
echo "   nano .env"
echo ""
echo "2. アプリケーションを起動"
echo "   source .venv/bin/activate"
echo "   python app.py"
echo ""
echo "3. ブラウザでアクセス"
echo "   http://localhost:5000"
echo ""
echo "🔐 ログイン情報："
echo "   ユーザー名: admin"
echo "   パスワード: secret （.envファイルで変更可能）"
echo ""
