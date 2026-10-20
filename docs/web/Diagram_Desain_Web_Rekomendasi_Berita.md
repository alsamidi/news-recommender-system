# Diagram Desain Awal — Web Sistem Rekomendasi Berita

Status: **usulan desain untuk direview sebelum implementasi agent**.

## Keputusan desain yang dipakai

1. Akun aplikasi (`users.id`) berbeda dari ID pengguna dataset MIND (`persona_user_id`).
2. Akun biasa mendapatkan feed awal dari berita populer (frekuensi klik pada data train, bukan output model). Setelah membaca, aplikasi menyimpan `nid` sebagai interaksi dan mengirim riwayat itu ke `POST /recommend` pada permintaan berikutnya.
3. Akun demo persona yang di-seed secara internal memakai jalur warm dengan `user_id` dataset. Untuk akun ini, profil dataset yang dipakai API; riwayat aplikasi tetap dicatat, tetapi tidak dicampur ke payload warm.
4. Pemilihan topik tidak menjadi langkah wajib MVP. Rekomendasi pengguna biasa sudah dapat berawal dari riwayat baca; onboarding topik bisa ditambahkan nanti setelah mapping ke katalog didefinisikan dan diuji.
5. Web tidak melatih ulang model, mengubah artefak, menulis ke Parquet, mengubah alpha=0.4, atau mengubah kontrak API v1.0.0.
6. Artikel dibaca dari katalog/API, bukan tabel artikel lokal. `interactions.nid` adalah referensi logis yang divalidasi aplikasi, bukan foreign key SQL.
7. MVP hanya mencatat event `view`. Rating, pencarian, profil preferensi, dan fitur admin tidak masuk diagram inti.
8. Feed rekomendasi: request `top_k=30`, filter semua `nid` yang pernah dibaca, deduplikasi berdasarkan `nid`, lalu tampilkan maksimal 10 dengan urutan hasil API yang tetap.
9. Jika akun persona warm mendapat 404 karena mapping tidak valid, coba jalur history jika ada; jangan tampilkan error mentah ke pengguna.

## 1. Use Case Diagram

```mermaid
flowchart LR
    visitor["Pengunjung"]
    reader["Pengguna terautentikasi"]
    persona["Akun demo persona dataset"]
    api["API rekomendasi beku v1.0.0\n(komponen backend)"]

    subgraph system["Sistem Web Rekomendasi Berita"]
        uc_register([Daftar akun])
        uc_login([Login])
        uc_logout([Logout])
        uc_feed([Lihat feed berita])
        uc_detail([Baca detail berita])
        uc_history([Lihat riwayat baca])
        uc_similar([Lihat berita serupa])
        uc_record([Catat interaksi baca])
    end

    visitor --> uc_register
    visitor --> uc_login
    reader --> uc_logout
    reader --> uc_feed
    reader --> uc_detail
    reader --> uc_history
    reader --> uc_similar
    persona --> uc_feed

    uc_feed -. "POST /recommend" .-> api
    uc_detail -. "GET /article/{nid}" .-> api
    uc_similar -. "GET /similar/{nid}" .-> api
    uc_detail -. "include" .-> uc_record

    classDef actor fill:#f5f5f5,stroke:#555,color:#111;
    classDef usecase fill:#eaf2ff,stroke:#4169a1,color:#111;
    class visitor,reader,persona,api actor;
    class uc_register,uc_login,uc_logout,uc_feed,uc_detail,uc_history,uc_similar,uc_record usecase;
```

Untuk notasi UML yang lebih formal, gunakan diagram Mermaid di atas sebagai
sumber; tidak ada berkas PlantUML/ZIP terpisah dalam repositori ini.

## 2. Activity Diagram — Versi Sederhana

Diagram ini sengaja dibuat satu alur tanpa percabangan keputusan. Perbedaan antara akun biasa dan akun persona MIND dirangkum di dalam langkah sistem agar diagram lebih mudah dibaca.

```mermaid
flowchart TD
    A((Mulai)) --> B[Pengguna membuka website]
    B --> C[Pengguna daftar / login]
    C --> D[Website menampilkan feed awal]
    D --> E[Pengguna membuka berita]
    E --> F[Website menampilkan detail artikel]
    F --> G[Simpan interaksi view ke SQLite]
    G --> H[Siapkan konteks rekomendasi]
    H --> I[Kirim permintaan ke API rekomendasi]
    I --> J[Tampilkan rekomendasi]
    J --> E
```

**Keterangan langkah sistem:**
- Feed pertama akun biasa yang belum punya riwayat menggunakan berita populer dari statistik klik data train.
- Akun demo persona menggunakan `user_id` dari dataset MIND untuk rekomendasi *warm*.
- Saat pengguna membuka artikel, sistem menyimpan event `view` ke SQLite.
- Untuk akun biasa, konteks rekomendasi berikutnya berasal dari `nid` dalam riwayat baca. Untuk persona MIND, konteksnya tetap `user_id` dataset.
- Interaksi website yang baru tercatat tidak otomatis melatih ulang model ALS.

Alur berulang dari **Tampilkan rekomendasi** ke **Pengguna membuka berita** menunjukkan bahwa pengguna dapat terus membaca berita dan menerima rekomendasi berikutnya.

## 3. Class Diagram — Versi Sederhana

Diagram ini hanya menampilkan kelas inti: akun, interaksi baca, data artikel, layanan autentikasi, layanan rekomendasi, dan API rekomendasi yang sudah tersedia.

```mermaid
classDiagram
    direction TB

    class User {
        +id
        +name
        +email
        +password_hash
    }

    class Interaction {
        +id
        +user_id
        +nid
        +event
        +created_at
    }

    class Article {
        +nid
        +title
        +category
    }

    class AuthService {
        +register()
        +login()
        +logout()
    }

    class RecommendationService {
        +getRecommendations()
        +recordView()
    }

    class RecommendationAPI {
        +recommend()
        +getArticle()
        +getSimilar()
    }

    User "1" --> "0..*" Interaction : has
    AuthService ..> User : manages account
    RecommendationService ..> Interaction : reads and saves
    RecommendationService ..> RecommendationAPI : requests data
    RecommendationAPI ..> Article : returns article data
    Interaction ..> Article : references by nid

    note for Article "Read-only article data from the existing API/catalog; not stored in the web database."
```

**Keterangan:**
- `User` menyimpan identitas akun website.
- `Interaction` menyimpan setiap kunjungan artikel (`event=view`) beserta waktu. Satu pengguna dapat memiliki banyak interaksi.
- `Article` adalah data artikel yang dibaca dari API/katalog, bukan tabel lokal website. `nid` menghubungkan catatan interaksi dengan artikel.
- `AuthService` menangani daftar, login, dan logout.
- `RecommendationService` membaca riwayat, mencatat kunjungan, dan meminta hasil dari `RecommendationAPI`.
- `RecommendationAPI` adalah layanan yang telah ada; diagram ini tidak menyatakan bahwa model rekomendasinya dibuat ulang oleh website.

## 4. ERD

```mermaid
erDiagram
    USERS ||--o{ SESSIONS : owns
    USERS ||--o{ INTERACTIONS : creates

    USERS {
        int id PK
        string name
        string email UK
        string password_hash
        string persona_user_id "nullable; internal seed only"
        datetime created_at
    }

    SESSIONS {
        int id PK
        string token_hash UK
        int user_id FK
        datetime created_at
        datetime expires_at
        string csrf_token
    }

    INTERACTIONS {
        int id PK
        int user_id FK
        string nid "logical catalog reference"
        string event "view in MVP"
        datetime created_at
        string source "feed|similar|history|direct"
    }
```

## Batas data dan implementasi

- SQLite hanya menyimpan `users`, `sessions`, dan `interactions` untuk MVP.
- Dataset katalog, interaksi penelitian, dan seluruh artefak model tetap read-only.
- Cookie menyimpan token sesi; database hanya menyimpan `token_hash`. Password disimpan sebagai hash.
- `interactions` tidak memakai constraint unik `(user_id, nid)` karena setiap kunjungan perlu tercatat; saat menyusun payload rekomendasi, daftar `nid` dibuat unik berdasarkan kunjungan terbaru.
- Jangan menyimpan score rekomendasi: nilainya dinormalisasi per request sehingga tidak tepat dibandingkan antar-request.
