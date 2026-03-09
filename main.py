#!/usr/bin/env python3
"""
Clip Pipeline - Ana Orchestrator
Kullanım: python main.py <youtube_url> [--clips 3] [--lang tr]
"""

import argparse
import sys
from pathlib import Path
from pipeline import ClipPipeline

def main():
    parser = argparse.ArgumentParser(description="YouTube → Viral Klip Pipeline")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--clips", type=int, default=3, help="Kaç klip çıkarılsın (varsayılan: 3)")