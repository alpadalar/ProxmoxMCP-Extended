# ProxmoxMCP HTTP Server Kılavuzu

Bu kılavuz, ProxmoxMCP'nin HTTP transport özelliği ile Django authentication entegrasyonunu açıklar.

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıkları Yükle

```bash
# Django desteği ile yükle
uv pip install -e ".[django]"

# Ya da manuel olarak
pip install fastmcp django djangorestframework pyjwt asgiref
```

### 2. Django Projesi Hazırla

#### Model Dosyalarını Kopyala

```bash
# Django projende auth uygulaması oluştur
python manage.py startapp auth

# Örnek modelleri kopyala
cp examples/django_models.py your_project/auth/models.py
```

#### Migration'ları Oluştur

```bash
python manage.py makemigrations auth
python manage.py migrate
```

#### Süper Kullanıcı ve Token Oluştur

```bash
# Süper kullanıcı oluştur
python manage.py createsuperuser

# Django shell'de token oluştur
python manage.py shell
```

```python
from django.contrib.auth.models import User
from auth.models import ApplicationToken, UserRole

# Rol oluştur
admin_role = UserRole.objects.create(
    name="Administrator",
    is_superuser=True,
    can_write=True,
    can_admin=True
)

# Kullanıcıya rol ata
user = User.objects.get(username='your_username')
user.role = admin_role
user.save()

# Token oluştur
token, raw_token = ApplicationToken.create_token(
    user=user,
    name="ProxmoxMCP Access",
    permission="admin",
    expires_days=30
)

print(f"Your token: {raw_token}")
```

### 3. ProxmoxMCP Konfigürasyonu

Mevcut `proxmox-config/config.json` dosyanızı kullanabilirsiniz:

```json
{
    "proxmox": {
        "host": "your-proxmox-host",
        "port": 8006,
        "verify_ssl": false,
        "service": "PVE"
    },
    "auth": {
        "user": "username@pve",
        "token_name": "your-token-name",
        "token_value": "your-token-value"
    },
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "file": "proxmox_mcp.log"
    }
}
```

### 4. HTTP Server'ı Başlat

#### Seçenek 1: Django Management Command

```bash
# Django projenizde ProxmoxMCP command'ini ekleyin
cp -r src/proxmox_mcp/management your_django_project/

# Server'ı başlatın
python manage.py run_mcp_server --host 0.0.0.0 --port 8812 --path /mcp-x798631
```

#### Seçenek 2: Standalone HTTP Server

```bash
# Start script kullan
./start_http_server.sh

# Ya da direkt Python ile
python -m proxmox_mcp.server_http --host 0.0.0.0 --port 8812 --path /mcp
```

## 🔒 Authentication ve Authorization

### Scope Sistemi

ProxmoxMCP üç scope seviyesi kullanır:

- **`user`**: Okuma işlemleri (get_nodes, get_vms, vb.)
- **`write`**: Yazma işlemleri (start_vm, create_snapshot, vb.)
- **`admin`**: Yönetici işlemleri (create_vm, delete_vm, stop_vm, vb.)

### Tool Permissions

| Tool | Required Scope | Açıklama |
|------|---------------|----------|
| `get_nodes` | `user` | Node listesi |
| `get_vms` | `user` | VM listesi |
| `get_vm_usage` | `user` | VM kaynak kullanımı |
| `start_vm` | `write` | VM başlat |
| `shutdown_vm` | `write` | VM'i zarif kapat |
| `execute_vm_command` | `write` | VM'de komut çalıştır |
| `create_vm` | `admin` | Yeni VM oluştur |
| `delete_vm` | `admin` | VM'i sil |
| `stop_vm` | `admin` | VM'i zorla durdur |

### Token Kullanımı

HTTP isteklerinde Authorization header kullanın:

```bash
curl -X POST http://localhost:8812/mcp \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
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
        "url": "http://localhost:8812/mcp",
        "headers": {
          "Authorization": "Bearer YOUR_TOKEN_HERE"
        }
      },
      "description": "ProxmoxMCP HTTP Server with Django Auth"
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
        "url": "http://localhost:8812/mcp/sse",
        "headers": {
          "Authorization": "Bearer YOUR_TOKEN_HERE"
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
curl -X POST http://localhost:8812/mcp \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'

# VM listesini test et
curl -X POST http://localhost:8812/mcp \
  -H "Authorization: Bearer YOUR_TOKEN" \
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
curl -X POST http://localhost:8812/mcp \
  -H "Authorization: Bearer YOUR_TOKEN" \
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
export MCP_HTTP_PATH="/mcp"
export PROXMOX_MCP_CONFIG="proxmox-config/config.json"
```

### Command Line Seçenekleri

```bash
python -m proxmox_mcp.server_http \
  --host 0.0.0.0 \
  --port 8812 \
  --path /mcp \
  --config proxmox-config/config.json \
  --no-auth  # Auth'u devre dışı bırak (test için)
```

## 🚨 Güvenlik Notları

1. **HTTPS Kullanın**: Production'da mutlaka HTTPS kullanın
2. **Token Güvenliği**: Token'ları güvenli şekilde saklayın
3. **IP Kısıtlaması**: ApplicationToken modelinde allowed_ips kullanın
4. **Token Expiration**: Token'lara mutlaka expiration süresi verin
5. **Rate Limiting**: Production'da rate limiting ekleyin

## 🔍 Troubleshooting

### Yaygın Hatalar

1. **Authentication Failed**
   ```
   Kimlik doğrulama gerekli. Geçerli bir token sağlayın.
   ```
   - Token'ınızı kontrol edin
   - Authorization header'ını doğru yazdığınızdan emin olun

2. **Permission Denied**
   ```
   Bu işlem için gerekli yetkilere (admin) sahip değilsiniz.
   ```
   - Kullanıcı rolünüzü kontrol edin
   - Token permission'ını kontrol edin

3. **Connection Error**
   - Server'ın çalıştığından emin olun
   - Port'un açık olduğunu kontrol edin
   - Firewall ayarlarını kontrol edin

### Debug Modu

```bash
python manage.py run_mcp_server --debug --host 0.0.0.0 --port 8812
```

### Log Analizi

```bash
tail -f proxmox_mcp.log | grep "AUDIT\|ERROR"
```

## 📚 Daha Fazla Bilgi

- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Django Authentication](https://docs.djangoproject.com/en/stable/topics/auth/)
- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- [ProxmoxMCP Ana Dokümantasyon](README.md)
