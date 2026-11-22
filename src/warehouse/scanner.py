"""Warehouse item picks, scan identity and quantity reconciliation."""
import json

SERIAL_CONTROLLED_SKUS={'CAMERA'}

class Scanner:
    def __init__(self,db,bus,settings=None,clock=None):
        self.db,self.bus,self.settings,self.clock=db,bus,settings,clock

    def pick(self,task_id,scanned_skus=None,serial_numbers=None,operator_id='warehouse-picker'):
        task=self.db.one('SELECT * FROM warehouse_tasks WHERE task_id=?',(task_id,))
        if not task:
            raise KeyError(task_id)
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(task['order_id'],))
        if (self.settings and self.settings.terminal_order_guards_enabled and
                (task['state']=='STOPPED' or order['status']=='CANCELLED')):
            return self._fail(task,'TASK_STOPPED')
        contents=json.loads(task['sku_list'])
        expected=[line['sku'] for line in contents for _ in range(line['qty'])]
        observed=list(scanned_skus) if scanned_skus is not None else list(expected)
        if sorted(expected)!=sorted(observed):
            return self._fail(task,'SKU_OR_QUANTITY_MISMATCH')
        serial_numbers=serial_numbers or {}
        if self.settings and self.settings.strict_pack_inspection:
            for line in contents:
                if line['sku'] in SERIAL_CONTROLLED_SKUS:
                    numbers=serial_numbers.get(line['line_id'],[])
                    if len(set(numbers))!=line['qty']:
                        return self._fail(task,'MISSING_OR_DUPLICATE_SERIAL')
        self.db.run("UPDATE warehouse_tasks SET state='PICKED' WHERE task_id=?",(task_id,))
        self.bus.publish('warehouse.picked',order_id=task['order_id'],task_id=task_id,
                         package_id=task['package_id'],operator_id=operator_id,
                         scanned_skus=observed,serial_numbers=serial_numbers)
        return True

    def _fail(self,task,reason):
        self.db.run("UPDATE warehouse_tasks SET state='EXCEPTION' WHERE task_id=?",(task['task_id'],))
        self.bus.publish('warehouse.pick_exception',order_id=task['order_id'],
                         task_id=task['task_id'],package_id=task['package_id'],reason=reason)
        return False
