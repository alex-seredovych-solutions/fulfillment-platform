"""Carrier service catalog and published pickup windows."""
SERVICE_WINDOWS={'N-A':['11:00','16:00'],'N-B':['11:00','16:00']}

def available_services(node,postal_code):
    if node not in SERVICE_WINDOWS:
        return []
    return ['STANDARD','EXPEDITED'] if len(str(postal_code))>=5 else ['STANDARD']

def pickup_windows(node):
    return SERVICE_WINDOWS.get(node,[])
