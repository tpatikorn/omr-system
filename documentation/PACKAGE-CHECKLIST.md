# Checklist: ไฟล์ที่ต้องเอาไปติดตั้งในเครื่องใหม่

## ✅ ไฟล์หลัก (จำเป็น)

### Docker Configuration
- [ ] `Dockerfile` - สำหรับ build Docker image
- [ ] `docker-compose.yml` - สำหรับจัดการ container
- [ ] `.dockerignore` - กำหนดไฟล์ที่ไม่ต้อง copy เข้า Docker

### Application Files
- [ ] `app.py` - Main Flask application
- [ ] `requirements.txt` - Python dependencies
- [ ] `.env` - Environment variables (⚠️ ต้องแก้ไข IP ก่อนใช้)

### Frontend Files
- [ ] `static/` - โฟลเดอร์ทั้งหมด
  - [ ] `static/css/`
  - [ ] `static/js/`
  - [ ] `static/images/` (ถ้ามี)
  
- [ ] `templates/` - โฟลเดอร์ทั้งหมด
  - [ ] `templates/*.html`

## 📚 ไฟล์เอกสาร (แนะนำ)
- [ ] `README.Docker.md` - คู่มือการใช้งาน Docker
- [ ] `DEPLOYMENT.md` - คู่มือการติดตั้งในเครื่องใหม่
- [ ] `PACKAGE-CHECKLIST.md` - ไฟล์นี้

## ❌ ไฟล์ที่ไม่ต้องเอาไป

### Generated Folders (จะถูกสร้างโดย Docker)
- ❌ `uploads/` - จะถูกสร้างอัตโนมัติ
- ❌ `debug_output/` - จะถูกสร้างอัตโนมัติ
- ❌ `config/` - จะถูกสร้างอัตโนมัติ

### Python Cache
- ❌ `__pycache__/`
- ❌ `*.pyc`
- ❌ `*.pyo`
- ❌ `*.pyd`

### IDE & Editor
- ❌ `.vscode/`
- ❌ `.idea/`
- ❌ `.kiro/`
- ❌ `*.swp`
- ❌ `*.swo`

### Version Control
- ❌ `.git/` (ถ้าไม่ต้องการ git history)
- ❌ `.gitignore`

### OS Files
- ❌ `.DS_Store` (Mac)
- ❌ `Thumbs.db` (Windows)
- ❌ `desktop.ini` (Windows)

## 📦 วิธีการ Package

### วิธีที่ 1: ZIP/TAR (แนะนำ)
```bash
# สร้าง zip file (Windows)
# เลือกไฟล์ที่จำเป็น → คลิกขวา → Send to → Compressed (zipped) folder

# สร้าง tar.gz (Mac/Linux)
tar -czf omr-system.tar.gz \
  Dockerfile \
  docker-compose.yml \
  .dockerignore \
  app.py \
  requirements.txt \
  .env \
  static/ \
  templates/ \
  README.Docker.md \
  DEPLOYMENT.md
```

### วิธีที่ 2: Git Clone (ถ้ามี Git Repository)
```bash
git clone <repository-url>
cd omr-system
```

### วิธีที่ 3: Docker Image Export (สำหรับเครื่องที่ไม่มี Internet)
```bash
# Export Docker image
docker save omr-system-project-omr-app:latest -o omr-system-image.tar

# Copy ไฟล์เหล่านี้ไปเครื่องใหม่:
# - omr-system-image.tar
# - docker-compose.yml
# - .env

# ในเครื่องใหม่ import image
docker load -i omr-system-image.tar

# แก้ไข .env แล้วรัน
docker-compose up -d
```

## 🔧 ขั้นตอนหลังการ Copy

### 1. แก้ไขไฟล์ .env
```env
# เปลี่ยน IP ให้ตรงกับเครื่องใหม่
OMR_BASE_URL=http://NEW_IP_ADDRESS:5000
```

### 2. ตรวจสอบ Docker
```bash
docker --version
docker-compose --version
```

### 3. Build และรัน
```bash
docker-compose build
docker-compose up -d
```

### 4. ทดสอบ
- เปิดเบราว์เซอร์: http://localhost:5000
- ทดสอบจากเครื่องอื่น: http://NEW_IP:5000

## 📋 Quick Copy Command

### สำหรับ Windows (PowerShell)
```powershell
# สร้างโฟลเดอร์ใหม่และ copy ไฟล์ที่จำเป็น
$dest = "C:\omr-system-deploy"
New-Item -ItemType Directory -Path $dest -Force
Copy-Item -Path Dockerfile, docker-compose.yml, .dockerignore, app.py, requirements.txt, .env -Destination $dest
Copy-Item -Path static, templates -Destination $dest -Recurse
Copy-Item -Path *.md -Destination $dest
```

### สำหรับ Mac/Linux (Bash)
```bash
# สร้างโฟลเดอร์ใหม่และ copy ไฟล์ที่จำเป็น
dest="$HOME/omr-system-deploy"
mkdir -p "$dest"
cp Dockerfile docker-compose.yml .dockerignore app.py requirements.txt .env "$dest/"
cp -r static templates "$dest/"
cp *.md "$dest/"
```

## 🎯 ขนาดโปรเจคโดยประมาณ

- ไฟล์ source code: ~5-10 MB
- Docker image: ~500-800 MB
- ข้อมูล runtime (uploads/config): ขึ้นอยู่กับการใช้งาน

## ⚠️ สิ่งที่ต้องระวัง

1. **ไฟล์ .env** - ต้องแก้ไข IP address ทุกครั้งที่ย้ายเครื่อง
2. **Port 5000** - ตรวจสอบว่าไม่ถูกใช้งานในเครื่องใหม่
3. **Firewall** - อาจต้องเปิด port 5000 ใน firewall
4. **Docker Desktop** - ต้องเปิดใช้งานก่อนรัน docker-compose
5. **Backup ข้อมูล** - สำรองข้อมูลใน uploads/ และ config/ ก่อนลบ container

## 📞 ติดปัญหา?

ดูคู่มือแก้ปัญหาใน `DEPLOYMENT.md` หรือตรวจสอบ logs:
```bash
docker-compose logs -f
```
