"""Incident records for damaged, missing, or mismatched packages."""
class WarehouseExceptions:
    def __init__(self,bus,db):
        self.bus,self.db=bus,db
        self.incidents=[]

    def on_exception(self,event):
        self.incidents.append({'order_id':event.payload['order_id'],
            'reason':event.payload['reason'],'at':event.occurred_at,
            'task_id':event.payload['task_id']})
        self.bus.publish('operations.exception_recorded',**self.incidents[-1])

    def list_for_order(self,order_id):
        return [x for x in self.incidents if x['order_id']==order_id]
