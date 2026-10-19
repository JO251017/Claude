#!/bin/bash
cd "$(dirname "$0")"
python3 -m src.cli run --source datalab
read -r -p "끝났습니다. Enter를 누르세요..."
