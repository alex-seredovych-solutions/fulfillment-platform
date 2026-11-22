"""Carrier manifest acceptance, rejection and custody event identity."""
class CarrierHandoff:
    def __init__(self,db,bus,clock,settings=None):
        self.db,self.bus,self.clock,self.settings=db,bus,clock,settings

    def accept(self,package_id,manifest_id=None):
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not package or not package['label_id']:
            raise ValueError('Unlabeled package cannot be accepted')
        label=self.db.one('SELECT * FROM labels WHERE label_id=?',(package['label_id'],))
        if not label or label['state']!='ACTIVE':
            raise ValueError('Current package label is not active')
        manifest_id=manifest_id or self.db.new_id('MAN')
        prior=self.db.one('SELECT * FROM carrier_manifests WHERE manifest_id=?',(manifest_id,))
        if prior:
            if prior['package_id']!=package_id:
                raise ValueError('Manifest ID was reused for a different package')
            return prior['status']=='ACCEPTED'
        if self.settings and self.settings.strict_dispatch_hold and package['status']!='RELEASED':
            raise ValueError('Package has not passed the dispatch gate')
        with self.db.transaction():
            self.db.run('INSERT INTO carrier_manifests VALUES (?,?,?,?,?,?)',
                        (manifest_id,package_id,package['label_id'],'ACCEPTED',self.clock.now(),None))
            self.db.run("UPDATE packages SET status='SHIPPED',carrier_accepted_at=? WHERE package_id=?",
                        (self.clock.now(),package_id))
        self.bus.publish('carrier.accepted',order_id=package['order_id'],package_id=package_id,
                         manifest_id=manifest_id,accepted_at=self.clock.now(),
                         label_id=package['label_id'],tracking_id=f'TRK-{manifest_id}')
        return True

    def reject(self,package_id,reason='MANIFEST_REJECTED',manifest_id=None):
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not package:
            raise KeyError(package_id)
        manifest_id=manifest_id or self.db.new_id('MAN')
        if not self.db.one('SELECT * FROM carrier_manifests WHERE manifest_id=?',(manifest_id,)):
            self.db.run('INSERT INTO carrier_manifests VALUES (?,?,?,?,?,?)',
                        (manifest_id,package_id,package['label_id'] or '',
                         'REJECTED',self.clock.now(),reason))
        # Manifest rejection is a separate event from warehouse release.
        self.bus.publish('carrier.rejected',order_id=package['order_id'],
                         package_id=package_id,manifest_id=manifest_id,reason=reason)
        return manifest_id


def acceptance_dedupe_key(package_id,manifest_id):
    return f'{package_id}:accept:{manifest_id}'
