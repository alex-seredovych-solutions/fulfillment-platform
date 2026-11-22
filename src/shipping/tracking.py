"""Provider tracking callbacks with configurable event-state precedence."""
STATE_ORDER={'LABEL_CREATED':0,'STAGED':1,'RELEASED':2,'SHIPPED':3,'DELIVERED':4}

class TrackingProjection:
    def __init__(self,settings=None):
        self.settings=settings
        self.packages={}

    def ingest(self,package_id,carrier_state,received_at,provider_event_id=None):
        if carrier_state not in STATE_ORDER:
            raise ValueError('Unsupported tracking state')
        last=self.packages.get(package_id)
        if last and provider_event_id and provider_event_id in last.get('provider_event_ids',set()):
            return last['status']
        if self.settings and self.settings.immutable_event_precedence and last:
            if STATE_ORDER[carrier_state]<STATE_ORDER[last['status']]:
                return last['status']
        # Without precedence enforcement, a late LABEL_CREATED callback may
        # overwrite a prior accepted custody scan based only on receive order.
        if last is None or received_at>=last['received_at']:
            seen=set(last.get('provider_event_ids',set())) if last else set()
            if provider_event_id:
                seen.add(provider_event_id)
            self.packages[package_id]={'status':carrier_state,'received_at':received_at,
                                       'provider_event_ids':seen}
        return self.packages[package_id]['status']
