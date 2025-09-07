# Image Syncer - iOS Photos風PWAアプリ

iPhone写真アプリのようなユーザーインターフェースを持つプライベートフォトライブラリです。

## 機能

- � 画像・動画のアップロード（ドラッグ&ドロップ対応）
- 🖼️ iOS Photos風のグリッド表示
- 👆 タッチジェスチャー対応（スワイプ、ピンチズーム）
- 🎬 動画再生とサムネイル自動生成
- 🔄 HEIC画像の自動JPEG変換
- � PWA対応（スマホのホーム画面に追加可能）
- 🔐 認証機能付き
- �️ 重複ファイル検出・削除
- ⬇️ 複数ファイル一括ダウンロード

## 必要な環境

- Python 3.8以上
- FFmpeg（動画サムネイル生成用）
- Git

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/YOUR_USERNAME/image-syncer.git
cd image-syncer
```

### 2. Python仮想環境の作成

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# または
.venv\Scripts\activate  # Windows
```

### 3. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 4. FFmpegのインストール

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

### 5. 環境変数の設定

`.env.example`をコピーして`.env`を作成：

```bash
cp .env.example .env
```

`.env`ファイルを編集して認証情報を設定：

```bash
# セッション用シークレットキー（必ず変更してください）
SECRET_KEY=your-very-long-random-secret-key-here

# 管理者認証情報
ADMIN_USERNAME=your-username
ADMIN_PASSWORD=your-secure-password

# 外部ストレージパス（オプション）
# 外部HDDなどを使用する場合に設定
EXTERNAL_STORAGE_PATH=/media/usb-hdd/photos
```

### 外部ストレージの使用

外部HDD等を使用する場合は、`.env`ファイルに`EXTERNAL_STORAGE_PATH`を設定してください。

```bash
# 例: USBドライブをマウントした場合
EXTERNAL_STORAGE_PATH=/media/usb-hdd/photos

# 例: 別のディレクトリを使用する場合
EXTERNAL_STORAGE_PATH=/path/to/external/storage
```

外部ストレージを使用すると：
- 写真は撮影日時に基づいて自動的に日付フォルダ（YYYYMM形式）に整理されます
- アプリのスキャンボタンで外部ストレージ内の既存ファイルをデータベースに追加できます
- iPhoneのエクスポート形式と同じ構造で管理されます

### 6. シークレットキーの生成

安全なシークレットキーを生成：

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
```

生成されたキーを`.env`ファイルの`SECRET_KEY`に設定してください。

### 7. アプリケーションの起動

```bash
python app.py
```

以下のURLでアクセス：
- ローカル: http://127.0.0.1:5000
- LAN内: http://YOUR_IP:5000

## 使用方法

1. ブラウザでアプリにアクセス
2. `.env`で設定したユーザー名とパスワードでログイン
3. 画像・動画をドラッグ&ドロップまたはファイル選択でアップロード
4. グリッド表示で写真を閲覧
5. 写真をタップして拡大表示・スワイプで次の写真へ

## PWAとしてインストール

### スマートフォン:
1. ブラウザでアプリを開く
2. 「ホーム画面に追加」を選択
3. ネイティブアプリのように使用可能

### デスクトップ (Chrome):
1. アドレスバーの「インストール」アイコンをクリック
2. デスクトップアプリとして起動可能

### デスクトップ (Chrome):
1. アドレスバーの「インストール」アイコンをクリック
2. デスクトップアプリとして起動可能

## ディレクトリ構造

```
image-syncer/
├── app.py                 # メインアプリケーション
├── requirements.txt       # Python依存関係
├── .env.example          # 環境変数テンプレート
├── .env                  # 環境変数（要作成）
├── image_syncer.db       # SQLiteデータベース（自動作成）
├── storage/              # アップロードファイル保存先
│   └── thumbnails/       # サムネイル保存先
├── static/               # 静的ファイル
│   ├── css/main.css     # スタイルシート
│   ├── js/main.js       # JavaScript
│   ├── icon-*.png       # PWAアイコン
│   ├── manifest.json    # PWAマニフェスト
│   └── sw.js           # Service Worker
└── templates/            # HTMLテンプレート
    ├── index.html       # メインページ
    └── login.html       # ログインページ
```

## 本番環境での注意事項

1. **セキュリティ**:
   - 強力なパスワードを設定
   - シークレットキーを定期的に変更
   - HTTPSを使用（nginxやCloudflare等）

2. **パフォーマンス**:
   - Gunicorn等のWSGIサーバーを使用
   - リバースプロキシ（nginx）の設定
   - データベースの定期バックアップ

3. **ファイル管理**:
   - `storage/`ディレクトリのバックアップ
   - ディスク容量の監視

## トラブルシューティング

### FFmpegが見つからない場合:
```bash
# パスの確認
which ffmpeg
# または
ffmpeg -version
```

### 権限エラーの場合:
```bash
# storageディレクトリの権限確認
chmod 755 storage/
chmod 755 storage/thumbnails/
```

### データベースエラーの場合:
```bash
# データベースファイルを削除して再作成
rm image_syncer.db
python app.py
```

## ライセンス

MIT License

## 貢献

Pull RequestやIssueを歓迎します。

## サポート

問題が発生した場合は、GitHubのIssuesでお知らせください。
```

### 2. アプリケーションの起動

```bash
# 開発サーバーの起動
python app.py
```

アプリケーションは以下のURLでアクセスできます：
- http://localhost:5000
- http://127.0.0.1:5000

### 3. スマホからの自動アップロード設定

#### iOS Shortcutsアプリの設定

1. ショートカットアプリを開く
2. 「新しいショートカット」を作成
3. 以下のアクションを追加：
   - 「写真を選択」→「複数選択を許可」をON
   - 「Web要求を取得」
     - URL: `http://[サーバーIP]:5000/upload`
     - メソッド: POST
     - 要求本文: フォームデータ
     - ファイルフィールド名: `files`
4. オートメーションで「WiFi」トリガーを設定
   - 自宅のWiFiネットワークを選択
   - 作成したショートカットを実行

#### Android Taskerアプリの設定

1. Taskerアプリをインストール
2. プロファイル作成：
   - 状況: WiFi接続（自宅のSSID）
3. タスク作成：
   - HTTP Postアクション
   - サーバー: `http://[サーバーIP]:5000`
   - パス: `/upload`
   - ファイルフィールド: `files`

## API エンドポイント

### ファイルアップロード
```http
POST /upload
Content-Type: multipart/form-data

files: (複数のファイル)
```

### ファイル一覧取得
```http
GET /files
```

### ファイル取得
```http
GET /files/{file_id}
```

### サムネイル取得
```http
GET /thumbnails/{file_id}
```

### ファイル削除
```http
DELETE /files/{file_id}
```

## ディレクトリ構造

```
image-syncer/
├── app.py              # メインアプリケーション
├── requirements.txt    # Python依存関係
├── image_syncer.db    # SQLiteデータベース
├── storage/           # アップロードファイル保存
│   └── thumbnails/    # サムネイル保存
└── .venv/             # Python仮想環境
```

## 外部公開（WSL2環境の場合）

### 🚨 重要: WSL2環境での制約

WSL2環境では、デフォルトでLAN内の他のデバイスからアクセスできません。以下のいずれかの方法で解決できます：

### 方法1: Windows ポートフォワーディング設定（推奨）

**Windows PowerShell（管理者権限）で実行：**

```powershell
# WSL2のIPアドレスを取得
$wslIP = (wsl hostname -I).Trim()

# ポートフォワーディング設定
netsh interface portproxy add v4tov4 listenport=5000 listenaddress=0.0.0.0 connectport=5000 connectaddress=$wslIP

# ファイアウォール許可
New-NetFirewallRule -DisplayName "WSL2 Flask App" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

**または自動設定スクリプト使用：**
```powershell
# PowerShell管理者権限で実行
./setup_wsl_port_forward.ps1
```

### 方法2: ngrok使用（簡単・一時的）

```bash
# ngrokセットアップ（初回のみ）
./setup_ngrok.sh

# ngrokアカウント設定後
ngrok http 5000
```

表示されるHTTPS URLをスマホでアクセス

### 方法3: WSL2設定ファイル編集

**Windows の `%USERPROFILE%\.wslconfig` ファイルを作成：**

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
firewall=false
autoProxy=true
```

**設定後、WSL2を再起動：**
```cmd
wsl --shutdown
```

## スマホからの接続確認

### iPhone/Android共通

1. **同じWiFiネットワークに接続**
2. **ブラウザで以下にアクセス：**
   - ポートフォワーディング設定済み: `http://[WindowsマシンIP]:5000`
   - ngrok使用: 表示されたHTTPS URL
3. **PWAとしてホーム画面に追加** （ブラウザメニューから）

### 接続テスト用スクリプト

```bash
# WSL2環境での設定確認
./wsl_lan_setup.sh
```

## 注意事項

- 開発サーバーなので本番環境では使用しないでください
- 外部公開する場合は適切な認証機構を追加してください
- 大容量ファイルのアップロードには時間がかかる場合があります

## トラブルシューティング

### python-magicのエラーが出る場合

**Ubuntu/Debian:**
```bash
sudo apt-get install libmagic1
```

**CentOS/RHEL:**
```bash
sudo yum install file-libs
```

**macOS:**
```bash
brew install libmagic
```

### ポート5000が使用中の場合

app.pyの最後の行を編集：
```python
app.run(host='0.0.0.0', port=8000, debug=True)  # ポート番号を変更
```
