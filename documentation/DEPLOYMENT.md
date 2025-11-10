# คู่มือการติดตั้งและใช้งาน OMR System ในเครื่องใหม่

## สิ่งที่ต้องเตรียม

### 1. ติดตั้ง Docker
- **Windows**: ดาวน์โหลด [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
- **Mac**: ดาวน์โหลด [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
- **Linux**: 
  ```bash
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  ```

### 2. ตรวจสอบการติดตั้ง
```bash
docker --version
docker-compose --version
```

## วิธีการติดตั้ง

### ขั้นตอนที่ 1: Copy ไฟล์โปรเจค
Copy ไฟล์และโฟลเดอร์ทั้งหมดไปยังเครื่องใหม่:
```
โปรเจค/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env
├── .dockerignore
├── app.py
├── static/
└── templates/
```

### ขั้นตอนที่ 2: แก้ไขไฟล์ .env
เปิดไฟล์ `.env` และแก้ไข IP address ให้ตรงกับเครื่องใหม่:

```env
# หา IP ของเครื่อง
# Windows: ipconfig
# Mac/Linux: ifconfig หรือ ip addr

OMR_BASE_URL=http://192.168.1.XXX:5000
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
FLASK_DEBUG=False
FLASK_ENV=production
```

**วิธีหา IP Address:**

**Windows:**
```cmd
ipconfig
```
มองหา "IPv4 Address" ในส่วน "Wireless LAN adapter Wi-Fi" หรือ "Ethernet adapter"

**Mac/Linux:**
```bash
ifconfig
# หรือ
ip addr show
```

### ขั้นตอนที่ 3: Build และรัน Docker

เปิด Terminal/Command Prompt ในโฟลเดอร์โปรเจค แล้วรันคำสั่ง:

```bash
# Build Docker image
docker-compose build

# รัน container
docker-compose up -d

# ดู logs เพื่อตรวจสอบ
docker-compose logs -f
```

### ขั้นตอนที่ 4: เข้าใช้งาน

เปิดเบราว์เซอร์และไปที่:
- **จากเครื่องเดียวกัน**: http://localhost:5000
- **จากเครื่องอื่นในเครือข่าย**: http://192.168.1.XXX:5000

## การจัดการ Container

### ดูสถานะ
```bash
docker ps
```

### ดู logs
```bash
docker-compose logs -f omr-app
```

### หยุด container
```bash
docker-compose down
```

### Restart container
```bash
docker-compose restart
```

### Rebuild (เมื่อมีการแก้ไขโค้ด)
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## การ Backup และ Restore ข้อมูล

### Backup
```bash
# Backup ข้อมูลทั้งหมด
tar -czf omr-backup-$(date +%Y%m%d).tar.gz uploads/ debug_output/ config/

# หรือ backup แยกส่วน
tar -czf uploads-backup.tar.gz uploads/
tar -czf config-backup.tar.gz config/
```

### Restore
```bash
# Extract backup
tar -xzf omr-backup-YYYYMMDD.tar.gz

# หรือ restore แยกส่วน
tar -xzf uploads-backup.tar.gz
tar -xzf config-backup.tar.gz
```

## Troubleshooting

### ปัญหา: Port 5000 ถูกใช้งานอยู่
```bash
# Windows
netstat -ano | findstr :5000

# Mac/Linux
lsof -i :5000

# แก้ไข: เปลี่ยน port ในไฟล์ docker-compose.yml
ports:
  - "5001:5000"  # เปลี่ยนจาก 5000:5000
```

### ปัญหา: ไม่สามารถเข้าถึงจากเครื่องอื่น
1. ตรวจสอบ Firewall
   - **Windows**: Settings → Windows Security → Firewall → Allow an app → เปิด port 5000
   - **Mac**: System Preferences → Security & Privacy → Firewall
   - **Linux**: `sudo ufw allow 5000`

2. ตรวจสอบว่า container รันอยู่
   ```bash
   docker ps
   ```

3. ตรวจสอบ IP address ใน .env ถูกต้อง

### ปัญหา: Container หยุดทำงานเอง
```bash
# ดู logs เพื่อหาสาเหตุ
docker logs omr-system

# ดู error ล่าสุด
docker logs omr-system --tail 100
```

### ปัญหา: Out of memory
แก้ไขไฟล์ `docker-compose.yml` เพิ่ม memory limit:
```yaml
services:
  omr-app:
    # ... existing config ...
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

## การอัพเดทโปรเจค

เมื่อมีการแก้ไขโค้ด:

```bash
# 1. หยุด container
docker-compose down

# 2. Pull โค้ดใหม่ หรือ copy ไฟล์ใหม่

# 3. Rebuild
docker-compose build --no-cache

# 4. รันใหม่
docker-compose up -d
```

## การลบและติดตั้งใหม่ทั้งหมด

```bash
# หยุดและลบ container
docker-compose down

# ลบ image
docker rmi omr-system-project-omr-app

# ลบ volumes (ระวัง: จะลบข้อมูลทั้งหมด)
docker volume prune

# ติดตั้งใหม่
docker-compose build
docker-compose up -d
```

## Production Deployment (สำหรับใช้งานจริง)

### 1. ใช้ HTTPS (แนะนำ)
ติดตั้ง nginx เป็น reverse proxy พร้อม SSL certificate

### 2. ตั้งค่า Auto-restart
ใน `docker-compose.yml` มีการตั้งค่า `restart: unless-stopped` อยู่แล้ว

### 3. Monitoring
```bash
# ดูการใช้ resources
docker stats omr-system

# ตั้งค่า health check
docker inspect omr-system | grep Health
```

### 4. Backup อัตโนมัติ
สร้าง cron job สำหรับ backup:
```bash
# เปิด crontab
crontab -e

# เพิ่มบรรทัดนี้ (backup ทุกวันเวลา 2:00 AM)
0 2 * * * cd /path/to/project && tar -czf backup-$(date +\%Y\%m\%d).tar.gz uploads/ config/
```

## ติดต่อและรายงานปัญหา

หากพบปัญหาในการใช้งาน:
1. ตรวจสอบ logs: `docker-compose logs -f`
2. ตรวจสอบ container status: `docker ps -a`
3. ตรวจสอบ network: `docker network ls`
