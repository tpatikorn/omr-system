document.addEventListener('DOMContentLoaded', function () {
    // --- Application State ---
    let currentMode = 'single'; // 'single' or 'multi'
    let uploadedImageCount = 0;
    let state = {
        single: {
            isAnswerKeySelected: false,
            resultsDataCache: null,
            answerKeyFileContent: null // ใช้เก็บเนื้อหาไฟล์ที่อัปโหลดชั่วคราว
        },
        multi: {
            isAnswerKeySelected: false,
            resultsDataCache: null,
            answerKeyFileContent: null // ใช้เก็บเนื้อหาไฟล์ที่อัปโหลดชั่วคราว
        }
    };
    let isStudentListSelected = false; // Shared state

    // --- DOM Elements ---
    const pcUploadInput = document.getElementById('pc-upload-input');
    const imagePreviewGrid = document.getElementById('image-preview-grid');
    const imageCountSpan = document.getElementById('image-count');
    const uploadPlaceholder = document.getElementById('upload-placeholder');
    const deleteSelectedBtn = document.getElementById('delete-selected-btn');
    const cleanSelectedBtn = document.getElementById('clean-selected-btn');
    const optimizeImagesBtn = document.getElementById('optimize-images-btn');
    const deleteAllBtn = document.getElementById('delete-all-btn');
    const modal = document.getElementById('image-modal');
    const modalImg = document.getElementById('modal-img');
    const modalClose = document.querySelector('.modal-close');
    // outputFilenameInput removed - using mode-specific inputs instead
    const newSessionBtn = document.getElementById('new-session-btn');
    const studentListInput = document.getElementById('student-list-input');
    const studentListLabel = document.getElementById('student-list-label');
    const viewStudentListBtn = document.getElementById('view-student-list-btn');
    const dataViewModal = document.getElementById('data-view-modal');
    const dataViewClose = document.getElementById('data-view-close');
    const dataViewTitle = document.getElementById('data-view-modal-title');
    const dataViewContent = document.getElementById('data-view-content');
    const copyMobileLinkBtn = document.getElementById('copy-mobile-link-btn');
    const showQrBtn = document.getElementById('show-qr-btn');
    const qrModal = document.getElementById('qr-modal');
    const qrModalClose = document.getElementById('qr-modal-close');
    const closeQrBtn = document.getElementById('close-qr-btn');
    const refreshQrBtn = document.getElementById('refresh-qr-btn');
    const qrCanvas = document.getElementById('qr-canvas');
    const qrLoading = document.getElementById('qr-loading');
    const sessionIdDisplay = document.getElementById('session-id-display');
    const deviceTypeDisplay = document.getElementById('device-type-display');
    const sessionIdDisplayHeader = document.getElementById('session-id-display-header');
    const deviceTypeDisplayHeader = document.getElementById('device-type-display-header');
    const copyMobileLinkBtnHeader = document.getElementById('copy-mobile-link-btn-header');
    const showQrBtnHeader = document.getElementById('show-qr-btn-header');

    // Elements for Manual Answer Key
    const manualAnswerKeyModal = document.getElementById('manual-answer-key-modal');
    const manualAnswerKeyClose = document.getElementById('manual-answer-key-close');
    const saveManualAnswerKeyBtn = document.getElementById('save-manual-answer-key-btn');
    const manualAnswerKeyContent = document.getElementById('manual-answer-key-content');
    const clearManualAnswerKeyBtn = document.getElementById('clear-manual-answer-key-btn');

    // Elements for Score Edit Modal
    const scoreEditModal = document.getElementById('score-edit-modal');
    const scoreEditClose = document.getElementById('score-edit-close');
    const scoreEditHighlightedImage = document.getElementById('score-edit-highlighted-image');
    const scoreEditStudentName = document.getElementById('score-edit-student-name');
    const scoreEditStudentId = document.getElementById('score-edit-student-id');
    const scoreEditAnswersForm = document.getElementById('score-edit-answers-form');
    const scoreEditAnswerKey = document.getElementById('score-edit-answer-key');
    const currentScoreDisplay = document.getElementById('current-score-display');
    const saveScoreEditBtn = document.getElementById('save-score-edit-btn');
    const cancelScoreEditBtn = document.getElementById('cancel-score-edit-btn');

    // --- TAB HANDLING ---
    document.querySelectorAll('.tab-link').forEach(button => {
        button.addEventListener('click', () => {
            const tabId = button.dataset.tab;
            currentMode = tabId.includes('single') ? 'single' : 'multi';

            document.querySelectorAll('.tab-link, .tab-pane, .results-panel').forEach(el => el.classList.remove('active'));

            button.classList.add('active');
            document.getElementById(tabId).classList.add('active');
            document.getElementById(`results-panel-${currentMode}`).classList.add('active');

            updateButtonStates();
        });
    });

    // --- Helper Function for Mode Elements ---
    function getModeElements(mode) {
        return {
            processBtn: document.getElementById(`process-btn-${mode}`),
            downloadCsvBtn: document.getElementById(`download-csv-btn-${mode}`),
            answerKeyInput: document.getElementById(`answer-key-input-${mode}`),
            answerKeyLabel: document.getElementById(`answer-key-label-${mode}`),
            createEditBtn: document.getElementById(`create-edit-answer-key-btn-${mode}`),
            viewAnswerKeyBtn: document.getElementById(`view-answer-key-btn-${mode}`),
            resultsTbody: document.getElementById(`results-tbody-${mode}`),
            resultsTable: document.getElementById(`results-table-${mode}`),
            resultsPlaceholder: document.getElementById(`results-placeholder-${mode}`),
            loadingSpinner: document.getElementById(`loading-spinner-${mode}`),
            clearResultsBtn: document.getElementById(`clear-results-btn-${mode}`),
        };
    }

    // --- Functions ---
    async function updateSessionStatus() {
        try {
            const response = await fetch('/get_session_info');
            const data = await response.json();

            if (data.has_session) {
                if (sessionIdDisplay) {
                    sessionIdDisplay.textContent = data.session_id;
                }
                if (deviceTypeDisplay) {
                    deviceTypeDisplay.textContent = data.device_type === 'browser' ? '🖥️ เบราว์เซอร์' : '📱 มือถือ';
                }

                // อัปเดต header elements ด้วย
                if (sessionIdDisplayHeader) {
                    sessionIdDisplayHeader.textContent = data.session_id || '';
                }

                // เก็บ session_id เต็มไว้ใน window._fullSessionId
                if (data.session_id_full) {
                    window._fullSessionId = data.session_id_full;
                }
            } else {
                if (sessionIdDisplay) {
                    sessionIdDisplay.textContent = 'ไม่มี session';
                }
                if (deviceTypeDisplay) {
                    deviceTypeDisplay.textContent = '-';
                }
                if (sessionIdDisplayHeader) {
                    sessionIdDisplayHeader.textContent = 'ไม่มี session';
                }
                if (deviceTypeDisplayHeader) {
                    deviceTypeDisplayHeader.textContent = '-';
                }
                window._fullSessionId = null;
            }
        } catch (error) {
            console.error('Error updating session status:', error);
            if (sessionIdDisplay) {
                sessionIdDisplay.textContent = 'ข้อผิดพลาด';
            }
            if (deviceTypeDisplay) {
                deviceTypeDisplay.textContent = '-';
            }
            if (sessionIdDisplayHeader) {
                sessionIdDisplayHeader.textContent = 'ข้อผิดพลาด';
            }
            if (deviceTypeDisplayHeader) {
                deviceTypeDisplayHeader.textContent = '-';
            }
        }
    }

    // --- Update Server Info ---
    async function updateServerInfo() {
        try {
            const response = await fetch('/get_server_info');
            const data = await response.json();

            const serverIpDisplayHeader = document.getElementById('server-ip-display-header');
            if (data.success && serverIpDisplayHeader) {
                serverIpDisplayHeader.textContent = data.local_ip;
                serverIpDisplayHeader.title = `Base URL: ${data.base_url}`;
            } else if (serverIpDisplayHeader) {
                serverIpDisplayHeader.textContent = 'ไม่ทราบ';
            }
        } catch (error) {
            console.error('Error updating server info:', error);
            const serverIpDisplayHeader = document.getElementById('server-ip-display-header');
            if (serverIpDisplayHeader) {
                serverIpDisplayHeader.textContent = 'ข้อผิดพลาด';
            }
        }
    }

    // --- Heartbeat: ping server every 30 seconds to mark activity ---
    async function sendHeartbeat() {
        try {
            await fetch('/heartbeat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ts: Date.now() })
            });
        } catch (e) {
            // suppress errors to avoid console noise
        }
    }
    // initial ping soon after load, then every 30s
    setTimeout(sendHeartbeat, 2000);
    setInterval(sendHeartbeat, 30000);

    function updateButtonStates() {
        const hasImages = uploadedImageCount > 0;
        const selectedCount = document.querySelectorAll('.delete-checkbox:checked').length;

        // Update buttons for current mode
        const elements = getModeElements(currentMode);
        if (elements.processBtn) {
            elements.processBtn.disabled = !(hasImages && state[currentMode].isAnswerKeySelected);
        }

        // Update shared buttons
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = selectedCount === 0;
        }
        if (cleanSelectedBtn) {
            cleanSelectedBtn.disabled = selectedCount === 0;
        }
        if (deleteAllBtn) {
            deleteAllBtn.disabled = !hasImages;
        }
        if (optimizeImagesBtn) {
            optimizeImagesBtn.disabled = !hasImages;
        }
        if (newSessionBtn && elements.resultsTbody) {
            newSessionBtn.disabled = !hasImages && elements.resultsTbody.childElementCount === 0;
        }
    }

    function addImageThumbnail(fileInfo) {
        if (document.querySelector(`.thumbnail[data-saved-name="${fileInfo.saved_name}"]`)) {
            return;
        }
        const thumbDiv = document.createElement('div');
        thumbDiv.className = 'thumbnail';
        thumbDiv.dataset.savedName = fileInfo.saved_name;
        const img = document.createElement('img');
        img.src = fileInfo.url;
        img.alt = fileInfo.original_name;
        img.dataset.originalUrl = fileInfo.url;
        img.addEventListener('click', () => openModal(img.dataset.originalUrl || img.src, fileInfo.original_name));
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'delete-checkbox';
        checkbox.addEventListener('change', () => {
            thumbDiv.classList.toggle('selected', checkbox.checked);
            updateButtonStates();
        });
        thumbDiv.appendChild(img);
        thumbDiv.appendChild(checkbox);

        if (imagePreviewGrid) {
            imagePreviewGrid.appendChild(thumbDiv);
        }
        uploadedImageCount++;
        if (imageCountSpan) {
            imageCountSpan.textContent = uploadedImageCount;
        }
        if (uploadPlaceholder) {
            uploadPlaceholder.style.display = 'none';
        }
        updateButtonStates();
    }

    function removeImageThumbnails(filenames) {
        filenames.forEach(name => {
            const thumb = document.querySelector(`.thumbnail[data-saved-name="${name}"]`);
            if (thumb) {
                thumb.remove();
                uploadedImageCount--;
            }
        });
        if (imageCountSpan) {
            imageCountSpan.textContent = uploadedImageCount;
        }
        if (uploadedImageCount === 0 && uploadPlaceholder) {
            uploadPlaceholder.style.display = 'flex';
        }
        updateButtonStates();
    }

    function updateImageThumbnails(cleanedFilesInfo) {
        const { filenames, timestamp } = cleanedFilesInfo;
        filenames.forEach(name => {
            const thumb = document.querySelector(`.thumbnail[data-saved-name="${name}"]`);
            if (thumb) {
                const img = thumb.querySelector('img');
                const baseUrl = img.dataset.originalUrl || img.src.split('?')[0];
                const newUrl = `${baseUrl}?t=${timestamp}`;
                img.src = newUrl;
                img.dataset.originalUrl = newUrl;
            }
        });
    }

    async function handleFileUpload(files) {
        if (files.length === 0) return;

        const uploadBtn = document.querySelector('label[for="pc-upload-input"]');
        const originalText = uploadBtn.textContent;

        // ตรวจสอบว่ามีไฟล์ PDF หรือไม่
        const hasPdf = Array.from(files).some(file => file.name.toLowerCase().endsWith('.pdf'));

        if (hasPdf) {
            uploadBtn.textContent = 'กำลังแปลง PDF...';
        } else {
            uploadBtn.textContent = 'กำลังอัปโหลด...';
        }

        uploadBtn.style.pointerEvents = 'none';

        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }
        try {
            const response = await fetch('/upload_image', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'เกิดข้อผิดพลาดในการอัปโหลด');
            }
            const result = await response.json();
            // แสดงรูปทันทีหลังอัปโหลด (ไม่ต้องรอ event)
            if (result.files && Array.isArray(result.files)) {
                result.files.forEach(addImageThumbnail);
            }
            // แสดงข้อความสำเร็จถ้ามีการแปลง PDF
            if (hasPdf && result.files) {
                const pdfFiles = Array.from(files).filter(file => file.name.toLowerCase().endsWith('.pdf'));
                const totalPages = result.files.length;
                if (pdfFiles.length > 0) {
                    alert(`แปลงไฟล์ PDF เสร็จแล้ว! ได้รูปภาพทั้งหมด ${totalPages} หน้า`);
                }
            }
        } catch (error) {
            console.error('Error uploading files:', error);
            alert(error.message || 'เกิดข้อผิดพลาดในการอัปโหลดไฟล์');
        } finally {
            uploadBtn.textContent = originalText;
            uploadBtn.style.pointerEvents = 'auto';
        }
    }

    async function deleteImagesOnServer(filenames) {
        if (filenames.length === 0) return;
        try {
            await fetch('/delete_images', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filenames })
            });
        } catch (error) {
            console.error('Error deleting files:', error);
            alert('เกิดข้อผิดพลาดในการลบไฟล์');
        }
    }

    function populateResultsTable(results, mode) {
        console.log('populateResultsTable called with:', results?.length, 'results for mode:', mode);

        const elements = getModeElements(mode);
        console.log('Elements found:', {
            resultsTbody: !!elements.resultsTbody,
            resultsTable: !!elements.resultsTable,
            resultsPlaceholder: !!elements.resultsPlaceholder
        });

        // Clear both tables
        elements.resultsTbody.innerHTML = '';
        const unmatchedTbody = document.getElementById(`unmatched-tbody-${mode}`);
        if (unmatchedTbody) unmatchedTbody.innerHTML = '';

        if (!results || results.length === 0) {
            console.log('No results, showing placeholder');
            elements.resultsPlaceholder.style.display = 'flex';
            hideAllTables(mode);
            elements.clearResultsBtn.style.display = 'none';

            // ล้างสถิติ
            const statsElement = document.getElementById(`results-stats-${mode}`);
            if (statsElement) statsElement.style.display = 'none';

            return;
        }

        // แยกผลลัพธ์เป็น 2 กลุ่ม
        const unmatchedResults = [];
        const matchedResults = [];

        results.forEach((item, index) => {
            const studentName = item.student_name || '';
            const studentId = item.student_id || '';

            console.log(`Processing item ${index + 1}:`, {
                name: studentName,
                id: studentId,
                originalItem: item
            });

            // ตรวจสอบว่าเป็นกระดาษที่ไม่สามารถจับคู่ได้หรือไม่
            const isNameNotFound = (
                studentName === 'ไม่พบชื่อ' ||
                studentName === 'ไม่พบชื่อในรายชื่อ' ||
                studentName === 'ข้อผิดพลาด' ||
                !studentName ||
                studentName.trim() === ''
            );

            const isIdInvalid = (
                studentId === 'Error Reading ID' ||
                studentId === 'ERROR' ||
                String(studentId).includes('-') ||
                !studentId ||
                String(studentId).trim() === ''
            );

            // ตรวจสอบว่ามีปัญหาการกาหลายคำตอบหรือไม่ (เฉพาะโหมด single)
            const hasIssues = mode === 'single' && item.has_issues === true;

            console.log(`Item ${index + 1} classification:`, {
                isNameNotFound,
                isIdInvalid,
                hasIssues,
                willBeUnmatched: isNameNotFound || isIdInvalid || hasIssues
            });

            if (isNameNotFound || isIdInvalid || hasIssues) {
                unmatchedResults.push(item);
                console.log(`Added to unmatched: ${studentName} - ${studentId}${hasIssues ? ' (มีปัญหาการกาหลายคำตอบ)' : ''}`);
            } else {
                matchedResults.push(item);
                console.log(`Added to matched: ${studentName} - ${studentId}`);
            }
        });

        // Sort เฉพาะกลุ่มที่จับคู่ได้
        const sortedMatchedResults = [...matchedResults].sort((a, b) => {
            const idA = String(a.student_id || '').toLowerCase();
            const idB = String(b.student_id || '').toLowerCase();
            return idA.localeCompare(idB, 'th', { numeric: true });
        });

        elements.resultsPlaceholder.style.display = 'none';
        elements.clearResultsBtn.style.display = 'inline-block';

        console.log('Results breakdown:', {
            total: results.length,
            unmatched: unmatchedResults.length,
            matched: sortedMatchedResults.length
        });

        // เติมข้อมูลในตารางก่อน
        if (unmatchedResults.length > 0) {
            console.log('Populating unmatched table with', unmatchedResults.length, 'items:', unmatchedResults);
            populateTable(unmatchedTbody, unmatchedResults, mode, false); // ไม่ sort
        } else {
            console.log('No unmatched results to populate');
        }

        if (sortedMatchedResults.length > 0) {
            console.log('Populating matched table with', sortedMatchedResults.length, 'items:', sortedMatchedResults);
            console.log('Target tbody element:', elements.resultsTbody);
            populateTable(elements.resultsTbody, sortedMatchedResults, mode, true); // sort แล้ว
        } else {
            console.log('No matched results to populate');
        }

        // แสดงตารางที่เหมาะสมหลังจากเติมข้อมูลแล้ว
        showRelevantTables(mode, unmatchedResults.length > 0, sortedMatchedResults.length > 0);

        // คำนวณสถิติ
        const totalResults = results.length;
        let validResults = 0;
        results.forEach(item => {
            if (item.score !== undefined && item.score !== null && !isNaN(item.score)) {
                validResults++;
            }
        });

        // เพิ่มสถิติ
        addStatsElement(mode, validResults, unmatchedResults.length, sortedMatchedResults.length);

        updateButtonStates();

        // ใช้ setTimeout หลายขั้นเพื่อให้แน่ใจว่าการแสดงผลเกิดขึ้น
        setTimeout(() => {
            if (sortedMatchedResults.length > 0) {
                const matchedSection = document.getElementById(`matched-section-${mode}`);
                const matchedTable = document.getElementById(`results-table-${mode}`);

                console.log('Force showing matched section and table:', {
                    section: !!matchedSection,
                    table: !!matchedTable,
                    tbody: !!elements.resultsTbody,
                    rowCount: elements.resultsTbody.children.length
                });

                if (matchedSection) {
                    // บังคับแสดงทุกอย่าง
                    matchedSection.style.display = 'block';
                    matchedSection.style.visibility = 'visible';
                    matchedSection.style.opacity = '1';

                    if (matchedTable) {
                        matchedTable.style.display = 'table';
                        matchedTable.style.visibility = 'visible';
                    }

                    if (elements.resultsTbody) {
                        elements.resultsTbody.style.display = 'table-row-group';
                        elements.resultsTbody.style.visibility = 'visible';
                    }

                    // Force reflow
                    matchedSection.offsetHeight;

                    console.log('Forced all elements to show, final check:', {
                        sectionDisplay: matchedSection.style.display,
                        sectionHeight: matchedSection.offsetHeight,
                        tableDisplay: matchedTable?.style.display,
                        tbodyDisplay: elements.resultsTbody.style.display,
                        rowCount: elements.resultsTbody.children.length
                    });
                }
            }
        }, 200);
    }

    function hideAllTables(mode) {
        const unmatchedSection = document.getElementById(`unmatched-section-${mode}`);
        const matchedSection = document.getElementById(`matched-section-${mode}`);

        if (unmatchedSection) unmatchedSection.style.display = 'none';
        if (matchedSection) matchedSection.style.display = 'none';
    }

    function showRelevantTables(mode, hasUnmatched, hasMatched) {
        const unmatchedSection = document.getElementById(`unmatched-section-${mode}`);
        const matchedSection = document.getElementById(`matched-section-${mode}`);

        console.log('showRelevantTables:', {
            mode,
            hasUnmatched,
            hasMatched,
            unmatchedSection: !!unmatchedSection,
            matchedSection: !!matchedSection
        });

        if (unmatchedSection) {
            unmatchedSection.style.display = hasUnmatched ? 'block' : 'none';
            console.log('Unmatched section display:', unmatchedSection.style.display);
        } else {
            console.error('Unmatched section not found:', `unmatched-section-${mode}`);
        }

        if (matchedSection) {
            matchedSection.style.display = hasMatched ? 'block' : 'none';
            console.log('Matched section display:', matchedSection.style.display);

            // Force reflow เพื่อให้แน่ใจว่าการแสดงผลเกิดขึ้นทันที
            if (hasMatched) {
                matchedSection.offsetHeight; // Force reflow
                console.log('Forced reflow for matched section');
            }
        } else {
            console.error('Matched section not found:', `matched-section-${mode}`);
        }
    }

    function addStatsElement(mode, validResults, unmatchedCount, matchedCount) {
        let statsElement = document.getElementById(`results-stats-${mode}`);
        if (!statsElement) {
            statsElement = document.createElement('div');
            statsElement.id = `results-stats-${mode}`;
            statsElement.style.cssText = 'text-align: center; font-weight: bold; background-color: #f8f9fa; padding: 8px; margin-bottom: 15px; border: 1px solid #dee2e6; border-radius: 4px;';

            // หาตำแหน่งที่เหมาะสมในการแทรก
            const tableContainer = document.querySelector(`#results-panel-${mode} .table-container`);
            if (tableContainer) {
                tableContainer.insertBefore(statsElement, tableContainer.firstChild);
                console.log('Stats element created and inserted');
            } else {
                console.error('Table container not found:', `#results-panel-${mode} .table-container`);
            }
        }

        if (validResults > 0) {
            let statsText = `ประมวลผลเสร็จแล้ว ${validResults} คน`;
            if (unmatchedCount > 0) {
                statsText += ` | ไม่จับคู่ได้: ${unmatchedCount} คน`;
            }
            if (matchedCount > 0) {
                statsText += ` | จับคู่ได้: ${matchedCount} คน`;
            }
            statsElement.textContent = statsText;
            statsElement.style.display = 'block';
        } else {
            statsElement.style.display = 'none';
        }
    }

    function populateTable(tbody, results, mode, isSorted) {
        console.log('populateTable called:', {
            tbody: !!tbody,
            tbodyId: tbody?.id,
            tbodyElement: tbody,
            resultsCount: results.length,
            mode,
            isSorted
        });

        if (!tbody) {
            console.error('tbody is null or undefined for mode:', mode, 'isSorted:', isSorted);
            return;
        }

        console.log('tbody element details:', {
            tagName: tbody.tagName,
            id: tbody.id,
            parentElement: tbody.parentElement?.tagName,
            parentId: tbody.parentElement?.id
        });

        // Clear existing rows
        tbody.innerHTML = '';
        console.log('Cleared tbody, starting to populate...');

        results.forEach((item, index) => {
            console.log(`Processing row ${index + 1}/${results.length}:`, {
                name: item.student_name,
                id: item.student_id,
                score: item.score,
                total: item.total
            });
            const row = tbody.insertRow();
            console.log(`Created row ${index + 1}, tbody now has ${tbody.children.length} rows`);
            let scoreClass = '';
            if (item.student_id === 'ERROR' || String(item.score).startsWith('Processing')) {
                scoreClass = 'score-error';
            } else if (item.status === 'partial') {
                scoreClass = 'score-partial';
            }

            // Cell 1: รูปภาพ
            const imageCell = row.insertCell(0);
            imageCell.style.textAlign = 'center';
            const img = document.createElement('img');
            img.src = item.image_url || `/uploads/${item.student_file}`;
            img.className = 'result-image';
            img.alt = item.student_file;
            img.addEventListener('click', () => openModal(img.src, item.student_file));
            imageCell.appendChild(img);

            // Cell 2: ชื่อนักศึกษา
            const nameCell = row.insertCell(1);
            nameCell.textContent = item.student_name || 'ไม่พบชื่อ';
            nameCell.style.textAlign = 'left';

            // เพิ่มสีแดงสำหรับชื่อที่ไม่พบ
            if (!isSorted && (item.student_name === 'ไม่พบชื่อ' || !item.student_name)) {
                nameCell.style.color = '#ef4444';
            }

            // Cell 3: รหัสนักศึกษา
            const idCell = row.insertCell(2);
            let idText = item.student_id;
            
            // เพิ่มคำเตือนถ้ารหัสซ้ำ
            if (item.is_duplicate) {
                idText += ' ⚠️ รหัสซ้ำ';
                idCell.style.color = '#ef4444';
                idCell.style.fontWeight = 'bold';
                idCell.title = 'พบรหัสนักศึกษาซ้ำ กรุณาแก้ไขรหัสให้ถูกต้อง';
            }
            // เพิ่มสีแดงสำหรับรหัสที่อ่านไม่ได้
            else if (!isSorted && (item.student_id === 'Error Reading ID' || item.student_id === 'ERROR' || String(item.student_id).includes('-'))) {
                idCell.style.color = '#ef4444';
            }
            
            idCell.textContent = idText;
            idCell.style.textAlign = 'left';

            // Cell 4: คะแนน
            const scoreCell = row.insertCell(3);
            let scoreText = `${item.score} / ${item.total}`;

            // เพิ่มไอคอนเตือนถ้ามีการกาหลายคำตอบ (เฉพาะโหมด single)
            if (mode === 'single' && item.multiple_answers_count > 0) {
                scoreText += ` ⚠️`;
                scoreCell.title = `มีการกา 2 คำตอบใน 1 ข้อ จำนวน ${item.multiple_answers_count} ข้อ`;
                scoreCell.style.color = '#ef4444';
                scoreCell.style.fontWeight = 'bold';
            }

            scoreCell.textContent = scoreText;
            scoreCell.style.textAlign = 'left';

            if (scoreClass) {
                scoreCell.className = scoreClass;
            }

            // Cell 5: การจัดการ
            const actionCell = row.insertCell(4);
            actionCell.style.textAlign = 'center';
            const editBtn = document.createElement('button');
            editBtn.className = 'edit-btn';
            editBtn.textContent = 'แก้ไข';
            editBtn.title = 'แก้ไขคะแนนนักศึกษา';
            editBtn.addEventListener('click', () => {
                openScoreEditModal(item, mode);
            });
            actionCell.appendChild(editBtn);
        });
    }

    // --- Zoom and Pan Variables ---
    let currentScale = 1;
    let currentTranslateX = 0;
    let currentTranslateY = 0;
    let isDragging = false;
    let lastMouseX = 0;
    let lastMouseY = 0;
    let isTouch = false;
    let lastTouchDistance = 0;

    function openModal(src, filename) {
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden'; // ล็อค scroll ของ body
        const timestamp = Date.now();
        const baseUrl = src.split('?')[0];
        modalImg.src = `${baseUrl}?t=${timestamp}`;

        // Reset zoom and pan
        resetImageTransform();

        // Add zoom and pan event listeners
        setupZoomAndPan();
    }

    function resetImageTransform() {
        currentScale = 1;
        currentTranslateX = 0;
        currentTranslateY = 0;
        updateImageTransform();
    }

    function updateImageTransform() {
        modalImg.style.transform = `scale(${currentScale}) translate(${currentTranslateX}px, ${currentTranslateY}px)`;
    }

    function setupZoomAndPan() {
        // Mouse wheel zoom - เพิ่มให้ทั้ง modal และ modalImg
        modal.addEventListener('wheel', handleWheel, { passive: false });
        modalImg.addEventListener('wheel', handleWheel, { passive: false });

        // Mouse drag
        modalImg.addEventListener('mousedown', handleMouseDown);
        modal.addEventListener('mousedown', handleModalMouseDown);
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);

        // Touch events
        modalImg.addEventListener('touchstart', handleTouchStart, { passive: false });
        modalImg.addEventListener('touchmove', handleTouchMove, { passive: false });
        modalImg.addEventListener('touchend', handleTouchEnd);

        // Keyboard shortcuts
        document.addEventListener('keydown', handleKeyDown);

        // Double click to reset
        modalImg.addEventListener('dblclick', resetImageTransform);

        // ป้องกัน scroll ทะลุไปด้านหลัง
        modal.addEventListener('scroll', (e) => {
            e.preventDefault();
            e.stopPropagation();
        });

        // ป้องกัน body scroll เมื่อ modal เปิด
        document.body.style.overflow = 'hidden';
    }

    function handleWheel(e) {
        // ป้องกันการ scroll ทะลุไปด้านหลัง
        e.preventDefault();
        e.stopPropagation();

        const rect = modalImg.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        const newScale = Math.max(0.1, Math.min(10, currentScale * delta));

        if (newScale !== currentScale) {
            const scaleChange = newScale / currentScale;
            currentTranslateX = mouseX - scaleChange * (mouseX - currentTranslateX);
            currentTranslateY = mouseY - scaleChange * (mouseY - currentTranslateY);
            currentScale = newScale;
            updateImageTransform();
        }
    }

    function handleMouseDown(e) {
        if (e.button === 0) { // Left mouse button
            isDragging = true;
            isTouch = false;
            lastMouseX = e.clientX;
            lastMouseY = e.clientY;
            modalImg.style.cursor = 'grabbing';
            e.preventDefault();
        }
    }

    function handleMouseMove(e) {
        if (isDragging && !isTouch) {
            const deltaX = e.clientX - lastMouseX;
            const deltaY = e.clientY - lastMouseY;

            currentTranslateX += deltaX / currentScale;
            currentTranslateY += deltaY / currentScale;

            lastMouseX = e.clientX;
            lastMouseY = e.clientY;

            updateImageTransform();
        }
    }

    function handleMouseUp(e) {
        if (e.button === 0) {
            isDragging = false;
            modalImg.style.cursor = 'grab';
        }
    }

    function handleModalMouseDown(e) {
        // ถ้าคลิกที่พื้นหลัง modal (ไม่ใช่รูปภาพ) ให้ปิด modal
        if (e.target === modal) {
            modal.style.display = 'none';
            cleanupModalEvents();
        }
    }

    function handleTouchStart(e) {
        e.preventDefault();
        isTouch = true;

        if (e.touches.length === 1) {
            // Single touch - pan
            isDragging = true;
            lastMouseX = e.touches[0].clientX;
            lastMouseY = e.touches[0].clientY;
        } else if (e.touches.length === 2) {
            // Two finger touch - zoom
            isDragging = false;
            const touch1 = e.touches[0];
            const touch2 = e.touches[1];
            lastTouchDistance = Math.sqrt(
                Math.pow(touch2.clientX - touch1.clientX, 2) +
                Math.pow(touch2.clientY - touch1.clientY, 2)
            );
        }
    }

    function handleTouchMove(e) {
        e.preventDefault();

        if (e.touches.length === 1 && isDragging) {
            // Single touch pan
            const deltaX = e.touches[0].clientX - lastMouseX;
            const deltaY = e.touches[0].clientY - lastMouseY;

            currentTranslateX += deltaX / currentScale;
            currentTranslateY += deltaY / currentScale;

            lastMouseX = e.touches[0].clientX;
            lastMouseY = e.touches[0].clientY;

            updateImageTransform();
        } else if (e.touches.length === 2) {
            // Two finger zoom
            const touch1 = e.touches[0];
            const touch2 = e.touches[1];
            const currentDistance = Math.sqrt(
                Math.pow(touch2.clientX - touch1.clientX, 2) +
                Math.pow(touch2.clientY - touch1.clientY, 2)
            );

            if (lastTouchDistance > 0) {
                const scaleChange = currentDistance / lastTouchDistance;
                const newScale = Math.max(0.1, Math.min(10, currentScale * scaleChange));

                if (newScale !== currentScale) {
                    const centerX = (touch1.clientX + touch2.clientX) / 2;
                    const centerY = (touch1.clientY + touch2.clientY) / 2;
                    const rect = modalImg.getBoundingClientRect();
                    const imageX = centerX - rect.left;
                    const imageY = centerY - rect.top;

                    const actualScaleChange = newScale / currentScale;
                    currentTranslateX = imageX - actualScaleChange * (imageX - currentTranslateX);
                    currentTranslateY = imageY - actualScaleChange * (imageY - currentTranslateY);
                    currentScale = newScale;
                    updateImageTransform();
                }
            }

            lastTouchDistance = currentDistance;
        }
    }

    function handleTouchEnd(e) {
        if (e.touches.length === 0) {
            isDragging = false;
            isTouch = false;
            lastTouchDistance = 0;
        } else if (e.touches.length === 1) {
            // Switch back to single touch mode
            lastMouseX = e.touches[0].clientX;
            lastMouseY = e.touches[0].clientY;
            isDragging = true;
        }
    }

    function handleKeyDown(e) {
        if (modal.style.display === 'block') {
            switch (e.key) {
                case '+':
                case '=':
                    e.preventDefault();
                    currentScale = Math.min(10, currentScale * 1.2);
                    updateImageTransform();
                    break;
                case '-':
                    e.preventDefault();
                    currentScale = Math.max(0.1, currentScale / 1.2);
                    updateImageTransform();
                    break;
                case '0':
                    e.preventDefault();
                    resetImageTransform();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    currentTranslateX += 50 / currentScale;
                    updateImageTransform();
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    currentTranslateX -= 50 / currentScale;
                    updateImageTransform();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    currentTranslateY += 50 / currentScale;
                    updateImageTransform();
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    currentTranslateY -= 50 / currentScale;
                    updateImageTransform();
                    break;
                case 'Escape':
                    modal.style.display = 'none';
                    cleanupModalEvents();
                    break;
            }
        }
    }

    function cleanupModalEvents() {
        // ตรวจสอบว่ายังมี modal อื่นเปิดอยู่หรือไม่
        const scoreEditModalOpen = scoreEditModal && scoreEditModal.style.display === 'block';
        const dataViewModalOpen = dataViewModal && dataViewModal.style.display === 'block';
        const manualAnswerKeyModalOpen = manualAnswerKeyModal && manualAnswerKeyModal.style.display === 'block';
        const qrModalOpen = qrModal && qrModal.style.display === 'block';

        // ถ้าไม่มี modal อื่นเปิดอยู่ ให้คืนค่า body scroll
        if (!scoreEditModalOpen && !dataViewModalOpen && !manualAnswerKeyModalOpen && !qrModalOpen) {
            document.body.style.overflow = 'auto';
        }
    }

    function clearUI() {
        imagePreviewGrid.innerHTML = '';
        uploadedImageCount = 0;
        imageCountSpan.textContent = 0;
        uploadPlaceholder.style.display = 'flex';

        // Clear both modes
        ['single', 'multi'].forEach(mode => {
            const elements = getModeElements(mode);
            state[mode].resultsDataCache = null;
            state[mode].answerKeyFileContent = null; // Clear cached file content
            populateResultsTable(null, mode);
            elements.downloadCsvBtn.style.display = 'none';
            elements.clearResultsBtn.style.display = 'none';
            elements.answerKeyInput.value = '';
            elements.answerKeyLabel.textContent = `ไฟล์เฉลย${mode === 'single' ? ' 1 คำตอบ' : 'หลายคำตอบ'} (.csv)`;
            elements.answerKeyLabel.style.borderColor = 'var(--border-color)';
            elements.answerKeyLabel.style.backgroundColor = '';
            state[mode].isAnswerKeySelected = false;
            elements.viewAnswerKeyBtn.style.display = 'none';
        });

        studentListInput.value = '';
        studentListLabel.textContent = 'รายชื่อนักศึกษา (ใช้ร่วมกัน)';
        studentListLabel.style.borderColor = 'var(--border-color)';
        studentListLabel.style.backgroundColor = '';
        isStudentListSelected = false;
        viewStudentListBtn.style.display = 'none';
        updateButtonStates();
    }

    async function loadSavedResults() {
        ['single', 'multi'].forEach(async (mode) => {
            try {
                const response = await fetch(`/get_results_${mode}`);
                const data = await response.json();
                if (data.results && data.results.length > 0) {
                    const elements = getModeElements(mode);
                    state[mode].resultsDataCache = data.results;
                    populateResultsTable(data.results, mode);
                    elements.downloadCsvBtn.style.display = 'block';
                }
            } catch (error) {
                console.error(`Could not load saved results for ${mode}:`, error);
            }
        });
    }

    async function loadSavedAnswerKey() {
        ['single', 'multi'].forEach(async (mode) => {
            try {
                // This endpoint now returns the key data, not just existence
                const response = await fetch(`/get_answer_key_${mode}`);
                const data = await response.json();
                if (data.has_answer_key && data.filename) {
                    const elements = getModeElements(mode);
                    elements.answerKeyLabel.textContent = `✓ ${data.filename} (บันทึกไว้)`;
                    elements.answerKeyLabel.style.borderColor = 'var(--success-color)';
                    elements.answerKeyLabel.style.backgroundColor = '#f0f9ff';
                    state[mode].isAnswerKeySelected = true;
                    elements.viewAnswerKeyBtn.style.display = 'inline-block';
                    updateButtonStates();
                }
            } catch (error) {
                // It's ok if this fails on startup (no key yet)
                // console.error(`Could not load saved answer key for ${mode}:`, error);
            }
        });
    }

    async function loadSavedStudentList() {
        try {
            const response = await fetch('/get_student_list');
            const data = await response.json();
            if (data.has_student_list && data.filename) {
                studentListLabel.textContent = `✓ ${data.filename} (บันทึกไว้)`;
                studentListLabel.style.borderColor = 'var(--success-color)';
                studentListLabel.style.backgroundColor = '#f0f9ff';
                isStudentListSelected = true;
                viewStudentListBtn.style.display = 'inline-block';
                updateButtonStates();
            }
        } catch (error) {
            console.error("Could not load saved student list:", error);
        }
    }

    async function loadInitialImages() {
        try {
            const response = await fetch('/get_images');
            const data = await response.json();
            if (data.files) {
                data.files.forEach(addImageThumbnail);
            }
        } catch (error) {
            console.error("Could not load initial images:", error);
        }
    }

    function connectToServerEvents() {
        const eventSource = new EventSource("/stream");
        eventSource.onmessage = function (event) {
            const msg = JSON.parse(event.data);
            // filter event by session_id (if present)
            let mySessionId = window._fullSessionId || null;
            if (msg.session_id && mySessionId && msg.session_id !== mySessionId) {
                return; // ignore events not for this session
            }
            if (msg.event === 'new_image') {
                addImageThumbnail(msg.data);
            } else if (msg.event === 'delete_images') {
                removeImageThumbnails(msg.data);
            } else if (msg.event === 'clear') {
                clearUI();
            } else if (msg.event === 'images_cleaned') {
                updateImageThumbnails(msg.data);
            }
        };
        eventSource.onerror = function (err) {
            console.error("EventSource failed:", err);
        };
    }

    // --- Utility Functions ---
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // --- Score Edit Modal Functions ---
    async function openScoreEditModal(studentData, mode) {
        console.log('Opening score edit modal for:', studentData, 'mode:', mode);

        // Store original student ID and mode for reference
        window.originalStudentId = studentData.student_id;
        window.currentMode = mode;

        // Set student info - make student ID editable
        scoreEditStudentName.textContent = studentData.student_name || 'ไม่พบชื่อ';
        scoreEditStudentName.style.color = ''; // Reset color
        scoreEditStudentName.className = ''; // Reset class

        // Reset name status indicator
        const nameStatusIndicator = document.getElementById('name-status-indicator');
        if (nameStatusIndicator) {
            nameStatusIndicator.textContent = '';
        }

        // Create dropdown for student selection
        scoreEditStudentId.innerHTML = `
            <select id="edit-student-id" style="border: 1px solid #ccc; padding: 4px; border-radius: 4px; width: 200px; font-size: 14px;">
                <option value="">กำลังโหลดรายชื่อ...</option>
            </select>
        `;

        // Load available students for dropdown
        console.log('About to load dropdown with studentId:', studentData.student_id, 'mode:', window.currentMode);
        await loadAvailableStudentsDropdown(studentData.student_id);

        // Add change event listener for dropdown
        const studentIdSelect = document.getElementById('edit-student-id');
        if (studentIdSelect) {
            studentIdSelect.addEventListener('change', async (e) => {
                const selectedValue = e.target.value;
                if (selectedValue) {
                    const selectedOption = e.target.options[e.target.selectedIndex];
                    const studentName = selectedOption.dataset.studentName;

                    // Update student name display
                    if (studentName) {
                        scoreEditStudentName.textContent = studentName;
                        scoreEditStudentName.style.color = '#10b981'; // Green color for selected
                        scoreEditStudentName.className = 'found';

                        const nameStatusIndicator = document.getElementById('name-status-indicator');
                        if (nameStatusIndicator) {
                            nameStatusIndicator.textContent = '(เลือกจากรายชื่อ ✓)';
                            nameStatusIndicator.style.color = '#10b981';
                        }
                    }
                } else {
                    // Reset if no selection
                    scoreEditStudentName.textContent = 'กรุณาเลือกนักศึกษา';
                    scoreEditStudentName.style.color = '#6b7280';
                    scoreEditStudentName.className = '';

                    const nameStatusIndicator = document.getElementById('name-status-indicator');
                    if (nameStatusIndicator) {
                        nameStatusIndicator.textContent = '';
                    }
                }
            });
        }

        // Hide the update button since we're using dropdown now
        const updateBtn = document.getElementById('update-student-name-btn');
        if (updateBtn) {
            updateBtn.style.display = 'none';
        }

        // <<< KEY CHANGE: Setup magnifier WHEN the new image has loaded >>>
        scoreEditHighlightedImage.onload = () => {
            setupScoreEditMagnifier();
        };
        scoreEditHighlightedImage.src = studentData.image_url || `/uploads/${studentData.student_file}`;

        // Setup view large image button
        const viewLargeImageBtn = document.getElementById('view-large-image-btn');
        if (viewLargeImageBtn) {
            // Remove any existing event listeners
            viewLargeImageBtn.replaceWith(viewLargeImageBtn.cloneNode(true));
            const newViewLargeBtn = document.getElementById('view-large-image-btn');

            newViewLargeBtn.addEventListener('click', () => {
                const imageSrc = scoreEditHighlightedImage.src;
                const filename = studentData.student_file || 'highlighted_image';
                openModal(imageSrc, filename);
            });
        }

        // Load detailed answers and answer key
        const [answersLoaded, keyLoaded] = await Promise.all([
            loadStudentDetailedAnswers(studentData.student_id, mode),
            loadAnswerKeyForEdit(mode)
        ]);

        if (!answersLoaded || !keyLoaded) {
            return;
        }

        // Show modal
        scoreEditModal.style.display = 'block';
        document.body.style.overflow = 'hidden'; // ล็อค scroll ของ body

        // No need for update button with dropdown selection
    }

    // Improved Magnifier Logic - แก้ไขปัญหาการซูมและตำแหน่ง
    function setupScoreEditMagnifier() {
        const container = scoreEditHighlightedImage.parentElement;
        let lens = container.querySelector('.magnifier-lens');
        const img = scoreEditHighlightedImage;

        // Create lens if it doesn't exist
        if (!lens) {
            lens = document.createElement("div");
            lens.setAttribute("class", "magnifier-lens");
            container.appendChild(lens);
        }

        // ระดับการซูมที่เหมาะสม - ไม่มากเกินไป
        const zoomLevel = 0.8;

        // ตั้งค่าพื้นหลังของแว่นขยาย
        lens.style.backgroundImage = `url('${img.src}')`;
        lens.style.backgroundRepeat = 'no-repeat';

        function moveMagnifier(e) {
            e.preventDefault();

            // ใช้ offsetX/Y สำหรับตำแหน่งบนรูปภาพโดยตรง
            const x = e.offsetX;
            const y = e.offsetY;

            // ตรวจสอบขอบเขต
            if (x < 0 || y < 0 || x > img.offsetWidth || y > img.offsetHeight) {
                lens.style.display = 'none';
                return;
            }

            // คำนวณอัตราส่วนระหว่างรูปจริงกับรูปที่แสดง
            const scaleX = img.naturalWidth / img.offsetWidth;
            const scaleY = img.naturalHeight / img.offsetHeight;

            // ขนาดแว่นขยาย
            const lensWidth = lens.offsetWidth;
            const lensHeight = lens.offsetHeight;

            // คำนวณตำแหน่งพื้นหลัง - แก้ไขสูตรให้ถูกต้อง
            const bgX = -(x * scaleX * zoomLevel - lensWidth / 2);
            const bgY = -(y * scaleY * zoomLevel - lensHeight / 2);

            // ตำแหน่งแว่นขยาย - ใช้ตำแหน่งเมาส์จริงบนหน้าจอ
            const imgRect = img.getBoundingClientRect();
            const lensX = imgRect.left + x - lensWidth / 2;
            const lensY = imgRect.top + y - lensHeight / 2;

            // อัปเดตตำแหน่งและพื้นหลัง
            lens.style.left = (lensX - container.getBoundingClientRect().left) + "px";
            lens.style.top = (lensY - container.getBoundingClientRect().top) + "px";
            lens.style.backgroundPosition = `${bgX}px ${bgY}px`;
            lens.style.backgroundSize = `${img.naturalWidth * zoomLevel}px ${img.naturalHeight * zoomLevel}px`;
            lens.style.display = 'block';
        }

        function showLens() {
            lens.style.display = 'block';
        }

        function hideLens() {
            lens.style.display = 'none';
        }

        // ล้าง event listener เก่า
        img.removeEventListener("mousemove", moveMagnifier);
        img.removeEventListener("mouseenter", showLens);
        img.removeEventListener("mouseleave", hideLens);
        container.removeEventListener("mouseleave", hideLens);

        // เพิ่ม event listener ใหม่
        img.addEventListener("mousemove", moveMagnifier);
        img.addEventListener("mouseenter", showLens);
        img.addEventListener("mouseleave", hideLens);
        container.addEventListener("mouseleave", hideLens);
    }

    async function loadStudentDetailedAnswers(studentId, mode) {
        try {
            const response = await fetch(`/get_student_detailed_answers?student_id=${studentId}&mode=${mode}`);
            const data = await response.json();

            if (data.success && data.answers) {
                generateAnswerForm(data.answers, mode);
                updateScoreDisplay(data.answers, mode);
                return true; // Success
            } else {
                console.error('Failed to load student answers:', data.error);
                scoreEditAnswersForm.innerHTML = `<p>ไม่สามารถโหลดคำตอบของนักศึกษาได้: ${data.error}</p>`;
                return false; // Failure
            }
        } catch (error) {
            console.error('Error loading student answers:', error);
            scoreEditAnswersForm.innerHTML = '<p>เกิดข้อผิดพลาดในการโหลดข้อมูล</p>';
            return false; // Failure
        }
    }

    async function loadAnswerKeyForEdit(mode) {
        try {
            const response = await fetch(`/get_answer_key_${mode}`);
            const data = await response.json();

            if (data.has_answer_key && data.answer_key) {
                displayAnswerKey(data.answer_key, mode);
                return true; // Success
            } else {
                scoreEditAnswerKey.innerHTML = '<p>ไม่พบเฉลย</p>';
                alert('ไม่สามารถโหลดไฟล์เฉลยได้ กรุณาอัปโหลดไฟล์เฉลยก่อนแก้ไขคะแนน');
                return false; // Failure
            }
        } catch (error) {
            console.error('Error loading answer key:', error);
            scoreEditAnswerKey.innerHTML = '<p>เกิดข้อผิดพลาดในการโหลดเฉลย</p>';
            return false; // Failure
        }
    }

    function generateAnswerForm(studentAnswers, mode) {
        scoreEditAnswersForm.innerHTML = '';

        // Sort questions by number
        const sortedQuestions = Object.keys(studentAnswers).sort((a, b) => parseInt(a) - parseInt(b));

        sortedQuestions.forEach(questionNum => {
            const answerData = studentAnswers[questionNum];
            const questionDiv = document.createElement('div');
            questionDiv.className = 'answer-question';
            questionDiv.dataset.question = questionNum;
            questionDiv.innerHTML = `
                <div class="question-header">
                    <span class="question-number">ข้อ ${questionNum}</span>
                    <span class="question-status status-${answerData.status}">${getStatusText(answerData.status)}</span>
                </div>
                <div class="answer-choices" data-question-choices="${questionNum}">
                    ${generateChoiceInputs(questionNum, answerData.answers, mode)}
                </div>
            `;
            scoreEditAnswersForm.appendChild(questionDiv);
        });

        // Add event listeners after creation
        document.querySelectorAll('.answer-choices input').forEach(input => {
            input.addEventListener('change', () => {
                // Call global update function
                window.updateAnswerChoice(
                    input.dataset.question,
                    input.value,
                    input.checked,
                    mode
                );
            });
        });
    }

    function generateChoiceInputs(questionNum, selectedAnswers, mode) {
        const choices = ['1', '2', '3', '4', '5'];
        const inputType = mode === 'single' ? 'radio' : 'checkbox';
        const inputName = mode === 'single' ? `question_${questionNum}` : `question_${questionNum}[]`;

        return choices.map(choice => {
            const isChecked = selectedAnswers.includes(parseInt(choice));
            const checkedAttr = isChecked ? 'checked' : '';

            return `
                <label class="choice-label">
                    <input type="${inputType}" 
                           name="${inputName}" 
                           value="${choice}" 
                           data-question="${questionNum}"
                           ${checkedAttr}>
                    <span class="choice-text">${choice}</span>
                </label>
            `;
        }).join('');
    }

    function getStatusText(status) {
        const statusMap = {
            'correct': 'ถูก',
            'incorrect': 'ผิด',
            'partial': 'ถูกบางส่วน',
            'no_key': 'ไม่มีเฉลย',
            'updated': 'แก้ไขแล้ว'
        };
        return statusMap[status] || 'ไม่ทราบ';
    }

    function displayAnswerKey(answerKey, mode) {
        // Store answer key globally for real-time score calculation
        window.currentAnswerKey = answerKey;

        scoreEditAnswerKey.innerHTML = '';

        // Sort questions by number
        const sortedQuestions = Object.keys(answerKey).sort((a, b) => parseInt(a) - parseInt(b));

        sortedQuestions.forEach(questionNum => {
            const correctAnswers = answerKey[questionNum];
            const keyDiv = document.createElement('div');
            keyDiv.className = 'answer-key-item';

            let answersText;
            if (mode === 'single') {
                answersText = correctAnswers.toString();
            } else {
                answersText = Array.isArray(correctAnswers) ? correctAnswers.sort().join(', ') : correctAnswers.toString();
            }

            keyDiv.innerHTML = `
                <span class="key-question">ข้อ ${questionNum}:</span>
                <span class="key-answers">${answersText}</span>
            `;
            scoreEditAnswerKey.appendChild(keyDiv);
        });
    }

    // Global function for answer choice updates, accessible from generated HTML
    window.updateAnswerChoice = function (questionNum, choice, isChecked, mode) {
        const choiceNum = parseInt(choice);

        if (mode === 'single') {
            // For radio buttons, the 'answers' array will only have one item
            window.currentStudentAnswers[questionNum].answers = isChecked ? [choiceNum] : [];
        } else {
            // For checkboxes, add or remove from the array
            const currentAnswers = window.currentStudentAnswers[questionNum].answers;
            if (isChecked) {
                if (!currentAnswers.includes(choiceNum)) {
                    currentAnswers.push(choiceNum);
                }
            } else {
                const index = currentAnswers.indexOf(choiceNum);
                if (index > -1) {
                    currentAnswers.splice(index, 1);
                }
            }
        }

        // Update status and score display in real-time
        updateQuestionStatus(questionNum, mode);
        updateScoreDisplay(window.currentStudentAnswers, mode);
    };

    function updateQuestionStatus(questionNum, mode) {
        if (!window.currentAnswerKey || !window.currentStudentAnswers[questionNum]) {
            return;
        }

        const studentAnswers = new Set(window.currentStudentAnswers[questionNum].answers);
        const correctAnswers = window.currentAnswerKey[questionNum];
        let status = 'incorrect';

        if (mode === 'single') {
            if (studentAnswers.size === 1 && correctAnswers && studentAnswers.has(correctAnswers)) {
                status = 'correct';
            }
        } else {
            const correctSet = new Set(Array.isArray(correctAnswers) ? correctAnswers : [correctAnswers]);
            if (correctSet.size === 0) {
                status = 'no_key';
            } else if (studentAnswers.size > 0 &&
                studentAnswers.size === correctSet.size && [...studentAnswers].every(ans => correctSet.has(ans))) {
                status = 'correct';
            } else if (studentAnswers.size > 0 && [...studentAnswers].every(ans => correctSet.has(ans))) {
                status = 'partial';
            }
        }

        // Update the status in memory and UI
        window.currentStudentAnswers[questionNum].status = status;

        const questionDiv = document.querySelector(`.answer-question[data-question="${questionNum}"]`);
        if (questionDiv) {
            const statusElement = questionDiv.querySelector('.question-status');
            if (statusElement) {
                statusElement.className = `question-status status-${status}`;
                statusElement.textContent = getStatusText(status);
            }
        }
    }

    function updateScoreDisplay(studentAnswers, mode) {
        // Store current answers globally for saving
        window.currentStudentAnswers = studentAnswers;
        window.currentMode = mode;

        let correctCount = 0;
        // ใช้จำนวนข้อจากเฉลยแทนการนับจากคำตอบนักเรียน
        let totalQuestions = window.currentAnswerKey ? Object.keys(window.currentAnswerKey).length : Object.keys(studentAnswers).length;
        console.log('Score Display - Answer Key Questions:', totalQuestions, 'Mode:', mode);
        let multipleAnswersCount = 0;

        Object.values(studentAnswers).forEach(answerData => {
            if (answerData.status === 'correct') {
                correctCount++;
            }
            // นับข้อที่มีการกาหลายคำตอบ (เฉพาะโหมด single)
            if (mode === 'single') {
                // ตรวจสอบจาก has_multiple_answers หรือนับจากจำนวนคำตอบ (fallback)
                const hasMultiple = answerData.has_multiple_answers || 
                                  (answerData.answers && answerData.answers.length > 1);
                if (hasMultiple) {
                    multipleAnswersCount++;
                }
            }
        });

        // แสดงคะแนนพร้อมคำเตือนถ้ามีการกาหลายคำตอบ
        let scoreText = `${correctCount}/${totalQuestions}`;
        if (mode === 'single' && multipleAnswersCount > 0) {
            scoreText += ` (มีการเลือก2คำตอบใน1ข้อ)`;
            currentScoreDisplay.style.color = '#ef4444'; // สีแดง
        } else {
            currentScoreDisplay.style.color = ''; // สีปกติ
        }
        currentScoreDisplay.textContent = scoreText;
    }

    // Function to load available students for dropdown
    async function loadAvailableStudentsDropdown(currentStudentId) {
        const studentIdSelect = document.getElementById('edit-student-id');
        if (!studentIdSelect) return;

        console.log('Loading available students for currentStudentId:', currentStudentId, 'mode:', window.currentMode);

        try {
            const response = await fetch('/get_available_students', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mode: window.currentMode,
                    current_student_id: currentStudentId || window.originalStudentId // ใช้ originalStudentId ถ้าไม่มี currentStudentId
                })
            });

            const result = await response.json();
            console.log('Available students response:', result);

            if (result.success) {
                // Clear existing options
                studentIdSelect.innerHTML = '';

                // Add default option
                const defaultOption = document.createElement('option');
                defaultOption.value = '';
                defaultOption.textContent = 'เลือกนักศึกษา...';
                studentIdSelect.appendChild(defaultOption);

                // Add current student as first option if exists
                const actualCurrentId = currentStudentId || window.originalStudentId;
                if (actualCurrentId) {
                    const currentOption = document.createElement('option');
                    currentOption.value = actualCurrentId;
                    currentOption.textContent = `${actualCurrentId} - ${scoreEditStudentName.textContent}`;
                    currentOption.dataset.studentName = scoreEditStudentName.textContent;
                    currentOption.selected = true;
                    studentIdSelect.appendChild(currentOption);
                }

                // Add available students
                result.students.forEach(student => {
                    // Skip if this is the current student (already added above)
                    if (student.student_id === actualCurrentId) return;

                    const option = document.createElement('option');
                    option.value = student.student_id;
                    option.textContent = student.display_text;
                    option.dataset.studentName = student.name;
                    studentIdSelect.appendChild(option);
                });

                // Add info about availability
                if (result.students.length === 0 && !actualCurrentId) {
                    const noAvailableOption = document.createElement('option');
                    noAvailableOption.value = '';
                    noAvailableOption.textContent = 'ไม่มีนักศึกษาที่ยังไม่ได้ใช้งาน';
                    noAvailableOption.disabled = true;
                    studentIdSelect.appendChild(noAvailableOption);
                }

                console.log(`Loaded ${result.students.length} available students (${result.used_count}/${result.total_students} used)`);

            } else {
                studentIdSelect.innerHTML = '<option value="">ไม่สามารถโหลดรายชื่อได้</option>';
                console.error('Error loading students:', result.error);
            }

        } catch (error) {
            console.error('Error loading available students:', error);
            studentIdSelect.innerHTML = '<option value="">เกิดข้อผิดพลาดในการโหลด</option>';
        }
    }

    // Function to update student name from ID (kept for backward compatibility)
    async function updateStudentNameFromId(studentId) {
        if (!studentId) return;

        try {
            const response = await fetch('/get_student_name_by_id', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ student_id: studentId })
            });

            const result = await response.json();
            const nameStatusIndicator = document.getElementById('name-status-indicator');

            if (result.success && result.student_name) {
                scoreEditStudentName.textContent = result.student_name;
                scoreEditStudentName.style.color = '#10b981'; // Green color for found
                scoreEditStudentName.className = 'found';
                nameStatusIndicator.textContent = '(พบในรายชื่อ ✓)';
                nameStatusIndicator.style.color = '#10b981';
            } else {
                scoreEditStudentName.textContent = 'ไม่พบชื่อในรายชื่อ';
                scoreEditStudentName.style.color = '#ef4444'; // Red color for not found
                scoreEditStudentName.className = 'not-found';
                nameStatusIndicator.textContent = '(ไม่พบในรายชื่อ ✗)';
                nameStatusIndicator.style.color = '#ef4444';
            }
        } catch (error) {
            console.error('Error fetching student name:', error);
            scoreEditStudentName.textContent = 'เกิดข้อผิดพลาดในการค้นหา';
            scoreEditStudentName.style.color = '#ef4444';

            const nameStatusIndicator = document.getElementById('name-status-indicator');
            nameStatusIndicator.textContent = '(เกิดข้อผิดพลาด ⚠)';
            nameStatusIndicator.style.color = '#f59e0b';

            // แสดงข้อความข้อผิดพลาด
            const updateBtn = document.getElementById('update-student-name-btn');
            const originalText = updateBtn.textContent;
            updateBtn.textContent = '⚠ ข้อผิดพลาด';
            updateBtn.style.background = '#f59e0b';
            updateBtn.style.color = 'white';

            setTimeout(() => {
                updateBtn.textContent = originalText;
                updateBtn.style.background = '';
                updateBtn.style.color = '';
            }, 2000);
        }
    }

    // Save score edit
    saveScoreEditBtn.addEventListener('click', async () => {
        if (!window.currentStudentAnswers || !window.currentMode) {
            alert('ไม่พบข้อมูลที่จะบันทึก');
            return;
        }

        try {
            const studentIdSelect = document.getElementById('edit-student-id');
            const studentId = studentIdSelect ? studentIdSelect.value.trim() : '';

            if (!studentId) {
                alert('กรุณาเลือกนักศึกษา');
                return;
            }

            console.log('Saving score for student ID:', studentId);
            const response = await fetch('/update_student_score', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    student_id: studentId,
                    student_name: scoreEditStudentName.textContent,
                    mode: window.currentMode,
                    answers: window.currentStudentAnswers,
                    original_student_id: window.originalStudentId || studentId
                })
            });

            const result = await response.json();
            console.log('Server response:', result);

            if (result.success) {
                alert('บันทึกคะแนนเรียบร้อยแล้ว');
                scoreEditModal.style.display = 'none';
                document.body.style.overflow = ''; // ปลดล็อค scroll ของ body

                // Refresh the results table
                if (state[window.currentMode].resultsDataCache) {
                    const studentIndex = state[window.currentMode].resultsDataCache.findIndex(
                        s => s.student_id === result.original_student_id || s.student_id === studentId
                    );
                    console.log('Found student at index:', studentIndex);

                    if (studentIndex !== -1) {
                        // คำนวณจำนวนข้อที่มีการกาหลายคำตอบใหม่
                        let multipleAnswersCount = 0;
                        if (window.currentMode === 'single') {
                            Object.values(window.currentStudentAnswers).forEach(answerData => {
                                const hasMultiple = answerData.has_multiple_answers || 
                                                  (answerData.answers && answerData.answers.length > 1);
                                if (hasMultiple) {
                                    multipleAnswersCount++;
                                }
                            });
                        }
                        
                        state[window.currentMode].resultsDataCache[studentIndex].student_id = studentId;
                        state[window.currentMode].resultsDataCache[studentIndex].student_name = scoreEditStudentName.textContent;
                        state[window.currentMode].resultsDataCache[studentIndex].score = result.new_score;
                        state[window.currentMode].resultsDataCache[studentIndex].total = result.total;
                        state[window.currentMode].resultsDataCache[studentIndex].multiple_answers_count = multipleAnswersCount;
                        
                        // โหลดข้อมูลใหม่จากเซิร์ฟเวอร์เพื่ออัปเดต is_duplicate และ has_issues
                        const refreshResponse = await fetch(`/get_results_${window.currentMode}`);
                        const refreshData = await refreshResponse.json();
                        if (refreshData.results) {
                            state[window.currentMode].resultsDataCache = refreshData.results;
                        }
                        
                        console.log('Updated student data:', state[window.currentMode].resultsDataCache[studentIndex]);
                        populateResultsTable(state[window.currentMode].resultsDataCache, window.currentMode);
                    } else {
                        console.error('Student not found in cache, reloading results...');
                        // โหลดผลลัพธ์ใหม่จากเซิร์ฟเวอร์
                        const response = await fetch(`/get_results_${window.currentMode}`);
                        const data = await response.json();
                        if (data.results) {
                            state[window.currentMode].resultsDataCache = data.results;
                            populateResultsTable(data.results, window.currentMode);
                        }
                    }
                }
            } else {
                alert('เกิดข้อผิดพลาด: ' + result.error);
            }
        } catch (error) {
            console.error('Error saving score:', error);
            alert('เกิดข้อผิดพลาดในการบันทึก');
        }
    });

    // Cancel score edit
    cancelScoreEditBtn.addEventListener('click', () => {
        scoreEditModal.style.display = 'none';
        document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
    });

    // Close score edit modal
    scoreEditClose.addEventListener('click', () => {
        scoreEditModal.style.display = 'none';
        document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
    });

    // --- Event Listeners ---
    pcUploadInput.addEventListener('change', () => {
        handleFileUpload(pcUploadInput.files);
        pcUploadInput.value = '';
    });

    // --- Drag and Drop Support ---
    const imagePreviewContainer = document.getElementById('image-preview-container');

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        imagePreviewContainer.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        imagePreviewContainer.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        imagePreviewContainer.addEventListener(eventName, unhighlight, false);
    });

    imagePreviewContainer.addEventListener('drop', handleDrop, false);

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function highlight(e) {
        imagePreviewContainer.classList.add('drag-over');
    }

    function unhighlight(e) {
        imagePreviewContainer.classList.remove('drag-over');
    }

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;

        // กรองเฉพาะไฟล์ที่รองรับ
        const validFiles = Array.from(files).filter(file => {
            const extension = file.name.toLowerCase().split('.').pop();
            return ['jpg', 'jpeg', 'png', 'pdf'].includes(extension);
        });

        if (validFiles.length > 0) {
            handleFileUpload(validFiles);
        } else {
            alert('กรุณาอัปโหลดไฟล์รูปภาพ (JPG, PNG) หรือ PDF เท่านั้น');
        }
    }

    // Event Listeners for both modes
    ['single', 'multi'].forEach(mode => {
        const elements = getModeElements(mode);

        // **FIX for NotReadableError**
        elements.answerKeyInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) {
                state[mode].answerKeyFileContent = null;
                return;
            }

            // Read the file content immediately and store it.
            try {
                state[mode].answerKeyFileContent = await file.text();
            } catch (readError) {
                console.error("Error reading answer key file locally:", readError);
                alert("ไม่สามารถอ่านไฟล์ได้ อาจมีปัญหาเรื่อง permission");
                state[mode].answerKeyFileContent = null;
                return;
            }

            const formData = new FormData();
            formData.append('answer_key', file);

            const uploadEndpoint = mode === 'single' ? '/upload_answer_key_single' : '/upload_answer_key_multi';
            try {
                const response = await fetch(uploadEndpoint, { method: 'POST', body: formData });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.message || 'Failed to upload answer key');
                }

                elements.answerKeyLabel.textContent = `✓ ${result.filename} (บันทึกไว้)`;
                elements.answerKeyLabel.style.borderColor = 'var(--success-color)';
                elements.answerKeyLabel.style.backgroundColor = '#f0f9ff';
                state[mode].isAnswerKeySelected = true;
                elements.viewAnswerKeyBtn.style.display = 'inline-block';
                // อัปเดตปุ่มดาวน์โหลดทันทีหลังอัปโหลด answer key
                window.updateDownloadButtons && window.updateDownloadButtons();
            } catch (error) {
                console.error(`Error uploading ${mode} answer key:`, error);
                alert(`เกิดข้อผิดพลาด: ${error.message}`);
                elements.answerKeyLabel.textContent = `❌ ${file.name} (ไม่สามารถบันทึกได้)`;
                elements.answerKeyLabel.style.borderColor = 'var(--danger-color)';
                elements.answerKeyLabel.style.backgroundColor = '#fef2f2';
                state[mode].isAnswerKeySelected = false;
                elements.viewAnswerKeyBtn.style.display = 'none';
            }
            updateButtonStates();
        });

        // Event for Processing
        elements.processBtn.addEventListener('click', async () => {
            elements.loadingSpinner.style.display = 'flex';
            elements.resultsPlaceholder.style.display = 'none';
            elements.resultsTable.style.display = 'none';
            elements.resultsTbody.innerHTML = '';
            elements.processBtn.disabled = true;
            elements.downloadCsvBtn.style.display = 'none';

            try {
                const response = await fetch(`/process_${mode}`, { method: 'POST' });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Processing failed');

                console.log('Processing completed, received data:', data);
                state[mode].resultsDataCache = data.results;
                populateResultsTable(data.results, mode);
                elements.downloadCsvBtn.style.display = 'block';
            } catch (error) {
                console.error('Processing error:', error);
                alert(`เกิดข้อผิดพลาดในการประมวลผล: ${error.message}`);
                elements.resultsPlaceholder.style.display = 'flex';
            } finally {
                elements.loadingSpinner.style.display = 'none';
                updateButtonStates();
            }
        });

        // Event for Download CSV
        elements.downloadCsvBtn.addEventListener('click', async () => {
            if (!state[mode].resultsDataCache) return;
            const filenameInput = document.getElementById(`output-filename-${mode}`);
            const filename = filenameInput ? filenameInput.value.trim() || 'omr_results' : 'omr_results';

            try {
                // ดึงข้อมูลล่าสุดจากเซิร์ฟเวอร์แทนการใช้ cache
                const resultsResponse = await fetch(`/get_results_${mode}`);
                const resultsData = await resultsResponse.json();
                const latestResults = resultsData.results || state[mode].resultsDataCache;

                const response = await fetch(`/download_results_${mode}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ results: latestResults, filename: filename })
                });
                if (!response.ok) throw new Error('Download failed');
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = `${filename}_${mode}.csv`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } catch (error) {
                console.error('Download error:', error);
                alert('เกิดข้อผิดพลาดในการดาวน์โหลด');
            }
        });

        // Event for Clear Results
        elements.clearResultsBtn.addEventListener('click', async () => {
            if (confirm('คุณต้องการลบผลลัพธ์ทั้งหมดหรือไม่?')) {
                try {
                    await fetch(`/clear_results_${mode}`, { method: 'POST' });
                    state[mode].resultsDataCache = null;
                    populateResultsTable(null, mode);
                    elements.downloadCsvBtn.style.display = 'none';
                    elements.clearResultsBtn.style.display = 'none';
                } catch (error) {
                    console.error('Clear results error:', error);
                    alert('เกิดข้อผิดพลาดในการลบผลลัพธ์');
                }
            }
        });

        // Event for View Answer Key
        elements.viewAnswerKeyBtn.addEventListener('click', async () => {
            dataViewModal.style.display = 'block';
            document.body.style.overflow = 'hidden'; // ล็อค scroll ของ body
            dataViewTitle.textContent = `เฉลย (${mode === 'single' ? 'ตัวเลือกเดียว' : 'หลายตัวเลือก'})`;
            dataViewContent.innerHTML = '<p>กำลังโหลด...</p>';

            try {
                const response = await fetch(`/view_answer_key_${mode}`);
                const data = await response.json();

                if (data.success && data.data.length > 0) {
                    let tableHtml = '<table class="data-table"><thead><tr><th>ข้อ</th><th>เฉลย</th></tr></thead><tbody>';
                    data.data.forEach(item => {
                        tableHtml += `<tr><td>${item.question}</td><td>${item.answer}</td></tr>`;
                    });
                    tableHtml += '</tbody></table>';
                    dataViewContent.innerHTML = tableHtml;
                } else {
                    dataViewContent.innerHTML = '<p>ไม่พบข้อมูลเฉลย</p>';
                }
            } catch (error) {
                console.error('Error loading answer key:', error);
                dataViewContent.innerHTML = '<p>เกิดข้อผิดพลาดในการโหลดข้อมูล</p>';
            }
        });

        // Event for Create/Edit Answer Key
        elements.createEditBtn.addEventListener('click', () => openAnswerKeyEditor());
    });

    studentListInput.addEventListener('change', async () => {
        if (studentListInput.files.length > 0) {
            const file = studentListInput.files[0];

            // แสดงสถานะกำลังบันทึก
            studentListLabel.textContent = `⏳ กำลังบันทึก ${file.name}...`;
            studentListLabel.style.borderColor = 'var(--warning-color)';
            studentListLabel.style.backgroundColor = '#fffbeb';

            try {
                // อัพโหลดและบันทึกทันที
                const formData = new FormData();
                formData.append('student_list', file);

                const response = await fetch('/upload_student_list', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error('Failed to upload student list');
                }

                const result = await response.json();

                // แสดงสถานะสำเร็จ
                studentListLabel.textContent = `✓ ${file.name} (บันทึกไว้)`;
                studentListLabel.style.borderColor = 'var(--success-color)';
                studentListLabel.style.backgroundColor = '#f0f9ff';
                isStudentListSelected = true;
                viewStudentListBtn.style.display = 'inline-block';

                // อัปเดตปุ่มดาวน์โหลดทันที
                window.updateDownloadButtons && window.updateDownloadButtons();

            } catch (error) {
                console.error('Error uploading student list:', error);
                studentListLabel.textContent = `❌ ${file.name} (ไม่สามารถบันทึกได้)`;
                studentListLabel.style.borderColor = 'var(--danger-color)';
                studentListLabel.style.backgroundColor = '#fef2f2';
                isStudentListSelected = false;
                viewStudentListBtn.style.display = 'none';
                alert('เกิดข้อผิดพลาดในการบันทึกไฟล์รายชื่อนักเรียน');
            }
        } else {
            studentListLabel.textContent = 'รายชื่อนักศึกษา (ใช้ร่วมกัน)';
            studentListLabel.style.borderColor = 'var(--border-color)';
            studentListLabel.style.backgroundColor = '';
            isStudentListSelected = false;
            viewStudentListBtn.style.display = 'none';
        }
        updateButtonStates();
    });

    cleanSelectedBtn.addEventListener('click', async () => {
        const selectedFiles = Array.from(document.querySelectorAll('.delete-checkbox:checked'))
            .map(cb => cb.closest('.thumbnail').dataset.savedName);

        if (selectedFiles.length === 0) return;

        const originalText = cleanSelectedBtn.textContent;
        cleanSelectedBtn.textContent = 'กำลังปรับ...';
        cleanSelectedBtn.disabled = true;

        try {
            await fetch('/clean_images', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filenames: selectedFiles })
            });
        } catch (error) {
            console.error('Error cleaning images:', error);
            alert('เกิดข้อผิดพลาดในการปรับแสงรูปภาพ');
        } finally {
            cleanSelectedBtn.textContent = originalText;
            updateButtonStates();
        }
    });

    optimizeImagesBtn.addEventListener('click', async () => {
        if (!confirm('ต้องการปรับขนาดรูปภาพทั้งหมดสำหรับแสดงผลบนเว็บหรือไม่?\n(จะช่วยลด bandwidth และเพิ่มความเร็วในการโหลด)')) {
            return;
        }

        const originalText = optimizeImagesBtn.textContent;
        optimizeImagesBtn.disabled = true;
        optimizeImagesBtn.textContent = '🔄 กำลังปรับขนาด...';

        try {
            const response = await fetch('/optimize_images', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const result = await response.json();
            if (response.ok) {
                alert(result.message);
                loadInitialImages(); // โหลดรูปใหม่
            } else {
                alert('เกิดข้อผิดพลาด: ' + result.error);
            }
        } catch (error) {
            alert('เกิดข้อผิดพลาดในการปรับขนาด: ' + error.message);
        } finally {
            optimizeImagesBtn.disabled = false;
            optimizeImagesBtn.textContent = originalText;
        }
    });

    deleteSelectedBtn.addEventListener('click', () => {
        const selectedFiles = Array.from(document.querySelectorAll('.delete-checkbox:checked'))
            .map(cb => cb.closest('.thumbnail').dataset.savedName);
        deleteImagesOnServer(selectedFiles);
    });

    deleteAllBtn.addEventListener('click', () => {
        if (confirm('คุณต้องการลบรูปภาพทั้งหมดใช่หรือไม่?')) {
            const allFiles = Array.from(document.querySelectorAll('.thumbnail'))
                .map(thumb => thumb.dataset.savedName);
            deleteImagesOnServer(allFiles);
        }
    });

    newSessionBtn.addEventListener('click', async () => {
        if (confirm('คุณต้องการเริ่มเซสชั่นใหม่และลบข้อมูลทั้งหมดหรือไม่? (ไฟล์รูปและผลลัพธ์จะถูกลบ)')) {
            try {
                await fetch('/new_session', { method: 'POST' });
                // รีเฟรชหน้าเว็บอัตโนมัติหลังจากเคลียร์เซสชั่นเสร็จ
                setTimeout(() => {
                    window.location.reload();
                }, 500);
            } catch (error) {
                console.error('Failed to start new session:', error);
                alert('ไม่สามารถเริ่มเซสชั่นใหม่ได้');
            }
        }
    });

    if (modalClose) {
        modalClose.addEventListener('click', () => {
            if (modal) modal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
            cleanupModalEvents();
        });
    }

    // --- START: Manual Answer Key Logic (UPDATED FOR DUAL MODE) ---

    function populateAnswerKeyModal(mode, existingAnswers = {}) {
        manualAnswerKeyContent.innerHTML = '';
        const totalQuestions = 120;
        const choices = 5;
        const questionsPerColumn = 30;
        const totalColumns = 4;

        // สร้าง container สำหรับ 4 คอลัมน์
        const columnsContainer = document.createElement('div');
        columnsContainer.className = 'answer-key-columns';
        columnsContainer.style.display = 'grid';
        columnsContainer.style.gridTemplateColumns = 'repeat(4, 1fr)';
        columnsContainer.style.gap = '20px';

        // สร้าง 4 คอลัมน์
        for (let col = 0; col < totalColumns; col++) {
            const columnDiv = document.createElement('div');
            columnDiv.className = 'answer-key-column';

            const columnHeader = document.createElement('h4');
            columnHeader.textContent = `คอลัมน์ ${col + 1} (ข้อ ${col * questionsPerColumn + 1}-${(col + 1) * questionsPerColumn})`;
            columnHeader.style.textAlign = 'center';
            columnHeader.style.marginBottom = '15px';
            columnHeader.style.color = 'var(--primary-color)';
            columnHeader.style.borderBottom = '2px solid var(--border-color)';
            columnHeader.style.paddingBottom = '8px';
            columnDiv.appendChild(columnHeader);

            // สร้างคำถามในแต่ละคอลัมน์ (30 ข้อ)
            for (let row = 0; row < questionsPerColumn; row++) {
                const questionNumber = col * questionsPerColumn + row + 1;

                const itemDiv = document.createElement('div');
                itemDiv.className = 'manual-answer-item';
                itemDiv.style.marginBottom = '8px';

                const header = document.createElement('div');
                header.className = 'manual-answer-item-header';
                header.textContent = `ข้อ ${questionNumber}`;
                header.style.fontSize = '14px';
                itemDiv.appendChild(header);

                if (mode === 'single') {
                    const choicesDiv = document.createElement('div');
                    choicesDiv.className = 'manual-answer-choices';

                    for (let j = 1; j <= choices; j++) {
                        const radioId = `q${questionNumber}-c${j}`;

                        const radioInput = document.createElement('input');
                        radioInput.type = 'radio';
                        radioInput.id = radioId;
                        radioInput.name = `question-${questionNumber}`;
                        radioInput.value = j;

                        if (existingAnswers[questionNumber] && parseInt(existingAnswers[questionNumber]) === j) {
                            radioInput.checked = true;
                        }

                        const radioLabel = document.createElement('label');
                        radioLabel.htmlFor = radioId;
                        radioLabel.textContent = j;

                        // Deselect Logic
                        radioLabel.addEventListener('click', function (e) {
                            e.preventDefault();
                            const boundInput = document.getElementById(this.htmlFor);

                            if (boundInput.checked) {
                                boundInput.checked = false;
                            } else {
                                boundInput.checked = true;
                            }
                        });

                        choicesDiv.appendChild(radioInput);
                        choicesDiv.appendChild(radioLabel);
                    }
                    itemDiv.appendChild(choicesDiv);
                } else { // multi mode
                    const choicesDiv = document.createElement('div');
                    choicesDiv.className = 'manual-answer-choices-multi';

                    for (let j = 1; j <= choices; j++) {
                        const checkInput = document.createElement('input');
                        checkInput.type = 'checkbox';
                        checkInput.id = `q${questionNumber}-c${j}`;
                        checkInput.name = `question-${questionNumber}`;
                        checkInput.value = j;

                        // เช็คค่าจาก existingAnswers ที่เป็น array
                        const currentAnswers = existingAnswers[questionNumber] ? String(existingAnswers[questionNumber]).split('&') : [];
                        if (currentAnswers.includes(String(j))) {
                            checkInput.checked = true;
                        }

                        const checkLabel = document.createElement('label');
                        checkLabel.htmlFor = `q${questionNumber}-c${j}`;
                        checkLabel.textContent = j;

                        choicesDiv.appendChild(checkInput);
                        choicesDiv.appendChild(checkLabel);
                    }
                    itemDiv.appendChild(choicesDiv);
                }

                columnDiv.appendChild(itemDiv);
            }

            columnsContainer.appendChild(columnDiv);
        }

        manualAnswerKeyContent.appendChild(columnsContainer);
    }

    // **FIX for NotReadableError** - This function is now much simpler.
    async function openAnswerKeyEditor() {
        const existingAnswers = {};

        // Priority 1: Use the file content we cached earlier.
        if (state[currentMode].answerKeyFileContent) {
            console.log("Using cached file content for editor.");
            const lines = state[currentMode].answerKeyFileContent.trim().split('\n');
            lines.forEach(line => {
                const parts = line.split(',');
                if (parts.length === 2) {
                    existingAnswers[parts[0].trim()] = parts[1].trim();
                }
            });
        }
        // Priority 2: If no new file, fetch from server
        else if (state[currentMode].isAnswerKeySelected) {
            try {
                console.log("Fetching saved key from server for editor.");
                const response = await fetch(`/view_answer_key_${currentMode}`);
                const data = await response.json();
                if (data.success && data.data) {
                    data.data.forEach(item => {
                        existingAnswers[item.question] = item.answer;
                    });
                }
            } catch (error) {
                console.error("Error fetching saved answer key:", error);
                alert("ไม่สามารถโหลดข้อมูลเฉลยที่บันทึกไว้ได้");
            }
        }

        populateAnswerKeyModal(currentMode, existingAnswers);
        manualAnswerKeyModal.style.display = 'block';
        document.body.style.overflow = 'hidden'; // ล็อค scroll ของ body
    }

    async function saveAnswerKeyFromModal() {
        let csvContent = "";
        const totalQuestions = 120;

        if (currentMode === 'single') {
            for (let i = 1; i <= totalQuestions; i++) {
                const selectedChoice = document.querySelector(`input[name="question-${i}"]:checked`);
                if (selectedChoice) {
                    csvContent += `${i},${selectedChoice.value}\n`;
                }
            }
        } else { // multi mode
            for (let i = 1; i <= totalQuestions; i++) {
                const selectedChoices = document.querySelectorAll(`input[name="question-${i}"]:checked`);
                if (selectedChoices.length > 0) {
                    const values = Array.from(selectedChoices).map(cb => cb.value);
                    csvContent += `${i},${values.join('&')}\n`; // เชื่อมคำตอบด้วย &
                }
            }
        }

        try {
            // ส่งข้อมูลไปที่ /save_answer_key_[currentMode]
            const response = await fetch(`/save_answer_key_${currentMode}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    csv_content: csvContent,
                    filename: `manual_answer_key_${currentMode}.csv`
                })
            });

            if (!response.ok) {
                throw new Error('Failed to save answer key');
            }

            const result = await response.json();
            const elements = getModeElements(currentMode);

            // อัปเดต UI
            elements.answerKeyLabel.textContent = `✓ ${result.filename} (บันทึกไว้)`;
            elements.answerKeyLabel.style.borderColor = 'var(--success-color)';
            elements.answerKeyLabel.style.backgroundColor = '#f0f9ff';
            state[currentMode].isAnswerKeySelected = true;
            elements.viewAnswerKeyBtn.style.display = 'inline-block';
            updateButtonStates();

            // อัปเดตปุ่มดาวน์โหลดทันที
            window.updateDownloadButtons && window.updateDownloadButtons();

            // แสดงข้อความสำเร็จ
            alert('บันทึกเฉลยสำเร็จ!');

        } catch (error) {
            console.error('Error saving answer key:', error);
            alert('เกิดข้อผิดพลาดในการบันทึกเฉลย กรุณาลองใหม่');
        }

        manualAnswerKeyModal.style.display = 'none';
        document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
    }

    function clearAllManualAnswers() {
        const checkedInputs = manualAnswerKeyContent.querySelectorAll('input:checked');
        checkedInputs.forEach(input => {
            input.checked = false;
        });
    }

    // Event Listeners for the manual editor modal
    if (saveManualAnswerKeyBtn) {
        saveManualAnswerKeyBtn.addEventListener('click', saveAnswerKeyFromModal);
    }
    if (clearManualAnswerKeyBtn) {
        clearManualAnswerKeyBtn.addEventListener('click', clearAllManualAnswers);
    }
    if (manualAnswerKeyClose) {
        manualAnswerKeyClose.addEventListener('click', () => {
            if (manualAnswerKeyModal) manualAnswerKeyModal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
        });
    }

    // Event Listeners for data view modal
    if (dataViewClose) {
        dataViewClose.addEventListener('click', () => {
            if (dataViewModal) dataViewModal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
        });
    }

    // Update session status and server info on page load and periodically
    updateSessionStatus();
    updateServerInfo();
    setInterval(updateSessionStatus, 30000); // อัปเดตทุก 30 วินาที
    setInterval(updateServerInfo, 60000); // อัปเดตทุก 60 วินาที

    // Event Listener for Copy Mobile Link button - แสดง QR Code แทน
    if (copyMobileLinkBtn) {
        copyMobileLinkBtn.addEventListener('click', async () => {
            clearQRCode(); // ล้าง QR Code เก่าก่อน
            qrModal.style.display = 'block';
            document.body.style.overflow = 'hidden'; // ล็อค scroll ของ body
            await generateQRCode();
        });
    }

    // QR Code Functions
    function clearQRCode() {
        const qrContainer = document.getElementById('qr-code-container');
        if (qrContainer) {
            // ลบ QR Code images และ link info ทั้งหมด (รวมทั้งที่มี class qr-image)
            const existingElements = qrContainer.querySelectorAll('img, .qr-image, div');
            existingElements.forEach(element => {
                // เก็บเฉพาะ qr-loading element ไว้
                if (element.id !== 'qr-loading') {
                    element.remove();
                }
            });

            // รีเซ็ต canvas และ loading state
            if (qrCanvas) {
                qrCanvas.style.display = 'none';
                qrCanvas.classList.remove('show');
            }

            if (qrLoading) {
                qrLoading.style.display = 'none';
                // รีเซ็ต loading content กลับเป็นเดิม
                qrLoading.innerHTML = `
                    <div class="spinner"></div>
                    <p>กำลังสร้าง QR Code...</p>
                `;
            }
        }
    }

    async function generateQRCode() {
        try {
            const qrContainer = document.getElementById('qr-code-container');

            // ลบ QR Code เก่าทั้งหมดก่อน (รวมทั้ง img และ canvas)
            clearQRCode();

            // แสดง loading
            qrLoading.style.display = 'block';
            qrCanvas.style.display = 'none';

            const response = await fetch('/generate_qr_code');
            const data = await response.json();

            if (response.ok && data.qr_code_url) {
                // สร้าง QR Code ด้วย API (ไม่ต้องใช้ library)
                const qrImg = document.createElement('img');
                qrImg.src = data.qr_code_url;
                qrImg.style.cssText = `
                    max-width: 100%;
                    height: auto;
                    border: 2px solid #e5e7eb;
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                    background: white;
                    padding: 8px;
                `;
                qrImg.className = 'qr-image'; // เพิ่ม class เพื่อง่ายต่อการจัดการ
                qrImg.alt = 'QR Code สำหรับเชื่อมต่อมือถือ';

                // รอให้รูปโหลดเสร็จ
                qrImg.onload = () => {
                    qrLoading.style.display = 'none';
                    qrCanvas.style.display = 'none';
                    qrContainer.appendChild(qrImg);

                    // ลบส่วนแสดงลิงก์ข้อมูลด้านล่าง QR Code เพื่อป้องกันการซ้อนทับ
                    // if (data.mobile_link) {
                    //     const linkInfo = document.createElement('div');
                    //     linkInfo.style.cssText = `
                    //         margin-top: 12px;
                    //         padding: 8px;
                    //         background: #f8f9fa;
                    //         border-radius: 6px;
                    //         font-size: 0.85em;
                    //         color: #6b7280;
                    //         text-align: center;
                    //         word-break: break-all;
                    //     `;
                    //     linkInfo.innerHTML = `
                    //         <div style="margin-bottom: 4px; font-weight: 500;">ลิงก์สำหรับมือถือ:</div>
                    //         <div style="font-family: monospace;">${data.mobile_link}</div>
                    //     `;
                    //     qrContainer.appendChild(linkInfo);
                    // }
                };

                qrImg.onerror = () => {
                    throw new Error('ไม่สามารถโหลด QR Code ได้ กรุณาลองใหม่อีกครั้ง');
                };

            } else {
                throw new Error(data.error || 'ไม่สามารถสร้าง QR Code ได้');
            }
        } catch (error) {
            console.error('Error generating QR code:', error);
            qrLoading.style.display = 'block';
            qrLoading.innerHTML = `
                <div style="color: #dc2626; padding: 20px; text-align: center;">
                    <div style="font-size: 2em; margin-bottom: 8px;">❌</div>
                    <p style="font-weight: 500; margin-bottom: 8px;">ไม่สามารถสร้าง QR Code ได้</p>
                    <p style="font-size: 0.9em; color: #6b7280;">${error.message}</p>
                    <button onclick="generateQRCode()" style="margin-top: 12px; padding: 6px 12px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer;">ลองใหม่</button>
                </div>
            `;
        }
    }

    // Event Listener for Copy Mobile Link button (Header) - แก้ไขให้ทำงานได้
    if (copyMobileLinkBtnHeader) {
        copyMobileLinkBtnHeader.addEventListener('click', async () => {
            try {
                const response = await fetch('/generate_mobile_link');
                const data = await response.json();

                if (response.ok && data.mobile_link) {
                    // ใช้ Clipboard API ที่ปลอดภัยกว่า
                    if (navigator.clipboard && window.isSecureContext) {
                        await navigator.clipboard.writeText(data.mobile_link);
                    } else {
                        // Fallback สำหรับเบราว์เซอร์เก่า
                        const textArea = document.createElement('textarea');
                        textArea.value = data.mobile_link;
                        document.body.appendChild(textArea);
                        textArea.select();
                        document.execCommand('copy');
                        document.body.removeChild(textArea);
                    }

                    // แสดงข้อความยืนยัน
                    const originalText = copyMobileLinkBtnHeader.textContent;
                    copyMobileLinkBtnHeader.textContent = '✓ คัดลอกแล้ว';
                    copyMobileLinkBtnHeader.style.background = '#10b981';

                    setTimeout(() => {
                        copyMobileLinkBtnHeader.textContent = originalText;
                        copyMobileLinkBtnHeader.style.background = '';
                    }, 2000);
                } else {
                    alert('ไม่สามารถสร้างลิงก์ได้: ' + (data.error || 'ข้อผิดพลาดไม่ทราบสาเหตุ'));
                }
            } catch (error) {
                console.error('Error copying mobile link:', error);
                alert('เกิดข้อผิดพลาดในการคัดลอกลิงก์: ' + error.message);
            }
        });
    }

    // Event Listener for Show QR button (Header)
    if (showQrBtnHeader) {
        showQrBtnHeader.addEventListener('click', async () => {
            clearQRCode(); // ล้าง QR Code เก่าก่อน
            qrModal.style.display = 'block';
            document.body.style.overflow = 'hidden'; // ล็อค scroll ของ body
            await generateQRCode();
        });
    }

    // Event Listener for Show QR button
    if (showQrBtn) {
        showQrBtn.addEventListener('click', async () => {
            clearQRCode(); // ล้าง QR Code เก่าก่อน
            qrModal.style.display = 'block';
            document.body.style.overflow = 'hidden'; // ล็อค scroll ของ body
            await generateQRCode();
        });
    }

    // Event Listeners for QR Modal
    if (qrModalClose) {
        qrModalClose.addEventListener('click', () => {
            if (qrModal) qrModal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
            // ล้าง QR Code เมื่อปิด modal
            clearQRCode();
        });
    }

    if (closeQrBtn) {
        closeQrBtn.addEventListener('click', () => {
            if (qrModal) qrModal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
            // ล้าง QR Code เมื่อปิด modal
            clearQRCode();
        });
    }

    if (refreshQrBtn) {
        refreshQrBtn.addEventListener('click', async () => {
            // ใช้ clearQRCode function เพื่อล้างทั้งหมด
            clearQRCode();
            await generateQRCode();
        });
    }

    // Close QR modal when clicking outside
    if (qrModal) {
        qrModal.addEventListener('click', (e) => {
            if (e.target === qrModal) {
                qrModal.style.display = 'none';
            }
        });
    }

    // Event Listener for view student list
    if (viewStudentListBtn) {
        viewStudentListBtn.addEventListener('click', async () => {
            if (dataViewModal) {
                dataViewModal.style.display = 'block';
                document.body.style.overflow = 'hidden'; // ล็อค scroll ของ body
            }
            if (dataViewTitle) dataViewTitle.textContent = 'รายชื่อนักศึกษา';
            if (dataViewContent) dataViewContent.innerHTML = '<p>กำลังโหลด...</p>';

            try {
                const response = await fetch('/view_student_list');
                const data = await response.json();

                if (data.success && data.data.length > 0) {
                    let tableHtml = '<table class="data-table"><thead><tr><th>รหัสนักศึกษา</th><th>ชื่อ</th></tr></thead><tbody>';
                    data.data.forEach(item => {
                        // แก้ไขจาก item.student_name เป็น item.name
                        tableHtml += `<tr><td>${item.student_id}</td><td>${item.name}</td></tr>`;
                    });
                    tableHtml += '</tbody></table>';
                    if (dataViewContent) dataViewContent.innerHTML = tableHtml;
                }
            } catch (error) {
                console.error('Error loading student list:', error);
                if (dataViewContent) dataViewContent.innerHTML = '<p>เกิดข้อผิดพลาดในการโหลดข้อมูล</p>';
            }
        });
    }

    // Global click listener to close any active modal
    window.addEventListener('click', (event) => {
        if (modal && event.target === modal) {
            modal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
            cleanupModalEvents();
        }
        if (dataViewModal && event.target === dataViewModal) {
            dataViewModal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
        }
        if (manualAnswerKeyModal && event.target === manualAnswerKeyModal) {
            manualAnswerKeyModal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
        }
        if (scoreEditModal && event.target === scoreEditModal) {
            scoreEditModal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
        }
        if (qrModal && event.target === qrModal) {
            qrModal.style.display = 'none';
            document.body.style.overflow = ''; // ปลดล็อค scroll ของ body
        }
    });

    // --- PDF Support Check ---
    async function checkPdfSupport() {
        try {
            const response = await fetch('/check_pdf_support');
            const data = await response.json();

            if (!data.pdf_supported) {
                // แสดงข้อความเตือนถ้าไม่รองรับ PDF
                const uploadBtn = document.querySelector('label[for="pc-upload-input"]');
                const originalText = uploadBtn.textContent;
                uploadBtn.textContent = 'อัปโหลดไฟล์ (รูปภาพเท่านั้น)';
                uploadBtn.title = 'PDF ไม่รองรับ - ต้องติดตั้ง Poppler';

                // อัปเดต accept attribute
                pcUploadInput.accept = 'image/*';

                // แสดงข้อความเตือนใน placeholder
                const placeholder = document.getElementById('upload-placeholder');
                if (placeholder) {
                    const pdfWarning = document.createElement('div');
                    pdfWarning.style.cssText = 'margin-top: 8px; padding: 8px; background: #fef3c7; border: 1px solid #f59e0b; border-radius: 4px; font-size: 0.8em; color: #92400e;';
                    pdfWarning.innerHTML = '⚠️ PDF ไม่รองรับ - ต้องติดตั้ง Poppler<br><small>ดูไฟล์ install_poppler.md</small>';
                    placeholder.appendChild(pdfWarning);
                }
            }
        } catch (error) {
            console.error('Could not check PDF support:', error);
        }
    }

    // --- Initial Setup ---
    loadInitialImages();
    loadSavedResults();
    loadSavedAnswerKey();
    loadSavedStudentList();
    checkPdfSupport();
    connectToServerEvents();

    function updateDownloadButtons() {
        fetch('/get_download_status')
            .then(res => res.json())
            .then(data => {
                const section = document.getElementById('download-files-section');
                let html = '<h4>ดาวน์โหลดไฟล์ที่อัปโหลดไว้</h4><div class="download-btn-group">';
                if (data.has_answer_key_single) {
                    html += '<a href="/download_answer_key_single" class="btn btn-success" download>ดาวน์โหลดเฉลย 1 ตัวเลือก</a>';
                }
                if (data.has_answer_key_multi) {
                    html += '<a href="/download_answer_key_multi" class="btn btn-info" download>ดาวน์โหลดเฉลยหลายตัวเลือก</a>';
                }
                if (data.has_student_list) {
                    html += '<a href="/download_student_list" class="btn btn-primary" download>ดาวน์โหลดรายชื่อนักศึกษา</a>';
                }
                html += '</div>';
                section.innerHTML = html;
            });
    }

    // เรียกหลังอัปโหลดไฟล์ answer key หรือ student list สำเร็จ
    window.updateDownloadButtons = updateDownloadButtons;

    // และเรียกตอนโหลดหน้าเว็บ
    updateDownloadButtons();

    document.addEventListener('DOMContentLoaded', () => {
        updateDownloadButtons();
    });

    // เพิ่ม event listener สำหรับปุ่ม clear session
    const clearSessionBtn = document.getElementById('new-session-btn');
    if (clearSessionBtn) {
        clearSessionBtn.addEventListener('click', async () => {
            // เรียก API เคลียร์ session
            await fetch('/clear_session', { method: 'POST' });
            // อัปเดตปุ่มดาวน์โหลดทันที
            updateDownloadButtons();
            // รีเฟรชหน้าเว็บอัตโนมัติ
            setTimeout(() => {
                window.location.reload();
            }, 500);
        });
    }
});