"""Packing station validation for parcel content, scanning, and weights."""
import json

class PackChecks:
    def __init__(self,db,bus):
        self.db,self.bus=db,bus

    def pack(self,task_id,measured_weight_g=None,scanned_skus=None):
        task=self.db.one('SELECT * FROM warehouse_tasks WHERE task_id=?',(task_id,))
        if task['state'] not in ('PICKED','ACCEPTED','STOPPED'):
            raise ValueError('Task is not ready for packing')
        contents=json.loads(task['sku_list'])
        expected=[r['sku'] for r in contents]
        if scanned_skus is not None and sorted(expected)!=sorted(scanned_skus):
            self.db.run("UPDATE warehouse_tasks SET state='EXCEPTION' WHERE task_id=?",(task_id,))
            self.bus.publish('warehouse.pack_exception',order_id=task['order_id'],task_id=task_id,
                             package_id=task['package_id'],reason='SKU_MISMATCH')
            return False
        self.db.run("UPDATE warehouse_tasks SET state='PACKED',packed_weight_g=? WHERE task_id=?",
                    (measured_weight_g,task_id))
        self.bus.publish('warehouse.packed',order_id=task['order_id'],task_id=task_id,
                         package_id=task['package_id'],weight_g=measured_weight_g)
        return True

    def verify(self,task_id):
        task=self.db.one('SELECT * FROM warehouse_tasks WHERE task_id=?',(task_id,))
        if task['state']!='PACKED':
            return False
        self.db.run('UPDATE warehouse_tasks SET pack_verified=1 WHERE task_id=?',(task_id,))
        self.bus.publish('warehouse.pack_verified',order_id=task['order_id'],task_id=task_id,
                         package_id=task['package_id'])
        return True
