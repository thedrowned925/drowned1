# Drowned PC Agent — LAN MVP

Bu klasör, Drowned Control Android uygulamasının aynı Wi-Fi/LAN üzerindeki Windows bilgisayara doğrudan bağlanması için kullanılan PC Agent katmanını içerir.

Bu sürümde **Cloudflare, relay sunucusu veya port yönlendirme yoktur**. Telefon doğrudan PC'nin yerel IP adresine bağlanır.

## İlk özellikler

- Token korumalı yerel HTTP API
- PC çevrimiçi durumu, CPU/RAM/disk telemetrisi
- Telefondan PC sürücülerini ve klasörlerini gezme
- İndirme klasörünü telefondan seçme
- FDM indirme klasörü izleme
- Yeni ZIP sabit kaldığında otomatik doğrulama ve güvenli çıkarma
- ZIP çıkarma sırasında ilerleme durumunu telefona gönderme
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

## FDM → ZIP akışı

1. Telefonda veya PC'de FDM indirme klasörü seçilir.
2. `İzlemeyi Başlat` denir.
3. Agent başlangıçtaki dosyaları baseline olarak alır; yalnızca sonradan yeni/değişen dosyayı takip eder.
4. Dosya boyutu **ve son değiştirilme zamanı** en az 8 saniye sabit kaldığında tamamlanmış aday kabul edilir.
5. Aday `.zip` ise CRC, path traversal, şifreleme ve symlink kontrollerinden geçirilir.
6. Boş disk alanı yeterliyse ZIP mevcut hiçbir klasörün üzerine yazmadan yeni bir kardeş klasöre çıkarılır.
7. Telefon durum alanında `ZIP doğrulanıyor`, `ZIP çıkarılıyor • %...`, `ZIP çıkarıldı` veya hata mesajını görür.
8. Çıkarılan tek üst klasör varsa `game_root` olarak belirlenir ve sonraki EXE/test aşamasında kullanılabilir.

İlk MVP otomatik arşiv tarafında yalnızca ZIP destekler. RAR/7z daha sonra ayrı bir 7-Zip adapter'ı ile eklenecek.

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

## ZIP güvenliği

- `../` veya mutlak yol ile hedef klasörden kaçmaya çalışan kayıtlar reddedilir.
- Şifreli ZIP otomatik çıkarılmaz.
- Sembolik link içeren ZIP reddedilir.
- CRC testi başarılı olmadan çıkarma başlamaz.
- Hedef klasör zaten varsa üzerine yazılmaz; yeni benzersiz hedef üretilir.
- Yetersiz disk alanında çıkarma başlamaz.
- Hata sırasında Agent'ın oluşturduğu yarım hedef klasörü temizlenir.

## Güvenlik notu

Bu MVP aynı yerel ağ için HTTP kullanır. Erişim token ile sınırlandırılır ancak trafik TLS ile şifrelenmez. İnternet üzerinden doğrudan port açılması önerilmez. Uzak erişim daha sonra aynı API korunarak Tailscale gibi özel ağ katmanı üzerinden eklenebilir.

## Sonraki adımlar

- QR ile cihaz eşleştirme
- Windows tray arayüzü ve başlangıçta otomatik çalışma
- Kalıcı job/task veritabanı
- Steam App ID metadata akışı
- RAR/7z için 7-Zip adapter'ı
- EXE otomatik tespiti ve sağlık testi
- Mevcut `drowned_shared.publish.publish_project` motoru ile publish entegrasyonu
