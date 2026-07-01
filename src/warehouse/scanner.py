"""Warehouse bin/SKU scanning and quantities."""
import json

class Scanner:
    def __init__(self,db,bus):
        self.db,self.bus=db,bus

    def pick(self,task_id,scanned_skus=None):
        task=self.db.one('SELECT * FROM warehouse_tasks WHERE task_id=?',(task_id,))
        if not task:
            raise KeyError(task_id)
        expected=[line['sku'] for line in json.loads(task['sku_list'])]
        if scanned_skus is not None and sorted(expected)!=sorted(scanned_skus):
            self.bus.publish('warehouse.pick_exception',order_id=task['order_id'],task_id=task_id,
                             reason='SKU_MISMATCH')
            self.db.run("UPDATE warehouse_tasks SET state='EXCEPTION' WHERE task_id=?",(task_id,))
            return False
        self.db.run("UPDATE warehouse_tasks SET state='PICKED' WHERE task_id=?",(task_id,))
        self.bus.publish('warehouse.picked',order_id=task['order_id'],task_id=task_id,
                         package_id=task['package_id'])
        return True
