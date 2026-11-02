'use strict';

(() => {
    document.documentElement.classList.add('js-enabled');

    function bindPlayer(container) {
        if (container.dataset.bound) return;
        container.dataset.bound = 'true';
        const video = container.querySelector('video');
        const toggle = container.querySelector('[data-player-toggle]');
        const metadata = container.querySelector('[data-player-metadata]');
        const error = container.querySelector('[data-player-error]');
        if (!video) return;

        const showPlaybackError = () => {
            video.hidden = true;
            if (error) error.hidden = false;
            if (metadata) metadata.textContent = 'Chưa phát được trên trình duyệt';
            if (toggle) toggle.disabled = true;
        };
        const updateMetadata = () => {
            if (!metadata || !video.videoWidth) return;
            const duration = Number.isFinite(video.duration) ? Math.round(video.duration) : null;
            const time = duration === null ? '' : ` · ${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}`;
            metadata.textContent = `${video.videoWidth} × ${video.videoHeight}${time}`;
            video.hidden = false;
            if (error) error.hidden = true;
            if (toggle) toggle.disabled = false;
        };
        const updateToggle = () => {
            if (!toggle) return;
            const playing = !video.paused && !video.ended;
            toggle.querySelector('span').textContent = playing ? 'Tạm dừng' : 'Phát';
            toggle.setAttribute('aria-label', `${playing ? 'Tạm dừng' : 'Phát'} ${video.getAttribute('aria-label') || 'video'}`);
            const use = toggle.querySelector('use');
            if (use) use.setAttribute('href', use.getAttribute('href').replace(/#[^#]*$/, playing ? '#pause' : '#play'));
        };
        video.addEventListener('loadedmetadata', updateMetadata);
        video.addEventListener('error', showPlaybackError);
        // A failed <source> does not always emit an error on the video element.
        video.querySelectorAll('source').forEach((source) => source.addEventListener('error', showPlaybackError));
        ['play', 'pause', 'ended'].forEach((name) => video.addEventListener(name, updateToggle));
        if (toggle) {
            toggle.addEventListener('click', async () => {
                if (!video.paused) {
                    video.pause();
                    return;
                }
                try {
                    await video.play();
                } catch (failure) {
                    if (failure.name === 'NotSupportedError' || video.error) showPlaybackError();
                    else if (metadata) metadata.textContent = 'Hãy thử phát bằng điều khiển video';
                }
            });
        }
        if (video.error) showPlaybackError();
        if (video.readyState >= 1) updateMetadata();
        updateToggle();
    }

    function initializeWorkspace(root) {
        const form = root.querySelector('[data-upload-form]');
        const input = form.querySelector('input[name="video"]');
        const dropzone = root.querySelector('[data-dropzone]');
        const preview = root.querySelector('[data-source-preview]');
        const placeholder = root.querySelector('[data-drop-placeholder]');
        const localNote = root.querySelector('[data-local-preview-note]');
        const submit = root.querySelector('[data-submit]');
        const status = root.querySelector('[data-status-text]');
        const error = root.querySelector('[data-error]');
        const chooseButtons = root.querySelectorAll('[data-choose-file]');
        let objectUrl = null;
        let busy = false;
        let stopRecovery = () => {};

        root.querySelectorAll('[data-player]').forEach(bindPlayer);
        try { window.SteadyCharts?.mount(root); } catch (failure) { console.error('Motion chart rendering failed', failure); }
        submit.disabled = !input.files.length;

        function resultLocation(jobId) {
            const url = new URL(form.action, window.location.href);
            if (jobId) url.searchParams.set('job', jobId);
            return url;
        }

        function displayResult(html, expectedJob) {
            const documentResult = new DOMParser().parseFromString(html, 'text/html');
            const updated = documentResult.querySelector('[data-workspace-root]');
            const serverError = updated?.querySelector('[data-error-message]')?.textContent.trim();
            if (serverError) throw new Error(serverError);
            if (!updated?.querySelector('[data-result]')) {
                throw new Error('Chưa tạo được video đầu ra. Hãy kiểm tra tệp và thử lại hoặc chọn video khác.');
            }
            if (expectedJob && updated.dataset.jobId !== expectedJob) throw new Error('Phản hồi không khớp mã tác vụ video.');
            releasePreview();
            window.SteadyCharts?.unmount(root);
            root.replaceChildren(...Array.from(updated.childNodes));
            root.dataset.state = 'complete';
            root.dataset.jobId = updated.dataset.jobId || '';
            initializeWorkspace(root);
            if (root.dataset.jobId) history.replaceState(null, '', resultLocation(root.dataset.jobId));
            root.querySelector('[data-result]').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
        }

        function watchSavedResult(jobId, onComplete, onError) {
            const controller = new AbortController();
            let stopped = false;
            let timer;
            const stop = () => { stopped = true; clearTimeout(timer); controller.abort(); };
            const check = async () => {
                try {
                    const url = resultLocation(jobId);
                    url.searchParams.set('result_status', '1');
                    const response = await fetch(url, { cache: 'no-store', credentials: 'same-origin', signal: controller.signal });
                    const state = await response.json();
                    if (state.state === 'complete') {
                        const resultResponse = await fetch(state.result_url, { cache: 'no-store', credentials: 'same-origin', signal: controller.signal });
                        if (!resultResponse.ok) throw new Error('Không đọc được kết quả đã lưu.');
                        const html = await resultResponse.text();
                        if (!stopped) { onComplete(html); stop(); }
                    } else if (state.state === 'error' && onError) {
                        stop();
                        onError(state.message);
                    }
                } catch (failure) {
                    // A temporary status-request failure must not cancel a real upload.
                    if (stopped) return;
                } finally {
                    if (!stopped) timer = setTimeout(check, 3000);
                }
            };
            check();
            return stop;
        }

        if (root.dataset.state === 'waiting' && /^[0-9a-f]{32}$/.test(root.dataset.jobId)) {
            status.textContent = 'Chưa có kết quả đã lưu · Đang kiểm tra mã tác vụ này…';
            stopRecovery = watchSavedResult(root.dataset.jobId, html => displayResult(html, root.dataset.jobId), showError);
        }

        function showError(message) {
            root.querySelector('[data-error-message]').textContent = message;
            error.hidden = false;
            root.dataset.state = 'error';
            status.textContent = 'Chưa hoàn tất · Bạn có thể thử lại';
        }

        function releasePreview() {
            preview.querySelectorAll('video').forEach((video) => {
                video.pause();
                video.removeAttribute('src');
                video.querySelectorAll('source').forEach((source) => source.removeAttribute('src'));
                video.load();
            });
            if (objectUrl) URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }

        function selectVideo() {
            if (busy) return;
            const file = input.files[0];
            if (!file) return;
            stopRecovery();
            const supportedExtension = /\.(mp4|mov|avi|mkv|webm|m4v|mpeg|mpg|wmv|3gp|mts|m2ts|ogv)$/i.test(file.name);
            if (!file.type.startsWith('video/') && !supportedExtension) {
                input.value = '';
                submit.disabled = true;
                showError('Hãy chọn một tệp video hợp lệ.');
                return;
            }
            if (file.size === 0) {
                input.value = '';
                submit.disabled = true;
                showError('Tệp đang trống. Hãy chọn video khác.');
                return;
            }
            releasePreview();
            preview.replaceChildren();
            const video = document.createElement('video');
            objectUrl = URL.createObjectURL(file);
            video.src = objectUrl;
            video.controls = true;
            video.playsInline = true;
            video.preload = 'metadata';
            video.setAttribute('aria-label', 'Xem trước video vừa chọn');
            const player = document.createElement('div');
            player.className = 'video-player';
            player.append(video);
            preview.append(player);
            video.addEventListener('error', () => { localNote.hidden = false; });
            video.addEventListener('loadedmetadata', () => { localNote.hidden = true; });
            preview.hidden = false;
            placeholder.hidden = true;
            localNote.hidden = true;
            error.hidden = true;
            const result = root.querySelector('[data-result]');
            if (result) {
                result.querySelectorAll('video').forEach((element) => element.pause());
                result.hidden = true;
            }
            root.querySelector('[data-file-info]').textContent = `${file.name} · ${(file.size / 1024 / 1024).toLocaleString('vi-VN', { maximumFractionDigits: 2 })} MB`;
            root.querySelector('[data-source-tag]').textContent = 'Đã chọn tệp';
            root.dataset.state = 'ready';
            root.dataset.jobId = '';
            history.replaceState(null, '', resultLocation(null));
            status.textContent = 'Video đã sẵn sàng · Nhấn “Ổn định video” để bắt đầu';
            submit.disabled = false;
        }

        chooseButtons.forEach((button) => button.addEventListener('click', () => { if (!busy) input.click(); }));
        input.addEventListener('change', selectVideo);
        ['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => {
            event.preventDefault();
            if (!busy) dropzone.classList.add('is-dragging');
        }));
        dropzone.addEventListener('dragleave', (event) => {
            if (!dropzone.contains(event.relatedTarget)) dropzone.classList.remove('is-dragging');
        });
        dropzone.addEventListener('drop', (event) => {
            event.preventDefault();
            dropzone.classList.remove('is-dragging');
            if (busy) return;
            const files = event.dataTransfer?.files;
            if (!files?.length) return;
            if (files.length !== 1) {
                showError('Vui lòng chọn một video cho mỗi lần xử lý.');
                return;
            }
            input.files = files;
            selectVideo();
        });

        root.querySelector('[data-retry]').addEventListener('click', () => {
            if (input.files.length) form.requestSubmit();
            else input.click();
        });

        form.addEventListener('submit', async (event) => {
            if (!window.fetch || !window.FormData || !window.DOMParser) return;
            event.preventDefault();
            if (busy) return;
            if (!input.files.length) {
                input.reportValidity();
                return;
            }
            const data = new FormData(form);
            const jobId = window.crypto?.randomUUID?.().replaceAll('-', '') || null;
            if (jobId) {
                data.set('job_id', jobId);
                root.dataset.jobId = jobId;
                history.replaceState(null, '', resultLocation(jobId));
            }
            const postController = new AbortController();
            let completed = false;
            const finish = html => {
                if (completed) return;
                displayResult(html, jobId);
                completed = true;
                stopRecovery();
                postController.abort();
            };
            busy = true;
            root.dataset.state = 'processing';
            form.setAttribute('aria-busy', 'true');
            error.hidden = true;
            root.querySelector('[data-processing]').hidden = false;
            status.textContent = 'Đang tải lên và xử lý video trên máy chủ…';
            submit.disabled = true;
            input.disabled = true;
            chooseButtons.forEach((button) => { button.disabled = true; });
            preview.querySelectorAll('video').forEach((video) => video.pause());
            const result = root.querySelector('[data-result]');
            if (result) result.hidden = true;
            stopRecovery();
            if (jobId) stopRecovery = watchSavedResult(jobId, finish);
            try {
                const response = await fetch(form.action, {
                    method: 'POST', body: data, credentials: 'same-origin',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    signal: postController.signal,
                });
                if (!response.ok) {
                    if (response.status === 403) throw new Error('Phiên gửi biểu mẫu không hợp lệ. Hãy tải lại trang rồi chọn video.');
                    if (response.status === 413) throw new Error('Máy chủ từ chối dung lượng tệp. Hãy thử video nhỏ hơn.');
                    throw new Error('Máy chủ không hoàn tất xử lý. Hãy thử lại hoặc chọn video khác.');
                }
                finish(await response.text());
            } catch (failure) {
                if (completed) return;
                showError(failure instanceof TypeError ? 'Không kết nối được với máy chủ. Kiểm tra kết nối rồi thử lại. Nếu máy chủ đã nhận video, tệp có thể vẫn đang được xử lý.' : failure.message);
            } finally {
                stopRecovery();
                busy = false;
                if (form.isConnected) {
                    form.removeAttribute('aria-busy');
                    root.querySelector('[data-processing]').hidden = true;
                    input.disabled = false;
                    submit.disabled = !input.files.length;
                    chooseButtons.forEach((button) => { button.disabled = false; });
                }
            }
        });
    }

    const root = document.querySelector('[data-workspace-root]');
    if (root) initializeWorkspace(root);
})();
