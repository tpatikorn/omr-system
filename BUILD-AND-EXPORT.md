# คู่มือการสร้าง Docker Image แบบไฟล์เดียว

## 🎯 แนวคิด
แทนที่จะเอาโค้ดทั้งหมดไป เราจะ:
1. Build Docker image ในเครื่องต้นทาง
2. Export เป็นไฟล์ `.tar` (ไฟล์เดียว ขนาดใหญ่ ~500-800 MB)
3. เอาไฟล์ image + docker-compose.prod.yml + .env ไปเครื่องปลายทาง
4. Import image และรัน

## 📦 ขั้นตอนที่ 1: Build และ Export Image (ทำในเครื่องต้นทาง)

### 1.1 Build Docker Image
```bash
# Build image จากโค้ดปัจจุบัน
docker-compose build

# หรือ build ด้วย tag ที่กำหนดเอง
docker build -t omr-system:latest .
```

### 1.2 Export Image เป็นไฟล์
```bash
# Export image เป็นไฟล์ .tar
docker save omr-system:latest -o omr-system-image.tar

# ตรวจสอบขนาดไฟล์
# Windows
dir omr-system-image.tar

# Mac/Linux
ls -lh omr-system-image.tar
```

### 1.3 (Optional) บีบอัดไฟล์เพื่อลดขนาด
```bash
# Windows (PowerShell)
Compress-Archive -Path omr-system-image.tar -DestinationPath omr-system-image.zip

# Mac/Linux
gzip omr-system-image.tar
# จะได้ไฟล์ omr-system-image.tar.gz (เล็กกว่าประมาณ 30-40%)
```

## 📤 ขั้นตอนที่ 2: เตรียมไฟล์สำหรับเครื่องปลายทาง

### ไฟล์ที่ต้องเอาไป (เพียง 3 ไฟล์!)
```
📦 Package/
├── 📄 omr-system-image.tar        # Docker image (ไฟล์ใหญ่ ~500-800 MB)
├── 📄 docker-compose.prod.yml     # Configuration สำหรับรัน
└── 📄 .env                        # Environment variables
```

### สร้าง Package
```bash
# Windows (PowerShell)
New-Item -ItemType Directory -Path "omr-deploy-package" -Force
Copy-Item omr-system-image.tar, docker-compose.prod.yml, .env -Destination omr-deploy-package/

# Mac/Linux
mkdir -p omr-deploy-package
cp omr-system-image.tar docker-compose.prod.yml .env omr-deploy-package/
```

## 📥 ขั้นตอนที่ 3: ติดตั้งในเครื่องปลายทาง

### 3.1 ติดตั้ง Docker (ถ้ายังไม่มี)
- Windows/Mac: ติดตั้ง [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Linux: `curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh`

### 3.2 Copy ไฟล์ทั้ง 3 ไปเครื่องปลายทาง
ใช้ USB, Network Share, หรือ Cloud Storage

### 3.3 Import Docker Image
```bash
# เข้าไปในโฟลเดอร์ที่มีไฟล์
cd omr-deploy-package

# Import image (ถ้าเป็นไฟล์ .tar.gz ให้ uncompress ก่อน)
docker load -i omr-system-image.tar

# ตรวจสอบว่า import สำเร็จ
docker images | grep omr-system
```

### 3.4 แก้ไขไฟล์ .env
```bash
# แก้ไข IP ให้ตรงกับเครื่องใหม่
# Windows: notepad .env
# Mac/Linux: nano .env

OMR_BASE_URL=http://NEW_IP_ADDRESS:5000
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
```

### 3.5 รัน Container
```bash
# รัน container ด้วย docker-compose.prod.yml
docker-compose -f docker-compose.prod.yml up -d

# ดู logs
docker-compose -f docker-compose.prod.yml logs -f

# ตรวจสอบสถานะ
docker ps
```

### 3.6 เข้าใช้งาน
- Local: http://localhost:5000
- Network: http://NEW_IP:5000

## 🔄 การอัพเดท Image

### ในเครื่องต้นทาง (มีโค้ด)
```bash
# 1. แก้ไขโค้ด
# 2. Build image ใหม่
docker-compose build

# 3. Export image ใหม่
docker save omr-system:latest -o omr-system-image-v2.tar

# 4. เอาไฟล์ใหม่ไปเครื่องปลายทาง
```

### ในเครื่องปลายทาง (ไม่มีโค้ด)
```bash
# 1. หยุด container เก่า
docker-compose -f docker-compose.prod.yml down

# 2. ลบ image เก่า (optional)
docker rmi omr-system:latest

# 3. Import image ใหม่
docker load -i omr-system-image-v2.tar

# 4. รัน container ใหม่
docker-compose -f docker-compose.prod.yml up -d
```

## 📊 เปรียบเทียบวิธีการ

### วิธีที่ 1: เอาโค้ดไป (เดิม)
```
✅ ข้อดี:
- แก้ไขโค้ดได้ในเครื่องปลายทาง
- Build ใหม่ได้เมื่อต้องการ

❌ ข้อเสีย:
- ต้อง copy ไฟล์เยอะ (โค้ด + dependencies)
- ต้อง build ทุกครั้งในเครื่องใหม่ (ใช้เวลานาน)
- ต้องมี internet สำหรับ download dependencies
```

### วิธีที่ 2: Export Image (ใหม่) ⭐ แนะนำ
```
✅ ข้อดี:
- Copy แค่ 3 ไฟล์ (image + yml + .env)
- ไม่ต้อง build ใหม่ (ประหยัดเวลา)
- ไม่ต้องมี internet ในเครื่องปลายทาง
- รันได้ทันที (แค่ import + up)

❌ ข้อเสีย:
- ไฟล์ image ใหญ่ (~500-800 MB)
- แก้ไขโค้ดไม่ได้ในเครื่องปลายทาง (ต้อง rebuild ในเครื่องต้นทาง)
```

## 🎯 Use Cases

### ใช้วิธีที่ 1 (เอาโค้ดไป) เมื่อ:
- ต้องการแก้ไขโค้ดในเครื่องปลายทาง
- มี internet ในเครื่องปลายทาง
- ไม่กังวลเรื่องเวลา build

### ใช้วิธีที่ 2 (Export Image) เมื่อ: ⭐
- ต้องการติดตั้งเร็ว
- ไม่มี internet ในเครื่องปลายทาง
- ไม่ต้องการแก้ไขโค้ด (ใช้งานอย่างเดียว)
- ต้องการติดตั้งหลายเครื่อง (export ครั้งเดียว ใช้ได้หลายเครื่อง)

## 🛠️ คำสั่งที่มีประโยชน์

### ดูขนาด Image
```bash
docker images omr-system:latest
```

### ลบ Image เก่า
```bash
docker rmi omr-system:latest
```

### ดู Image ทั้งหมด
```bash
docker images
```

### ลบ Image ที่ไม่ใช้งาน
```bash
docker image prune -a
```

## 📝 Template ไฟล์ .env สำหรับเครื่องปลายทาง

สร้างไฟล์ `.env.template` เพื่อให้ผู้ใช้แก้ไข:

```env
# OMR System Configuration
# แก้ไข IP_ADDRESS ให้ตรงกับเครื่องของคุณ

# วิธีหา IP:
# Windows: เปิด CMD พิมพ์ ipconfig
# Mac/Linux: เปิด Terminal พิมพ์ ifconfig

OMR_BASE_URL=http://YOUR_IP_ADDRESS:5000
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
FLASK_DEBUG=False
FLASK_ENV=production
```

## 🚀 Quick Start Script

### สำหรับ Windows (PowerShell)
สร้างไฟล์ `start.ps1`:
```powershell
# OMR System Quick Start Script

Write-Host "=== OMR System Deployment ===" -ForegroundColor Green

# ตรวจสอบว่ามี Docker หรือไม่
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Docker not found. Please install Docker Desktop first." -ForegroundColor Red
    exit 1
}

# ตรวจสอบว่ามีไฟล์ image หรือไม่
if (!(Test-Path "omr-system-image.tar")) {
    Write-Host "Error: omr-system-image.tar not found." -ForegroundColor Red
    exit 1
}

# Import image
Write-Host "Importing Docker image..." -ForegroundColor Yellow
docker load -i omr-system-image.tar

# ตรวจสอบไฟล์ .env
if (!(Test-Path ".env")) {
    Write-Host "Warning: .env file not found. Creating from template..." -ForegroundColor Yellow
    Copy-Item .env.template .env
    Write-Host "Please edit .env file and set your IP address, then run this script again." -ForegroundColor Yellow
    exit 0
}

# รัน container
Write-Host "Starting container..." -ForegroundColor Yellow
docker-compose -f docker-compose.prod.yml up -d

# แสดงสถานะ
Write-Host "`n=== Container Status ===" -ForegroundColor Green
docker ps

Write-Host "`n=== Access URLs ===" -ForegroundColor Green
Write-Host "Local: http://localhost:5000"
$env_content = Get-Content .env | Select-String "OMR_BASE_URL"
if ($env_content) {
    Write-Host "Network: $($env_content -replace 'OMR_BASE_URL=','')"
}

Write-Host "`nTo view logs: docker-compose -f docker-compose.prod.yml logs -f" -ForegroundColor Cyan
```

### สำหรับ Mac/Linux (Bash)
สร้างไฟล์ `start.sh`:
```bash
#!/bin/bash

# OMR System Quick Start Script

echo "=== OMR System Deployment ==="

# ตรวจสอบว่ามี Docker หรือไม่
if ! command -v docker &> /dev/null; then
    echo "Error: Docker not found. Please install Docker first."
    exit 1
fi

# ตรวจสอบว่ามีไฟล์ image หรือไม่
if [ ! -f "omr-system-image.tar" ]; then
    echo "Error: omr-system-image.tar not found."
    exit 1
fi

# Import image
echo "Importing Docker image..."
docker load -i omr-system-image.tar

# ตรวจสอบไฟล์ .env
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Creating from template..."
    cp .env.template .env
    echo "Please edit .env file and set your IP address, then run this script again."
    exit 0
fi

# รัน container
echo "Starting container..."
docker-compose -f docker-compose.prod.yml up -d

# แสดงสถานะ
echo ""
echo "=== Container Status ==="
docker ps

echo ""
echo "=== Access URLs ==="
echo "Local: http://localhost:5000"
grep "OMR_BASE_URL" .env | sed 's/OMR_BASE_URL=/Network: /'

echo ""
echo "To view logs: docker-compose -f docker-compose.prod.yml logs -f"
```

ทำให้ script รันได้:
```bash
chmod +x start.sh
./start.sh
```

## 📦 Final Package Structure

```
omr-deploy-package/
├── omr-system-image.tar          # Docker image (ไฟล์ใหญ่)
├── docker-compose.prod.yml       # Docker compose config
├── .env.template                 # Template สำหรับ config
├── start.ps1                     # Quick start script (Windows)
├── start.sh                      # Quick start script (Mac/Linux)
└── README.txt                    # คำแนะนำสั้นๆ
```

### README.txt
```
OMR System - Quick Installation Guide

1. Install Docker Desktop (if not installed)
   https://www.docker.com/products/docker-desktop/

2. Copy .env.template to .env and edit your IP address
   
3. Run the start script:
   - Windows: Right-click start.ps1 → Run with PowerShell
   - Mac/Linux: ./start.sh

4. Access the application:
   - Local: http://localhost:5000
   - Network: http://YOUR_IP:5000

For more details, see DEPLOYMENT.md
```
