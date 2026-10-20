# ProxmoxMCP HTTP Sunucu Kılavuzu

Bu kılavuz ProxmoxMCP'nin streamable HTTP taşımasını ve API anahtarı (API key) ile kimlik
doğrulamayı anlatır. Kurulum, yapılandırma ve güvenlik modeli için [README.tr.md](README.tr.md)
dosyasına bakın. Buradaki komutlar `scripts/verify_docs_commands.sh` ile temiz bir kopyada
çalıştırılarak doğrulanır.

## Hızlı başlangıç

### 1. API anahtarı üret ve digest'ini hesapla

```bash
# Anahtar üret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# SHA-256 digest'ini hesapla (anahtarın kendisi asla yapılandırmaya yazılmaz)
echo -n 'my-secret-key' | uv run python -m proxmox_mcp.auth.apikey
```

### 2. Digest'i sunucuya ver

Öncelik: CLI/constructor > ortam değişkeni > config dosyası. Kaynaklar birbirinin yerine geçer
(birleştirilmez); anahtar döndürürken eski bir digest'in config'de kalıp geçerli olmaya devam etmesi
bu şekilde engellenir.

```bash
# Ortam değişkeni (virgülle ayrılmış, isteğe bağlı "sha256:" öneki)
export PROXMOX_MCP_API_KEY_HASHES=<digest>[,<digest2>]
```

Ya da config dosyasında `http.api_key_digests` (64 karakterlik sha256 hex digest listesi). Digest
verilmezse sunucu başlamaz (fail-closed). `proxmox.timeout` saniye cinsindendir (varsayılan 30,
en çok 300, ortam değişkeni `PROXMOX_TIMEOUT`).

### 3. Sunucuyu başlat

```bash
# Başlatma betiği (varsayılan 127.0.0.1:8812/proxmox-mcp)
./start_http_server.sh

# Ya da doğrudan Python ile
uv run python -m proxmox_mcp.server_http --config proxmox-config/config.json --port 8812 --path /proxmox-mcp
```

Betik şu ortam değişkenlerini okur: `MCP_HTTP_HOST` (varsayılan `127.0.0.1`), `MCP_HTTP_PORT`
(`8812`), `MCP_HTTP_PATH` (`/proxmox-mcp`) ve `PROXMOX_MCP_CONFIG`
(`proxmox-config/config.json`). `python -m proxmox_mcp.server_http` ise ortam değişkeni değil
`--host`, `--port`, `--path`, `--config` bayraklarını kabul eder.

Yalnızca yerel geliştirme için: `--no-auth` kimlik doğrulamayı kapatır ve yalnızca loopback
adreslerinde (`127.0.0.1`, `::1`, `localhost`) çalışır; bu modda loopback olmayan `Host`/`Origin`
başlıkları 403 ile reddedilir.

## Kimlik doğrulama

Tek bir paylaşılan anahtar seviyesi vardır; scope/rol ayrımı yoktur. Geçerli anahtara sahip istemci,
politikanın izin verdiği tüm araçları kullanabilir, bu yüzden anahtarı gizli tutun. Yazma, yıkıcı
ve exec araçları ayrıca `read_only` / `allow_destructive` / `allow_exec` politikasıyla korunur
(varsayılan: yıkıcı ve exec kapalı).

İstemci anahtarı `Authorization: Bearer <key>` veya `X-API-Key: <key>` başlığıyla gönderir. Anahtar
yoksa ya da yanlışsa sunucu 401 döndürür.

## MCP oturum akışı (curl)

Streamable HTTP oturumlu çalışır: önce `initialize` ile oturum açılır, dönen `mcp-session-id`
başlığı sonraki isteklerde gönderilir. Yanıtlar SSE biçimindedir (`event: message` / `data: ...`).

<!-- verify:session-flow -->
```bash
URL=${URL:-http://127.0.0.1:8812/proxmox-mcp}
KEY=${KEY:-my-secret-key}
H1='Content-Type: application/json'
H2='Accept: application/json, text/event-stream'

# 1) Oturum aç ve oturum kimliğini al
SID=$(curl -fsS -D - -o /dev/null -X POST "$URL" -H "$H1" -H "$H2" \
  -H "Authorization: Bearer $KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' \
  | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' | tr -d '\r')

# 2) Başlatmayı onayla
curl -fsS -X POST "$URL" -H "$H1" -H "$H2" -H "Authorization: Bearer $KEY" \
  -H "mcp-session-id: $SID" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3) Araçları listele
curl -fsS -X POST "$URL" -H "$H1" -H "$H2" -H "Authorization: Bearer $KEY" \
  -H "mcp-session-id: $SID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

# 4) Bir aracı çağır (health)
curl -fsS -X POST "$URL" -H "$H1" -H "$H2" -H "Authorization: Bearer $KEY" \
  -H "mcp-session-id: $SID" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"health","arguments":{}}}'
```

Bir VM listesi için 4. adımda `"name":"get_vms"` kullanın. Yıkıcı bir aracı (`delete_vm` gibi)
çağırmak `allow_destructive` ve `confirm=true` gerektirir; `confirm` olmadan yalnızca önizleme
döner.

### Sağlık kontrolü

`GET /health` kimlik doğrulamasız tek uç noktadır ve yalnızca `{"status":"ok"}` döndürür:

```bash
curl -fsS http://127.0.0.1:8812/health
```

Geçerli bir anahtarla çağıranlar ek ayrıntı görür (kimlik doğrulama modu, politika, Proxmox
erişilebilirliği, PVE sürümü); aynı bilgi `health` aracıyla da alınabilir:

```bash
curl -fsS -H 'Authorization: Bearer my-secret-key' http://127.0.0.1:8812/health
```

## İstemci yapılandırması

Claude Desktop, Cursor ve Cline için çalışan yapılandırma örnekleri [README.tr.md](README.tr.md)
dosyasındaki "İstemci yapılandırması" bölümünde ve [`examples/`](examples) dizinindedir. HTTP için
özet:

- **Cursor**: `{"url": "http://127.0.0.1:8812/proxmox-mcp", "headers": {"Authorization": "Bearer YOUR_API_KEY"}}`
- **Cline**: aynısı, ayrıca `"type": "streamableHttp"`
- **Claude Desktop**: uzak HTTP için `npx mcp-remote` köprüsü kullanılır

## Docker

```bash
export PROXMOX_MCP_API_KEY_HASHES=<digest>
docker compose up -d --build
curl -fsS http://127.0.0.1:8812/health
```

Port yalnızca `127.0.0.1` üzerinde yayınlanır; uzaktan erişim için TLS sonlandıran bir reverse
proxy kullanın.

## Güvenlik notları

1. **HTTPS kullanın**: Sunucuda yerleşik TLS yoktur. Loopback dışına bağlanırsanız TLS sonlandıran
   bir reverse proxy koyun (başlangıçta uyarı loglanır).
2. **Anahtar güvenliği**: Düz anahtarı güvenli saklayın; sunucuya yalnızca SHA-256 digest'i verilir.
3. **Anahtar döndürme**: Yeni digest'i ortam değişkenine koyun; ortam değişkeni config'deki listeyi
   tamamen değiştirir.
4. **Rate limiting**: Production'da reverse proxy seviyesinde ekleyin.

## Sorun giderme

1. **401 Unauthorized**: `Authorization: Bearer <düz anahtar>` veya `X-API-Key: <düz anahtar>`
   gönderdiğinizden emin olun (digest'i değil).
2. **400 "Missing session ID"**: `initialize` ile oturum açıp `mcp-session-id` başlığını sonraki
   isteklere ekleyin (yukarıdaki akış).
3. **403 "Host or Origin not allowed"**: `--no-auth` modunda yalnızca loopback `Host`/`Origin`
   kabul edilir.
4. **Sunucu başlamıyor (API anahtarı digest'i yok)**: `PROXMOX_MCP_API_KEY_HASHES` veya
   `http.api_key_digests` ayarlayın; yerel geliştirmede loopback üzerinde `--no-auth` kullanın.
5. **Bağlantı hatası**: Sunucunun çalıştığını, portun ve `MCP_HTTP_HOST`/`MCP_HTTP_PORT`
   değerlerinin doğru olduğunu kontrol edin.

Loglar varsayılan olarak stderr'e yazılır (Docker'da `docker compose logs`). İsteğe bağlı olarak
`logging.file` / `LOG_FILE` ile 0600 izinli, döndürülen (10 MiB x 5) bir dosyaya da yazılabilir.

## Daha fazla bilgi

- [FastMCP dokümantasyonu](https://gofastmcp.com)
- [MCP protokol spesifikasyonu](https://modelcontextprotocol.io/specification)
- [Ana dokümantasyon](README.tr.md)
