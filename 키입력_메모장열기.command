#!/bin/bash
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
open -e .env
