import argparse
import os
from pathlib import Path

import license_store

DB_PATH=os.environ.get('LICENSE_DB_PATH',str(Path(__file__).resolve().parent/'licenses.db'))


def main():
    p=argparse.ArgumentParser(description='TACO License Server 2.0 管理 CLI')
    sp=p.add_subparsers(dest='cmd',required=True)
    q=sp.add_parser('issue'); q.add_argument('--company',required=True); q.add_argument('--tier',choices=sorted(license_store.VALID_TIERS),required=True); q.add_argument('--expires',default=''); q.add_argument('--maintenance-until',default=''); q.add_argument('--max-devices',type=int,default=1); q.add_argument('--channel',choices=['stable','beta'],default='stable'); q.add_argument('--min-version',default=''); q.add_argument('--latest-version',default=''); q.add_argument('--offline-grace-hours',type=int,default=72,help='離線寬限小時，預設 72，範圍 1~720')
    q=sp.add_parser('list')
    q=sp.add_parser('devices'); q.add_argument('--license-id',required=True)
    q=sp.add_parser('revoke'); q.add_argument('--token',required=True)
    q=sp.add_parser('revoke-device'); q.add_argument('--license-id',required=True); q.add_argument('--device-id',required=True)
    q=sp.add_parser('backup'); q.add_argument('--to',default=str(Path(__file__).resolve().parent/'backups'))
    a=p.parse_args()
    if a.cmd=='issue':
        token=license_store.issue_license(DB_PATH,a.company,a.tier,a.expires,maintenance_until=a.maintenance_until,max_devices=a.max_devices,update_channel=a.channel,min_version=a.min_version,latest_version=a.latest_version,offline_grace_hours=a.offline_grace_hours)
        print('授權碼（只顯示這一次）：',token)
    elif a.cmd=='list':
        for x in license_store.list_licenses(DB_PATH): print(x)
    elif a.cmd=='devices':
        for x in license_store.list_devices(DB_PATH,a.license_id): print(x)
    elif a.cmd=='revoke': print('OK' if license_store.revoke_license(DB_PATH,a.token) else 'NOT FOUND')
    elif a.cmd=='revoke-device': print('OK' if license_store.revoke_device(DB_PATH,a.license_id,a.device_id) else 'NOT FOUND')
    elif a.cmd=='backup': print(license_store.backup_db(DB_PATH,a.to))


if __name__=='__main__': main()
