#!/bin/bash

cd /home/ubuntu/cryptoauto
git add trading_decisions.sqlite
git commit -m "Update trading decisions $(date '+%Y-%m-%d %H:%M:%S')"
git push origin main
