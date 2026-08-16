# Drowned Distribution Suite

Windows odaklı GitHub Releases dağıtım sistemi.

## Uygulamalar

- **Drowned Release Manager** — oyun/proje yayınlama, katalog yönetimi ve güvenli silme.
- **Drowned Launcher** — Steam benzeri kütüphane, raw katalog/artwork okuma, indirme ve SHA-256 doğrulama.

Android uygulaması ve Android build pipeline'ı projeden tamamen kaldırılmıştır.

## Dağıtım mimarisi

Büyük binary içerikler normal Git history içine konmaz. Release Manager kaynak klasörü stream ederek yaklaşık **1900 MiB** chunk'lar üretir ve bunları GitHub Release Assets olarak yükler. Aynı anda yaklaşık tek chunk kadar geçici disk alanı gerekir.

```text
Kaynak klasör
  -> streaming chunk
  -> SHA-256
  -> GitHub draft release
  -> chunk assets
  -> manifest.json
  -> catalog.json
  -> publish
```

Launcher tarafında chunk'lar kalıcı bir arşiv olarak tutulmaz; manifest segment haritasına göre doğrudan final dosyaların doğru offset'lerine yazılır.

## Raw-first metadata

Normal kullanıcı okumaları mümkün olduğunca REST API yerine aşağıdaki adreslerden yapılır:

- `catalog.json` -> `raw.githubusercontent.com`
- manifestler -> `raw.githubusercontent.com`
- hero / cover / logo -> `raw.githubusercontent.com`
- büyük chunk dosyaları -> GitHub Releases download URL'leri

Launcher raw CDN gecikmesini hesaba katar:

- cache-busting query ekler,
- birkaç kez yeniden dener,
- raw geçici olarak hazır değilse son başarılı katalog cache'ini gösterebilir,
- raw hatası nedeniyle uygulamayı kapatmaz.

## Artwork

- **Hero**: geniş arka plan, önerilen `1920x620`.
- **Cover**: dikey oyun kapağı, önerilen `600x900`.
- **Logo**: tercihen şeffaf PNG/WebP oyun logosu/yazısı.

Repo yapısı:

```text
artwork/<platform>/<game-id>/hero.*
artwork/<platform>/<game-id>/cover.*
artwork/<platform>/<game-id>/logo.*
manifests/<platform>/<game-id>/<channel>/<version>.json
catalog.json
```

## Release Manager token izinleri

Fine-grained PAT kullanın ve yalnız dağıtım repository'sine erişim verin.

Önerilen repository permissions:

- `Contents: Read and write`
- `Workflows: Read and write` (repository workflow dosyaları içeriyorsa)

Token kaynak koda yazılmaz; Windows keyring / Credential Manager üzerinden saklanır.

## Güvenli silme

Release Manager'da bir kanal veya oyunun tamamı silindiğinde sistem sırayla:

1. GitHub Release'i ve assetlerini,
2. ilgili Git tag'i,
3. raw manifest kaydını,
4. artık başka kayıt tarafından kullanılmayan artwork dosyalarını,
5. en son `catalog.json` kaydını

temizler.

Katalog son adımda güncellenir; böylece yarım kalmış silme işlemi katalogda sahte bir başarı durumu oluşturmaz.

## Windows build

GitHub Actions workflow'u:

- Python/pip cache kullanır,
- aynı branch'te eski build varsa iptal eder,
- `PySide6-Essentials` kullanır,
- `drowned_shared` paketini PyInstaller içine açıkça toplar,
- syntax kontrolü yapar,
- paket içi modül kontrolü yapar,
- EXE için gerçek startup smoke test çalıştırır.

Yerel geliştirme için Python 3.13 önerilir.

Release Manager:

```bash
python -m pip install shared/python
python -m pip install -r windows/release-manager/requirements.txt
python windows/release-manager/app_v3.py
```

Launcher:

```bash
python -m pip install shared/python
python -m pip install -r windows/launcher/requirements.txt
python windows/launcher/app_v4.py
```

## Test

```bash
python -m pip install shared/python
python -m unittest discover -s tests -v
```

## İçerik

Bu altyapıyı yalnızca dağıtım hakkına sahip olduğunuz oyun, yazılım, homebrew, dataset ve diğer içerikler için kullanın.
