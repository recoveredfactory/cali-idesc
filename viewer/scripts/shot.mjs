#!/usr/bin/env node
// Headless screenshot of the viewer over CDP.
//   node scripts/shot.mjs <url> <outPath> [width height]
// Uses the proven recipe: OLD headless + swiftshader (software WebGL) + a real
// debugging port, cache disabled so swapped relief PNGs aren't stale. Waits for
// the map's `idle` event (exposed via window.__map in dev) before capturing.
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const argv = process.argv.slice(2);
const CLEAN = argv.includes('--clean');
const camIdx = argv.indexOf('--cam'); // --cam <zoom,lat,lon>
const CAM = camIdx >= 0 ? argv[camIdx + 1].split(',').map(Number) : null; // [zoom,lat,lon]
const satIdx = argv.indexOf('--sat'); // override relief raster-saturation
const SAT = satIdx >= 0 ? Number(argv[satIdx + 1]) : null;
const conIdx = argv.indexOf('--contrast'); // override relief raster-contrast
const CON = conIdx >= 0 ? Number(argv[conIdx + 1]) : null;
const drop = new Set([camIdx + 1, satIdx + 1, conIdx + 1]);
const rest = argv.filter((a, i) => !['--clean', '--cam', '--sat', '--contrast'].includes(a) && !drop.has(i));
const [URL, OUT, W = '1280', H = '900'] = rest;
if (!URL || !OUT) {
	console.error('usage: shot.mjs <url> <outPath> [width height] [--clean] [--cam zoom,lat,lon]');
	process.exit(1);
}
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn('google-chrome', [
	'--headless', // OLD headless — --headless=new fails WebGL init
	'--enable-unsafe-swiftshader',
	`--remote-debugging-port=${PORT}`,
	'--no-sandbox',
	'--hide-scrollbars',
	`--window-size=${W},${H}`,
	'about:blank'
], { stdio: 'ignore' });

async function cdpTarget() {
	for (let i = 0; i < 40; i++) {
		try {
			const r = await fetch(`http://127.0.0.1:${PORT}/json/new`, { method: 'PUT' });
			if (r.ok) return await r.json();
		} catch { /* not up yet */ }
		await sleep(250);
	}
	throw new Error('chrome devtools never came up');
}

let id = 0;
function rpc(ws, method, params = {}) {
	return new Promise((resolve, reject) => {
		const mid = ++id;
		const onMsg = (event) => {
			const msg = JSON.parse(event.data);
			if (msg.id === mid) {
				ws.removeEventListener('message', onMsg);
				msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
			}
		};
		ws.addEventListener('message', onMsg);
		ws.send(JSON.stringify({ id: mid, method, params }));
	});
}

const evalJs = (ws, expr) =>
	rpc(ws, 'Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });

try {
	const target = await cdpTarget();
	const ws = new WebSocket(target.webSocketDebuggerUrl);
	await new Promise((res) => (ws.onopen = res));

	await rpc(ws, 'Page.enable');
	await rpc(ws, 'Runtime.enable');
	await rpc(ws, 'Network.enable');
	await rpc(ws, 'Network.setCacheDisabled', { cacheDisabled: true });
	await rpc(ws, 'Emulation.setDeviceMetricsOverride', {
		width: +W, height: +H, deviceScaleFactor: 2, mobile: false
	});

	await rpc(ws, 'Page.navigate', { url: URL });
	// Wait for MapLibre to settle: poll the dev-exposed __map for an idle frame.
	let ready = false;
	for (let i = 0; i < 60; i++) {
		await sleep(500);
		const r = await evalJs(ws, `(() => {
			const m = window.__map; if (!m) return 'nomap';
			return (m.loaded() && m.areTilesLoaded && m.areTilesLoaded()) ? 'idle' : 'busy';
		})()`);
		if (r.result?.value === 'idle') { ready = true; break; }
	}
	if (!ready) console.error('warning: map not fully idle, capturing anyway');

	if (CLEAN) {
		// Unobstructed, identically-framed map: drop the dock + top chrome, zero the
		// dock padding, and recenter on the same geographic point so every variant
		// lines up pixel-for-pixel.
		await evalJs(ws, `(() => {
			const css = '.dock,header,.maplibregl-ctrl-top-right,.maplibregl-ctrl-bottom-left{display:none!important}';
			const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
			const m = window.__map;
			if (m) {
				m.setPadding({top:0,right:0,bottom:0,left:0});
				const cam = ${CAM ? JSON.stringify(CAM) : 'null'};
				if (cam) m.jumpTo({center:[cam[2], cam[1]], zoom: cam[0]});
				else { const c = m.getCenter(), z = m.getZoom(); m.jumpTo({center:c, zoom:z}); }
			}
		})()`);
		await sleep(900);
	}
	if (SAT !== null || CON !== null) {
		// Tune the relief raster's render-time punch live (layer id '__dem').
		await evalJs(ws, `(() => { const m = window.__map; if (!m || !m.getLayer('__dem')) return;
			${SAT !== null ? `m.setPaintProperty('__dem','raster-saturation', ${SAT});` : ''}
			${CON !== null ? `m.setPaintProperty('__dem','raster-contrast', ${CON});` : ''}
		})()`);
		await sleep(500);
	}
	await sleep(1200); // let the relief raster paint

	const shot = await rpc(ws, 'Page.captureScreenshot', { format: 'png', fromSurface: true });
	writeFileSync(OUT, Buffer.from(shot.data, 'base64'));
	console.log(`wrote ${OUT}`);
	ws.close();
} finally {
	chrome.kill('SIGKILL');
}
