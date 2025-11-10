#!/bin/bash
# OMR System Quick Start Script for Mac/Linux

echo "========================================"
echo "   OMR System - Quick Deployment"
echo "========================================"
echo ""

# ตรวจสอบว่ามี Docker หรือไม่
echo "[1/5] Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker not found!"
    echo "Please install Docker from: https://www.docker.com/products/docker-desktop/"
    exit 1
fi
echo "✅ Docker found"
echo ""

# ตรวจสอบว่า Docker กำลังรันอยู่หรือไม่
echo "[2/5] Checking Docker status..."
if ! docker ps &> /dev/null; then
    echo "❌ Error: Docker is not running!"
    echo "Please start Docker and try again."
    exit 1
fi
echo "✅ Docker is running"
echo ""

# ตรวจสอบว่ามีไฟล์ image หรือไม่
echo "[3/5] Checking Docker image file..."
if [ ! -f "omr-system-image.tar" ]; then
    echo "❌ Error: omr-system-image.tar not found!"
    echo "Please make sure the image file is in the same folder as this script."
    exit 1
fi
echo "✅ Image file found"
echo ""

# ตรวจสอบว่ามี image ใน Docker แล้วหรือยัง
echo "[4/5] Checking Docker image..."
if ! docker images omr-system:latest -q | grep -q .; then
    echo "Importing Docker image (this may take a few minutes)..."
    docker load -i omr-system-image.tar
    if [ $? -eq 0 ]; then
        echo "✅ Image imported successfully"
    else
        echo "❌ Error: Failed to import image"
        exit 1
    fi
else
    echo "Docker image already exists, skipping import..."
    echo "✅ Image ready"
fi
echo ""

# ตรวจสอบไฟล์ .env
echo "[5/5] Checking configuration..."
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found!"
    if [ -f ".env.template" ]; then
        echo "Creating .env from template..."
        cp .env.template .env
        echo ""
        echo "========================================"
        echo "  IMPORTANT: Configuration Required!"
        echo "========================================"
        echo ""
        echo "Please edit the .env file and set your IP address:"
        echo "1. Open .env file with a text editor"
        echo "2. Find YOUR_IP_ADDRESS and replace it with your actual IP"
        echo "3. Save the file"
        echo "4. Run this script again"
        echo ""
        echo "To find your IP address, run: ifconfig or ip addr"
        exit 0
    else
        echo "❌ Error: .env.template not found!"
        exit 1
    fi
fi

# ตรวจสอบว่า .env ถูกแก้ไขแล้วหรือยัง
if grep -q "YOUR_IP_ADDRESS" .env; then
    echo "⚠️  Warning: .env file has not been configured!"
    echo "Please edit .env and replace YOUR_IP_ADDRESS with your actual IP"
    exit 0
fi

echo "✅ Configuration file ready"
echo ""

# หยุด container เก่า (ถ้ามี)
if docker ps -a -q -f name=omr-system | grep -q .; then
    echo "Stopping existing container..."
    docker-compose -f docker-compose.prod.yml down 2>/dev/null
fi

# รัน container
echo "========================================"
echo "   Starting OMR System..."
echo "========================================"
echo ""

docker-compose -f docker-compose.prod.yml up -d

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "   ✅ OMR System Started Successfully!"
    echo "========================================"
    echo ""
    
    # แสดงสถานะ container
    echo "Container Status:"
    docker ps --filter name=omr-system --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo ""
    
    # แสดง URL สำหรับเข้าใช้งาน
    echo "Access URLs:"
    echo "  Local:   http://localhost:5000"
    
    BASE_URL=$(grep "OMR_BASE_URL" .env | cut -d '=' -f2)
    if [ ! -z "$BASE_URL" ]; then
        echo "  Network: $BASE_URL"
    fi
    echo ""
    
    echo "Useful Commands:"
    echo "  View logs:    docker-compose -f docker-compose.prod.yml logs -f"
    echo "  Stop system:  docker-compose -f docker-compose.prod.yml down"
    echo "  Restart:      docker-compose -f docker-compose.prod.yml restart"
    echo ""
else
    echo ""
    echo "❌ Error: Failed to start container"
    echo "Please check the error messages above."
    exit 1
fi
