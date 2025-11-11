@echo off
cd C:\dev\PrivAI\galene

:: Run with command-line flags only
galene.exe -data .\data -groups .\groups -http :8443 -insecure -turn "" -recordings .\recordings