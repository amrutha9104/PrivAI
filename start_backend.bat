@echo off
cd C:\dev\PrivAI
uvicorn src.main:app --port 8000 --reload