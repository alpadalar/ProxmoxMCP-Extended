# ProxmoxMCP HTTP Server Kılavuzu

Bu kılavuz, ProxmoxMCP'nin HTTP transport özelliğini ve API anahtarı (API key) ile kimlik doğrulamayı açıklar.

## 🚀 Hızlı Başlangıç

### 1. API Anahtarı Üret ve Hash'le

```bash
# Anahtar üret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# SHA-256 digest'ini hesapla (anahtarın kendisi asla yapılandırmaya yazılmaz)
echo -n '<key>' | python -m proxmox_mcp.auth.apikey
```

### 2. Digest'i Yapılandır

Digest şu kaynaklardan biriyle verilir. Öncelik: CLI/constructor > ortam değişkeni > config dosyası.
Kaynaklar birbirinin yerine geçer (birleştirilmez); anahtar döndürürken eski bir digest'in config'de
kalıp geçerli olmaya devam etmesi bu şekilde engellenir.

```bash
# Ortam değişkeni (virgülle ayrılmış, isteğe bağlı "sha256:" öneki)
export PROXMOX_MCP_API_KEY_HASHES=<digest>[,<digest2>]
```

Ya da config dosyasında (`http.api_key_digests`):

```json
{
    "proxmox": {
        "host": "your-proxmox-host",
        "port": 8006,
        "verify_ssl": true,
        "service": "PVE",
        "timeout": 30
    },
    "auth": {
        "user": "username@pve",
        "token_name": "your-token-name",
        "token_value": "your-token-value"
    },
    "http": {
        "api_key_digests": ["<64 karakterlik sha256 hex digest>"]
    },
    "logging": {
        "level": "INFO"
    }
}
```

`proxmox.timeout` saniye cinsindendir (varsayılan 30, `0 < t <= 300`, ortam değişkeni `PROXMOX_TIMEOUT`).
Digest verilmezse sunucu başlamaz (fail-closed).

### 3. HTTP Server'ı Başlat

```bash
# Start script kullan
./start_http_server.sh

# Ya da direkt Python ile
python -m proxmox_mcp.server_http --config proxmox-config/config.json --port 8812 --path /proxmox-mcp
```

Yalnızca yerel geliştirme için: `--no-auth` kimlik doğrulamayı kapatır ve sadece loopback
adreslerinde (`127.0.0.1`, `::1`, `localhost`) çalışır. `/health` yolu kimlik doğrulamasından muaftır.

## 🔒 Authentication

Tek bir paylaşılan anahtar seviyesi vardır; scope/rol ayrımı yoktur. Geçerli anahtara sahip istemci tüm
araçları kullanabilir (VM oluşturma, silme ve komut çalıştırma dahil), bu yüzden anahtarı gizli tutun.

### Anahtar Kullanımı

İstemci anahtarı `Authorization: Bearer <key>` veya `X-API-Key: <key>` başlığıyla gönderir:

```bash
curl -X POST http://localhost:8812/proxmox-mcp \
  -H "Authorization: Bearer YOUR_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"method": "tools/list"}'
```

## 🔌 Cursor/VS Code Entegrasyonu

### MCP Settings Konfigürasyonu

Cursor/VS Code'da MCP ayarlarınıza şunu ekleyin:

```json
{
  "mcpServers": {
    "ProxmoxMCP-HTTP": {
      "transport": {
        "type": "http",
        "url": "http://localhost:8812/proxmox-mcp",
        "headers": {
          "Authorization": "Bearer YOUR_API_KEY_HERE"
        }
      },
      "description": "ProxmoxMCP HTTP Server (API key auth)"
    }
  }
}
```

### SSE (Server-Sent Events) Desteği

Daha iyi performans için SSE kullanabilirsiniz:

```json
{
  "mcpServers": {
    "ProxmoxMCP-SSE": {
      "transport": {
        "type": "sse",
        "url": "http://localhost:8812/proxmox-mcp/sse",
        "headers": {
          "Authorization": "Bearer YOUR_API_KEY_HERE"
        }
      }
    }
  }
}
```

## 🛠️ Geliştirme ve Test

### Logging

Debug modu için:

```bash
python manage.py run_mcp_server --debug --log-file debug.log
```

### Test Toolları

```bash
# Tool listesini test et
curl -X POST http://localhost:8812/proxmox-mcp \
  -H "Authorization: Bearer YOUR_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'

# VM listesini test et
curl -X POST http://localhost:8812/proxmox-mcp \
  -H "Authorization: Bearer YOUR_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "get_vms",
      "arguments": {}
    }
  }'
```

### Health Check

```bash
curl -X POST http://localhost:8812/proxmox-mcp \
  -H "Authorization: Bearer YOUR_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "health",
      "arguments": {}
    }
  }'
```

## 🔧 Konfigürasyon Seçenekleri

### Environment Variables

```bash
export MCP_HTTP_HOST="0.0.0.0"
export MCP_HTTP_PORT="8812"
export MCP_HTTP_PATH="/proxmox-mcp"
export PROXMOX_MCP_CONFIG="proxmox-config/config.json"
```

### Command Line Seçenekleri

```bash
python -m proxmox_mcp.server_http \
  --host 0.0.0.0 \
  --port 8812 \
  --path /proxmox-mcp \
  --config proxmox-config/config.json \
  --no-auth  # Auth'u devre dışı bırak (test için)
```

## 🚨 Güvenlik Notları

1. **HTTPS Kullanın**: Production'da mutlaka TLS sonlandıran bir reverse proxy kullanın
2. **Anahtar Güvenliği**: API anahtarını güvenli saklayın; yapılandırmaya yalnızca SHA-256 digest yazılır
3. **Anahtar Döndürme**: Yeni digest'i ortam değişkenine koyun; ortam değişkeni config'deki listeyi tamamen değiştirir
4. **Rate Limiting**: Production'da reverse proxy seviyesinde rate limiting ekleyin

## 🔍 Troubleshooting

### Yaygın Hatalar

1. **401 Unauthorized**
   ```
   {"error": "unauthorized", "message": "Valid API key required"}
   ```
   - Anahtarınızı ve digest'inizi kontrol edin
   - `Authorization: Bearer <key>` veya `X-API-Key` başlığını doğru yazdığınızdan emin olun

2. **Sunucu başlamıyor (No API key digests configured)**
   - `PROXMOX_MCP_API_KEY_HASHES` veya `http.api_key_digests` ayarlayın
   - Yerel geliştirmede loopback üzerinde `--no-auth` kullanın

3. **Connection Error**
   - Server'ın çalıştığından emin olun
   - Port'un açık olduğunu kontrol edin
   - Firewall ayarlarını kontrol edin

### Log Analizi

```bash
tail -f proxmox_mcp.log | grep "AUDIT\|ERROR"
```

## 📚 Daha Fazla Bilgi

- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- [ProxmoxMCP Ana Dokümantasyon](README.md)
