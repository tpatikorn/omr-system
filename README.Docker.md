# Docker Setup สำหรับ OMR System

## การติดตั้งและรัน

### 1. ติดตั้ง Docker
ตรวจสอบว่าคุณติดตั้ง Docker และ Docker Compose แล้ว:
```bash
docker --version
docker-compose --version
```

### 2. แก้ไขไฟล์ .env
แก้ไข `OMR_BASE_URL` ในไฟล์ `.env` ให้ตรงกับ IP ของเครื่อง server:
```
OMR_BASE_URL=http://YOUR_SERVER_IP:5000
```

### 3. Build และรัน Docker Container

#### วิธีที่ 1: ใช้ Docker Compose (แนะนำ)
```bash
# Build และรัน
docker-compose up -d

# ดู logs
docker-compose logs -f

# หยุด container
docker-compose down

# หยุดและลบ volumes
docker-compose down -v
```

#### วิธีที่ 2: ใช้ Docker โดยตรง
```bash
# Build image
docker build -t omr-system .

# รัน container
docker run -d \
  --name omr-system \
  -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/debug_output:/app/debug_output \
  -v $(pwd)/config:/app/config \
  --env-file .env \
  omr-system

# ดู logs
docker logs -f omr-system

# หยุด container
docker stop omr-system

# ลบ container
docker rm omr-system
```

### 4. เข้าใช้งาน
เปิดเบราว์เซอร์และไปที่:
- Local: http://localhost:5000
- Network: http://YOUR_SERVER_IP:5000

## คำสั่งที่มีประโยชน์

```bash
# ดูสถานะ containers
docker-compose ps

# Restart container
docker-compose restart

# ดู logs แบบ real-time
docker-compose logs -f omr-app

# เข้าไปใน container
docker-compose exec omr-app bash

# Rebuild image (เมื่อมีการเปลี่ยนแปลงโค้ด)
docker-compose up -d --build

# ดูการใช้ resources
docker stats omr-system
```

## การจัดการข้อมูล

### Volumes
ข้อมูลจะถูกเก็บใน volumes ดังนี้:
- `./uploads` - ไฟล์ที่อัปโหลด
- `./debug_output` - ไฟล์ debug และผลลัพธ์
- `./config` - ไฟล์ configuration และ session data

### Backup ข้อมูล
```bash
# Backup volumes
tar -czf omr-backup-$(date +%Y%m%d).tar.gz uploads/ debug_output/ config/

# Restore
tar -xzf omr-backup-YYYYMMDD.tar.gz
```

## Troubleshooting

### ปัญหา: Container ไม่สามารถเริ่มได้
```bash
# ดู logs เพื่อหาสาเหตุ
docker-compose logs omr-app

# ตรวจสอบว่า port 5000 ว่างหรือไม่
netstat -an | grep 5000
```

### ปัญหา: ไม่สามารถเข้าถึงจากเครือข่ายภายนอก
- ตรวจสอบ firewall settings
- ตรวจสอบว่า `OMR_BASE_URL` ใน `.env` ถูกต้อง
- ตรวจสอบว่า Docker container bind กับ `0.0.0.0:5000`

### ปัญหา: OpenCV หรือ pdf2image ไม่ทำงาน
```bash
# Rebuild image ใหม่
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Production Deployment

สำหรับ production แนะนำให้:
1. ใช้ reverse proxy (nginx/traefik)
2. เปิดใช้ HTTPS
3. ตั้งค่า resource limits
4. ใช้ Docker secrets สำหรับข้อมูลที่เป็นความลับ
5. ตั้งค่า health checks
6. ใช้ logging driver ที่เหมาะสม

### ตัวอย่าง docker-compose.yml สำหรับ production:
```yaml
services:
  omr-app:
    # ... existing config ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```
