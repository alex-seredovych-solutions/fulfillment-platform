"""Warehouse task allocation, package lineage and asynchronous state changes."""
import json

class TaskDispatcher:
    def __init__(self,db,bus):
        self.db,self.bus=db,bus

    def on_order_created(self,event):
        order_id=event.payload['order_id']
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(order_id,))
        if not order or order['status']=='CANCELLED':
            return
        lines=self.db.all('SELECT * FROM order_lines WHERE order_id=?',(order_id,))
        for node in sorted({row['node'] for row in lines}):
            existing=self.db.one('SELECT * FROM packages WHERE order_id=? AND node=?',(order_id,node))
            if existing:
                continue
            selected=[row for row in lines if row['node']==node]
            contents=[{'line_id':row['line_id'],'sku':row['sku'],'qty':row['quantity']}
                      for row in selected]
            package_id=self.db.new_id('PKG')
            task_id=self.db.new_id('WMS')
            with self.db.transaction():
                self.db.run('INSERT INTO packages VALUES (?,?,?,?,?,?)',
                            (package_id,order_id,node,'ALLOCATED',None,None))
                self.db.run('INSERT INTO warehouse_tasks VALUES (?,?,?,?,?,?,?,?)',
                            (task_id,order_id,package_id,node,'ACCEPTED',
                             json.dumps(contents,sort_keys=True),None,0))
                for line in selected:
                    self.db.run('INSERT INTO package_lines VALUES (?,?,?)',
                                (package_id,line['line_id'],line['quantity']))
            # Task assignment and inventory reservation are separate asynchronous flows.
            self.bus.publish('fulfillment.accepted',order_id=order_id,package_id=package_id,
                             task_id=task_id,node=node,order_version=order['version'])

    def on_order_cancelled(self,event):
        self.db.run("UPDATE warehouse_tasks SET state='STOPPED' "
                    "WHERE order_id=? AND state NOT IN ('RELEASED')",
                    (event.payload['order_id'],))
        self.bus.publish('fulfillment.stop_requested',order_id=event.payload['order_id'],
                         order_version=event.payload.get('version'))

    def on_pack_completed(self,event):
        row=self.db.one('SELECT * FROM warehouse_tasks WHERE task_id=?',(event.payload['task_id'],))
        if not row:
            return
        # Pack-completion messages update the task projection on receipt.
        self.db.run("UPDATE warehouse_tasks SET state='PACKED' WHERE task_id=?",
                    (event.payload['task_id'],))

    def tasks(self,order_id):
        return self.db.all('SELECT * FROM warehouse_tasks WHERE order_id=? ORDER BY task_id',
                           (order_id,))

    def package_contents(self,package_id):
        return self.db.all('SELECT ol.line_id,ol.sku,pl.quantity FROM package_lines pl '
                           'JOIN order_lines ol ON ol.line_id=pl.line_id WHERE pl.package_id=?',
                           (package_id,))
