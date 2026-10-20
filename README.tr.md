# ProxmoxMCP-Extended - Geliştirilmiş Proxmox MCP Sunucusu


Proxmox sanallaştırma platformlarıyla etkileşim için geliştirilmiş, Python tabanlı bir Model Context Protocol (MCP) sunucusu. Bu proje, **[canvrno/ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP)** üzerine inşa edilmiştir ve kapsamlı OpenAPI entegrasyonu ile daha güçlü sanallaştırma yönetimi yetenekleri dahil olmak üzere çok sayıda yeni özellik ve iyileştirme sunar.

## Teşekkürler

Bu proje, [@canvrno](https://github.com/canvrno) tarafından geliştirilen açık kaynak [ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP) projesi üzerine kuruludur. Temel çerçeveyi ve ilhamı sağladığı için orijinal yazara teşekkürler!

## Çatallanma (Fork) Geçmişi

- **Orijinal proje**: [canvrno/ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP)
- **İlk fork**: [RekklesNA/ProxmoxMCP-Plus](https://github.com/RekklesNA/ProxmoxMCP-Plus)  
- **Bu fork**: [alpadalar/ProxmoxMCP-Extended](https://github.com/alpadalar/ProxmoxMCP-Extended) (buradasınız)

### 🚀 **ProxmoxMCP-Extended'deki Büyük Geliştirmeler:**

- **🎯 Gelişmiş VM Yönetimi**
  - VM oluşturma sırasında isteğe bağlı ISO bağlama (`iso_name`/`iso_storage` parametreleri)
  - Kapsamlı VM snapshot yönetimi (`create_snapshot`, `rollback_snapshot`)
  - VM kaynak kullanım izleme (`get_vm_usage`)
  - Geliştirilmiş konteyner desteği (`get_containers`)

- **⚡ HTTP MCP Server Entegrasyonu**
  - Modern MCP istemcileri için FastMCP tabanlı HTTP taşıması
  - 8812 portunda Docker Compose dağıtımı
  - Gerçek zamanlı Server-Sent Events (SSE) desteği
  - MCP Inspector uyumluluğu

- **🔧 Altyapı İyileştirmeleri**  
  - Test takımı modernizasyonu ve kapsamlı kapsam
  - Import yan etkilerini önlemek için ProxmoxMCPServer lazy loading
  - Sağlık kontrolü uç noktaları ve başlatma doğrulaması
  - Gelişmiş hata yönetimi ve yapılandırma yönetimi

- **📚 Dokümantasyon ve Yerelleştirme**
  - Kapsamlı İngilizce ve Türkçe dokümantasyon
  - Docker Compose hızlı başlangıç kılavuzları
  - Cursor/VS Code entegrasyon örnekleri
  - API uç nokta dokümantasyonu (11'den 14 araca genişletildi)

## 🆕 Yeni Özellikler ve İyileştirmeler

### Orijinal sürüme göre başlıca iyileştirmeler:

- ✨ **Tam VM Yaşam Döngüsü Yönetimi**
  - Yeni `create_vm` aracı - Özel yapılandırmalarla sanal makine oluşturma desteği
  - Yeni `delete_vm` aracı - Güvenli VM silme (zorla silme seçeneğiyle)
  - Gelişmiş akıllı depolama türü algılama (LVM/dosya tabanlı)

- 🔧 **Genişletilmiş Güç Yönetimi Özellikleri**
  - `start_vm` - Sanal makine başlatma
  - `stop_vm` - Sanal makineyi zorla durdurma
  - `shutdown_vm` - Zarif kapatma
  - `reset_vm` - Sanal makineyi yeniden başlatma

- 🐳 **Yeni Konteyner Desteği**
  - `get_containers` - Tüm LXC konteynerlerini ve durumlarını listeleme

- 📊 **Gelişmiş İzleme ve Görselleştirme**
  - Geliştirilmiş depolama havuzu durum izleme
  - Daha detaylı küme sağlık kontrolü
  - Zengin çıktı biçimlendirme ve temalar

- 🌐 **Eksiksiz OpenAPI Entegrasyonu**
  - 14 tam işlevsel REST API uç noktası (11'den genişletildi)
  - Üretime hazır Docker dağıtımı
  - Open WebUI ile kusursuz entegrasyon
  - Doğal dil ile VM oluşturma desteği

- 🚀 **HTTP MCP Server (YENİ!)**
  - Cursor/VS Code entegrasyonu için FastMCP tabanlı HTTP taşıması
  - Gerçek zamanlı Server-Sent Events (SSE) desteği
  - 8812 portunda Docker Compose dağıtımı
  - MCP Inspector uyumlu uç nokta

- 📸 **Gelişmiş VM Snapshot Yönetimi (YENİ!)**
  - `create_snapshot` - İsteğe bağlı bellek durumu ile VM snapshot'ları oluşturma
  - `rollback_snapshot` - VM'leri önceki snapshot'lara geri döndürme
  - Tam snapshot yaşam döngüsü yönetimi

- 📊 **Gelişmiş VM İzleme (YENİ!)**
  - `get_vm_usage` - Gerçek zamanlı VM kaynak kullanım takibi
  - CPU, bellek, disk ve ağ kullanım metrikleri
  - Performans izleme yetenekleri

- 🏥 **Sağlık Kontrolü ve Teşhis**
  - İzleme için yerleşik sağlık kontrolü uç noktaları
  - Başlatma doğrulaması ve isteğe bağlı test
  - Gelişmiş hata teşhisi ve loglama

- 🛡️ **Üretim Seviyesinde Güvenlik ve Kararlılık**
  - Gelişmiş hata yönetimi mekanizmaları
  - Kapsamlı parametre doğrulama
  - Üretim seviyesinde logging
  - Tam birim test kapsamı

## Kullanılan Teknolojiler

- [Cline](https://github.com/cline/cline) - Otonom kodlama ajanı - Cline ile daha hızlı
- [Proxmoxer](https://github.com/proxmoxer/proxmoxer) - Proxmox API için Python sarmalayıcısı
- [MCP SDK](https://github.com/modelcontextprotocol/sdk) - Model Context Protocol SDK
- [Pydantic](https://docs.pydantic.dev/) - Python tip açıklamalarıyla veri doğrulama

## Özellikler

- 🤖 Cline ve Open WebUI ile tam entegrasyon
- 🛠️ Resmi MCP SDK ile geliştirilmiştir
- 🔒 Proxmox ile güvenli token tabanlı kimlik doğrulama
- 🖥️ Tam VM yaşam döngüsü yönetimi (oluştur, başlat, durdur, reset, kapat, sil)
- 💻 VM konsol komutu çalıştırma
- 🐳 LXC konteyner yönetimi desteği
- 🗃️ Akıllı depolama türü algılama (LVM/dosya tabanlı)
- 📝 Yapılandırılabilir logging sistemi
- ✅ Pydantic ile tip güvenli uygulama
- 🎨 Özelleştirilebilir temalarla zengin çıktı biçimlendirme
- 🌐 Entegrasyon için OpenAPI REST uç noktaları
- 📡 14 tam işlevsel API uç noktası


## Kurulum

### Önkoşullar
- UV paket yöneticisi (önerilir)
- Python 3.9 veya üzeri
- Git
- API token bilgilerine sahip bir Proxmox sunucusuna erişim

Başlamadan önce emin olun:
- [ ] Proxmox sunucu ana bilgisayar adı veya IP adresi
- [ ] Proxmox API token (bkz. [Proxmox API Token Kurulumu](#proxmox-api-token-kurulumu))
- [ ] UV kurulu (`pip install uv`)

### Seçenek 1: Hızlı Kurulum (Önerilen)

1. Klonla ve ortamı hazırla:
   ```bash
   # Depoyu klonla
   git clone https://github.com/alpadalar/ProxmoxMCP-Extended.git
   cd ProxmoxMCP-Extended

   # Sanal ortam oluştur ve aktifleştir
   uv venv
   source .venv/bin/activate  # Linux/macOS
   # VEYA
   .\.venv\Scripts\Activate.ps1  # Windows
   ```

2. Bağımlılıkları yükle:
   ```bash
   # Geliştirme bağımlılıklarıyla yükle
   uv pip install -e ".[dev]"
   ```

3. Yapılandırmayı oluştur:
   ```bash
   # Yapılandırma klasörünü oluştur ve şablonu kopyala
   mkdir -p proxmox-config
   cp proxmox-config/config.example.json proxmox-config/config.json
   ```

4. `proxmox-config/config.json` dosyasını düzenle:
   ```json
   {
       "proxmox": {
           "host": "PROXMOX_HOST",        # Zorunlu: Proxmox sunucu adresiniz
           "port": 8006,                  # Opsiyonel: Varsayılan 8006
           "verify_ssl": false,           # Opsiyonel: Self-signed sertifikalar için false
           "service": "PVE"               # Opsiyonel: Varsayılan PVE
       },
       "auth": {
           "user": "USER@pve",            # Zorunlu: Proxmox kullanıcı adınız
           "token_name": "TOKEN_NAME",    # Zorunlu: API token ID
           "token_value": "TOKEN_VALUE"   # Zorunlu: API token değeri
       },
       "logging": {
           "level": "INFO",               # Opsiyonel: Daha fazla detay için DEBUG
           "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
           "file": "proxmox_mcp.log"      # Opsiyonel: Dosyaya logla
       }
   }
   ```

### Kurulumu Doğrulama

1. Python ortamını kontrol et:
   ```bash
   python -c "import proxmox_mcp; print('Installation OK')"
   ```

2. Testleri çalıştır:
   ```bash
   pytest
   ```

3. Yapılandırmayı doğrula:
   ```bash
   # Linux/macOS
   PROXMOX_MCP_CONFIG="proxmox-config/config.json" python -m proxmox_mcp.server

   # Windows (PowerShell)
   $env:PROXMOX_MCP_CONFIG="proxmox-config\config.json"; python -m proxmox_mcp.server
   ```

## Yapılandırma

### Proxmox API Token Kurulumu
1. Proxmox web arayüzünüze giriş yapın
2. Datacenter -> Permissions -> API Tokens bölümüne gidin
3. Yeni bir API token oluşturun:
   - Bir kullanıcı seçin (ör. root@pam)
   - Bir token ID girin (ör. "mcp-token")
   - Tam erişim istiyorsanız "Privilege Separation" işaretini kaldırın
   - Kaydedin ve token ID ile secret değerini kopyalayın

## Sunucuyu Çalıştırma

### 🐳 Docker Compose (Önerilen)

ProxmoxMCP-Extended'i çalıştırmanın en kolay yolu Docker Compose kullanmaktır:

```bash
# Hızlı başlatma
docker compose up -d

# Durumu kontrol et
docker compose ps

# Logları görüntüle
docker compose logs -f

# Sunucuyu durdur
docker compose down
```

**🌐 HTTP MCP Server URL:** `http://localhost:8812/proxmox-mcp`

**Özellikler:**
- ✅ Cursor/VS Code entegrasyonu için HTTP/SSE taşıması
- ✅ MCP Inspector uyumluluğu
- ✅ Üretime hazır konteyner dağıtımı
- ✅ Otomatik sağlık kontrolleri
- ✅ Konteyner adı: `ProxmoxMCP-Extended`

### Geliştirme Modu (Stdio)
Test ve geliştirme için:
```bash
# Önce sanal ortamı aktifleştirin
source .venv/bin/activate  # Linux/macOS
# VEYA
.\.venv\Scripts\Activate.ps1  # Windows

# Sunucuyu çalıştır
python -m proxmox_mcp.server
```

### HTTP Modu (Yerel Geliştirme)
Yerel HTTP taşıması geliştirmesi için:
```bash
# HTTP sunucusunu başlat
./start_http_server.sh

# Veya özel ayarlarla
python -m proxmox_mcp.server_http --host 127.0.0.1 --port 8812 --path /proxmox-mcp
```

**Özellikler:**
- ✅ FastMCP HTTP taşıması
- ✅ Server-Sent Events (SSE) desteği
- ✅ MCP Inspector entegrasyonu
- ✅ Gerçek zamanlı araç etkileşimi

### OpenAPI Dağıtımı (Üretime Hazır)

ProxmoxMCP-Extended’i Open WebUI ve diğer uygulamalarla entegrasyon için standart OpenAPI REST uç noktaları olarak dağıtın.

#### Hızlı OpenAPI Başlatma
```bash
# mcpo (MCP-to-OpenAPI proxy) kurun
pip install mcpo

# OpenAPI servisini 8811 portunda başlatın
./start_openapi.sh
```

#### Docker Dağıtımı
```bash
# Docker ile imajı oluşturun ve çalıştırın
docker build -t proxmox-mcp-api .
docker run -d --name proxmox-mcp-api -p 8811:8811 \
  -v $(pwd)/proxmox-config:/app/proxmox-config proxmox-mcp-api

# Ya da Docker Compose kullanın
docker compose up -d
```

#### OpenAPI Servisine Erişim
Dağıtım tamamlandığında servis erişimi:
- **📖 API Dokümantasyonu**: http://your-server:8811/docs
- **🔧 OpenAPI Spesifikasyonu**: http://your-server:8811/openapi.json
- **❤️ Sağlık Kontrolü**: POST http://your-server:8811/health (gövde: `{}`)

### Cursor/VS Code Entegrasyonu

#### Seçenek 1: Docker Compose (Önerilen)
Docker ile üretim dağıtımı için:

```json
{
    "mcpServers": {
        "ProxmoxMCP-Extended": {
            "transport": {
                "type": "http",
                "url": "http://localhost:8812/proxmox-mcp"
            },
            "description": "ProxmoxMCP-Extended with HTTP Transport"
        }
    }
}
```

#### Seçenek 2: Yerel HTTP Server
Yerel geliştirme sunucusu için:

```json
{
    "mcpServers": {
        "ProxmoxMCP-Local": {
            "transport": {
                "type": "http",
                "url": "http://localhost:8812/proxmox-mcp"
            },
            "description": "ProxmoxMCP Local Development"
        }
    }
}
```

#### Seçenek 3: Geleneksel Stdio (Eski)
Cline kullanıcıları için, MCP ayar dosyanıza şu yapılandırmayı ekleyin:

```json
{
  "mcpServers": {
    "ProxmoxMCP-Extended": {
      "command": "/absolute/path/to/ProxmoxMCP-Extended/.venv/bin/python",
      "args": ["-m", "proxmox_mcp.server"],
      "cwd": "/absolute/path/to/ProxmoxMCP-Extended",
      "env": {
        "PYTHONPATH": "/absolute/path/to/ProxmoxMCP-Extended/src",
        "PROXMOX_MCP_CONFIG": "/absolute/path/to/ProxmoxMCP-Extended/proxmox-config/config.json",
        "PROXMOX_HOST": "your-proxmox-host",
        "PROXMOX_USER": "username@pve",
        "PROXMOX_TOKEN_NAME": "token-name",
        "PROXMOX_TOKEN_VALUE": "token-value",
        "PROXMOX_PORT": "8006",
        "PROXMOX_VERIFY_SSL": "false",
        "PROXMOX_SERVICE": "PVE",
        "LOG_LEVEL": "DEBUG"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Mevcut Araçlar ve API Uç Noktaları

Sunucu, MCP araçları ve karşılık gelen REST API uç noktaları sağlar (14 adet):

### VM Yönetim Araçları

#### create_vm 
Belirtilen kaynaklarla yeni bir sanal makine oluşturur. Oluşturma sırasında opsiyonel olarak ISO bağlayabilir.

**Parametreler:**
- `node` (string, zorunlu): Düğüm adı
- `vmid` (string, zorunlu): Yeni VM için ID
- `name` (string, zorunlu): VM adı
- `cpus` (integer, zorunlu): CPU çekirdek sayısı (1-32)
- `memory` (integer, zorunlu): Bellek MB cinsinden (512-131072)
- `disk_size` (integer, zorunlu): Disk boyutu GB cinsinden (5-1000)
- `storage` (string, opsiyonel): Depolama havuzu adı
- `ostype` (string, opsiyonel): İşletim sistemi türü (varsayılan: l26)
- `iso_name` (string, opsiyonel): Bağlanacak ISO dosya adı (ör. `debian-12.iso`)
- `iso_storage` (string, opsiyonel): ISO'nun bulunduğu depolama adı (verilmezse otomatik bulunur)

**API Uç Noktası:**
```http
POST /create_vm
Content-Type: application/json

{
  "node": "pve",
  "vmid": "200",
  "name": "my-vm",
  "cpus": 1,
  "memory": 2048,
  "disk_size": 10,
  "iso_name": "debian-12.5.0-amd64-netinst.iso"
}
```

**Örnek Yanıt:**
```
🎉 VM 200 created successfully!

📋 VM Configuration:
  • Name: my-vm
  • Node: pve
  • VM ID: 200
  • CPU Cores: 1
  • Memory: 2048 MB (2.0 GB)
  • Disk: 10 GB (local-lvm, raw format)
  • Storage Type: lvmthin
  • Network: virtio (bridge=vmbr0)
  • QEMU Agent: Enabled
  • ISO: debian-12.5.0-amd64-netinst.iso (from local on ide3)

🔧 Task ID: UPID:pve:001AB729:0442E853:682FF380:qmcreate:200:root@pam!mcp
```

#### VM Güç Yönetimi 🆕

**start_vm**: Sanal makine başlatma
```http
POST /start_vm
{"node": "pve", "vmid": "200"}
```

**stop_vm**: Sanal makineyi zorla durdurma
```http
POST /stop_vm
{"node": "pve", "vmid": "200"}
```

**shutdown_vm**: Sanal makineyi zarif şekilde kapatma
```http
POST /shutdown_vm
{"node": "pve", "vmid": "200"}
```

**reset_vm**: Sanal makineyi resetleme (yeniden başlatma)
```http
POST /reset_vm
{"node": "pve", "vmid": "200"}
```

**delete_vm** 🆕: Sanal makineyi tamamen silme
```http
POST /delete_vm
{"node": "pve", "vmid": "200", "force": false}
```

### 🆕 Konteyner Yönetim Araçları

#### get_containers 🆕
Küme genelindeki tüm LXC konteynerleri listeleme.

**API Uç Noktası:** `POST /get_containers`

**Örnek Yanıt:**
```
🐳 Containers

🐳 nginx-server (ID: 200)
  • Status: RUNNING
  • Node: pve
  • CPU Cores: 2
  • Memory: 1.5 GB / 2.0 GB (75.0%)
```

### İzleme Araçları

#### get_nodes
Proxmox kümesindeki tüm düğümleri listeler.

**API Uç Noktası:** `POST /get_nodes`

**Örnek Yanıt:**
```
🖥️ Proxmox Nodes

🖥️ pve-compute-01
  • Status: ONLINE
  • Uptime: ⏳ 156d 12h
  • CPU Cores: 64
  • Memory: 186.5 GB / 512.0 GB (36.4%)
```

#### get_node_status
Belirli bir düğümün detaylı durumunu verir.

**Parametreler:**
- `node` (string, zorunlu): Düğüm adı

**API Uç Noktası:** `POST /get_node_status`

#### get_vms
Küme genelindeki tüm VM’leri listeler.

**API Uç Noktası:** `POST /get_vms`

#### get_storage
Mevcut depolama havuzlarını listeler.

**API Uç Noktası:** `POST /get_storage`

#### get_cluster_status
Genel küme durumu ve sağlık bilgisi.

**API Uç Noktası:** `POST /get_cluster_status`

#### execute_vm_command
QEMU Guest Agent kullanarak bir VM’in konsolunda komut çalıştırır.

**Parametreler:**
- `node` (string, zorunlu): VM’in çalıştığı düğüm adı
- `vmid` (string, zorunlu): VM’in ID’si
- `command` (string, zorunlu): Çalıştırılacak komut

**API Uç Noktası:** `POST /execute_vm_command`

**Gereksinimler:**
- VM çalışır durumda olmalı
- VM içinde QEMU Guest Agent kurulu ve çalışır olmalı

### Anlık Görüntü (Snapshot) Yönetimi ve VM Kullanımı

#### create_snapshot
Bir VM için snapshot oluşturur.

```http
POST /create_snapshot
{"node": "pve", "vmid": "100", "name": "pre-upgrade", "description": "yükseltme öncesi", "vmstate": false}
```

**Parametreler:**
- `node` (string, zorunlu): Düğüm adı
- `vmid` (string, zorunlu): VM ID
- `name` (string, zorunlu): Snapshot adı
- `description` (string, opsiyonel): Açıklama
- `vmstate` (boolean, opsiyonel): Bellek durumunu dahil et (varsayılan: false)

**API Uç Noktası:** `POST /create_snapshot`

#### rollback_snapshot
Bir VM’i belirli bir snapshot’a geri alır.

```http
POST /rollback_snapshot
{"node": "pve", "vmid": "100", "name": "pre-upgrade"}
```

**Parametreler:**
- `node` (string, zorunlu): Düğüm adı
- `vmid` (string, zorunlu): VM ID
- `name` (string, zorunlu): Snapshot adı

**API Uç Noktası:** `POST /rollback_snapshot`

#### get_vm_usage
Bir VM için anlık kaynak kullanımını döner (CPU, bellek, disk).

```http
POST /get_vm_usage
{"node": "pve", "vmid": "100"}
```

**Parametreler:**
- `node` (string, zorunlu): Düğüm adı
- `vmid` (string, zorunlu): VM ID

**API Uç Noktası:** `POST /get_vm_usage`

## Open WebUI Entegrasyonu

### Open WebUI’yi Yapılandırma

1. Open WebUI instance’ınıza erişin
2. **Settings** → **Connections** → **OpenAPI** yolunu izleyin
3. Yeni bir API yapılandırması ekleyin:

```json
{
  "name": "Proxmox MCP API Extended",
  "base_url": "http://your-server:8811",
  "api_key": "",
  "description": "Enhanced Proxmox Virtualization Management API"
}
```

### Doğal Dille VM Oluşturma

Kullanıcılar artık doğal dil ile VM talep edebilir:

- **"1 cpu çekirdek ve 2 GB ram ile 10GB diskli bir VM oluşturur musun"**
- **"Minimal kaynaklarla test için yeni bir VM oluştur"**
- **"4 çekirdek ve 8GB RAM’li bir geliştirme sunucusuna ihtiyacım var"**

Yapay zeka asistanı otomatik olarak uygun API’leri çağırır ve detaylı geri bildirim sunar.

## Depolama Türü Desteği

### Akıllı Depolama Algılama

ProxmoxMCP Extended, depolama türlerini otomatik algılar ve uygun disk formatlarını seçer:

#### LVM Depolama (local-lvm, vm-storage)
- ✅ Format: `raw`
- ✅ Yüksek performans
- ⚠️ Cloud-init imaj desteği yok

#### Dosya Tabanlı Depolama (local, NFS, CIFS)
- ✅ Format: `qcow2`
- ✅ Cloud-init desteği
- ✅ Esnek anlık görüntü (snapshot) yetenekleri

## Proje Yapısı

```
ProxmoxMCP-Extended/
├── 📁 src/                          # Kaynak kod
│   └── proxmox_mcp/
│       ├── server.py                # Ana MCP sunucu uygulaması
│       ├── config/                  # Yapılandırma işlemleri
│       ├── core/                    # Çekirdek işlevler
│       ├── formatting/              # Çıktı biçimlendirme ve temalar
│       ├── tools/                   # Araç implementasyonları
│       │   ├── vm.py               # VM yönetimi (oluşturma/güç) 🆕
│       │   ├── container.py        # Konteyner yönetimi 🆕
│       │   └── console/            # VM konsol işlemleri
│       └── utils/                   # Yardımcılar (auth, logging)
│
├── 📁 tests/                       # Birim testleri
├── 📁 scripts/live/                 # Entegrasyon testleri ve demolar
│   ├── README.md                   # Test dokümantasyonu
│   ├── test_vm_power.py           # VM güç yönetimi testleri 🆕
│   ├── test_vm_start.py           # VM başlatma testleri
│   ├── test_create_vm.py          # VM oluşturma testleri 🆕
│   └── test_openapi.py            # OpenAPI servis testleri
│
├── 📁 proxmox-config/              # Yapılandırma dosyaları
│   └── config.json                # Sunucu yapılandırması
│
├── 📄 Yapılandırma Dosyaları
│   ├── pyproject.toml             # Proje meta verisi
│   ├── docker-compose.yml         # Docker orkestrasyonu
│   ├── Dockerfile                 # Docker imaj tanımı
│   └── requirements.in            # Bağımlılıklar
│
├── 📄 Scriptler
│   ├── start_server.sh            # MCP sunucu başlatıcı
│   └── start_openapi.sh           # OpenAPI servis başlatıcı
│
└── 📄 Dokümantasyon
    ├── README.md                  # Bu dosya
    ├── VM_CREATION_GUIDE.md       # VM oluşturma kılavuzu
    ├── OPENAPI_DEPLOYMENT.md      # OpenAPI dağıtımı
    └── LICENSE                    # MIT Lisansı
```

## Test

### Birim Testlerini Çalıştır
```bash
pytest
```

### Entegrasyon Testlerini Çalıştır
```bash
cd scripts/live

# VM güç yönetimi testi
python test_vm_power.py

# VM oluşturma testi
python test_create_vm.py

# OpenAPI servis testi
python test_openapi.py
```

### curl ile API Testi
```bash
# Düğüm listeleme testi
curl -X POST "http://your-server:8811/get_nodes" \
  -H "Content-Type: application/json" \
  -d "{}"

# VM oluşturma testi
curl -X POST "http://your-server:8811/create_vm" \
  -H "Content-Type: application/json" \
  -d '{
    "node": "pve",
    "vmid": "300",
    "name": "test-vm",
    "cpus": 1,
    "memory": 2048,
    "disk_size": 10
  }'
```

## Üretim Güvenliği

### API Anahtarı ile Kimlik Doğrulama
Güvenli API erişimini ayarlayın:

```bash
export PROXMOX_API_KEY="your-secure-api-key"
export PROXMOX_MCP_CONFIG="/app/proxmox-config/config.json"
```

### Nginx Ters Vekil (Reverse Proxy)
Örnek nginx yapılandırması:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8811;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Sorun Giderme

### Yaygın Sorunlar

1. **Port zaten kullanımda**
   ```bash
   netstat -tlnp | grep 8811
   # Gerekirse portu değiştirin
   mcpo --port 8812 -- ./start_server.sh
   ```

2. **Yapılandırma hataları**
   ```bash
   # Yapılandırma dosyasını doğrulayın
   cat proxmox-config/config.json
   ```

3. **Bağlantı sorunları**
   ```bash
   # Proxmox bağlantısını test edin
   curl -k https://your-proxmox:8006/api2/json/version
   ```

### Logları Görüntüle
```bash
# Servis loglarını görüntüle
tail -f proxmox_mcp.log

# Docker logları
docker logs proxmox-mcp-api -f
```

## Dağıtım Durumu

### ✅ Özellik Tamamlama: %100

- [x] VM Oluşturma (kullanıcı isteği: 1 CPU + 2GB RAM + 10GB disk) 🆕
- [x] VM Güç Yönetimi (start VPN-Server ID:101) 🆕
- [x] VM Silme Özelliği 🆕
- [x] Konteyner Yönetimi (LXC) 🆕
- [x] Depolama Uyumluluğu (LVM/dosya tabanlı)
- [x] OpenAPI Entegrasyonu (port 8811)
- [x] Open WebUI Entegrasyonu
- [x] Hata Yönetimi ve Doğrulama
- [x] Tam Dokümantasyon ve Test

### Üretime Hazır!

**ProxmoxMCP Extended artık üretim kullanımına tamamen hazır!**

Kullanıcılar **"1 cpu çekirdek ve 2 GB ram ile 10GB diskli bir VM oluşturur musun"** dediğinde, yapay zeka asistanı:

1. 📞 `create_vm` API’sini çağırır
2. 🔧 Uygun depolama ve formatı otomatik seçer
3. 🎯 İstenilen özelliklerde VM oluşturur
4. 📊 Detaylı yapılandırma bilgisini döner
5. 💡 Sonraki adımlar için öneriler sağlar

## Geliştirme

Sanal ortamı aktifleştirdikten sonra:

- Testleri çalıştır: `pytest`
- Kod biçimlendirme: `black .`
- Tip kontrolü: `mypy .`
- Lint: `ruff .`

## Lisans

MIT Lisansı

## Özel Teşekkürler

- Mükemmel temel projeyi sağlayan [@canvrno](https://github.com/canvrno) ve [ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP) için teşekkürler
- Güçlü sanallaştırma platformunu sağlayan Proxmox topluluğuna teşekkürler
- Tüm katkıda bulunanlara ve kullanıcılara destekleri için teşekkürler

---

**Dağıtıma Hazır!** 🎉 OpenAPI entegrasyonlu, geliştirilmiş Proxmox MCP servisiniz üretim için hazır.


