running="/var/run/haproxy-private.pid"
if [ -f "$running" ]
then
  kill $(cat </var/run/haproxy-private.pid)
fi