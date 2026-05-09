#!/usr/bin/env python3
"""
Seed a demo project for quick testing.

Usage:
    python scripts/seed_demo_project.py --backend http://localhost:8080
"""
from __future__ import annotations

import argparse
import sys

import httpx


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", default="http://localhost:8080")
    p.add_argument("--name", default="Demo 醫療轉錄")
    args = p.parse_args()

    body = {
        "name": args.name,
        "description": "由 seed 腳本建立的測試專案",
        "hotwords": ["糖尿病", "胰島素", "血糖", "高血壓", "VibeVoice"],
    }

    r = httpx.post(f"{args.backend}/api/admin/projects", json=body, timeout=10)
    if r.status_code == 201:
        proj = r.json()
        print(f"Created project #{proj['id']}: {proj['name']}")
        print(f"  Hotwords: {proj['hotwords']}")
    elif r.status_code == 409:
        print(f"Project '{args.name}' already exists.")
    else:
        print(f"Error {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
