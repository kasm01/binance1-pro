#!/bin/bash
# deployment/startup_supervisor.sh
# Supervisor ile botu başlatmak için

# Redis servisinin başlatılması
service redis-server start

# Supervisor ile botu başlat
supervisord -c /etc/supervisor/conf.d/supervisord.conf
