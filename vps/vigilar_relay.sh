#!/bin/bash
# Lo corre cron cada 5 minutos (/etc/cron.d/relay-binance). Si el relay no contesta en 10 s, lo reinicia
# y lo anota en /var/log/relay-binance-vigilancia.log. Un 403 sin token quiere decir que anda.
codigo=$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://localhost:8082/anuncios)
if [ "$codigo" != "403" ]; then
  echo "$(date '+%d/%m/%Y %H:%M') no respondió (código $codigo): reiniciado" >> /var/log/relay-binance-vigilancia.log
  systemctl restart relay-binance
fi
