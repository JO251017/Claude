#!/bin/bash
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
python3 -m src.cli init
read -r -p "끝났습니다. Enter를 누르세요..."
