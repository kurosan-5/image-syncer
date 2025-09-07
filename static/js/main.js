// iPhone写真アプリ風のJavaScript

class PhotoApp {
    constructor() {
        this.files = [];
        this.selectedFiles = new Set();
        this.isSelectionMode = false;
        this.currentViewerIndex = 0;
        this.isViewerUIVisible = true;
        
        // DOM要素
        this.uploadSection = document.getElementById('uploadSection');
        this.photoGrid = document.getElementById('photoGrid');
        this.fileInput = document.getElementById('fileInput');
        this.uploadArea = document.getElementById('uploadArea');
        this.loadingIndicator = document.getElementById('loadingIndicator');
        this.photoViewer = document.getElementById('photoViewer');
        this.viewerContent = document.getElementById('viewerContent');
        this.viewerInfo = document.getElementById('viewerInfo');
        
        // ナビゲーション要素
        this.selectBtn = document.getElementById('selectBtn');
        this.fabUpload = document.getElementById('fabUpload');
        this.selectionActions = document.getElementById('selectionActions');
        this.downloadSelected = document.getElementById('downloadSelected');
        this.deleteSelected = document.getElementById('deleteSelected');
        
        // ビューア
        this.viewerClose = document.getElementById('viewerClose');
        this.viewerShare = document.getElementById('viewerShare');
        this.viewerDelete = document.getElementById('viewerDelete');
        
        // ビューア内の要素（使用しない - CSSで制御）
        // this.viewerHeader = document.querySelector('#photoViewer .viewer-header');
        this.viewerInfo = document.getElementById('viewerInfo');
        
        this.init();
    }
    
    init() {
        // デバッグ: ブラウザキャッシュとStorageの状況をログ出力
        console.log('=== BROWSER CACHE DEBUG ===');
        console.log('LocalStorage keys:', Object.keys(localStorage));
        console.log('SessionStorage keys:', Object.keys(sessionStorage));
        
        // グローバルからアクセスできるようにする
        window.photoApp = this;
        window.debugClearCache = () => {
            localStorage.clear();
            sessionStorage.clear();
            if ('caches' in window) {
                caches.keys().then(names => {
                    names.forEach(name => caches.delete(name));
                });
            }
            location.reload(true);
        };
        console.log('デバッグ: window.debugClearCache() でキャッシュクリア可能');
        
        this.setupServiceWorker();
        this.setupEventListeners();
        this.loadFiles();
    }
    
    // Service Worker登録
    setupServiceWorker() {
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js')
                    .then(registration => {
                        console.log('Service Worker registered successfully');
                        // 既存のService Workerがある場合は更新
                        if (registration.waiting) {
                            registration.waiting.postMessage({ action: 'skipWaiting' });
                        }
                    })
                    .catch(error => console.log('Service Worker registration failed:', error));
            });
        }
    }
    
    // イベントリスナーの設定
    setupEventListeners() {
        // ファイルアップロード
        this.fileInput.addEventListener('change', (e) => {
            this.handleFiles(e.target.files);
        });
        
        // ドラッグ&ドロップ
        this.setupDragAndDrop();
        
        // ナビゲーション
        this.selectBtn.addEventListener('click', () => this.toggleSelectionMode());
        this.fabUpload.addEventListener('click', () => this.openFileSelector());
        
        // スキャンボタン
        const scanStorageBtn = document.getElementById('scanStorageBtn');
        if (scanStorageBtn) {
            scanStorageBtn.addEventListener('click', () => this.scanExternalStorage());
        }
        
        // 選択時のアクション
        this.downloadSelected.addEventListener('click', () => this.downloadSelectedFiles());
        this.deleteSelected.addEventListener('click', () => this.deleteSelectedFiles());
        
        // アップロードエリアクリック
        this.uploadArea.addEventListener('click', () => this.openFileSelector());
        
        // ビューア
        this.viewerClose.addEventListener('click', () => this.closeViewer());
        this.viewerShare.addEventListener('click', () => this.shareCurrentFile());
        this.viewerDelete.addEventListener('click', () => this.deleteCurrentFile());
        
        // ビューアにスワイプ機能を追加（タップでのUI切り替えも含む）
        this.setupSwipeGestures();
        
        // キーボードイベント
        document.addEventListener('keydown', (e) => this.handleKeydown(e));
        
        // ハプティックフィードバック（iOS Safari対応）
        this.setupHapticFeedback();
    }
    
    setupDragAndDrop() {
        let isDragging = false;
        
        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (!isDragging) {
                this.uploadArea.classList.add('dragover');
                isDragging = true;
            }
        });
        
        this.uploadArea.addEventListener('dragleave', (e) => {
            if (!this.uploadArea.contains(e.relatedTarget)) {
                this.uploadArea.classList.remove('dragover');
                isDragging = false;
            }
        });
        
        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('dragover');
            isDragging = false;
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFiles(files);
            }
        });
    }
    
    setupHapticFeedback() {
        // iOS Safari でのハプティックフィードバック
        const createHapticFeedback = (type) => {
            if ('vibrate' in navigator) {
                const patterns = {
                    light: [10],
                    medium: [50],
                    heavy: [100]
                };
                navigator.vibrate(patterns[type] || patterns.light);
            }
        };
        
        // 各種ボタンにハプティックフィードバックを追加
        document.querySelectorAll('.nav-btn, .fab, .viewer-btn').forEach(btn => {
            btn.addEventListener('touchstart', () => createHapticFeedback('light'));
        });
        
        // 写真選択時
        this.photoGrid.addEventListener('touchstart', (e) => {
            if (e.target.closest('.photo-item')) {
                createHapticFeedback('light');
            }
        });
    }
    
    // スワイプジェスチャーの設定
    setupSwipeGestures() {
        let startX = 0;
        let startY = 0;
        let endX = 0;
        let endY = 0;
        let isSwipping = false;
        let startTime = 0;
        let hasMoved = false;
        
        // タッチ開始
        this.viewerContent.addEventListener('touchstart', (e) => {
            if (!this.photoViewer.classList.contains('active')) return;
            
            const touch = e.touches[0];
            startX = touch.clientX;
            startY = touch.clientY;
            endX = startX;
            endY = startY;
            isSwipping = true;
            startTime = Date.now();
            hasMoved = false;
        }, { passive: true });
        
        // タッチ移動
        this.viewerContent.addEventListener('touchmove', (e) => {
            if (!isSwipping || !this.photoViewer.classList.contains('active')) return;
            
            const touch = e.touches[0];
            endX = touch.clientX;
            endY = touch.clientY;
            
            const deltaX = Math.abs(endX - startX);
            const deltaY = Math.abs(endY - startY);
            
            // 移動が検出されたらフラグを立てる
            if (deltaX > 10 || deltaY > 10) {
                hasMoved = true;
            }
            
            // 水平スワイプの場合のみスクロールを防止
            if (deltaX > deltaY && deltaX > 20) {
                e.preventDefault();
            }
        }, { passive: false });
        
        // タッチ終了
        this.viewerContent.addEventListener('touchend', (e) => {
            if (!isSwipping || !this.photoViewer.classList.contains('active')) return;
            
            const deltaX = endX - startX;
            const deltaY = endY - startY;
            const minSwipeDistance = 50; // 最小スワイプ距離
            const maxTapTime = 300; // タップとみなす最大時間（ms）
            const touchDuration = Date.now() - startTime;
            
            // タップかスワイプかを判定
            if (!hasMoved && touchDuration < maxTapTime && Math.abs(deltaX) < 10 && Math.abs(deltaY) < 10) {
                // タップとして扱う - UI切り替え
                this.toggleViewerUI();
            } else if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > minSwipeDistance) {
                // スワイプとして扱う
                if (deltaX > 0) {
                    // 右スワイプ（前の画像）
                    this.navigateViewer(-1);
                } else {
                    // 左スワイプ（次の画像）
                    this.navigateViewer(1);
                }
                
                // ハプティックフィードバック
                if ('vibrate' in navigator) {
                    navigator.vibrate([30]);
                }
            }
            
            // リセット
            isSwipping = false;
            startX = 0;
            startY = 0;
            endX = 0;
            endY = 0;
            hasMoved = false;
        }, { passive: true });
        
        // タッチキャンセル
        this.viewerContent.addEventListener('touchcancel', () => {
            isSwipping = false;
            startX = 0;
            startY = 0;
            endX = 0;
            endY = 0;
            hasMoved = false;
        });
    }
    
    // ファイル選択ダイアログを開く
    openFileSelector() {
        this.fileInput.click();
    }
    
    // ファイル処理
    async handleFiles(files) {
        if (files.length === 0) return;
        
        this.showLoading(true);
        
        const formData = new FormData();
        for (let file of files) {
            formData.append('files', file);
        }
        
        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok) {
                // 成功時のハプティックフィードバック
                if ('vibrate' in navigator) {
                    navigator.vibrate([50, 50, 50]);
                }
                
                await this.loadFiles();
                this.showUploadSuccess(result.files.length);
            } else {
                this.showError('アップロードに失敗しました: ' + result.error);
            }
        } catch (error) {
            this.showError('アップロードに失敗しました: ' + error.message);
        } finally {
            this.showLoading(false);
            this.fileInput.value = '';
        }
    }
    
    // ファイル一覧の読み込み
    async loadFiles() {
        try {
            // キャッシュを無効にするためにタイムスタンプを追加
            const timestamp = new Date().getTime();
            const response = await fetch(`/files?_t=${timestamp}`, {
                cache: 'no-cache',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });
            const data = await response.json();
            console.log('Loaded files from server:', data.files.map(f => f.id));
            this.files = data.files;
            this.renderPhotoGrid();
        } catch (error) {
            console.error('Failed to load files:', error);
            this.showError('ファイルの読み込みに失敗しました');
        }
    }
    
    // 写真グリッドの描画
    renderPhotoGrid() {
        console.log('=== RENDER PHOTO GRID ===');
        console.log('Files to render:', this.files.map(f => ({ id: f.id, name: f.original_name, type: f.file_type })));
        
        if (this.files.length === 0) {
            this.uploadSection.style.display = 'flex';
            this.photoGrid.style.display = 'none';
            return;
        }
        
        this.uploadSection.style.display = 'none';
        this.photoGrid.style.display = 'grid';
        
        this.photoGrid.innerHTML = this.files.map((file, index) => {
            const isSelected = this.selectedFiles.has(file.id);
            const isVideo = file.file_type === 'video';
            
            console.log(`Creating HTML for file ${file.id} (${file.file_type})`);
            
            return `
                <div class="photo-item ${isSelected ? 'selected' : ''}" 
                     data-file-id="${file.id}" 
                     data-index="${index}">
                    ${isVideo ? 
                        `<video muted playsinline preload="metadata" poster="/thumbnails/${file.id}">
                            <source src="/files/${file.id}" type="${file.mime_type || 'video/mp4'}">
                        </video>
                        <div class="video-overlay">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                <polygon points="5,3 19,12 5,21"/>
                            </svg>
                            動画
                        </div>` :
                        `<img src="/thumbnails/${file.id}" 
                              alt="${file.original_name}"
                              loading="lazy"
                              onerror="console.error('Failed to load thumbnail for ${file.id}'); this.style.display='none'; this.parentElement.innerHTML='<div style=\\'display:flex;align-items:center;justify-content:center;height:100%;background:#f0f0f0;color:#666;\\'>画像を読み込めません</div>'">`
                    }
                    <div class="selection-indicator"></div>
                </div>
            `;
        }).join('');
        
        // イベントリスナーを追加
        this.photoGrid.querySelectorAll('.photo-item').forEach(item => {
            item.addEventListener('click', (e) => this.handlePhotoClick(e));
        });
    }
    
    // 写真クリック処理
    handlePhotoClick(e) {
        const photoItem = e.currentTarget;
        const fileId = photoItem.dataset.fileId;
        const index = parseInt(photoItem.dataset.index);
        
        if (this.isSelectionMode) {
            // 選択モード
            if (this.selectedFiles.has(fileId)) {
                this.selectedFiles.delete(fileId);
                photoItem.classList.remove('selected');
            } else {
                this.selectedFiles.add(fileId);
                photoItem.classList.add('selected');
            }
            
            this.updateSelectionUI();
        } else {
            // ビューアモード
            this.openViewer(index);
        }
    }
    
    // 選択モードの切り替え
    toggleSelectionMode() {
        this.isSelectionMode = !this.isSelectionMode;
        
        if (this.isSelectionMode) {
            this.selectBtn.textContent = 'キャンセル';
            this.photoGrid.classList.add('selection-mode');
            this.selectionActions.classList.add('visible');
        } else {
            this.selectBtn.textContent = '選択';
            this.photoGrid.classList.remove('selection-mode');
            this.selectionActions.classList.remove('visible');
            this.selectedFiles.clear();
            this.renderPhotoGrid();
        }
        this.updateSelectionUI();
    }
    
    // 選択UI更新
    updateSelectionUI() {
        const count = this.selectedFiles.size;
        if (this.isSelectionMode) {
            if (count > 0) {
                this.selectBtn.textContent = `${count}個選択中`;
            } else {
                this.selectBtn.textContent = 'キャンセル';
            }
        }
    }
    
    // ビューアを開く
    openViewer(index) {
        this.currentViewerIndex = index;
        this.isViewerUIVisible = true; // UI表示状態を初期化
        const file = this.files[index];
        
        // スムーズな切り替えのためのフェード効果
        const isAlreadyOpen = this.photoViewer.classList.contains('active');
        
        if (isAlreadyOpen) {
            // 既に開いている場合はフェードアウト→コンテンツ変更→フェードイン
            this.viewerContent.style.opacity = '0';
            
            setTimeout(() => {
                this.updateViewerContent(file);
                this.viewerContent.style.opacity = '1';
            }, 150);
        } else {
            // 初回表示の場合
            this.updateViewerContent(file);
            this.photoViewer.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
        
        this.viewerInfo.innerHTML = `
            <h3>${file.original_name}</h3>
            <p>サイズ: ${this.formatFileSize(file.file_size)}</p>
            <p>作成日: ${this.formatDate(file.created_at)}</p>
        `;
        
        this.showViewerUI(true); // 初期表示はUI表示
    }
    
    // ビューアコンテンツを更新
    updateViewerContent(file) {
        this.viewerContent.innerHTML = file.file_type === 'video' ?
            `<video controls autoplay muted playsinline preload="metadata">
                <source src="/files/${file.id}" type="${file.mime_type || 'video/mp4'}">
                <p>お使いのブラウザは動画再生をサポートしていません。</p>
            </video>` :
            `<img src="/files/${file.id}" alt="${file.original_name}" loading="eager">`;
    }
    
    // ビューアUI表示切り替え
    toggleViewerUI() {
        this.isViewerUIVisible = !this.isViewerUIVisible;
        this.showViewerUI(this.isViewerUIVisible);
    }
    
    // ビューアUI表示制御 - CSSのみで制御するため簡略化
    showViewerUI(show) {
        // CSSで制御するため、JavaScriptでの操作を最小限に
        this.photoViewer.classList.toggle('ui-hidden', !show);
    }
    
    // ビューアを閉じる
    closeViewer() {
        this.photoViewer.classList.remove('active');
        this.photoViewer.classList.remove('ui-hidden');
        document.body.style.overflow = '';
        
        // フォーカスのクリア（最小限の処理）
        setTimeout(() => {
            if (document.activeElement && document.activeElement.blur) {
                document.activeElement.blur();
            }
        }, 50);
    }
    
    // 現在のファイルを共有
    async shareCurrentFile() {
        const file = this.files[this.currentViewerIndex];
        
        if (navigator.share) {
            try {
                const response = await fetch(`/files/${file.id}`);
                const blob = await response.blob();
                const shareFile = new File([blob], file.original_name, { type: file.mime_type });
                
                await navigator.share({
                    title: file.original_name,
                    files: [shareFile]
                });
            } catch (error) {
                console.log('共有に失敗しました:', error);
            }
        } else {
            // フォールバック: URLをコピー
            const url = `${window.location.origin}/files/${file.id}`;
            navigator.clipboard.writeText(url);
            this.showMessage('URLをコピーしました');
        }
    }
    
    // 現在のファイルを削除
    async deleteCurrentFile() {
        const file = this.files[this.currentViewerIndex];
        
        if (confirm(`"${file.original_name}" を削除しますか？`)) {
            try {
                const response = await fetch(`/files/${file.id}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    this.closeViewer();
                    await this.loadFiles();
                    this.showMessage('削除しました');
                } else {
                    this.showError('削除に失敗しました');
                }
            } catch (error) {
                this.showError('削除に失敗しました: ' + error.message);
            }
        }
    }
    
    // 選択されたファイルをダウンロード
    async downloadSelectedFiles() {
        if (this.selectedFiles.size === 0) return;
        
        for (const fileId of this.selectedFiles) {
            const file = this.files.find(f => f.id === fileId);
            if (file) {
                // ファイルをダウンロード
                const link = document.createElement('a');
                link.href = `/files/${file.id}`;
                link.download = file.original_name;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        }
        
        this.showMessage(`${this.selectedFiles.size}個のファイルをダウンロードしました`);
    }
    
    // 選択されたファイルを削除
    async deleteSelectedFiles() {
        if (this.selectedFiles.size === 0) return;
        
        if (!confirm(`選択した${this.selectedFiles.size}個のファイルを削除しますか？`)) return;
        
        try {
            const deletePromises = Array.from(this.selectedFiles).map(fileId => 
                fetch(`/files/${fileId}`, { method: 'DELETE' })
            );
            
            await Promise.all(deletePromises);
            
            this.selectedFiles.clear();
            this.toggleSelectionMode(); // 選択モードを終了
            await this.loadFiles();
            this.showMessage('選択したファイルを削除しました');
        } catch (error) {
            this.showError('削除に失敗しました: ' + error.message);
        }
    }
    
    // キーボードイベント処理
    handleKeydown(e) {
        if (this.photoViewer.classList.contains('active')) {
            switch (e.key) {
                case 'Escape':
                    this.closeViewer();
                    break;
                case 'ArrowLeft':
                    this.navigateViewer(-1);
                    break;
                case 'ArrowRight':
                    this.navigateViewer(1);
                    break;
                case 'Delete':
                case 'Backspace':
                    this.deleteCurrentFile();
                    break;
            }
        }
    }
    
    // ビューア内ナビゲーション
    navigateViewer(direction) {
        const newIndex = this.currentViewerIndex + direction;
        if (newIndex >= 0 && newIndex < this.files.length) {
            this.openViewer(newIndex);
        }
    }
    
    // ユーティリティ関数
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    formatDate(dateString) {
        return new Date(dateString).toLocaleString('ja-JP');
    }
    
    showLoading(show) {
        this.loadingIndicator.style.display = show ? 'flex' : 'none';
    }
    
    showUploadSuccess(count) {
        this.showMessage(`${count}個のファイルをアップロードしました`);
    }
    
    showError(message) {
        // 簡単なエラー表示（後で改善可能）
        alert(message);
    }
    
    showMessage(message) {
        // 簡単なメッセージ表示（後で改善可能）
        console.log(message);
    }
    
    // 外部ストレージスキャン
    async scanExternalStorage() {
        const scanStorageBtn = document.getElementById('scanStorageBtn');
        const originalIcon = scanStorageBtn.innerHTML;
        
        try {
            // ローディング状態にする
            scanStorageBtn.innerHTML = `
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 12a9 9 0 11-6.219-8.56"/>
                </svg>
            `;
            scanStorageBtn.style.animation = 'spin 1s linear infinite';
            scanStorageBtn.disabled = true;
            
            const response = await fetch('/scan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                // 成功メッセージ表示
                const message = `スキャン完了: ${result.added}件の新しいファイルを追加しました`;
                this.showToast(message, 'success');
                
                // ギャラリーを再読み込み
                await this.loadGallery();
            } else {
                this.showToast('スキャンに失敗しました', 'error');
            }
        } catch (error) {
            console.error('Scan error:', error);
            this.showToast('スキャン中にエラーが発生しました', 'error');
        } finally {
            // ボタンを元に戻す
            scanStorageBtn.innerHTML = originalIcon;
            scanStorageBtn.style.animation = '';
            scanStorageBtn.disabled = false;
        }
    }

    // トースト通知
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        // フェードイン
        setTimeout(() => toast.classList.add('show'), 100);
        
        // 3秒後にフェードアウト
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// アプリケーション初期化
document.addEventListener('DOMContentLoaded', () => {
    new PhotoApp();
});
