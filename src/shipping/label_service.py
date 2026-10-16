"""Carrier-label purchases, retries, and package address versions."""
class LabelService:
    def __init__(self,db,bus,clock):
        self.db,self.bus,self.clock=db,bus,clock

    def on_fulfillment_accepted(self,event):
        self.create(event.payload['package_id'])

    def create(self,package_id,service='STANDARD'):
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not package:
            raise KeyError(package_id)
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(package['order_id'],))
        lid=self.db.new_id('LBL')
        self.db.run('INSERT INTO labels VALUES (?,?,?,?,?,?,?)',
                    (lid,package_id,order['address_version'],1,service,'ACTIVE',self.clock.now()))
        self.db.run('UPDATE packages SET label_id=? WHERE package_id=?',(lid,package_id))
        self.bus.publish('shipping.label_created',order_id=package['order_id'],package_id=package_id,
                         label_id=lid,address_version=order['address_version'])
        return lid

    def void(self,label_id):
        self.db.run("UPDATE labels SET state='VOIDED' WHERE label_id=?",(label_id,))
        return True


def label_callback_payload(label_id, package_id, state):
    return {'label_id':label_id,'package_id':package_id,'state':state}


def label_manifest_reference(package_id, label_id):
    return {'package_id':package_id,'label_id':label_id,'source':'label-service'}


def superseded_label_callback(active_label_id, callback_label_id):
    return active_label_id != callback_label_id
