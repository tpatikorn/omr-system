document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('file-input');
    const uploadArea = document.getElementById('upload-area');
    const uploadBtn = document.getElementById('upload-btn');
    const selectedFiles = document.getElementById('selected-files');
    const fileList = document.getElementById('file-list');
    const progressOverlay = document.getElementById('progress-overlay');
    const progressText = document.getElementById('progress-text');
    const progressFill = document.getElementById('progress-fill');
    
    let selectedFilesList = [];

    // Handle file selection
    function handleFiles(files) {
        selectedFilesList = Array.from(files);
        updateFileList();
        uploadBtn.disabled = selectedFilesList.length === 0;
    }

    // Update file list display
    function updateFileList() {
        if (selectedFilesList.length === 0) {
            selectedFiles.style.display = 'none';
            return;
        }

        selectedFiles.style.display = 'block';
        fileList.innerHTML = '';

        selectedFilesList.forEach((file, index) => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            
            const fileName = document.createElement('span');
            fileName.className = 'file-name';
            fileName.textContent = file.name;
            
            const fileSize = document.createElement('span');
            fileSize.className = 'file-size';
            fileSize.textContent = formatFileSize(file.size);
            
            fileItem.appendChild(fileName);
            fileItem.appendChild(fileSize);
            fileList.appendChild(fileItem);
        });
    }

    // Format file size
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Handle upload
    async function uploadFiles() {
        if (selectedFilesList.length === 0) return;

        progressOverlay.style.display = 'flex';
        progressText.textContent = `กำลังอัปโหลด ${selectedFilesList.length} ไฟล์...`;
        progressFill.style.width = '0%';

        const formData = new FormData();
        selectedFilesList.forEach(file => {
            formData.append('files', file);
        });

        try {
            // Simulate progress
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress += Math.random() * 15;
                if (progress > 90) progress = 90;
                progressFill.style.width = progress + '%';
            }, 200);

            const response = await fetch('/upload_image', {
                method: 'POST',
                body: formData
            });

            clearInterval(progressInterval);
            progressFill.style.width = '100%';

            if (!response.ok) {
                throw new Error('Upload failed');
            }

            progressText.textContent = '✅ อัปโหลดสำเร็จ!';
            
            // Add haptic feedback if available
            if (navigator.vibrate) {
                navigator.vibrate([100, 50, 100]);
            }

            setTimeout(() => {
                progressOverlay.style.display = 'none';
                // Reset form
                selectedFilesList = [];
                fileInput.value = '';
                updateFileList();
                uploadBtn.disabled = true;
            }, 2000);

            // โหลดภาพใหม่ทันทีหลังอัปโหลดสำเร็จ
            try {
                const imgResp = await fetch('/get_images');
                const imgData = await imgResp.json();
                if (imgData.files && Array.isArray(imgData.files)) {
                    // สมมุติว่ามีฟังก์ชัน showUploadedImages หรือ implement ด้านล่างนี้
                    if (typeof showUploadedImages === 'function') {
                        showUploadedImages(imgData.files);
                    } else {
                        // fallback: reload หน้า
                        // location.reload(); // หรือแจ้งเตือนให้ refresh
                    }
                }
            } catch (e) { /* ignore */ }

        } catch (error) {
            console.error('Error uploading files:', error);
            progressText.textContent = '❌ อัปโหลดไม่สำเร็จ กรุณาลองใหม่';
            progressFill.style.width = '0%';
            
            if (navigator.vibrate) {
                navigator.vibrate([200, 100, 200]);
            }

            setTimeout(() => {
                progressOverlay.style.display = 'none';
            }, 3000);
        }
    }

    // Event listeners
    uploadArea.addEventListener('click', () => fileInput.click());
    
    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    uploadBtn.addEventListener('click', uploadFiles);

    // Drag and drop functionality
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        const files = Array.from(e.dataTransfer.files).filter(file => 
            file.type.startsWith('image/')
        );
        
        if (files.length > 0) {
            handleFiles(files);
        }
    });
});