running="/var/run/haproxy-private.pid"
if [ -f "$running" ]
then
	haproxy -f haproxy.conf -sf $(cat /var/run/haproxy-private.pid)
else
	haproxy -f haproxy.conf
fi