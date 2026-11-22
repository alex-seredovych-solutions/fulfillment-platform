"""Carrier label lifecycle and source order address-version coordination."""
class LabelService:
    def __init__(self,db,bus,clock):
        self.db,self.bus,self.clock=db,bus,clock

    def on_fulfillment_accepted(self,event):
        return self.create(event.payload['package_id'])

    def create(self,package_id,service='STANDARD'):
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not package:
            raise KeyError(package_id)
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(package['order_id'],))
        if service not in ('STANDARD','EXPEDITED','SIGNATURE'):
            raise ValueError('Unsupported carrier service')
        # Existing provider client generates a new purchase per request. It does
        # not reuse a stable package-version idempotency key on retry.
        label_id=self.db.new_id('LBL')
        previous=self.db.one('SELECT MAX(package_version) AS v FROM labels WHERE package_id=?',(package_id,))
        version=previous['v'] or 1
        self.db.run('INSERT INTO labels VALUES (?,?,?,?,?,?,?)',
                    (label_id,package_id,order['address_version'],version,
                     service,'ACTIVE',self.clock.now()))
        self.db.run('UPDATE packages SET label_id=? WHERE package_id=?',(label_id,package_id))
        self.bus.publish('shipping.label_created',order_id=package['order_id'],
                         package_id=package_id,label_id=label_id,
                         address_version=order['address_version'],package_version=version)
        return label_id

    def replace_after_address_change(self,package_id,new_service='STANDARD'):
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not package:
            raise KeyError(package_id)
        if package['carrier_accepted_at']:
            raise ValueError('Cannot replace label after carrier custody')
        active=self.db.all("SELECT * FROM labels WHERE package_id=? AND state='ACTIVE'",
                           (package_id,))
        for row in active:
            self.void(row['label_id'])
        # This is a best-effort local transition. In a real provider, the void
        # can complete asynchronously, allowing a new label before final void.
        return self.create(package_id,service=new_service)

    def void(self,label_id):
        current=self.db.one('SELECT * FROM labels WHERE label_id=?',(label_id,))
        if not current:
            raise KeyError(label_id)
        if current['state']=='VOIDED':
            return True
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(current['package_id'],))
        if package['carrier_accepted_at']:
            return False
        self.db.run("UPDATE labels SET state='VOIDED' WHERE label_id=?",(label_id,))
        self.bus.publish('shipping.label_voided',package_id=current['package_id'],label_id=label_id)
        return True

    def active_for(self,package_id):
        return self.db.all("SELECT * FROM labels WHERE package_id=? AND state='ACTIVE'",
                           (package_id,))


def label_callback_payload(label_id,package_id,state):
    return {'label_id':label_id,'package_id':package_id,'state':state}

def label_manifest_reference(package_id,label_id):
    return {'package_id':package_id,'label_id':label_id,'source':'label-service'}

def superseded_label_callback(active_label_id,callback_label_id):
    return active_label_id!=callback_label_id
