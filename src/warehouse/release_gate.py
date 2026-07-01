"""Dispatch eligibility immediately before physical handoff."""
class DispatchGate:
    def __init__(self,db,bus,clock,settings):
        self.db,self.bus,self.clock,self.settings=db,bus,clock,settings

    def on_packed(self,event):
        pkg=self.db.one('SELECT * FROM packages WHERE package_id=?',(event.payload['package_id'],))
        if not pkg or not pkg['label_id']:
            return
        if self.settings.strict_dispatch_hold:
            order=self.db.one('SELECT * FROM orders WHERE order_id=?',(pkg['order_id'],))
            from datetime import datetime
            age=(self.clock.current-datetime.fromisoformat(order['accepted_at'])).total_seconds()
            if age<self.settings.cancellation_window_seconds or order['status']=='CANCELLED' or order['risk_state']!='CLEAR':
                return
        self.db.run("UPDATE packages SET status='RELEASED' WHERE package_id=?",(pkg['package_id'],))
        self.db.run("UPDATE warehouse_tasks SET state='RELEASED' WHERE package_id=?",(pkg['package_id'],))
        self.bus.publish('warehouse.released',order_id=pkg['order_id'],package_id=pkg['package_id'],
                         label_id=pkg['label_id'])
