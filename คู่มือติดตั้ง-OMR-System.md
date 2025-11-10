# คู่มือติดตั้ง OMR System (ระบบตรวจข้อสอบ)

## 📦 ไฟล์ที่ต้องมี (ทั้งหมด 5 ไฟล์)

```
✅ omr-system-image.tar          (ไฟล์ใหญ่ ~500-800 MB)
✅ docker-compose.prod.yml       
✅ .env.template                 
✅ start.ps1                     (สำหรับ Windows)
✅ start.sh                      (สำหรับ Mac/Linux)
```

---

## 🚀 ขั้นตอนการติดตั้ง

### ขั้นตอนที่ 1: ติดตั้ง Docker Desktop

#### สำหรับ Windows
1. ดาวน์โหลด Docker Desktop จาก: https://www.docker.com/products/docker-desktop/
2. ติดตั้งและรีสตาร์ทเครื่อง
3. เปิด Docker Desktop และรอให้เริ่มทำงาน

#### สำหรับ Mac
1. ดาวน์โหลด Docker Desktop จาก: https://www.docker.com/products/docker-desktop/
2. ลาก Docker.app ไปที่ Applications
3. เปิด Docker Desktop

#### สำหรับ Linux
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl start docker
sudo systemctl enable docker
```

### ขั้นตอนที่ 2: เตรียมไฟล์

1. Copy ไฟล์ทั้ง 5 ไฟล์มาไว้ในโฟลเดอร์เดียวกัน
2. ตรวจสอบว่าไฟล์ครบทั้ง 5 ไฟล์

---

## 🖥️ วิธีติดตั้งและรัน

### สำหรับ Windows

#### วิธีที่ 1: ใช้ Script (แนะนำ)
1. **คลิกขวา** ที่ไฟล์ `start.ps1`
2. เลือก **"Run with PowerShell"**
3. ทำตามคำแนะนำบนหน้าจอ

#### วิธีที่ 2: ใช้ Command Line
```powershell
# เปิด PowerShell ในโฟลเดอร์ที่มีไฟล์
.\start.ps1
```

### สำหรับ Mac/Linux

```bash
# 1. ทำให้ script รันได้
chmod +x start.sh

# 2. รัน script
./start.sh
```

---

## ⚙️ การตั้งค่า IP Address

### ขั้นตอนที่ 1: หา IP Address ของเครื่อง

#### Windows
```cmd
# เปิด Command Prompt (CMD) แล้วพิมพ์
ipconfig

# มองหา "IPv4 Address" ในส่วน Wi-Fi หรือ Ethernet
# ตัวอย่าง: 192.168.1.100
```

#### Mac
```bash
# เปิด Terminal แล้วพิมพ์
ifconfig | grep "inet "

# หรือดูที่ System Preferences → Network
```

#### Linux
```bash
# เปิด Terminal แล้วพิมพ์
ip addr show

# หรือ
hostname -I
```

### ขั้นตอนที่ 2: แก้ไขไฟล์ .env

Script จะสร้างไฟล์ `.env` ให้อัตโนมัติ แล้วให้คุณแก้ไข:

#### Windows
```powershell
# Script จะเปิด Notepad ให้อัตโนมัติ
# หรือเปิดเองด้วย
notepad .env
```

#### Mac
```bash
open -e .env
```

#### Linux
```bash
nano .env
```

### ขั้นตอนที่ 3: แก้ไข IP

เปลี่ยนบรรทัดนี้:
```env
OMR_BASE_URL=http://YOUR_IP_ADDRESS:5000
```

เป็น (ตัวอย่าง):
```env
OMR_BASE_URL=http://192.168.1.100:5000
```

**บันทึกไฟล์** แล้วรัน script อีกครั้ง

---

## ✅ การเข้าใช้งาน

หลังจากติดตั้งสำเร็จ เข้าใช้งานได้ที่:

### จากเครื่องเดียวกัน
```
http://localhost:5000
```

### จากเครื่องอื่นในเครือข่าย
```
http://192.168.1.100:5000
(เปลี่ยนเป็น IP ของคุณ)
```

---

## 📂 โฟลเดอร์ที่ถูกสร้างอัตโนมัติ

หลังจากรันครั้งแรก จะมีโฟลเดอร์เหล่านี้ถูกสร้างขึ้น:

```
โฟลเดอร์ของคุณ/
├── omr-system-image.tar
├── docker-compose.prod.yml
├── .env.template
├── .env                         (สร้างใหม่)
├── start.ps1
├── start.sh
├── uploads/                     (สร้างใหม่ - เก็บไฟล์ที่อัปโหลด)
├── debug_output/                (สร้างใหม่ - เก็บผลลัพธ์)
└── config/                      (สร้างใหม่ - เก็บ config)
```

---

## 🛠️ คำสั่งที่มีประโยชน์

### ดู Logs (ดูการทำงานของระบบ)
```bash
docker-compose -f docker-compose.prod.yml logs -f
```
กด `Ctrl+C` เพื่อออก

### หยุดระบบ
```bash
docker-compose -f docker-compose.prod.yml down
```

### เริ่มระบบใหม่
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Restart ระบบ
```bash
docker-compose -f docker-compose.prod.yml restart
```

### ดูสถานะ Container
```bash
docker ps
```

### ดูการใช้ Resources (CPU, Memory)
```bash
docker stats omr-system
```

### เข้าไปใน Container
```bash
docker exec -it omr-system bash
```

### ดูขนาดของ Volumes
```bash
# Windows (PowerShell)
Get-ChildItem uploads, debug_output, config -Recurse | Measure-Object -Property Length -Sum

# Mac/Linux
du -sh uploads/ debug_output/ config/
```

---

## 🔧 การแก้ปัญหา

### ปัญหา: Port 5000 ถูกใช้งานอยู่

#### ตรวจสอบว่าโปรแกรมไหนใช้ port 5000
```bash
# Windows
netstat -ano | findstr :5000

# Mac/Linux
lsof -i :5000
```

#### แก้ไข: เปลี่ยน port
แก้ไขไฟล์ `docker-compose.prod.yml`:
```yaml
ports:
  - "5001:5000"  # เปลี่ยนจาก 5000:5000
```

แล้วแก้ไขไฟล์ `.env`:
```env
OMR_BASE_URL=http://192.168.1.100:5001
```

### ปัญหา: ไม่สามารถเข้าถึงจากเครื่องอื่น

#### 1. ตรวจสอบ Firewall

**Windows:**
1. เปิด Windows Security
2. ไปที่ Firewall & network protection
3. คลิก "Allow an app through firewall"
4. เพิ่ม Docker Desktop หรือเปิด port 5000

**Mac:**
1. System Preferences → Security & Privacy → Firewall
2. คลิก Firewall Options
3. เพิ่ม Docker

**Linux:**
```bash
sudo ufw allow 5000
sudo ufw reload
```

#### 2. ตรวจสอบว่า Container รันอยู่
```bash
docker ps
```

#### 3. ตรวจสอบ IP ใน .env ถูกต้อง
```bash
# Windows
type .env

# Mac/Linux
cat .env
```

### ปัญหา: Docker ไม่ทำงาน

#### Windows/Mac
- เปิด Docker Desktop
- รอให้สถานะเป็น "Running"

#### Linux
```bash
sudo systemctl start docker
sudo systemctl status docker
```

### ปัญหา: Container หยุดทำงานเอง

#### ดู logs เพื่อหาสาเหตุ
```bash
docker logs omr-system --tail 100
```

#### ดูสถานะ container ทั้งหมด
```bash
docker ps -a
```

### ปัญหา: Out of Memory

แก้ไขไฟล์ `docker-compose.prod.yml` เพิ่ม memory limit:
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

---

## 🔄 การอัพเดทระบบ

เมื่อมี version ใหม่:

### 1. หยุดระบบเก่า
```bash
docker-compose -f docker-compose.prod.yml down
```

### 2. Backup ข้อมูล (แนะนำ)
```bash
# Windows (PowerShell)
Compress-Archive -Path uploads, config -DestinationPath backup-$(Get-Date -Format 'yyyyMMdd').zip

# Mac/Linux
tar -czf backup-$(date +%Y%m%d).tar.gz uploads/ config/
```

### 3. ลบ image เก่า
```bash
docker rmi omr-system:latest
```

### 4. Import image ใหม่
```bash
docker load -i omr-system-image-new.tar
```

### 5. รันระบบใหม่
```bash
docker-compose -f docker-compose.prod.yml up -d
```

---

## 🗑️ การถอนการติดตั้ง

### 1. หยุดและลบ Container
```bash
docker-compose -f docker-compose.prod.yml down
```

### 2. ลบ Image
```bash
docker rmi omr-system:latest
```

### 3. ลบ Volumes (ระวัง: จะลบข้อมูลทั้งหมด)
```bash
# Windows (PowerShell)
Remove-Item -Recurse -Force uploads, debug_output, config

# Mac/Linux
rm -rf uploads/ debug_output/ config/
```

### 4. ลบไฟล์ทั้งหมด
ลบโฟลเดอร์ที่มีไฟล์ทั้งหมด

---

## 💾 การ Backup และ Restore

### Backup ข้อมูล

#### Windows (PowerShell)
```powershell
# Backup ทั้งหมด
Compress-Archive -Path uploads, debug_output, config -DestinationPath "omr-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss').zip"
```

#### Mac/Linux
```bash
# Backup ทั้งหมด
tar -czf omr-backup-$(date +%Y%m%d-%H%M%S).tar.gz uploads/ debug_output/ config/
```

### Restore ข้อมูล

#### Windows (PowerShell)
```powershell
# Restore
Expand-Archive -Path omr-backup-YYYYMMDD-HHMMSS.zip -DestinationPath .
```

#### Mac/Linux
```bash
# Restore
tar -xzf omr-backup-YYYYMMDD-HHMMSS.tar.gz
```

---

## 📊 ตรวจสอบสถานะระบบ

### ดูว่าระบบทำงานหรือไม่
```bash
docker ps --filter name=omr-system
```

### ดูการใช้ Resources
```bash
docker stats omr-system --no-stream
```

### ดูขนาดของ Image
```bash
docker images omr-system:latest
```

### ดูขนาดของข้อมูล
```bash
# Windows (PowerShell)
Get-ChildItem uploads, debug_output, config -Recurse | 
  Measure-Object -Property Length -Sum | 
  Select-Object @{Name="Size(MB)";Expression={[math]::Round($_.Sum/1MB,2)}}

# Mac/Linux
du -sh uploads/ debug_output/ config/
```

---

## 🔐 ความปลอดภัย

### แนะนำสำหรับการใช้งานจริง

1. **เปลี่ยน Secret Key** (ถ้ามีการใช้งาน session)
2. **ตั้งค่า Firewall** ให้เปิดเฉพาะ IP ที่ต้องการ
3. **Backup ข้อมูลสม่ำเสมอ**
4. **อัพเดท Docker** เป็นเวอร์ชันล่าสุด
5. **ตรวจสอบ Logs** เป็นประจำ

---

## 📞 ติดต่อและรายงานปัญหา

หากพบปัญหาในการใช้งาน:

1. ตรวจสอบ logs: `docker-compose -f docker-compose.prod.yml logs -f`
2. ตรวจสอบสถานะ: `docker ps -a`
3. ตรวจสอบ network: `docker network ls`
4. ดูคู่มือแก้ปัญหาด้านบน

---

## ✅ Checklist การติดตั้ง

- [ ] ติดตั้ง Docker Desktop แล้ว
- [ ] Docker กำลังทำงานอยู่
- [ ] มีไฟล์ครบทั้ง 5 ไฟล์
- [ ] รัน start script แล้ว
- [ ] แก้ไขไฟล์ .env แล้ว (ใส่ IP)
- [ ] รัน script อีกครั้งแล้ว
- [ ] เข้าใช้งาน http://localhost:5000 ได้
- [ ] ทดสอบจากเครื่องอื่นในเครือข่ายได้

---

## 🎯 สรุปคำสั่งสำคัญ

```bash
# รันระบบ
docker-compose -f docker-compose.prod.yml up -d

# หยุดระบบ
docker-compose -f docker-compose.prod.yml down

# Restart
docker-compose -f docker-compose.prod.yml restart

# ดู logs
docker-compose -f docker-compose.prod.yml logs -f

# ดูสถานะ
docker ps

# ดูการใช้ resources
docker stats omr-system
```

---

**เวอร์ชัน:** 1.0  
**อัพเดทล่าสุด:** 2024  
**ระบบ:** OMR System (Optical Mark Recognition)
