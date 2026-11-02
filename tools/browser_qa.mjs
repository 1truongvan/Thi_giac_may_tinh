import {spawn} from 'node:child_process';
import {mkdtemp, readFile, writeFile, mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';

const project = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
const folder = path.join(project, '_backups', 'processing_browser_qa', process.env.QA_BROWSER || 'edge');
await mkdir(folder, {recursive:true});
const executable = process.env.QA_BROWSER === 'chrome' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const output = path.join(folder, 'screenshots');
await mkdir(output, {recursive:true});
const profile = await mkdtemp(path.join(tmpdir(), 'steady-chrome-'));
const browser = spawn(executable, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-allow-origins=*', '--remote-debugging-port=0', `--user-data-dir=${profile}`], {windowsHide:true, stdio:['ignore','ignore','pipe']});
process.once('SIGINT', () => { browser.kill(); process.exit(130); });
browser.stderr.on('data', chunk => console.error(String(chunk).slice(0,800)));
let socket;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const checks = [];
const errors = [];
const badResponses = [];
const keepAlive = setInterval(() => {}, 1000);
function pass(name) { checks.push(name); console.log('PASS', name); }
try {
    let port;
    for (let i=0;i<100;i++) {
        try { port = (await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; } catch {}
        await delay(100);
    }
    assert(port, 'Chrome did not start');
    const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method:'PUT'})).json();
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve,reject) => {socket.onopen=resolve; socket.onerror=reject;});
    const pending = new Map();
    socket.onclose = event => { for(const item of pending.values()) item.reject(new Error('CDP closed '+event.code+' '+event.reason)); pending.clear(); };
    socket.onerror = event => console.error('CDP error',event.message);
    let id = 0;
    socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.id) {
            const item = pending.get(message.id);
            if (!item) return;
            pending.delete(message.id);
            if (message.error) item.reject(new Error(JSON.stringify(message.error)));
            else item.resolve(message.result);
        } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text + ': ' + (message.params.exceptionDetails.exception?.description || ''));
        else if(message.method === 'Network.responseReceived' && message.params.response.status >= 400) badResponses.push({url:message.params.response.url,status:message.params.response.status});
    };
    const send = (method,params={}) => new Promise((resolve,reject) => {
        const current = ++id;
        pending.set(current,{resolve,reject});
        const timeout = setTimeout(() => { if(pending.has(current)) {pending.delete(current);reject(new Error('CDP timeout '+method));} },10000);
        timeout.unref();
        socket.send(JSON.stringify({id:current,method,params}));
    });
    const evaluate = async expression => {
        const result = await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});
        if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
        return result.result.value;
    };
    const until = async expression => {
        for(let i=0;i<150;i++) { if(await evaluate(expression)) return; await delay(100); }
        throw new Error('Timed out: ' + expression);
    };
    const navigate = async route => {
        await send('Page.navigate',{url:'http://127.0.0.1:8766'+route});
        await until(`document.readyState === 'complete' && location.pathname === ${JSON.stringify(route)}`);
    };
    const viewport = width => send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
    const screenshot = async name => {
        await evaluate("document.activeElement?.blur(); scrollTo({top:0,behavior:'instant'})");
        await delay(150);
        const metrics = await send('Page.getLayoutMetrics');
        const size = metrics.cssContentSize || metrics.contentSize;
        const capture = await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:size.width,height:size.height,scale:1}});
        await writeFile(path.join(output,name+'.png'),Buffer.from(capture.data,'base64'));
    };
    await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
    for (const route of ['/', '/workspace/']) {
        await viewport(1440); await navigate(route);
        for(const width of [1440,1024,768,390,320]) {
            await viewport(width); await delay(100);
            const geometry = await evaluate('({viewport:innerWidth,document:document.documentElement.scrollWidth})');
            assert(geometry.document <= geometry.viewport, JSON.stringify({route,width,...geometry}));
            if(width===1440 || width===390) await screenshot((route==='/'?'home':'workspace')+'-'+width);
        }
        pass(route+' responsive 1440/1024/768/390/320 without horizontal overflow');
    }
    await viewport(390); await navigate('/');
    assert(await evaluate(`(() => {document.querySelector('.nav-toggle').click(); return document.querySelector('.nav-toggle').getAttribute('aria-expanded')==='true' && getComputedStyle(document.querySelector('.main-navigation')).display==='flex'})()`));
    pass('mobile menu opens');
    await viewport(1440); await navigate('/workspace/');
    assert(await evaluate(`!document.querySelector('[data-result]') && document.querySelector('[data-submit]').disabled`));
    pass('empty workspace hides result and disables submit');
    const sample = path.join(profile, 'real_sample.mp4');
    const sampleResponse = await fetch('http://127.0.0.1:8766/media/qa_sample.mp4', {signal:AbortSignal.timeout(10000)});
    assert.equal(sampleResponse.status, 200);
    await writeFile(sample, Buffer.from(await sampleResponse.arrayBuffer()));
    const dom = await send('DOM.getDocument');
    const input = await send('DOM.querySelector',{nodeId:dom.root.nodeId,selector:'input[name="video"]'});
    await send('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[sample]});
    await until(`document.querySelector('[data-workspace-root]').dataset.state==='ready'`);
    assert(await evaluate(`!!document.querySelector('[data-source-preview] video') && !document.querySelector('[data-submit]').disabled`));
    pass('file selection creates real local preview');
    assert(await evaluate(`(() => {const transfer=new DataTransfer();transfer.items.add(document.querySelector('input[name="video"]').files[0]);document.querySelector('[data-dropzone]').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));return document.querySelector('[data-workspace-root]').dataset.state==='ready'})()`));
    pass('drag and drop selects a real video');
    assert.equal(await evaluate(`(() => {document.querySelector('form').requestSubmit();return document.querySelector('[data-workspace-root]').dataset.state})()`),'processing');
    pass('processing state is shown during actual POST');
    await until(`document.querySelector('[data-workspace-root]').dataset.state==='complete'`);
    assert.equal(await evaluate('location.pathname'),'/workspace/');
    assert(await evaluate(`!!document.querySelector('[data-result] video') && !!document.querySelector('#source-player')`));
    pass('real OpenCV result appears inside the same Workspace');
    const download = await evaluate(`document.querySelector('.download-button').href`);
    const response = await fetch(download);
    assert.equal(response.status,200);
    assert((await response.arrayBuffer()).byteLength > 100);
    pass('MP4 download returns real nonempty video');
    await screenshot('result-1440');
    await viewport(390); await delay(150); await screenshot('result-390');
    assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'));
    pass('result has no mobile overflow');
    await until(`document.querySelector('#result-player').readyState >= 2`);
    assert(await evaluate(`document.querySelector('#result-player').error === null && !document.querySelector('#result-player').hidden`));
    pass('newly processed H.264 result decodes in the browser');
    assert(await evaluate(`(() => {const charts=Array.from(document.querySelectorAll('[data-motion-chart]'));return charts.length===3 && charts.every(c=>c.width>0 && c.height>0)})()`));
    pass('all three real motion charts render');
    const analysisUrl=await evaluate(`document.querySelector('.analysis-download').href`);
    const analysisResponse=await fetch(analysisUrl);
    assert.equal(analysisResponse.status,200);
    const report=await analysisResponse.json();
    assert.equal(report.output.codec,'h264');
    assert.equal(report.output.pixel_format,'yuv420p');
    assert.equal(report.output.frame_count,12);
    assert.equal(report.before.frames.length,11);
    assert.equal(report.after.frames.length,11);
    assert(report.timings.total_processing_seconds>0);
    pass('JSON download contains real metadata, motion series and timings');
    await evaluate(`(() => {const video=document.querySelector('#result-player'); video.loop=true; video.closest('[data-player]').querySelector('[data-player-toggle]').click()})()`);
    await until(`!document.querySelector('#result-player').paused`);
    await evaluate(`document.querySelector('#result-player').closest('[data-player]').querySelector('[data-player-toggle]').click()`);
    assert(await evaluate(`document.querySelector('#result-player').paused`));
    pass('Play/Pause works on the newly processed H.264 result');
    await evaluate(`document.querySelector('.comparison-details').open=true`);
    await until(`document.querySelector('#comparison-player').readyState>=2`);
    pass('new comparison video decodes in the browser');
    await navigate('/workspace/');
    await evaluate(`(() => {const t=new DataTransfer();t.items.add(new File(['invalid video bytes'],'broken.mp4',{type:'video/mp4'}));const input=document.querySelector('input[name="video"]');input.files=t.files;input.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('form').requestSubmit()})()`);
    await until(`document.querySelector('[data-workspace-root]').dataset.state==='error'`);
    assert(await evaluate(`!document.querySelector('[data-error]').hidden && !document.querySelector('[data-submit]').disabled && !document.querySelector('[data-result]')`));
    pass('real invalid upload shows retry without a fake result');
    assert.deepEqual(errors,[]);
    pass('no uncaught JavaScript exceptions');
    assert.deepEqual(badResponses,[]);
    pass('no HTTP errors for pages, static assets or media');
    await writeFile(path.join(folder,'browser-report.json'),JSON.stringify({checks,errors,badResponses},null,2));
    await send('Browser.close').catch(()=>{});
} finally {
    clearInterval(keepAlive);
    if(socket) socket.close();
    browser.kill();
}
