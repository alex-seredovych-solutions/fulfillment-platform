"""Fulfillment task creation after an accepted order event."""
import json

class TaskDispatcher:
    def __init__(self,db,bus):
        self.db,self.bus=db,bus

    def on_order_created(self,event):
        order_id=event.payload['order_id']
        lines=self.db.all('SELECT * FROM order_lines WHERE order_id=?',(order_id,))
        for node in sorted(set(r['node'] for r in lines)):
            contents=[{'line_id':r['line_id'],'sku':r['sku'],'qty':r['quantity']} for r in lines if r['node']==node]
            package_id=self.db.new_id('PKG')
            task_id=self.db.new_id('WMS')
            self.db.run('INSERT INTO packages VALUES (?,?,?,?,?,?)',(package_id,order_id,node,'ALLOCATED',None,None))
            self.db.run('INSERT INTO warehouse_tasks VALUES (?,?,?,?,?,?,?,?)',
                        (task_id,order_id,package_id,node,'ACCEPTED',json.dumps(contents),None,0))
            self.bus.publish('fulfillment.accepted',order_id=order_id,package_id=package_id,
                             task_id=task_id,node=node)

    def on_order_cancelled(self,event):
        self.db.run("UPDATE warehouse_tasks SET state='STOPPED' WHERE order_id=? AND state NOT IN ('RELEASED')",
                    (event.payload['order_id'],))

    def on_pack_completed(self,event):
        self.db.run("UPDATE warehouse_tasks SET state='PACKED' WHERE task_id=?",(event.payload['task_id'],))

    def tasks(self,order_id):
        return self.db.all('SELECT * FROM warehouse_tasks WHERE order_id=?',(order_id,))
