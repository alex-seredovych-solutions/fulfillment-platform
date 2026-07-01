"""Warehouse-node selection based on inventory quotes and fulfillment capacity."""
class NodeAllocation:
    def __init__(self,availability):
        self.availability=availability

    def choose(self,sku,qty,preferred='N-A'):
        candidates=self.availability.quote(sku,qty)
        for candidate in sorted(candidates,key=lambda x:x['node']!=preferred):
            if candidate['can_fulfill']:
                return candidate['node']
        return None
