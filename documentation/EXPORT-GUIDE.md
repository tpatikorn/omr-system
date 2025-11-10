# คู่มือการ Export และติดตั้งแบบไฟล์เดียว

## 🎯 สรุปแนวคิด

แทนที่จะเอาโค้ดทั้งหมดไป เราจะ:
1. **Build** Docker image ในเครื่องที่มีโค้ด
2. **Export** เป็นไฟล์ `.tar` (ไฟล์เดียว ~500-800 MB)
3. **Copy** แค่ 4 ไฟล์ไปเครื่องใหม่
4. **Import** และรันทันที

---

## 📦 STEP 1: Export Image (ทำในเครื่องที่มีโค้ด)

### 1.1 Build Docker Image
```bash
# Build image จาก Dockerfile
docker-compose build

# ตรวจสอบว่า build สำเร็จ
docker images | grep omr-system
```

### 1.2 Export Image เป็นไฟล์
```bash
# Export image เป็นไฟล์ .tar
docker save omr-system-project-omr-app:latest -o omr-system-image.tar

# หรือถ้าต้องการใช้ชื่อ tag ที่สั้นกว่า
docker tag omr-system-project-omr-app:latest omr-system:latest
docker save omr-system:latest -o omr-system-image.tar
```

### 1.3 ตรวจสอบขนาดไฟล์
```bash
# Windows (PowerShell)
Get-Item omr-system-image.tar | Select-Object Name, @{Name="Size(MB)";Expression={[math]::Round($_.Length/1MB,2)}}

# Mac/Linux
ls -lh omr-system-image.tar
```

### 1.4 (Optional) บีบอัดเพื่อลดขนาด
```bash
# Windows (PowerShell)
Compress-Archive -Path omr-system-image.tar -DestinationPath omr-system-image.zip

# Mac/Linux
gzip omr-system-image.tar
# จะได้ omr-system-image.tar.gz (เล็กกว่าประมาณ 30-40%)
```

---

## 📤 STEP 2: เตรียม Package สำหรับเครื่องปลายทาง

### ไฟล์ที่ต้องเอาไป (เพียง 4-5 ไฟล์!)
```
📦 omr-deploy-package/
├── 📄 omr-system-image.tar       # Docker image (ไฟล์ใหญ่)
├── 📄 docker-compose.prod.yml    # Config สำหรับรัน
├── 📄 .env.template              # Template สำหรับ config
├── 📄 start.ps1                  # Script สำหรับ Windows
└── 📄 start.sh                   # Script สำหรับ Mac/Linux
```

### สร้าง Package อัตโนมัติ

**Windows (PowerShell):**
```powershell
# สร้างโฟลเดอร์
New-Item -ItemType Directory -Path "omr-deploy-package" -Force

# Copy ไฟล์ที่จำเป็น
Copy-Item omr-system-image.tar -Destination omr-deploy-package/
Copy-Item docker-compose.prod.yml -Destination omr-deploy-package/
Copy-Item .env.template -Destination omr-deploy-package/
Copy-Item start.ps1 -Destination omr-deploy-package/
Copy-Item start.sh -Destination omr-deploy-package/

# สร้าง README
@"
OMR System - Quick Installation

1. Install Docker Desktop: https://www.docker.com/products/docker-desktop/
2. Run start script:
   - Windows: Right-click start.ps1 → Run with PowerShell
   - Mac/Linux: chmod +x start.sh && ./start.sh
3. Follow the instructions to configure .env file
4. Access: http://localhost:5000

"@ | Out-File -FilePath omr-deploy-package/README.txt

Write-Host "✅ Package created in omr-deploy-package/" -ForegroundColor Green
```

**Mac/Linux (Bash):**
```bash
# สร้างโฟลเดอร์
mkdir -p omr-deploy-package

# Copy ไฟล์ที่จำเป็น
cp omr-system-image.tar omr-deploy-package/
cp docker-compose.prod.yml omr-deploy-package/
cp .env.template omr-deploy-package/
cp start.ps1 omr-deploy-package/
cp start.sh omr-deploy-package/

# สร้าง README
cat > omr-deploy-package/README.txt << 'EOF'
OMR System - Quick Installation

1. Install Docker Desktop: https://www.docker.com/products/docker-desktop/
2. Run start script:
   - Windows: Right-click start.ps1 → Run with PowerShell
   - Mac/Linux: chmod +x start.sh && ./start.sh
3. Follow the instructions to configure .env file
4. Access: http://localhost:5000
EOF

echo "✅ Package created in omr-deploy-package/"
```

---

## 📥 STEP 3: ติดตั้งในเครื่องปลายทาง

### 3.1 ติดตั้ง Docker (ถ้ายังไม่มี)
- **Windows/Mac**: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Linux**: `curl -fsSL https://get.docker.com | sh`

### 3.2 Copy Package ไปเครื่องปลายทาง
ใช้ USB, Network Share, Cloud Storage, หรือ SCP

### 3.3 รัน Start Script

**Windows:**
```powershell
# คลิกขวาที่ start.ps1 → Run with PowerShell
# หรือเปิด PowerShell แล้วรัน:
.\start.ps1
```

**Mac/Linux:**
```bash
# ทำให้ script รันได้
chmod +x start.sh

# รัน script
./start.sh
```

### 3.4 Script จะทำอะไร?
1. ✅ ตรวจสอบว่ามี Docker
2. ✅ ตรวจสอบว่า Docker กำลังรัน
3. ✅ ตรวจสอบว่ามีไฟล์ image
4. ✅ Import image (ถ้ายังไม่มี)
5. ✅ สร้างไฟล์ .env จาก template
6. ⚠️ แจ้งให้แก้ไข .env (ใส่ IP address)
7. ✅ รัน container
8. ✅ แสดง URL สำหรับเข้าใช้งาน

### 3.5 แก้ไขไฟล์ .env
```bash
# Windows
notepad .env

# Mac
open -e .env

# Linux
nano .env
```

แก้ไขบรรทัดนี้:
```env
OMR_BASE_URL=http://YOUR_IP_ADDRESS:5000
```

เป็น:
```env
OMR_BASE_URL=http://192.168.1.100:5000  # ใส่ IP จริงของคุณ
```

### 3.6 รัน Script อีกครั้ง
```bash
# Windows
.\start.ps1

# Mac/Linux
./start.sh
```

### 3.7 เข้าใช้งาน
- **Local**: http://localhost:5000
- **Network**: http://YOUR_IP:5000

---

## 🔄 การอัพเดท

### ในเครื่องต้นทาง (มีโค้ด)
```bash
# 1. แก้ไขโค้ด
# 2. Build ใหม่
docker-compose build

# 3. Export ใหม่
docker save omr-system:latest -o omr-system-image-v2.tar

# 4. เอาไฟล์ใหม่ไปเครื่องปลายทาง
```

### ในเครื่องปลายทาง
```bash
# 1. หยุด container
docker-compose -f docker-compose.prod.yml down

# 2. ลบ image เก่า
docker rmi omr-system:latest

# 3. Import image ใหม่
docker load -i omr-system-image-v2.tar

# 4. รันใหม่
docker-compose -f docker-compose.prod.yml up -d
```

---

## 🛠️ คำสั่งที่มีประโยชน์

### ดู Logs
```bash
docker-compose -f docker-compose.prod.yml logs -f
```

### หยุด Container
```bash
docker-compose -f docker-compose.prod.yml down
```

### Restart Container
```bash
docker-compose -f docker-compose.prod.yml restart
```

### ดูสถานะ
```bash
docker ps
```

### ดูการใช้ Resources
```bash
docker stats omr-system
```

---

## 📊 เปรียบเทียบ

|                      | วิธีเดิม (เอาโค้ด)            | วิธีใหม่ (Export Image) |
|----------------------|-------------------------------|-------------------------|
| **ไฟล์ที่ต้อง copy** | ~50+ ไฟล์                     | 4-5 ไฟล์                |
| **ขนาดรวม**          | ~10-20 MB                     | ~500-800 MB             |
| **ต้อง build**       | ✅ ใช่ (~5-10 นาที)            | ❌ ไม่ต้อง               |
| **ต้อง internet**    | ✅ ใช่ (download dependencies) | ❌ ไม่ต้อง               |
| **เวลาติดตั้ง**      | ~10-15 นาที                   | ~2-3 นาที               |
| **แก้ไขโค้ดได้**     | ✅ ได้                         | ❌ ไม่ได้                |
| **เหมาะสำหรับ**      | Development                   | Production              |

---

## ✅ Checklist

### ในเครื่องต้นทาง
- [ ] Build Docker image สำเร็จ
- [ ] Export image เป็นไฟล์ .tar
- [ ] Copy ไฟล์ docker-compose.prod.yml
- [ ] Copy ไฟล์ .env.template
- [ ] Copy script (start.ps1 / start.sh)
- [ ] ทดสอบ package ในเครื่องอื่น (ถ้าทำได้)

### ในเครื่องปลายทาง
- [ ] ติดตั้ง Docker Desktop
- [ ] Copy package ทั้งหมด
- [ ] รัน start script
- [ ] แก้ไขไฟล์ .env
- [ ] รัน script อีกครั้ง
- [ ] ทดสอบเข้าใช้งาน http://localhost:5000
- [ ] ทดสอบจากเครื่องอื่นในเครือข่าย

---

## 🎯 สรุป

**ขั้นตอนสั้นๆ:**

1. **Export** (ในเครื่องที่มีโค้ด):
   ```bash
   docker-compose build
   docker save omr-system:latest -o omr-system-image.tar
   ```

2. **Package** (รวมไฟล์):
   - omr-system-image.tar
   - docker-compose.prod.yml
   - .env.template
   - start.ps1 / start.sh

3. **Deploy** (ในเครื่องใหม่):
   ```bash
   ./start.sh  # หรือ start.ps1
   # แก้ไข .env
   ./start.sh  # รันอีกครั้ง
   ```

4. **Done!** เข้าใช้งานที่ http://localhost:5000

---

## 💡 Tips

- ใช้ USB 3.0 หรือ SSD external สำหรับ copy ไฟล์ image (เร็วกว่า)
- บีบอัดด้วย gzip ถ้าต้องการลดขนาด (~30-40%)
- Export image ครั้งเดียว ใช้ได้หลายเครื่อง
- เก็บ image file ไว้สำหรับติดตั้งในอนาคต
