#!/bin/bash
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
python3 -m src.cli check
read -n1 -p "아무 키나 누르면 닫힙니다."
