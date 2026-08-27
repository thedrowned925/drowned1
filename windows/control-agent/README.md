# Drowned PC Agent — LAN MVP

Bu klasör, Drowned Control Android uygulamasının aynı Wi-Fi/LAN üzerindeki Windows bilgisayara doğrudan bağlanması için kullanılan PC Agent katmanını içerir.

Bu sürümde **Cloudflare, relay sunucusu veya port yönlendirme yoktur**. Telefon doğrudan PC'nin yerel IP adresine bağlanır.

## İlk özellikler

- Token korumalı yerel HTTP API
- PC çevrimiçi durumu, CPU/RAM/disk telemetrisi
- Telefondan PC sürücülerini ve klasörlerini gezme
- İndirme klasörünü telefondan seçme
- FDM indirme klasörü izleme
- PC'den EXE seçip test başlatma
- Test process ağacını izleme
- Oyun penceresi / ekran önizlemesini telefona gönderme
- Kullanıcının testi başarılı/başarısız olarak onaylaması

Agent'ta genel amaçlı shell/PowerShell/cmd endpoint'i yoktur. Sadece önceden tanımlanmış komutlar kabul edilir.

## Geliştirme ortamında çalıştırma

Windows üzerinde:

```powershell
cd windows/control-agent
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python launcher.py
```

İlk açılışta Agent:

1. Portu sorar. Varsayılan: `47821`
2. Cihaz ID oluşturur.
3. Güçlü bir erişim anahtarı üretir.
4. Telefona girilecek yerel adresi gösterir. Örnek: `http://192.168.1.34:47821`

Token Windows'ta `%APPDATA%\DrownedAgent\config.json` içinde DPAPI ile korunarak saklanır.

## Android bağlantısı

Drowned Control > PC ekranında:

- **PC Agent adresi:** Agent'ın gösterdiği `http://LAN-IP:47821`
- **Erişim anahtarı:** Agent'ın ilk kurulumda gösterdiği token

Telefon ve PC aynı ağda olmalıdır. Windows Güvenlik Duvarı ilk çalıştırmada Python veya Drowned-Agent için yerel ağ izni isteyebilir.

## LAN API

Tüm endpoint'ler `Authorization: Bearer <token>` ister.

- `GET /api/status`
- `GET /api/drives`
- `GET /api/files?path=...`
- `GET /api/events/next?client_id=...`
- `POST /api/command`

Örnek komut:

```json
{
  "type": "command",
  "command": "set_download_folder",
  "request_id": "...",
  "path": "D:\\Downloads\\Games"
}
```

Desteklenen ilk komutlar:

- `request_status`
- `choose_download_folder`
- `set_download_folder`
- `start_download_watch`
- `stop_download_watch`
- `choose_executable`
- `start_test`
- `approve_test`
- `reject_test`
- `stop_test`

## Güvenlik notu

Bu MVP aynı yerel ağ için HTTP kullanır. Erişim token ile sınırlandırılır ancak trafik TLS ile şifrelenmez. İnternet üzerinden doğrudan port açılması önerilmez. Uzak erişim daha sonra aynı API korunarak Tailscale gibi özel ağ katmanı üzerinden eklenebilir.

## Sonraki adımlar

- QR ile cihaz eşleştirme
- Windows tray arayüzü ve başlangıçta otomatik çalışma
- Kalıcı job/task veritabanı
- Steam App ID metadata akışı
- Yetkili indirme sağlayıcısı adapter'ları
- Arşiv doğrulama / güvenli çıkarma
- EXE otomatik tespiti ve sağlık testi
- Mevcut Drowned release-manager ile publish entegrasyonu
