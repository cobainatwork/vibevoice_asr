#!/usr/bin/env python3
"""
QC Integration Simulator — exercise the v1 WebSocket and sync endpoints.

Use this to validate the QC integration end-to-end after M6.

Usage:
    # WS upload (recommended)
    python qc_simulator.py ws \\
        --url ws://localhost:8080/api/v1/transcribe \\
        --api-key vva_xxxxxxxxxxxxxxxxxxxxxxx \\
        --audio sample.mp3 \\
        --callback-url https://webhook.site/xxx     (optional)

    # Sync upload (≤2 min audio)
    python qc_simulator.py sync \\
        --url http://localhost:8080/api/v1/transcribe/sync \\
        --api-key vva_xxxxxxxxxxxxxxxxxxxxxxx \\
        --audio short.wav

    # Webhook receiver (for local testing)
    python qc_simulator.py listen --port 9999

Requires: websockets, httpx, aiofiles
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

# Lazy imports so each subcommand only requires what it needs
def _import_ws():
    try:
        import websockets
        import aiofiles
        return websockets, aiofiles
    except ImportError:
        sys.exit("Install dependencies: pip install websockets aiofiles")


def _import_http():
    try:
        import httpx
        return httpx
    except ImportError:
        sys.exit("Install dependencies: pip install httpx")


# ============================================================
# WS upload
# ============================================================


async def ws_transcribe(
    url: str,
    api_key: str,
    audio_path: Path,
    callback_url: str | None = None,
    metadata: dict | None = None,
    chunk_size: int = 256 * 1024,
) -> dict:
    websockets, aiofiles = _import_ws()

    subprotocol = f"bearer.{api_key}"
    print(f"→ Connecting to {url} (subprotocol={subprotocol[:20]}...)")

    async with websockets.connect(url, subprotocols=[subprotocol]) as ws:
        # Wait for ready
        ready = json.loads(await ws.recv())
        if ready.get("type") != "ready":
            raise RuntimeError(f"Expected ready, got: {ready}")
        print(f"← ready (session_id={ready.get('session_id')})")

        # Send start metadata
        start_msg = {
            "type": "start",
            "filename": audio_path.name,
            "mime": _guess_mime(audio_path.suffix),
            "expected_size_bytes": audio_path.stat().st_size,
        }
        if callback_url:
            start_msg["callback_url"] = callback_url
        if metadata:
            start_msg["metadata"] = metadata
        await ws.send(json.dumps(start_msg))
        print(f"→ start (filename={audio_path.name}, size={audio_path.stat().st_size})")

        # Wait for ack
        ack = json.loads(await ws.recv())
        if ack.get("type") != "ack":
            raise RuntimeError(f"Expected ack, got: {ack}")
        print("← ack")

        # Stream audio in chunks
        sent = 0
        async with aiofiles.open(audio_path, "rb") as f:
            while chunk := await f.read(chunk_size):
                await ws.send(chunk)
                sent += len(chunk)
        print(f"→ sent {sent} bytes")

        # Send eof
        await ws.send(json.dumps({"type": "eof"}))
        print("→ eof")

        # Receive until done
        while True:
            msg = json.loads(await ws.recv())
            t = msg.get("type")
            if t == "queued":
                print(f"← queued (job_id={msg.get('job_id')})")
            elif t == "running":
                print(f"← running")
            elif t == "progress":
                print(f"← progress {msg.get('phase')}: {msg.get('value')}")
            elif t == "done":
                print(f"← done ({len(msg.get('segments', []))} segments)")
                return msg
            elif t == "error":
                raise RuntimeError(f"Server error: {msg.get('code')} {msg.get('detail')}")
            else:
                print(f"← unknown msg: {msg}")


def _guess_mime(ext: str) -> str:
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
    }.get(ext.lower(), "application/octet-stream")


# ============================================================
# Sync upload
# ============================================================


async def sync_transcribe(
    url: str,
    api_key: str,
    audio_path: Path,
    metadata: dict | None = None,
    idempotency_key: str | None = None,
) -> dict:
    httpx = _import_http()
    headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    files = {"file": (audio_path.name, audio_path.read_bytes(), _guess_mime(audio_path.suffix))}
    data = {}
    if metadata:
        data["metadata"] = json.dumps(metadata)

    async with httpx.AsyncClient(timeout=300.0) as c:
        r = await c.post(url, headers=headers, files=files, data=data)
    r.raise_for_status()
    return r.json()


# ============================================================
# Webhook listener (test receiver)
# ============================================================


def run_webhook_listener(port: int, secret: str | None = None):
    """Simple HTTP server that prints incoming webhook payloads + verifies HMAC."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            sig = self.headers.get("X-Webhook-Signature", "")
            ts = self.headers.get("X-Webhook-Timestamp", "")
            event = self.headers.get("X-Webhook-Event", "")

            print(f"\n=== Webhook received: {event} ===")
            print(f"Signature: {sig}")
            print(f"Timestamp: {ts}")

            if secret:
                expected = "sha256=" + hmac.new(
                    secret.encode(), f"{ts}.{body.decode()}".encode(),
                    hashlib.sha256
                ).hexdigest()
                ok = hmac.compare_digest(sig, expected)
                print(f"HMAC: {'VALID' if ok else 'INVALID'}")

            try:
                payload = json.loads(body)
                print(f"Payload:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")
            except json.JSONDecodeError:
                print(f"Body: {body[:200]}")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"received": true}')

        def log_message(self, *args, **kwargs):
            pass  # suppress default logging

    print(f"Listening on port {port} (secret {'set' if secret else 'NOT set — HMAC unverified'})")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


# ============================================================
# CLI
# ============================================================


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    ws = sub.add_parser("ws", help="WebSocket upload")
    ws.add_argument("--url", required=True)
    ws.add_argument("--api-key", required=True)
    ws.add_argument("--audio", required=True, type=Path)
    ws.add_argument("--callback-url", default=None)
    ws.add_argument("--metadata", default=None, help="JSON string")

    sync = sub.add_parser("sync", help="Synchronous HTTP upload (≤2 min)")
    sync.add_argument("--url", required=True)
    sync.add_argument("--api-key", required=True)
    sync.add_argument("--audio", required=True, type=Path)
    sync.add_argument("--metadata", default=None)
    sync.add_argument("--idempotency-key", default=None)

    listen = sub.add_parser("listen", help="Run a webhook receiver")
    listen.add_argument("--port", type=int, default=9999)
    listen.add_argument("--secret", default=None, help="Webhook secret (for HMAC verify)")

    args = p.parse_args()

    if args.cmd == "ws":
        meta = json.loads(args.metadata) if args.metadata else None
        result = asyncio.run(ws_transcribe(
            args.url, args.api_key, args.audio, args.callback_url, meta
        ))
        print("\n=== Final result ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.cmd == "sync":
        meta = json.loads(args.metadata) if args.metadata else None
        result = asyncio.run(sync_transcribe(
            args.url, args.api_key, args.audio, meta, args.idempotency_key
        ))
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.cmd == "listen":
        run_webhook_listener(args.port, args.secret)


if __name__ == "__main__":
    main()
