# ProxmoxMCP-Extended

[English](README.md) | Türkçe

MCP istemcilerinin (Claude Desktop, Cursor, Cline, ...) bir Proxmox VE kümesini Proxmox API'si
üzerinden incelemesini ve yönetmesini sağlayan Python tabanlı bir
[Model Context Protocol](https://modelcontextprotocol.io) (MCP) sunucusu: düğümler, VM'ler, LXC
konteynerleri, depolama, snapshot'lar, yedekler, görevler ve HA durumu.

27 aracı stdio veya kimlik doğrulamalı streamable HTTP üzerinden sunar. Durum değiştiren her şey
varsayılan olarak kapalı bir güvenlik politikasıyla korunur ([Güvenlik modeli](#güvenlik-modeli)).

## Fork geçmişi

- **Orijinal proje**: [canvrno/ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP)
- **İlk fork**: [RekklesNA/ProxmoxMCP-Plus](https://github.com/RekklesNA/ProxmoxMCP-Plus)
- **Bu fork**: [alpadalar/ProxmoxMCP-Extended](https://github.com/alpadalar/ProxmoxMCP-Extended) (buradasınız)

## Teşekkürler

Bu proje, [@canvrno](https://github.com/canvrno) tarafından geliştirilen açık kaynak
[ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP) projesi üzerine kuruludur. Temeli sağladığı
için orijinal yazara, ProxmoxMCP-Plus bakımcılarına ve Proxmox topluluğuna teşekkürler. Upstream
telif bildirimleri [LICENSE](LICENSE) ve [NOTICE](NOTICE) dosyalarında korunur.

[Proxmoxer](https://github.com/proxmoxer/proxmoxer), [FastMCP](https://gofastmcp.com),
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) ve
[Pydantic](https://docs.pydantic.dev/) ile geliştirilmiştir.

## Gereksinimler

- Python 3.10 veya üzeri
- [uv](https://docs.astral.sh/uv/)
- API token'ı olan Proxmox VE 8.x veya 9.x ([API token oluşturma](#api-token-oluşturma))
- Docker ve Compose v2 (yalnızca konteyner dağıtımı için)

## Kurulum

```bash
git clone https://github.com/alpadalar/ProxmoxMCP-Extended.git
cd ProxmoxMCP-Extended
uv sync
```

## Yapılandırma

Yapılandırmanızı şablondan oluşturun (gerçek dosya git tarafından yok sayılır; asla commit etmeyin):

```bash
cp proxmox-config/config.example.json proxmox-config/config.json
```

`proxmox-config/config.json` dosyasını düzenleyin: `proxmox.host`, `auth.user`, `auth.token_name`
ve `auth.token_value` değerlerini girin. TLS doğrulaması varsayılan olarak açıktır; özel bir CA için
doğrulamayı kapatmak yerine `proxmox.ca_bundle` kullanın.

Yapılandırma tek bir yükleyici tarafından çözülür. Öncelik (yüksek olan kazanır):
**CLI bayrakları > ortam değişkenleri > JSON yapılandırma dosyası > yerleşik varsayılanlar.**
Bilinmeyen anahtarlar, hatalı yazılmış boolean'lar (ör. `PROXMOX_VERIFY_SSL=ture`) ve geçersiz
değerler, gizli değer içermeyen bir hata ile başlangıçta başarısız olur.

| Ayar | JSON anahtarı | Ortam değişkeni | CLI bayrağı |
|---|---|---|---|
| Host | `proxmox.host` | `PROXMOX_HOST` | |
| Port (varsayılan 8006) | `proxmox.port` | `PROXMOX_PORT` | |
| TLS doğrulaması (varsayılan `true`) | `proxmox.verify_ssl` | `PROXMOX_VERIFY_SSL` | `--verify-ssl` (yalnızca stdio) |
| CA bundle dosyası (özel CA) | `proxmox.ca_bundle` | `PROXMOX_CA_BUNDLE` | `--ca-bundle` (yalnızca stdio) |
| Servis (`PVE`/`PMG`/`PBS`) | `proxmox.service` | `PROXMOX_SERVICE` | |
| İstek zaman aşımı, saniye (varsayılan 30, en çok 300) | `proxmox.timeout` | `PROXMOX_TIMEOUT` | |
| API kullanıcısı | `auth.user` | `PROXMOX_USER` | |
| Token adı | `auth.token_name` | `PROXMOX_TOKEN_NAME` | |
| Token gizli değeri | `auth.token_value` | `PROXMOX_TOKEN_VALUE` | |
| HTTP API anahtarı digest'leri | `http.api_key_digests` | `PROXMOX_MCP_API_KEY_HASHES` | |
| Salt okunur mod | `policy.read_only` | `PROXMOX_MCP_READ_ONLY` | `--read-only` |
| Yıkıcı araçlara izin ver | `policy.allow_destructive` | `PROXMOX_MCP_ALLOW_DESTRUCTIVE` | `--allow-destructive` |
| Exec aracına izin ver | `policy.allow_exec` | `PROXMOX_MCP_ALLOW_EXEC` | `--allow-exec` |
| Exec zaman aşımı, saniye (varsayılan 30) | `policy.exec_timeout_seconds` | `PROXMOX_MCP_EXEC_TIMEOUT` | |
| Akış başına exec çıktı sınırı, bayt (varsayılan 65536) | `policy.exec_max_output_bytes` | `PROXMOX_MCP_EXEC_MAX_OUTPUT` | |
| Eşzamanlı exec çağrısı (varsayılan 2) | `policy.exec_max_concurrent` | `PROXMOX_MCP_EXEC_MAX_CONCURRENT` | |
| Log seviyesi (varsayılan `INFO`) | `logging.level` | `LOG_LEVEL` | `--log-level` (yalnızca stdio) |
| Log dosyası | `logging.file` | `LOG_FILE` | `--log-file` (yalnızca stdio) |

"(yalnızca stdio)" işaretli dört satır yalnızca `proxmox-mcp` bayraklarıdır; `python -m proxmox_mcp.server_http` (ve dolayısıyla Docker imajı) bunları kabul etmez, orada ortam değişkenlerini veya JSON dosyasını kullanın.

Boolean'lar `true/false`, `1/0`, `yes/no`, `on/off` kabul eder. Boş ortam değişkenleri tanımsız
sayılır. `ca_bundle`, `verify_ssl=false` ile birlikte kullanılamaz; doğrulamayı kapatmak bir uyarı
loglar.

### API token oluşturma

1. Proxmox web arayüzünde Datacenter -> Permissions -> API Tokens bölümünden bir token ekleyin.
2. `root@pam` yerine ayrılmış, en az yetkili bir kullanıcı kullanın (örneğin `monitor@pve`).
3. **Privilege Separation** seçeneğini açık tutun ve token'a yalnızca gereken yollarda gereken
   rolleri verin. Tüm `read` araçları için `/` üzerinde `PVEAuditor` gibi salt okunur bir rol
   yeterlidir; VM/depolama yetkilerini (örneğin `VM.PowerMgmt`, `VM.Snapshot`, `VM.Allocate`)
   yalnızca etkinleştirmeyi düşündüğünüz yazma ve yıkıcı araçlar için ekleyin. Hata mesajları eksik
   yetkinin adını verir.
4. Token gizli değerini bir kez kopyalayın; Proxmox bir daha göstermez.

## Çalıştırma

### stdio (Claude Desktop, Cursor, Cline sunucuyu sizin yerinize başlatır)

```bash
uv run proxmox-mcp --config proxmox-config/config.json
```

`./start_server.sh` aynı işi yapar. Politika bayrakları (`--read-only`, `--allow-destructive`,
`--allow-exec`) sona eklenebilir.

### HTTP (streamable HTTP, API anahtarı zorunlu)

HTTP modu API anahtarı digest'i olmadan başlamayı reddeder (fail-closed). Bir anahtar üretin,
sunucuda yalnızca sha256 digest'ini saklayın ve düz anahtarı istemcinize verin:

```bash
echo -n 'my-secret-key' | uv run python -m proxmox_mcp.auth.apikey
export PROXMOX_MCP_API_KEY_HASHES=<digest>[,<digest2>]
```

Sunucuyu başlatın (varsayılan bağlama `127.0.0.1:8812`, yol `/proxmox-mcp`):

```bash
./start_http_server.sh
# or
uv run python -m proxmox_mcp.server_http --config proxmox-config/config.json
```

İstemciler `Authorization: Bearer my-secret-key` veya `X-API-Key: my-secret-key` gönderir:

```bash
curl -s -X POST http://127.0.0.1:8812/proxmox-mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Authorization: Bearer my-secret-key' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

Notlar:

- `start_http_server.sh` `MCP_HTTP_HOST`, `MCP_HTTP_PORT`, `MCP_HTTP_PATH` ve
  `PROXMOX_MCP_CONFIG` değişkenlerini okur; modül `--host`, `--port`, `--path` ve `--config`
  kabul eder.
- Digest'ler yapılandırma dosyasında `http.api_key_digests` olarak da verilebilir. Öncelik:
  CLI/constructor > `PROXMOX_MCP_API_KEY_HASHES` > yapılandırma; kaynaklar birbirinin yerine geçer,
  asla birleştirilmez.
- `--no-auth` yalnızca loopback üzerinde kabul edilir.
- `GET /health` kimlik doğrulamasız tek uç noktadır ve yalnızca `{"status": "ok"}` döndürür.
  Geçerli anahtarı olan çağıranlar (ve `health` aracı) ayrıca kimlik doğrulama modunu, Proxmox
  erişilebilirliğini, politikayı ve PVE sürümünü görür.
- Sunucuda yerleşik TLS yoktur. Loopback olmayan bir host'a bağlanırsanız API anahtarı düz metin
  olarak taşınır; TLS'i bir reverse proxy'de sonlandırın (başlangıçta bir uyarı loglanır).

Daha uzun bir HTTP anlatımı için [HTTP_MCP_GUIDE.md](HTTP_MCP_GUIDE.md) dosyasına bakın.

### Docker Compose

İmaj digest ile sabitlenmiştir; root olmayan bir kullanıcıyla (uid 10001), salt okunur dosya
sisteminde, tüm capability'ler düşürülmüş olarak çalışır ve portu yalnızca `127.0.0.1` üzerinde
yayınlar. Yapılandırma `./proxmox-config` dizininden salt okunur bağlanır; imaja hiçbir gizli
değer gömülmez.

```bash
echo -n 'my-secret-key' | uv run python -m proxmox_mcp.auth.apikey
export PROXMOX_MCP_API_KEY_HASHES=<digest>
docker compose up -d --build
docker compose ps
curl -s http://127.0.0.1:8812/health
docker compose down
```

`PROXMOX_MCP_API_KEY_HASHES` tanımlı değilse `docker compose` başlamayı reddeder. Konteyner,
yerleşik bir `HEALTHCHECK` ile sağlık durumunu bildirir.

## Güvenlik modeli

Tüm kapılar varsayılan olarak kapalıdır; kapalı araçlar kayıtlı kalır (araç listesi asla
değişmez) ve çağrı anında açıklayıcı bir hata ile reddedilir.

| Bayrak | Varsayılan | Etki |
|---|---|---|
| `read_only` | `false` | `true` iken tüm yazma, yıkıcı ve exec araçlarını engeller ve `allow_*` bayraklarını geçersiz kılar |
| `allow_destructive` | `false` | Yıkıcı araçları açar (VM durdur/sıfırla/sil, snapshot geri al/sil, konteyner durdur, VM güncelle) |
| `allow_exec` | `false` | `execute_vm_command` aracını açar |

Bunları `--read-only` / `--allow-destructive` / `--allow-exec`, `PROXMOX_MCP_*` ortam
değişkenleri veya yapılandırma dosyasındaki `policy` bölümüyle ayarlayın.

- `confirm` alan yıkıcı araçlar (`delete_vm`, `stop_vm`, `reset_vm`, `rollback_snapshot`,
  `delete_snapshot`, `stop_container`), `confirm=true` verilmedikçe ne olacağının önizlemesini
  döndürür.
- `execute_vm_command` programı QEMU guest agent üzerinden doğrudan, shell olmadan çalıştırır:
  `command` ile birlikte bir `args` listesi verin (shell gerekiyorsa `/bin/sh` ve
  `['-c', '...']` değerlerini açıkça verin). Her akış sınırlandırılır
  (`exec_max_output_bytes`), çağrılar zaman aşımına uğrar (`exec_timeout_seconds`) ve eşzamanlılık
  sınırlıdır (`exec_max_concurrent`).
- Başlatma, durdurma, kapatma, sıfırlama, silme, snapshot ve konteyner araçları (`create_vm`,
  `update_vm` ve `execute_vm_command` hariç), Proxmox görevinin (UPID) bitmesini beklemek ve gerçek çıkış durumunu
  bildirmek için isteğe bağlı `wait` ve `timeout` kabul eder.
- HTTP modu API anahtarı gerektirir ve varsayılan olarak loopback'e bağlanır.

Tehdit modeli için [SECURITY.md](SECURITY.md) dosyasına bakın.

## Araçlar

27 araç. Tablo, `scripts/gen_tool_table.py` ile `tests/golden/tools.json` dosyasından üretilir;
zorunlu parametreler kalındır.

<!-- tools:start -->
| Tool | Risk class | Gate | Parameters |
|---|---|---|---|
| `get_cluster_status` | read | always available |  |
| `get_containers` | read | always available |  |
| `get_ha_status` | read | always available |  |
| `get_node_status` | read | always available | **node** |
| `get_nodes` | read | always available |  |
| `get_storage` | read | always available |  |
| `get_task_status` | read | always available | **upid** |
| `get_vm_usage` | read | always available | **node**, **vmid** |
| `get_vms` | read | always available |  |
| `health` | read | always available |  |
| `list_backups` | read | always available | **node**, storage, vmid |
| `list_snapshots` | read | always available | **node**, **vmid** |
| `wait_for_task` | read | always available | timeout, **upid** |
| `create_snapshot` | write | blocked by `read_only` | description, **name**, **node**, timeout, **vmid**, vmstate, wait |
| `create_vm` | write | blocked by `read_only` | **cpus**, **disk_size**, iso_name, iso_storage, **memory**, **name**, **node**, ostype, storage, **vmid** |
| `shutdown_container` | write | blocked by `read_only` | node, timeout, **vmid**, wait |
| `shutdown_vm` | write | blocked by `read_only` | **node**, timeout, **vmid**, wait |
| `start_container` | write | blocked by `read_only` | node, timeout, **vmid**, wait |
| `start_vm` | write | blocked by `read_only` | **node**, timeout, **vmid**, wait |
| `delete_snapshot` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, **name**, **node**, timeout, **vmid**, wait |
| `delete_vm` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, force, **node**, timeout, **vmid**, wait |
| `reset_vm` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, **node**, timeout, **vmid**, wait |
| `rollback_snapshot` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, **name**, **node**, timeout, **vmid**, wait |
| `stop_container` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, node, timeout, **vmid**, wait |
| `stop_vm` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, **node**, timeout, **vmid**, wait |
| `update_vm` | destructive | needs `allow_destructive`; blocked by `read_only` | cpus, memory, name, **node**, **vmid** |
| `execute_vm_command` | exec | needs `allow_exec`; blocked by `read_only` | args, **command**, **node**, **vmid** |
<!-- tools:end -->

Kullanım notları:

- **Keşif**: `get_nodes`, `get_node_status`, `get_cluster_status`, `get_vms`, `get_containers`,
  `get_storage`, `get_vm_usage`, `health`. `get_vms` ve `get_containers` kümedeki tüm konukları
  listeler.
- **Görevler**: durum değiştiren araçlar bir UPID döndürür. Anlık durum için `get_task_status`,
  beklemek için `wait_for_task` kullanın (`timeout` ile sınırlıdır).
- **VM yaşam döngüsü**: `create_vm` (`iso_name`/`iso_storage` ile isteğe bağlı ISO; disk biçimi
  depolama türüne göre seçilir), `start_vm`, `shutdown_vm` (nazik), `stop_vm` (zorla),
  `reset_vm`, `delete_vm`, `update_vm`.
- **Konteynerler (LXC)**: `get_containers`, `start_container`, `shutdown_container`,
  `stop_container`.
- **Snapshot ve yedekler**: `list_snapshots`, `create_snapshot`, `rollback_snapshot`,
  `delete_snapshot`, `list_backups` (salt okunur; geri yükleme uygulanmamıştır).
- **HA**: `get_ha_status`.
- **Konuk içi komut**: `execute_vm_command` (QEMU guest agent ve `allow_exec` gerekir).

## İstemci yapılandırması

`/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended` yerine checkout yolunuzu, `YOUR_API_KEY` yerine düz API
anahtarını (digest'i sunucuda tanımlı olan anahtar) yazın. Aşağıdaki JSON'lar
[`examples/`](examples) altındaki dosyaların birebir içeriğidir. stdio girdileri, test paketinde 27
aracın tamamını listeleyen gerçek bir MCP el sıkışmasıyla çalıştırılır; istemci arayüzünün kabulü
elle kontrol edilir.

### Claude Desktop

Dosya: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) veya
`%APPDATA%\Claude\claude_desktop_config.json` (Windows). Düzenledikten sonra Claude Desktop'ı
yeniden başlatın. Uzak HTTP sunucuları bu dosyada yapılandırılmaz; bu yüzden HTTP girdisi
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote) köprüsünü kullanır (Node.js gerekir).
Kaynak: [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json).

```json
{
  "mcpServers": {
    "proxmox-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended",
        "run",
        "proxmox-mcp"
      ],
      "env": {
        "PROXMOX_MCP_CONFIG": "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended/proxmox-config/config.json"
      }
    },
    "proxmox-mcp-http": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://127.0.0.1:8812/proxmox-mcp",
        "--allow-http",
        "--header",
        "Authorization:${PROXMOX_MCP_AUTH}"
      ],
      "env": {
        "PROXMOX_MCP_AUTH": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

### Cursor

Dosya: `~/.cursor/mcp.json` (global) veya bir projedeki `.cursor/mcp.json`. Cursor ayrıca `url`,
`headers` ve `env` içinde `${env:NAME}` enterpolasyonunu destekler; böylece anahtarı dosyaya
yazmaktan kaçınabilirsiniz. Kaynak: [`examples/cursor_mcp_config.json`](examples/cursor_mcp_config.json).

```json
{
  "mcpServers": {
    "proxmox-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended",
        "run",
        "proxmox-mcp"
      ],
      "env": {
        "PROXMOX_MCP_CONFIG": "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended/proxmox-config/config.json"
      }
    },
    "proxmox-mcp-http": {
      "url": "http://127.0.0.1:8812/proxmox-mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

### Cline

Dosya: `cline_mcp_settings.json` (Cline'daki MCP Servers panelinden açılır). Uzak sunucular
`"type": "streamableHttp"` gerektirir; yoksa Cline eski SSE varsayar. Kaynak:
[`examples/cline_mcp_settings.json`](examples/cline_mcp_settings.json).

```json
{
  "mcpServers": {
    "proxmox-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended",
        "run",
        "proxmox-mcp"
      ],
      "env": {
        "PROXMOX_MCP_CONFIG": "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended/proxmox-config/config.json"
      },
      "disabled": false,
      "autoApprove": []
    },
    "proxmox-mcp-http": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8812/proxmox-mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Geliştirme

```bash
uv sync
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest -q
```

- Test paketi sahte (mock) bir Proxmox API'sine karşı çalışır; CI'da gerçek küme gerekmez
  (ve kullanılmaz).
- `tests/golden/tools.json` genel araç yüzeyinin anlık görüntüsüdür. Bir araç adını veya
  parametresini değiştirmek anlık görüntüyü değiştirir ve kırıcı bir değişikliktir; README
  tablosunu `uv run python scripts/gen_tool_table.py` ile yeniden üretin.
- `bash scripts/verify_docs_commands.sh`, belgelenen komutları deponun temiz bir kopyasında yeniden
  çalıştırır (konteyneri de dahil etmek için `VERIFY_DOCKER=1` verin).
- `scripts/live/` gerçek bir küme gerektiren elle çalıştırılan betikleri içerir; test paketinin
  parçası değildir.

## Sorun giderme

- **Sunucu başlangıçta API anahtarlarından söz ederek çıkıyor**: HTTP modu digest gerektirir;
  [HTTP (streamable HTTP, API anahtarı zorunlu)](#http-streamable-http-api-anahtarı-zorunlu)
  bölümüne bakın.
- **HTTP uç noktasından 401**: `Authorization: Bearer <düz anahtar>` gönderin (digest'i değil).
- **Proxmox'a TLS hataları**: özel CA için `proxmox.ca_bundle` kullanın; `verify_ssl=false` son
  çaredir.
- **"Permission denied ... Required privilege"**: token'ın o yolda belirtilen yetkisi yok.
- **Bir araç politika nedeniyle kapalı diyor**: [Güvenlik modeli](#güvenlik-modeli) bölümüne bakın.
- Loglar varsayılan olarak stderr'e gider (konteynerde `docker compose logs`; json-file sürücüsü
  10 MB x 5 dosya tutar). İsteğe bağlı dosya için `logging.file` / `LOG_FILE` ayarlayın: dosya
  döndürülür (10 MiB x 5 yedek) ve 0600 izniyle oluşturulur. Konteynerin küçük ve yeniden
  başlatmada silinen `/tmp` tmpfs'ine yazmayın; bir volume bağlayın.

## Güvenlik

Bu sunucunun hipervizörünüze neler yapabileceği ve güvenlik açıklarını nasıl bildireceğiniz için
[SECURITY.md](SECURITY.md) dosyasını okuyun.

## Katkıda bulunma

[CONTRIBUTING.md](CONTRIBUTING.md) dosyasına bakın. Önemli değişiklikler
[CHANGELOG.md](CHANGELOG.md) dosyasında listelenir.

## Lisans

MIT. [LICENSE](LICENSE) dosyasına bakın; upstream atıfları [NOTICE](NOTICE) dosyasındadır.
