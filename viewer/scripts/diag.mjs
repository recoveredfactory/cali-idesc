#!/usr/bin/env node
// Diagnostic: report WebGL MAX_TEXTURE_SIZE + the relief image source dims on a
// running map, and whether the dem image exceeds the texture cap (-> downscaled).
//   node scripts/diag.mjs <url>
import { spawn } from 'node:child_process';
const URL = process.argv[2];
const PORT = 9344;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn('google-chrome', ['--headless', '--enable-unsafe-swiftshader',
	`--remote-debugging-port=${PORT}`, '--no-sandbox', '--window-size=1280,900', 'about:blank'],
	{ stdio: 'ignore' });
let id = 0;
function rpc(ws, method, params = {}) {
	return new Promise((res, rej) => {
		const mid = ++id;
		const h = (ev) => { const m = JSON.parse(ev.data); if (m.id === mid) { ws.removeEventListener('message', h); m.error ? rej(new Error(m.error.message)) : res(m.result); } };
		ws.addEventListener('message', h); ws.send(JSON.stringify({ id: mid, method, params }));
	});
}
const ev = (ws, e) => rpc(ws, 'Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true });
try {
	let t; for (let i = 0; i < 40; i++) { try { const r = await fetch(`http://127.0.0.1:${PORT}/json/new`, { method: 'PUT' }); if (r.ok) { t = await r.json(); break; } } catch {} await sleep(250); }
	const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
	await rpc(ws, 'Page.enable'); await rpc(ws, 'Runtime.enable');
	await rpc(ws, 'Page.navigate', { url: URL });
	await sleep(9000);
	const out = await ev(ws, `(() => {
		const c = document.createElement('canvas');
		const gl = c.getContext('webgl2') || c.getContext('webgl');
		const max = gl ? gl.getParameter(gl.MAX_TEXTURE_SIZE) : 'no-gl';
		const m = window.__map;
		let dem = 'no __map (prod build)';
		if (m) { const s = m.getStyle && m.getStyle().sources; dem = s && s['__dem-src'] ? JSON.stringify(s['__dem-src']).slice(0,200) : 'no __dem-src'; }
		return { maxTextureSize: max, dem };
	})()`);
	console.log(JSON.stringify(out.result.value, null, 2));
	ws.close();
} finally { chrome.kill('SIGKILL'); }
