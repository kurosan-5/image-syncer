import os
import sqlite3
import uuid
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
import mimetypes
from PIL import Image
import magic
import pillow_heif  # HEIC画像サポート
from functools import wraps
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

from flask import Flask, request, jsonify, send_file, render_template, Response, redirect, url_for, session, flash
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# セッション設定（シンプルで安定した方法）
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['SESSION_PERMANENT'] = False

# 認証設定（環境変数から取得）
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'password')

# HEIC画像サポートを有効化
pillow_heif.register_heif_opener()

# 設定
STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(exist_ok=True)

THUMBNAILS_DIR = Path("storage/thumbnails")
THUMBNAILS_DIR.mkdir(exist_ok=True)

# 外部HDDストレージのパス（環境変数から取得、デフォルトはstorageディレクトリ）
EXTERNAL_STORAGE_DIR = Path(os.environ.get('EXTERNAL_STORAGE_PATH', 'storage'))
EXTERNAL_STORAGE_DIR.mkdir(exist_ok=True)

DATABASE_PATH = "image_syncer.db"

# データベース初期化
def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            original_name TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            relative_path TEXT,
            date_folder TEXT,
            thumbnail_path TEXT,
            file_type TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER NOT NULL,
            file_hash TEXT,
            taken_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 新しいカラムが存在しない場合は追加
    cursor.execute("PRAGMA table_info(files)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'file_hash' not in columns:
        cursor.execute("ALTER TABLE files ADD COLUMN file_hash TEXT")
    if 'relative_path' not in columns:
        cursor.execute("ALTER TABLE files ADD COLUMN relative_path TEXT")
    if 'date_folder' not in columns:
        cursor.execute("ALTER TABLE files ADD COLUMN date_folder TEXT")
    if 'taken_date' not in columns:
        cursor.execute("ALTER TABLE files ADD COLUMN taken_date TIMESTAMP")
    
    # インデックスを作成
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON files(file_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_date_folder ON files(date_folder)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_taken_date ON files(taken_date)")
    
    conn.commit()
    conn.close()

# 認証関連の関数
def login_required(f):
    """ログインが必要なルートに適用するデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            if request.is_json:
                return jsonify({"error": "認証が必要です"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def check_credentials(username, password):
    """認証情報をチェック"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def get_image_taken_date(file_path):
    """画像の撮影日時を取得（EXIF情報から）"""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        
        with Image.open(file_path) as img:
            exifdata = img.getexif()
            for tag_id in exifdata:
                tag = TAGS.get(tag_id, tag_id)
                if tag == "DateTime" or tag == "DateTimeOriginal":
                    date_str = exifdata.get(tag_id)
                    if date_str:
                        try:
                            return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                        except ValueError:
                            continue
    except Exception as e:
        print(f"EXIF日時取得エラー: {e}")
    
    # EXIFから取得できない場合はファイルの作成日時を使用
    try:
        stat = Path(file_path).stat()
        return datetime.fromtimestamp(stat.st_mtime)
    except:
        return datetime.now()

def get_date_folder_name(taken_date):
    """撮影日時からフォルダ名を生成（YYYYMM形式）"""
    return taken_date.strftime("%Y%m")

def ensure_date_folder(taken_date):
    """撮影日時に対応するフォルダが存在することを確認し、なければ作成"""
    folder_name = get_date_folder_name(taken_date)
    folder_path = EXTERNAL_STORAGE_DIR / folder_name
    folder_path.mkdir(exist_ok=True)
    return folder_path, folder_name

def scan_external_storage():
    """外部ストレージの既存ファイルをスキャンしてデータベースに登録"""
    print(f"[SCAN] 外部ストレージをスキャン中: {EXTERNAL_STORAGE_DIR}")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # サポートする拡張子
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif'}
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
    
    scanned_count = 0
    added_count = 0
    
    # フォルダをスキャン
    for folder_path in EXTERNAL_STORAGE_DIR.iterdir():
        if not folder_path.is_dir():
            continue
            
        # 日付フォルダかチェック（YYYYMM形式）
        folder_name = folder_path.name
        if not (len(folder_name) == 6 and folder_name.isdigit()):
            continue
            
        print(f"[SCAN] フォルダをスキャン中: {folder_name}")
        
        # フォルダ内のファイルをスキャン
        for file_path in folder_path.rglob('*'):
            if not file_path.is_file():
                continue
                
            file_ext = file_path.suffix.lower()
            if file_ext not in image_extensions and file_ext not in video_extensions:
                continue
                
            scanned_count += 1
            
            # ファイルハッシュを計算
            try:
                file_hash = get_file_hash(str(file_path))
            except Exception as e:
                print(f"[ERROR] ハッシュ計算エラー: {file_path}, {e}")
                continue
            
            # 既にデータベースに存在するかチェック
            cursor.execute("SELECT id FROM files WHERE file_hash = ?", (file_hash,))
            if cursor.fetchone():
                continue  # 既に存在する
            
            # ファイル情報を取得
            try:
                file_size = file_path.stat().st_size
                file_type = 'image' if file_ext in image_extensions else 'video'
                mime_type = mimetypes.guess_type(str(file_path))[0]
                
                # 撮影日時を取得
                taken_date = get_image_taken_date(str(file_path))
                
                # 相対パスを計算
                relative_path = str(file_path.relative_to(EXTERNAL_STORAGE_DIR))
                
                # データベースに追加
                file_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO files (
                        id, original_name, filename, file_path, relative_path, 
                        date_folder, file_type, mime_type, file_size, file_hash, taken_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_id, file_path.name, file_path.name, str(file_path),
                    relative_path, folder_name, file_type, mime_type, file_size, file_hash, taken_date
                ))
                
                added_count += 1
                
                if added_count % 100 == 0:
                    print(f"[SCAN] {added_count}件のファイルを追加済み...")
                    conn.commit()
                    
            except Exception as e:
                print(f"[ERROR] ファイル処理エラー: {file_path}, {e}")
                continue
    
    conn.commit()
    conn.close()
    
    print(f"[SCAN] スキャン完了: {scanned_count}件スキャン, {added_count}件新規追加")
    return scanned_count, added_count

def create_thumbnail(file_path, thumbnail_path, size=(200, 200)):
    """画像のサムネイルを作成"""
    try:
        with Image.open(file_path) as img:
            # EXIF情報を考慮して回転
            img = img.convert('RGB')
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumbnail_path, 'JPEG', quality=85)
            return True
    except Exception as e:
        print(f"サムネイル作成エラー: {e}")
        return False

def create_video_thumbnail(video_path, thumbnail_path):
    """動画の最初のフレームからサムネイルを作成"""
    try:
        import subprocess
        # FFmpegを使用して最初のフレームを取得
        command = [
            'ffmpeg',
            '-i', str(video_path),
            '-ss', '00:00:01',  # 1秒目のフレーム
            '-vframes', '1',    # 1フレームのみ
            '-vf', 'scale=200:200:force_original_aspect_ratio=decrease',
            '-y',               # 上書き
            str(thumbnail_path)
        ]
        
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            return True
        else:
            print(f"FFmpeg エラー: {result.stderr}")
            return False
    except Exception as e:
        print(f"動画サムネイル作成エラー: {e}")
        return False

def get_file_type(file_path):
    """ファイルタイプを判定"""
    mime = magic.from_file(str(file_path), mime=True)
    if mime.startswith('image/'):
        return 'image'
    elif mime.startswith('video/'):
        return 'video'
    else:
        return 'other'

def get_file_hash(file_path):
    """ファイルのSHA256ハッシュを計算"""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def convert_heic_to_jpeg(heic_path, jpeg_path, quality=90):
    """HEICファイルをJPEGに変換"""
    try:
        with Image.open(heic_path) as img:
            # RGBモードに変換（JPEG用）
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # JPEGで保存
            img.save(jpeg_path, 'JPEG', quality=quality, optimize=True)
            return True
    except Exception as e:
        print(f"HEIC変換エラー: {e}")
        return False

# 認証ルート
@app.route('/login', methods=['GET', 'POST'])
def login():
    """ログインページ"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if check_credentials(username, password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='ユーザー名またはパスワードが正しくありません')
    
    # 既にログインしている場合はメインページにリダイレクト
    if session.get('logged_in'):
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """ログアウト"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """PWAフロントエンド"""
    return render_template('index.html')

@app.route('/manifest.json')
def manifest():
    """PWAマニフェスト"""
    return jsonify({
        "name": "Image Syncer",
        "short_name": "ImageSync",
        "description": "写真とビデオのシンクアプリ",
        "start_url": "/",
        "display": "standalone",
        "orientation": "portrait",
        "theme_color": "#007bff",
        "background_color": "#ffffff",
        "categories": ["photo", "utilities"],
        "icons": [
            {
                "src": "/static/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    })

@app.route('/sw.js')
def service_worker():
    """Service Worker"""
    return send_file('static/sw.js', mimetype='application/javascript')

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """ファイルアップロード"""
    # リクエスト詳細をログ出力
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'Unknown')
    print(f"[UPLOAD] Client: {client_ip}, User-Agent: {user_agent}")
    
    # 'files' または 'image' キーに対応
    files = []
    if 'files' in request.files:
        files = request.files.getlist('files')
        print(f"[UPLOAD] Found {len(files)} files in 'files' key")
    elif 'image' in request.files:
        files = request.files.getlist('image')
        print(f"[UPLOAD] Found {len(files)} files in 'image' key")
    
    if not files:
        print("[UPLOAD] No files found in request")
        return jsonify({"error": "ファイルが選択されていません"}), 400
    uploaded_files = []
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        for file in files:
            if file.filename == '':
                continue
            
            print(f"[UPLOAD] Processing file: {file.filename}")
                
            # 一時保存してメタデータ抽出
            file_id = str(uuid.uuid4())
            original_name = file.filename
            file_ext = Path(original_name).suffix.lower()
            temp_filename = f"temp_{file_id}{file_ext}"
            temp_file_path = STORAGE_DIR / temp_filename
            
            # 一時ファイル保存
            file.save(temp_file_path)
            
            # 撮影日時を取得
            taken_date = get_image_taken_date(str(temp_file_path))
            print(f"[UPLOAD] Detected taken date: {taken_date}")
            
            # 適切なフォルダを確保
            date_folder_path, date_folder_name = ensure_date_folder(taken_date)
            
            # 最終的なファイル名とパス
            filename = f"{file_id}{file_ext}"
            final_file_path = date_folder_path / filename
            
            # HEICファイルの場合はJPEGに変換
            if file_ext.lower() == '.heic':
                print(f"[UPLOAD] Converting HEIC to JPEG: {original_name}")
                # JPEG用の新しいファイルパスを作成
                jpeg_filename = f"{file_id}.jpg"
                jpeg_file_path = date_folder_path / jpeg_filename
                
                if convert_heic_to_jpeg(temp_file_path, jpeg_file_path):
                    # 変換成功：一時ファイルを削除し、JPEGを使用
                    temp_file_path.unlink()
                    final_file_path = jpeg_file_path
                    filename = jpeg_filename
                    file_ext = '.jpg'
                    print(f"[UPLOAD] HEIC converted to JPEG: {filename}")
                else:
                    print(f"[UPLOAD] HEIC conversion failed, keeping original file")
                    # 変換失敗の場合は元ファイルを移動
                    shutil.move(str(temp_file_path), str(final_file_path))
            else:
                # 通常ファイルは移動
                shutil.move(str(temp_file_path), str(final_file_path))
            
            # ハッシュ計算（最終ファイルに対して）
            file_hash = get_file_hash(final_file_path)
            print(f"[UPLOAD] File hash: {file_hash}")
            
            # 重複チェック
            cursor.execute("SELECT id, original_name FROM files WHERE file_hash = ?", (file_hash,))
            existing_file = cursor.fetchone()
            
            if existing_file:
                print(f"[UPLOAD] Duplicate file detected! Existing: {existing_file[1]}")
                # 重複ファイルの場合は削除して既存ファイル情報を返す
                final_file_path.unlink()
                uploaded_files.append({
                    "id": existing_file[0],
                    "original_name": existing_file[1],
                    "status": "duplicate",
                    "message": f"ファイル '{original_name}' は既にアップロード済みです"
                })
                continue
            
            # ファイル情報取得
            file_size = final_file_path.stat().st_size
            file_type = get_file_type(final_file_path)
            mime_type = magic.from_file(str(final_file_path), mime=True)
            
            # HEICからJPEGに変換した場合は、MIME typeを修正
            if file_ext == '.jpg' and original_name.lower().endswith('.heic'):
                mime_type = 'image/jpeg'
            
            # 相対パスを計算
            relative_path = str(final_file_path.relative_to(EXTERNAL_STORAGE_DIR))
            
            # サムネイル作成（動画の場合のみ - 画像は元画像を使用）
            thumbnail_path = None
            if file_type == 'video':
                thumbnail_filename = f"thumb_{file_id}.jpg"
                thumbnail_path = THUMBNAILS_DIR / thumbnail_filename
                if create_video_thumbnail(final_file_path, thumbnail_path):
                    thumbnail_path = str(thumbnail_path)
                else:
                    thumbnail_path = None
            
            # データベースに保存
            cursor.execute("""
                INSERT INTO files (
                    id, original_name, filename, file_path, relative_path, 
                    date_folder, thumbnail_path, file_type, mime_type, 
                    file_size, file_hash, taken_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id, original_name, filename, str(final_file_path), relative_path,
                date_folder_name, thumbnail_path, file_type, mime_type, 
                file_size, file_hash, taken_date
            ))
            
            print(f"[UPLOAD] Successfully uploaded: {original_name} -> {date_folder_name}/{filename}")
            uploaded_files.append({
                "id": file_id,
                "original_name": original_name,
                "filename": filename,
                "file_type": file_type,
                "file_size": file_size,
                "date_folder": date_folder_name,
                "status": "uploaded"
            })
        
        conn.commit()
        return jsonify({
            "message": f"{len(uploaded_files)}個のファイルがアップロードされました",
            "files": uploaded_files
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"アップロードエラー: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/scan', methods=['POST'])
@login_required
def scan_storage():
    """外部ストレージをスキャンしてデータベースに登録"""
    try:
        scanned_count, added_count = scan_external_storage()
        return jsonify({
            "message": f"スキャン完了: {scanned_count}件スキャン, {added_count}件新規追加",
            "scanned": scanned_count,
            "added": added_count
        })
    except Exception as e:
        return jsonify({"error": f"スキャンエラー: {str(e)}"}), 500

@app.route('/cleanup', methods=['POST'])
def cleanup_database():
    """データベースとファイルシステムの整合性をチェックし、不整合なエントリを削除"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # データベース内の全ファイルを取得
    cursor.execute("SELECT id, file_path, thumbnail_path FROM files")
    db_files = cursor.fetchall()
    
    cleaned_files = []
    for file_id, file_path, thumbnail_path in db_files:
        # ファイルが存在しない場合は削除
        if not Path(file_path).exists():
            print(f"[CLEANUP] Removing missing file from DB: {file_id} ({file_path})")
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            cleaned_files.append(file_id)
        # サムネイルが指定されているが存在しない場合はNULLに更新
        elif thumbnail_path and not Path(thumbnail_path).exists():
            print(f"[CLEANUP] Clearing missing thumbnail for: {file_id} ({thumbnail_path})")
            cursor.execute("UPDATE files SET thumbnail_path = NULL WHERE id = ?", (file_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "message": f"クリーンアップ完了: {len(cleaned_files)}個の不整合エントリを削除",
        "cleaned_files": cleaned_files
    })

@app.route('/files', methods=['GET'])
@login_required
def list_files():
    """ファイル一覧取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, original_name, filename, file_type, file_size, created_at
        FROM files
        ORDER BY created_at DESC
    """)
    
    files = []
    for row in cursor.fetchall():
        files.append({
            "id": row[0],
            "original_name": row[1],
            "filename": row[2],
            "file_type": row[3],
            "file_size": row[4],
            "created_at": row[5]
        })
    
    # デバッグ用ログ
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'Unknown')
    print(f"[DEBUG] /files request from {client_ip}, returning {len(files)} files: {[f['id'] for f in files]}")
    
    conn.close()
    
    response = jsonify({"files": files})
    # キャッシュを無効にする
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/files/<file_id>', methods=['GET'])
@login_required
def get_file(file_id):
    """ファイル取得"""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT file_path, original_name, mime_type FROM files WHERE id = ?", (file_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print(f"[DEBUG] File {file_id} not found in database")
        return jsonify({"error": "ファイルが見つかりません"}), 404
    
    file_path, original_name, mime_type = result
    
    if not Path(file_path).exists():
        print(f"[DEBUG] File {file_id} not found on disk: {file_path}")
        return jsonify({"error": "ファイルが存在しません"}), 404
    
    print(f"[DEBUG] /files/{file_id} request from {client_ip} ({user_agent})")
    
    # キャッシュヘッダーを追加してRange Requestを制御
    response = send_file(
        file_path, 
        as_attachment=False, 
        download_name=original_name, 
        mimetype=mime_type,
        conditional=True  # ETagとLast-Modifiedを有効化
    )
    
    # キャッシュヘッダーを設定
    response.headers['Cache-Control'] = 'public, max-age=31536000'  # 1年間キャッシュ
    response.headers['Accept-Ranges'] = 'bytes'  # Range Requestを許可
    
    return response

@app.route('/thumbnails/<file_id>', methods=['GET'])
@login_required
def get_thumbnail(file_id):
    """サムネイル取得（画像の場合は元画像、動画の場合はサムネイル）"""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'Unknown')
    print(f"[DEBUG] /thumbnails/{file_id} request from {client_ip} ({user_agent})")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT file_path, thumbnail_path, file_type, mime_type FROM files WHERE id = ?", (file_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print(f"[DEBUG] Thumbnail for {file_id} not found in database")
        return jsonify({"error": "ファイルが見つかりません"}), 404
    
    file_path, thumbnail_path, file_type, mime_type = result
    
    # 画像の場合は元画像を返す（HEICは既にJPEGに変換済み）
    if file_type == 'image':
        if Path(file_path).exists():
            response = send_file(file_path, mimetype=mime_type, conditional=True)
            response.headers['Cache-Control'] = 'public, max-age=86400'  # 24時間キャッシュ
            return response
        else:
            print(f"[DEBUG] Image file {file_id} not found on disk: {file_path}")
            return jsonify({"error": "ファイルが存在しません"}), 404
    
    # 動画の場合はサムネイルを返す
    if thumbnail_path and Path(thumbnail_path).exists():
        response = send_file(thumbnail_path, mimetype='image/jpeg', conditional=True)
        response.headers['Cache-Control'] = 'public, max-age=86400'  # 24時間キャッシュ
        return response
    
    # サムネイルがない場合はデフォルト画像やエラーを返す
    print(f"[DEBUG] Thumbnail for {file_id} not found on disk: {thumbnail_path}")
    return jsonify({"error": "サムネイルが見つかりません"}), 404

@app.route('/files/<file_id>', methods=['DELETE'])
@login_required
def delete_file(file_id):
    """ファイル削除"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT file_path, thumbnail_path FROM files WHERE id = ?", (file_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({"error": "ファイルが見つかりません"}), 404
    
    file_path, thumbnail_path = result
    
    try:
        # ファイル削除
        if Path(file_path).exists():
            Path(file_path).unlink()
        
        # サムネイル削除
        if thumbnail_path and Path(thumbnail_path).exists():
            Path(thumbnail_path).unlink()
        
        # データベースから削除
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"message": "ファイルが削除されました"})
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"削除エラー: {str(e)}"}), 500

# Service Worker

SERVICE_WORKER_JS = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Image Syncer</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#007bff">
    
    <!-- PWA用メタタグ -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="ImageSync">
    <meta name="mobile-web-app-capable" content="yes">
    
    <!-- アドレスバー非表示を促進 -->
    <meta name="format-detection" content="telephone=no">
    <meta name="msapplication-tap-highlight" content="no">
    <style>
        :root {
            /* カスタムプロパティでビューポート高さを動的に設定 */
            --vh: 1vh;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        html {
            /* モバイルでのスクロール問題を解決 */
            height: 100%;
            overflow-x: hidden;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f8f9fa;
            line-height: 1.6;
            /* 初期は標準の高さ */
            min-height: 100vh;
            height: auto;
            /* iOS Safari でのスクロールバウンスを無効化 */
            -webkit-overflow-scrolling: touch;
            /* モバイルでのタップハイライトを無効化 */
            -webkit-tap-highlight-color: transparent;
        }
        
        .header {
            background: linear-gradient(135deg, #007bff, #0056b3);
            color: white;
            padding: 1rem;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 1rem;
        }
        
        .upload-section {
            background: white;
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }
        
        .upload-area {
            border: 3px dashed #007bff;
            border-radius: 12px;
            padding: 3rem;
            text-align: center;
            background: #f8f9ff;
            transition: all 0.3s ease;
            cursor: pointer;
            /* モバイルタッチ対応 */
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
            user-select: none;
            /* タッチ時のハイライト無効化 */
            -webkit-tap-highlight-color: transparent;
        }
        
        .upload-area:hover,
        .upload-area:focus,
        .upload-area:active {
            background: #f0f4ff;
            border-color: #0056b3;
            outline: none;
        }
        
        .upload-area.dragover {
            background: #e3f2fd;
            border-color: #1976d2;
        }
        
        .file-input {
            display: none;
        }
        
        .upload-btn {
            background: #007bff;
            color: white;
            border: none;
            padding: 1rem 2rem;
            border-radius: 8px;
            font-size: 1.1rem;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 1rem;
            /* モバイルタッチ対応 */
            -webkit-tap-highlight-color: transparent;
            min-height: 44px; /* iOS推奨タッチターゲットサイズ */
            min-width: 44px;
        }
        
        .upload-btn:hover,
        .upload-btn:focus {
            background: #0056b3;
            transform: translateY(-2px);
            outline: none;
        }
        
        .upload-btn:active {
            transform: translateY(0);
        }
        
        .upload-btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
        }
        
        .files-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-top: 2rem;
        }
        
        .file-card {
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        
        .file-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.15);
        }
        
        .file-preview {
            width: 100%;
            height: 200px;
            object-fit: cover;
            background: #f8f9fa;
        }
        
        .file-info {
            padding: 1rem;
        }
        
        .file-name {
            font-weight: 600;
            margin-bottom: 0.5rem;
            word-break: break-word;
        }
        
        .file-meta {
            color: #6c757d;
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }
        
        .file-actions {
            display: flex;
            gap: 0.5rem;
        }
        
        .btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
            font-size: 0.9rem;
        }
        
        .btn-primary {
            background: #007bff;
            color: white;
        }
        
        .btn-danger {
            background: #dc3545;
            color: white;
        }
        
        .btn:hover {
            transform: translateY(-1px);
        }
        
        .loading {
            text-align: center;
            padding: 2rem;
            color: #6c757d;
        }
        
        .video-placeholder {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 200px;
            background: #e9ecef;
            color: #6c757d;
            font-size: 1.2rem;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 0.5rem;
            }
            
            .upload-section {
                padding: 1rem;
                margin-bottom: 1rem;
            }
            
            .upload-area {
                padding: 2rem 1rem;
            }
            
            .files-grid {
                grid-template-columns: 1fr;
                gap: 1rem;
            }
            
            /* モバイル専用のスクロール改善 */
            body {
                /* 初期状態では制御を緩める */
                overscroll-behavior-x: none;
                overscroll-behavior-y: auto;
            }
            
            /* アドレスバーが隠れた後の安定化 */
            body.address-bar-hidden {
                overscroll-behavior-y: contain;
            }
            
            /* モバイルでのタッチ操作改善 */
            .file-card {
                /* タッチ時のスケール変更を軽減 */
                transform: none;
            }
            
            .file-card:active {
                transform: scale(0.98);
            }
            
            /* iOS Safari でのビューポート問題対策 */
            .header {
                position: relative;
                z-index: 10;
            }
        }
        
        /* 極小画面対応 */
        @media (max-width: 480px) {
            .upload-area {
                padding: 1.5rem 0.5rem;
            }
            
            .upload-btn {
                width: 100%;
                padding: 1rem;
            }
            
            .file-actions {
                flex-direction: column;
                gap: 0.5rem;
            }
            
            .btn {
                width: 100%;
                padding: 0.75rem;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📱 Image Syncer</h1>
        <p>スマホの写真を自動同期</p>
    </div>
    
    <div class="container">
        <div class="upload-section">
            <div class="upload-area" id="uploadArea">
                <div style="font-size: 3rem; margin-bottom: 1rem;">📁</div>
                <h3>ファイルをドロップまたはクリックして選択あ</h3>
                <p style="color: #6c757d; margin-top: 0.5rem;">画像・動画ファイルをサポート</p>
                <input type="file" id="fileInput" class="file-input" multiple accept="image/*,video/*">
                <button class="upload-btn" id="uploadBtn" onclick="document.getElementById('fileInput').click()">
                    ファイルを選択
                </button>
            </div>
        </div>
        
        <div id="filesList">
            <div class="loading">ファイルを読み込み中...</div>
        </div>
        
        <!-- アドレスバー非表示のための動的余白エリア -->
        <div style="height: 50px; background: transparent; transition: height 0.3s ease;" id="addressBarSpacer"></div>
    </div>

    <script>
        // ビューポート高さの動的計算（モバイル対応）
        let initialViewportHeight = window.innerHeight;
        let addressBarHidden = false;
        let stabilizeTimeout;
        
        function setViewportHeight() {
            const vh = window.innerHeight * 0.01;
            document.documentElement.style.setProperty('--vh', `${vh}px`);
            
            // アドレスバーの状態を正確に検出
            const heightDifference = Math.abs(window.innerHeight - initialViewportHeight);
            const isAddressBarNowHidden = heightDifference > 50; // 50px以上の差でアドレスバーが隠れたと判定
            
            if (isAddressBarNowHidden && !addressBarHidden) {
                // アドレスバーが隠れた時の処理
                addressBarHidden = true;
                document.body.classList.add('address-bar-hidden');
                
                // 一定時間後にスクロール制御を強化
                clearTimeout(stabilizeTimeout);
                stabilizeTimeout = setTimeout(() => {
                    // コンテンツ高さを調整してスクロール領域を最適化
                    const spacer = document.getElementById('addressBarSpacer');
                    if (spacer) {
                        spacer.style.height = '0px';
                    }
                }, 1000);
                
            } else if (!isAddressBarNowHidden && addressBarHidden) {
                // アドレスバーが再表示された時の処理
                addressBarHidden = false;
                document.body.classList.remove('address-bar-hidden');
                
                // スペーサーを復活
                const spacer = document.getElementById('addressBarSpacer');
                if (spacer) {
                    spacer.style.height = '50px';
                }
            }
        }
        
        // 初期設定
        setViewportHeight();
        
        // リサイズ時の再計算（デバウンス処理）
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(setViewportHeight, 100);
        });
        
        // オリエンテーション変更時の再計算
        window.addEventListener('orientationchange', () => {
            setTimeout(setViewportHeight, 500);
        });
        
        // スクロール位置の復元防止（iOS Safari対策）
        let scrollPosition = 0;
        let ticking = false;
        let isScrolling = false;
        let scrollTimer;
        
        function updateScrollPosition() {
            scrollPosition = window.pageYOffset;
            ticking = false;
            
            // スクロール終了を検出
            clearTimeout(scrollTimer);
            scrollTimer = setTimeout(() => {
                isScrolling = false;
            }, 150);
        }
        
        // アドレスバー非表示を促すスクロールトリガー
        function triggerAddressBarHide() {
            // アドレスバーが表示されており、まだ隠れていない場合のみ実行
            if (!addressBarHidden && window.innerHeight < initialViewportHeight) {
                const currentScroll = window.pageYOffset;
                
                // より自然なスクロールアニメーションでアドレスバーを隠す
                let scrollStep = 0;
                const targetScroll = Math.min(currentScroll + 100, document.body.scrollHeight - window.innerHeight);
                
                function smoothScrollStep() {
                    scrollStep += 5;
                    const newScroll = currentScroll + scrollStep;
                    
                    if (newScroll < targetScroll && scrollStep < 100) {
                        window.scrollTo(0, newScroll);
                        requestAnimationFrame(smoothScrollStep);
                    } else {
                        // 少し下にスクロールした後、自然に元の位置に戻る
                        setTimeout(() => {
                            if (!isScrolling) { // ユーザーがスクロールしていない場合のみ
                                window.scrollTo({
                                    top: currentScroll,
                                    behavior: 'smooth'
                                });
                            }
                        }, 300);
                    }
                }
                
                smoothScrollStep();
            }
        }
        
        // ページロード後にアドレスバー非表示をトリガー
        window.addEventListener('load', () => {
            // 初期ビューポート高さを記録
            initialViewportHeight = window.innerHeight;
            
            // 少し待ってからアドレスバー非表示を試行
            setTimeout(() => {
                if (!isScrolling) {
                    triggerAddressBarHide();
                }
            }, 1000);
        });
        
        // タッチ操作後にアドレスバー非表示をトリガー
        let touchTriggered = false;
        document.addEventListener('touchend', () => {
            if (!touchTriggered && !isScrolling) {
                setTimeout(() => {
                    if (!isScrolling && !addressBarHidden) {
                        triggerAddressBarHide();
                    }
                }, 300);
                touchTriggered = true;
                
                // 一定時間後にフラグをリセット
                setTimeout(() => {
                    touchTriggered = false;
                }, 3000);
            }
        });
        
        window.addEventListener('scroll', () => {
            isScrolling = true;
            if (!ticking) {
                requestAnimationFrame(updateScrollPosition);
                ticking = true;
            }
        });
        
        // タッチ開始時にスクロール状態をリセット
        document.addEventListener('touchstart', () => {
            isScrolling = true;
        });
        
        // タッチ終了時の処理
        document.addEventListener('touchend', () => {
            setTimeout(() => {
                if (!isScrolling && !addressBarHidden) {
                    triggerAddressBarHide();
                }
            }, 200);
        });
        
        // Service Worker登録
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js')
                    .then(registration => console.log('SW registered'))
                    .catch(error => console.log('SW registration failed'));
            });
        }

        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        
        // モバイルでのタッチ操作を改善
        let touchStartTime = 0;
        let isDragging = false;
        
        // ドラッグ&ドロップ（デスクトップ用）
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (!isDragging) {
                uploadArea.classList.add('dragover');
                isDragging = true;
            }
        });
        
        uploadArea.addEventListener('dragleave', (e) => {
            // ドラッグエリアから完全に離れた場合のみリセット
            if (!uploadArea.contains(e.relatedTarget)) {
                uploadArea.classList.remove('dragover');
                isDragging = false;
            }
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            isDragging = false;
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFiles(files);
            }
        });
        
        // タッチ操作（モバイル用）
        uploadArea.addEventListener('touchstart', (e) => {
            touchStartTime = Date.now();
        });
        
        uploadArea.addEventListener('touchend', (e) => {
            const touchDuration = Date.now() - touchStartTime;
            // 短いタップの場合のみファイル選択を開く
            if (touchDuration < 300 && !isDragging) {
                e.preventDefault();
                fileInput.click();
            }
        });
        
        // クリック操作（デスクトップ用）
        uploadArea.addEventListener('click', (e) => {
            // タッチデバイスでない場合のみクリック処理
            if (!('ontouchstart' in window)) {
                fileInput.click();
            }
        });
        
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });
        
        async function handleFiles(files) {
            if (files.length === 0) return;
            
            const formData = new FormData();
            for (let file of files) {
                formData.append('files', file);
            }
            
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'アップロード中...';
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    alert(result.message);
                    loadFiles();
                } else {
                    alert('エラー: ' + result.error);
                }
            } catch (error) {
                alert('アップロードに失敗しました: ' + error.message);
            } finally {
                uploadBtn.disabled = false;
                uploadBtn.textContent = 'ファイルを選択';
                fileInput.value = '';
            }
        }
        
        async function loadFiles() {
            try {
                const response = await fetch('/files');
                const data = await response.json();
                displayFiles(data.files);
            } catch (error) {
                document.getElementById('filesList').innerHTML = 
                    '<div class="loading">ファイルの読み込みに失敗しました</div>';
            }
        }
        
        function displayFiles(files) {
            const filesList = document.getElementById('filesList');
            
            if (files.length === 0) {
                filesList.innerHTML = '<div class="loading">ファイルがありません</div>';
                return;
            }
            
            const grid = document.createElement('div');
            grid.className = 'files-grid';
            
            files.forEach(file => {
                const card = document.createElement('div');
                card.className = 'file-card';
                
                const previewElement = file.file_type === 'image' 
                    ? `<img src="/thumbnails/${file.id}" class="file-preview" alt="${file.original_name}" onerror="this.src='/files/${file.id}'">`
                    : `<div class="video-placeholder">🎥 ${file.file_type.toUpperCase()}</div>`;
                
                card.innerHTML = `
                    ${previewElement}
                    <div class="file-info">
                        <div class="file-name">${file.original_name}</div>
                        <div class="file-meta">
                            ${formatFileSize(file.file_size)} • ${formatDate(file.created_at)}
                        </div>
                        <div class="file-actions">
                            <a href="/files/${file.id}" target="_blank" class="btn btn-primary">開く</a>
                            <button class="btn btn-danger" onclick="deleteFile('${file.id}')">削除</button>
                        </div>
                    </div>
                `;
                
                grid.appendChild(card);
            });
            
            filesList.innerHTML = '';
            filesList.appendChild(grid);
        }
        
        async function deleteFile(fileId) {
            if (!confirm('このファイルを削除しますか？')) return;
            
            try {
                const response = await fetch(`/files/${fileId}`, {
                    method: 'DELETE'
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    alert(result.message);
                    loadFiles();
                } else {
                    alert('エラー: ' + result.error);
                }
            } catch (error) {
                alert('削除に失敗しました: ' + error.message);
            }
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function formatDate(dateString) {
            return new Date(dateString).toLocaleString('ja-JP');
        }
        
        // 初期読み込み
        loadFiles();
    </script>
</body>
</html>
"""

# Service Worker
SERVICE_WORKER_JS = """
const CACHE_NAME = 'image-syncer-v1';
const urlsToCache = [
    '/',
    '/manifest.json'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(urlsToCache))
    );
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                if (response) {
                    return response;
                }
                return fetch(event.request);
            })
    );
});
"""

if __name__ == '__main__':
    init_db()
    
    # 外部ストレージの自動スキャン（環境変数で制御）
    auto_scan = os.environ.get('AUTO_SCAN_STORAGE', 'true').lower() == 'true'
    if auto_scan:
        print("[STARTUP] Auto-scanning external storage...")
        try:
            scanned_count, added_count = scan_external_storage()
            print(f"[STARTUP] Auto-scan completed: {scanned_count} scanned, {added_count} added")
        except Exception as e:
            print(f"[STARTUP] Auto-scan failed: {e}")
    
    # デバッグ: 起動時にデータベースの内容を確認
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, original_name, file_type FROM files")
    all_files = cursor.fetchall()
    print(f"[STARTUP] Database contains {len(all_files)} files:")
    for file_id, name, file_type in all_files:
        print(f"  - {file_id}: {name} ({file_type})")
    conn.close()
    
    # 外部ストレージパスの表示
    print(f"[STARTUP] External storage path: {EXTERNAL_STORAGE_DIR}")
    print(f"[STARTUP] Thumbnails path: {THUMBNAILS_DIR}")
    
    # LAN内アクセス用の設定
    print("=" * 50)
    print("Image Syncer サーバーを起動中...")
    print("=" * 50)
    print("ローカルアクセス: http://127.0.0.1:5000")
    print("LAN内アクセス: http://172.26.155.97:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)