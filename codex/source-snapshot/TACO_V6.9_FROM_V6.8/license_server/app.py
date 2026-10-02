import os
import threading
import time
import ipaddress
from collections import defaultdict, deque

from flask import Flask, jsonify, request

import license_store

DB_PATH=os.environ.get('LICENSE_DB_PATH',os.path.join(os.path.dirname(os.path.abspath(__file__)),'licenses.db'))
VERIFY_LIMIT_PER_MINUTE=max(10,int(os.environ.get('VERIFY_LIMIT_PER_MINUTE','60')))
DEFAULT_OFFLINE_GRACE_HOURS=max(1,min(720,int(os.environ.get('DEFAULT_OFFLINE_GRACE_HOURS','72'))))
LICENSE_HOST=os.environ.get('LICENSE_HOST','127.0.0.1').strip() or '127.0.0.1'
LICENSE_PORT=int(os.environ.get('LICENSE_PORT','5000'))
ALLOW_LAN_TEST=os.environ.get('ALLOW_LAN_TEST','0').strip() == '1'
app=Flask(__name__)
_hits=defaultdict(deque); _lock=threading.Lock()




def _client_allowed(ip):
    # LAN Test Mode only accepts loopback/private/link-local addresses.
    # This prevents accidentally exposing the temporary Flask test server to public clients.
    if not ALLOW_LAN_TEST:
        return True
    try:
        addr=ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private or addr.is_link_local
    except ValueError:
        return False

def _rate_limited(ip):
    now=time.time(); cutoff=now-60
    with _lock:
        q=_hits[ip]
        while q and q[0]<cutoff: q.popleft()
        if len(q)>=VERIFY_LIMIT_PER_MINUTE: return True
        q.append(now); return False


@app.route('/health',methods=['GET'])
def health(): return jsonify({'status':'ok','service':'taco-license-server-2.0'})


@app.route('/verify',methods=['POST'])
def verify():
    client_ip=request.remote_addr or 'unknown'
    if not _client_allowed(client_ip):
        return jsonify({'valid':False,'code':'lan_only','message':'LAN 測試模式只接受本機或私人區域網路來源。'}),403
    if _rate_limited(client_ip):
        return jsonify({'valid':False,'code':'rate_limited','message':'驗證請求過於頻繁，請稍後再試。'}),429
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): return jsonify({'valid':False,'message':'請求格式不正確，需要 JSON body。'}),400
    result=license_store.verify_token(
        DB_PATH,
        str(payload.get('token','')).strip(),
        str(payload.get('app','')).strip(),
        str(payload.get('version','')).strip(),
        str(payload.get('device_id','')).strip(),
        str(payload.get('device_name','')).strip(),
        default_offline_grace_hours=DEFAULT_OFFLINE_GRACE_HOURS,
    )
    return jsonify(result), (200 if result.get('valid') else 403)


if __name__=='__main__':
    license_store.init_db(DB_PATH)
    print(f'TACO License Server 2.0 listening on {LICENSE_HOST}:{LICENSE_PORT}')
    if LICENSE_HOST in ('0.0.0.0','::'):
        print('LAN TEST MODE: temporary testing only; do not expose this Flask server to the Internet.')
    app.run(host=LICENSE_HOST,port=LICENSE_PORT,debug=False)
