'use strict';

window.SteadyCharts = (() => {
    const observers = new WeakMap();

    function mount(root) {
        const dataElement = root.querySelector('#motion-analysis');
        if (!dataElement) return;
        let data;
        try { data = JSON.parse(dataElement.textContent); } catch { return; }
        root.querySelectorAll('[data-motion-chart]').forEach((canvas) => {
            if (observers.has(canvas)) return;
            const key = canvas.dataset.motionChart;
            const before = data.before;
            const after = data.after;
            if (!before?.frames?.length || !after?.frames?.length) return;
            const context = canvas.getContext('2d');
            if (!context) return;
            let selected = null;
            const readout = canvas.parentElement.querySelector('.chart-readout');

            function draw() {
                const width = canvas.clientWidth;
                const height = 210;
                if (!width) return;
                const ratio = window.devicePixelRatio || 1;
                canvas.width = Math.round(width * ratio);
                canvas.height = Math.round(height * ratio);
                context.setTransform(ratio, 0, 0, ratio, 0, 0);
                context.clearRect(0, 0, width, height);
                const pad = {left: 46, right: 16, top: 15, bottom: 30};
                const plotWidth = width - pad.left - pad.right;
                const plotHeight = height - pad.top - pad.bottom;
                const values = before[key].concat(after[key]);
                let min = Math.min(0, ...values);
                let max = Math.max(0, ...values);
                if (max === min) { min -= 0.5; max += 0.5; }
                else { const margin = (max - min) * 0.08; min -= margin; max += margin; }
                const first = Math.min(before.frames[0], after.frames[0]);
                const last = Math.max(before.frames.at(-1), after.frames.at(-1));
                const x = frame => pad.left + (frame - first) / Math.max(1, last - first) * plotWidth;
                const y = value => pad.top + (max - value) / (max - min) * plotHeight;
                context.font = '10px Segoe UI, sans-serif';
                context.lineWidth = 1;
                context.setLineDash([]);
                for (let i = 0; i <= 4; i++) {
                    const value = min + (max - min) * i / 4;
                    context.strokeStyle = '#253346';
                    context.beginPath(); context.moveTo(pad.left, y(value)); context.lineTo(width - pad.right, y(value)); context.stroke();
                    context.fillStyle = '#8195ad'; context.textAlign = 'right';
                    context.fillText(value.toFixed(2), pad.left - 7, y(value) + 3);
                }
                context.textAlign = 'center';
                for (let i = 0; i <= 3; i++) {
                    const frame = Math.round(first + (last - first) * i / 3);
                    context.fillText(String(frame), x(frame), height - 12);
                }
                for (const [series, color, dash] of [[before, '#9c9ec5', [4, 3]], [after, '#38c8ef', []]]) {
                    context.strokeStyle = color;
                    context.lineWidth = 1.7;
                    context.setLineDash(dash);
                    context.beginPath();
                    series.frames.forEach((frame, index) => {
                        if (index === 0) context.moveTo(x(frame), y(series[key][index]));
                        else context.lineTo(x(frame), y(series[key][index]));
                    });
                    context.stroke();
                    if (series.frames.length === 1) {
                        context.fillStyle = color;
                        context.beginPath(); context.arc(x(first), y(series[key][0]), 3, 0, Math.PI * 2); context.fill();
                    }
                }
                if (selected !== null) {
                    const target = first + Math.max(0, Math.min(1, (selected - pad.left) / plotWidth)) * (last - first);
                    const nearest = series => series.frames.reduce((best, frame, index) => Math.abs(frame - target) < Math.abs(series.frames[best] - target) ? index : best, 0);
                    const a = nearest(before), b = nearest(after);
                    context.setLineDash([3, 4]); context.strokeStyle = '#718397';
                    context.beginPath(); context.moveTo(x(before.frames[a]), pad.top); context.lineTo(x(before.frames[a]), height - pad.bottom); context.stroke();
                    readout.textContent = `Frame ${before.frames[a]} · Gốc: ${before[key][a].toFixed(4)} · Kết quả: ${after[key][b].toFixed(4)} pixel/frame`;
                }
            }

            canvas.addEventListener('pointermove', event => { selected = event.clientX - canvas.getBoundingClientRect().left; draw(); });
            canvas.addEventListener('pointerleave', () => { selected = null; draw(); });
            const observer = new ResizeObserver(draw);
            observer.observe(canvas);
            observers.set(canvas, observer);
            draw();
        });
    }

    function unmount(root) {
        root.querySelectorAll('[data-motion-chart]').forEach(canvas => {
            observers.get(canvas)?.disconnect();
            observers.delete(canvas);
        });
    }
    return {mount, unmount};
})();
