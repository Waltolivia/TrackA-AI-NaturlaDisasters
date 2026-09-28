"""IPAWS adapter placeholder.

FEMA IPAWS access requires choosing/configuring the feed available to this deployment.
Implement fetch() here once credentials/feed details are known; the returned objects should
be NormalizedAlert instances so the rest of the pipeline requires no changes.
"""
async def fetch(*args,**kwargs):
    raise RuntimeError('IPAWS collector is not configured yet')
