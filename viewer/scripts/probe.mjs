#!/usr/bin/env node
// Load a URL fresh (cache disabled) and report console errors + failed network
// requests + a screenshot. For diagnosing prod load failures.
//   node scripts/probe.mjs <url> <outPng>
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
const [URL, OUT] = process.argv.slice(2);
const PORT = 9355;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn('google-chrome', ['--headless', '--enable-unsafe-swiftshader',
	`--remote-debugging-port=${PORT}`, '--no-sandbox', '--window-size=1280,900', 'about:blank'], { stdio: 'ignore' });
let id = 0;
const send = (ws, method, params = {}) => new Promise((res, rej) => {
	const mid = ++id;
	const h = (ev) => { const m = JSON.parse(ev.data); if (m.id === mid) { ws.removeEventListener('message', h); m.error ? rej(new Error(m.error.message)) : res(m.result); } };
	ws.addEventListener('message', h); ws.send(JSON.stringify({ id: mid, method, params }));
});
const errors = [], failed = [];
try {
	let t; for (let i = 0; i < 40; i++) { try { const r = await fetch(`http://127.0.0.1:${PORT}/json/new`, { method: 'PUT' }); if (r.ok) { t = await r.json(); break; } } catch {} await sleep(250); }
	const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
	ws.addEventListener('message', (ev) => {
		const m = JSON.parse(ev.data);
		if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errors.push(m.params.entry.text);
		if (m.method === 'Runtime.exceptionThrown') errors.push('EXC: ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
		if (m.method === 'Network.loadingFailed') failed.push(`${m.params.type} ${m.params.errorText} ${m.params.requestId}`);
		if (m.method === 'Network.responseReceived' && m.params.response.status >= 400) failed.push(`HTTP ${m.params.response.status} ${m.params.response.url}`);
	});
	await send(ws, 'Page.enable'); await send(ws, 'Runtime.enable'); await send(ws, 'Log.enable'); await send(ws, 'Network.enable');
	await send(ws, 'Network.setCacheDisabled', { cacheDisabled: true });
	await send(ws, 'Page.navigate', { url: URL });
	await sleep(11000);
	const shot = await send(ws, 'Page.captureScreenshot', { format: 'png' });
	if (OUT) writeFileSync(OUT, Buffer.from(shot.data, 'base64'));
	console.log('=== console errors ==='); console.log(errors.length ? errors.join('\n') : '(none)');
	console.log('=== failed/4xx requests ==='); console.log(failed.length ? [...new Set(failed)].join('\n') : '(none)');
	ws.close();
} finally { chrome.kill('SIGKILL'); }
