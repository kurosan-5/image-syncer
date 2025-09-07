const CACHE_NAME = 'image-syncer-v2';
const urlsToCache = [
    '/',
    '/manifest.json',
    '/static/css/main.css',
    '/static/js/main.js',
    '/static/icon-192.png',
    '/static/icon-512.png'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Service Worker: キャッシュファイルを追加中');
                return cache.addAll(urlsToCache);
            })
            .then(() => {
                console.log('Service Worker: インストール完了');
                return self.skipWaiting();
            })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Service Worker: 古いキャッシュを削除', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => {
            console.log('Service Worker: アクティベート完了');
            return self.clients.claim();
        })
    );
});

self.addEventListener('fetch', (event) => {
    // ファイルとサムネイルはキャッシュしない（動的コンテンツ）
    if (event.request.url.includes('/files/') || 
        event.request.url.includes('/thumbnails/')) {
        return;
    }
    
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                if (response) {
                    return response;
                }
                return fetch(event.request).catch(() => {
                    // オフライン時のフォールバック
                    if (event.request.destination === 'document') {
                        return caches.match('/');
                    }
                });
            })
    );
});
