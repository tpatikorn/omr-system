# OMR System Quick Start Script for Windows
# สคริปต์สำหรับติดตั้งและรัน OMR System อย่างรวดเร็ว

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   OMR System - Quick Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ตรวจสอบว่ามี Docker หรือไม่
Write-Host "[1/5] Checking Docker installation..." -ForegroundColor Yellow
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: Docker not found!" -ForegroundColor Red
    Write-Host "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "✅ Docker found" -ForegroundColor Green
Write-Host ""

# ตรวจสอบว่า Docker กำลังรันอยู่หรือไม่
Write-Host "[2/5] Checking Docker status..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: Docker is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# ตรวจสอบว่ามีไฟล์ image หรือไม่
Write-Host "[3/5] Checking Docker image file..." -ForegroundColor Yellow
if (!(Test-Path "omr-system-image.tar")) {
    Write-Host "❌ Error: omr-system-image.tar not found!" -ForegroundColor Red
    Write-Host "Please make sure the image file is in the same folder as this script." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "✅ Image file found" -ForegroundColor Green
Write-Host ""

# ตรวจสอบว่ามี image ใน Docker แล้วหรือยัง
$imageExists = docker images omr-system:latest -q
if (!$imageExists) {
    Write-Host "[4/5] Importing Docker image (this may take a few minutes)..." -ForegroundColor Yellow
    docker load -i omr-system-image.tar
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Image imported successfully" -ForegroundColor Green
    } else {
        Write-Host "❌ Error: Failed to import image" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Host "[4/5] Docker image already exists, skipping import..." -ForegroundColor Yellow
    Write-Host "✅ Image ready" -ForegroundColor Green
}
Write-Host ""

# ตรวจสอบไฟล์ .env
Write-Host "[5/5] Checking configuration..." -ForegroundColor Yellow
if (!(Test-Path ".env")) {
    Write-Host "⚠️  Warning: .env file not found!" -ForegroundColor Yellow
    if (Test-Path ".env.template") {
        Write-Host "Creating .env from template..." -ForegroundColor Yellow
        Copy-Item .env.template .env
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Red
        Write-Host "  IMPORTANT: Configuration Required!" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Red
        Write-Host ""
        Write-Host "Please edit the .env file and set your IP address:" -ForegroundColor Yellow
        Write-Host "1. Open .env file with Notepad" -ForegroundColor White
        Write-Host "2. Find YOUR_IP_ADDRESS and replace it with your actual IP" -ForegroundColor White
        Write-Host "3. Save the file" -ForegroundColor White
        Write-Host "4. Run this script again" -ForegroundColor White
        Write-Host ""
        Write-Host "To find your IP address, run: ipconfig" -ForegroundColor Cyan
        Write-Host ""
        
        # เปิดไฟล์ .env ด้วย notepad
        $openFile = Read-Host "Do you want to open .env file now? (Y/N)"
        if ($openFile -eq "Y" -or $openFile -eq "y") {
            notepad .env
        }
        
        Read-Host "Press Enter to exit"
        exit 0
    } else {
        Write-Host "❌ Error: .env.template not found!" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ตรวจสอบว่า .env ถูกแก้ไขแล้วหรือยัง
$envContent = Get-Content .env -Raw
if ($envContent -match "YOUR_IP_ADDRESS") {
    Write-Host "⚠️  Warning: .env file has not been configured!" -ForegroundColor Yellow
    Write-Host "Please edit .env and replace YOUR_IP_ADDRESS with your actual IP" -ForegroundColor Yellow
    Write-Host ""
    
    $openFile = Read-Host "Do you want to open .env file now? (Y/N)"
    if ($openFile -eq "Y" -or $openFile -eq "y") {
        notepad .env
        Write-Host ""
        Write-Host "After editing, run this script again." -ForegroundColor Yellow
    }
    
    Read-Host "Press Enter to exit"
    exit 0
}

Write-Host "✅ Configuration file ready" -ForegroundColor Green
Write-Host ""

# หยุด container เก่า (ถ้ามี)
$existingContainer = docker ps -a -q -f name=omr-system
if ($existingContainer) {
    Write-Host "Stopping existing container..." -ForegroundColor Yellow
    docker-compose -f docker-compose.prod.yml down 2>$null
}

# รัน container
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Starting OMR System..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

docker-compose -f docker-compose.prod.yml up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "   ✅ OMR System Started Successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    
    # แสดงสถานะ container
    Write-Host "Container Status:" -ForegroundColor Cyan
    docker ps --filter name=omr-system --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    Write-Host ""
    
    # แสดง URL สำหรับเข้าใช้งาน
    Write-Host "Access URLs:" -ForegroundColor Cyan
    Write-Host "  Local:   http://localhost:5000" -ForegroundColor White
    
    $baseUrl = (Get-Content .env | Select-String "OMR_BASE_URL" | Out-String).Trim() -replace 'OMR_BASE_URL=',''
    if ($baseUrl) {
        Write-Host "  Network: $baseUrl" -ForegroundColor White
    }
    Write-Host ""
    
    Write-Host "Useful Commands:" -ForegroundColor Cyan
    Write-Host "  View logs:    docker-compose -f docker-compose.prod.yml logs -f" -ForegroundColor White
    Write-Host "  Stop system:  docker-compose -f docker-compose.prod.yml down" -ForegroundColor White
    Write-Host "  Restart:      docker-compose -f docker-compose.prod.yml restart" -ForegroundColor White
    Write-Host ""
    
    # ถามว่าต้องการดู logs หรือไม่
    $viewLogs = Read-Host "Do you want to view logs now? (Y/N)"
    if ($viewLogs -eq "Y" -or $viewLogs -eq "y") {
        Write-Host ""
        Write-Host "Press Ctrl+C to exit logs view" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        docker-compose -f docker-compose.prod.yml logs -f
    }
    
} else {
    Write-Host ""
    Write-Host "❌ Error: Failed to start container" -ForegroundColor Red
    Write-Host "Please check the error messages above." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
