"""Tracking provider callback state projection."""
class TrackingProjection:
    def __init__(self):
        self.packages={}

    def ingest(self,package_id,carrier_state,received_at):
        last=self.packages.get(package_id)
        if last is None or received_at>=last['received_at']:
            self.packages[package_id]={'status':carrier_state,'received_at':received_at}
        return self.packages[package_id]['status']
