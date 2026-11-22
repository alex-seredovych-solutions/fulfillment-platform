"""Warehouse dispatch decision at physical carrier-handoff boundary."""
import json
from datetime import datetime

class DispatchGate:
    def __init__(self,db,bus,clock,settings):
        self.db,self.bus,self.clock,self.settings=db,bus,clock,settings

    def evaluate(self,package_id):
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not package:
            raise KeyError(package_id)
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(package['order_id'],))
        task=self.db.one('SELECT * FROM warehouse_tasks WHERE package_id=?',(package_id,))
        label=self.db.one('SELECT * FROM labels WHERE label_id=?',(package['label_id'],)) if package['label_id'] else None
        reasons=[]
        age=(self.clock.current-datetime.fromisoformat(order['accepted_at'])).total_seconds()
        if age<self.settings.cancellation_window_seconds:
            reasons.append('CANCELLATION_WINDOW_OPEN')
        if order['status']=='CANCELLED':
            reasons.append('ORDER_CANCELED')
        if order['risk_state']!='CLEAR':
            reasons.append('RISK_HOLD')
        if not task or task['state'] not in ('PACKED','RELEASED') or not task['pack_verified']:
            reasons.append('PACK_NOT_VERIFIED')
        if not label or label['state']!='ACTIVE':
            reasons.append('NO_ACTIVE_LABEL')
        elif label['address_version']!=order['address_version']:
            reasons.append('STALE_ADDRESS_LABEL')
        shortages=self.db.one("""SELECT COUNT(*) AS n FROM package_lines pl LEFT JOIN reservations r
              ON pl.line_id=r.line_id AND r.status='CONFIRMED'
              WHERE pl.package_id=? AND r.reservation_id IS NULL""",(package_id,))['n']
        if shortages:
            reasons.append('UNCONFIRMED_INVENTORY')
        return {'package_id':package_id,'order_version':order['version'],
                'eligible':not reasons,'reasons':reasons,'label_id':package['label_id']}

    def attempt_release(self,package_id):
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not package or not package['label_id']:
            return False
        decision=self.evaluate(package_id)
        can_release=decision['eligible'] if self.settings.strict_dispatch_hold else True
        self.db.run('INSERT INTO dispatch_decisions VALUES (?,?,?,?,?,?)',
                    (self.db.new_id('GATE'),package_id,'ALLOW' if can_release else 'BLOCK',
                     json.dumps(decision['reasons']),self.clock.now(),decision['order_version']))
        if not can_release:
            self.bus.publish('warehouse.release_blocked',order_id=package['order_id'],
                             package_id=package_id,reasons=decision['reasons'])
            return False
        if package['status']=='RELEASED':
            return True
        self.db.run("UPDATE packages SET status='RELEASED' WHERE package_id=?",(package_id,))
        self.db.run("UPDATE warehouse_tasks SET state='RELEASED' WHERE package_id=?",(package_id,))
        self.bus.publish('warehouse.released',order_id=package['order_id'],package_id=package_id,
                         label_id=package['label_id'],order_version=decision['order_version'])
        return True

    def on_packed(self,event):
        return self.attempt_release(event.payload['package_id'])

    def on_pack_verified(self,event):
        if self.settings.strict_dispatch_hold:
            return self.attempt_release(event.payload['package_id'])
        return False
