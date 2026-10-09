"""Carrier manifest response and physical custody record."""
class CarrierHandoff:
    def __init__(self,db,bus,clock):
        self.db,self.bus,self.clock=db,bus,clock

    def accept(self,package_id,manifest_id=None):
        pkg=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not pkg or not pkg['label_id']:
            raise ValueError('Unlabeled package cannot be accepted')
        manifest_id=manifest_id or self.db.new_id('MAN')
        self.db.run("UPDATE packages SET status='SHIPPED', carrier_accepted_at=? WHERE package_id=?",
                    (self.clock.now(),package_id))
        self.bus.publish('carrier.accepted',order_id=pkg['order_id'],package_id=package_id,
                         manifest_id=manifest_id,accepted_at=self.clock.now(),label_id=pkg['label_id'])

    def reject(self,package_id,reason='MANIFEST_REJECTED'):
        pkg=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        self.bus.publish('carrier.rejected',order_id=pkg['order_id'],package_id=package_id,reason=reason)


def acceptance_dedupe_key(package_id, manifest_id):
    return f'{package_id}:accept:{manifest_id}'
