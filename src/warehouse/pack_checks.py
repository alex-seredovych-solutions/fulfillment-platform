"""Pack-station rules for SKUs, weight, secondary verification and exceptions.

Physical inspection results are persisted separately from warehouse task states;
verification policies are enabled per fulfillment deployment.
"""
import json

CATALOG_WEIGHT_G={'CAMERA':950,'BOOK':550,'WIDGET':400,'HEADPHONES':360}

class PackChecks:
    def __init__(self,db,bus,clock=None,settings=None):
        self.db,self.bus,self.clock,self.settings=db,bus,clock,settings

    def _task_and_contents(self,task_id):
        task=self.db.one('SELECT * FROM warehouse_tasks WHERE task_id=?',(task_id,))
        if task is None:
            raise KeyError(task_id)
        return task,json.loads(task['sku_list'])

    def _expected_weight(self,contents):
        # Packaging dunnage weight is an estimate and is not a substitute
        # for the actual measured parcel weight at the station.
        return 150+sum(CATALOG_WEIGHT_G.get(row['sku'],300)*row['qty'] for row in contents)

    def _paid_merchandise(self,contents):
        total=0
        for row in contents:
            allocation=self.db.one('SELECT merchandise_cents,coupon_allocated_cents,points_allocated_cents '
                                   'FROM order_line_allocations WHERE line_id=?',(row['line_id'],))
            if allocation:
                total+=allocation['merchandise_cents']-allocation['coupon_allocated_cents']-allocation['points_allocated_cents']
        return total

    def pack(self,task_id,measured_weight_g=None,scanned_skus=None,second_operator_id=None):
        task,contents=self._task_and_contents(task_id)
        if task['state'] not in ('PICKED','ACCEPTED','STOPPED'):
            raise ValueError('Task is not ready for packing')
        expected=[row['sku'] for row in contents for _ in range(row['qty'])]
        observed=list(scanned_skus) if scanned_skus is not None else list(expected)
        if sorted(expected)!=sorted(observed):
            return self._exception(task,expected,observed,measured_weight_g,
                                   second_operator_id,'SKU_MISMATCH')
        if measured_weight_g is not None and measured_weight_g<=0:
            return self._exception(task,expected,observed,measured_weight_g,
                                   second_operator_id,'INVALID_WEIGHT')
        weight=self._expected_weight(contents)
        reason=None
        if self.settings and self.settings.strict_pack_inspection:
            if measured_weight_g is None:
                reason='MISSING_WEIGHT'
            elif weight_variance_percent(measured_weight_g,weight)>self.settings.weight_tolerance_percent:
                reason='WEIGHT_VARIANCE'
            elif (self._paid_merchandise(contents)>=self.settings.signing_threshold_cents
                  and not second_operator_id):
                reason='MISSING_SECOND_VERIFIER'
        if reason:
            return self._exception(task,expected,observed,measured_weight_g,second_operator_id,reason)
        self._audit(task,expected,observed,measured_weight_g,weight,second_operator_id,'PASS',None)
        self.db.run('UPDATE warehouse_tasks SET state=?,packed_weight_g=? WHERE task_id=?',
                    ('PACKED',measured_weight_g,task_id))
        self.bus.publish('warehouse.packed',order_id=task['order_id'],task_id=task_id,
                         package_id=task['package_id'],weight_g=measured_weight_g,
                         expected_weight_g=weight)
        return True

    def _audit(self,task,expected,observed,measured,expected_weight,secondary,outcome,reason):
        self.db.run('INSERT INTO pack_inspections VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (self.db.new_id('INSP'),task['task_id'],task['package_id'],
                     json.dumps(expected),json.dumps(observed),measured,expected_weight,
                     secondary,outcome,reason,self.clock.now() if self.clock else 'UNKNOWN'))

    def _exception(self,task,expected,observed,measured,secondary,reason):
        self._audit(task,expected,observed,measured,self._expected_weight(json.loads(task['sku_list'])),
                    secondary,'FAIL',reason)
        self.db.run("UPDATE warehouse_tasks SET state='EXCEPTION',pack_verified=0 WHERE task_id=?",
                    (task['task_id'],))
        self.bus.publish('warehouse.pack_exception',order_id=task['order_id'],
                         task_id=task['task_id'],package_id=task['package_id'],reason=reason)
        return False

    def verify(self,task_id):
        task=self.db.one('SELECT * FROM warehouse_tasks WHERE task_id=?',(task_id,))
        if task is None or task['state']!='PACKED':
            return False
        if self.settings and self.settings.strict_pack_inspection:
            inspection=self.db.one('SELECT * FROM pack_inspections WHERE task_id=? '
                                   'ORDER BY inspection_id DESC LIMIT 1',(task_id,))
            if not inspection or inspection['outcome']!='PASS':
                return False
        self.db.run('UPDATE warehouse_tasks SET pack_verified=1 WHERE task_id=?',(task_id,))
        self.bus.publish('warehouse.pack_verified',order_id=task['order_id'],task_id=task_id,
                         package_id=task['package_id'],verified_at=self.clock.now() if self.clock else None)
        return True


def weight_variance_percent(measured_grams,expected_grams):
    if measured_grams is None or expected_grams<=0:
        return None
    return 100.0*abs(measured_grams-expected_grams)/expected_grams

def packing_release_metadata(task_id,package_id,verified):
    return {'task_id':task_id,'package_id':package_id,'pack_verified':bool(verified)}
