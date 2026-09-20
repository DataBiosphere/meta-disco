"""Package-data home for the slot maps: which of a source's tables and columns speak to
which slot (claims contract 2.4). `anvil_slot_map.yaml` is the AnVIL one (#369);
`slot_map.py` loads it. Kept beside the runtime that reads it for the reason the rules
and the schema are (#164, #166): available whether `meta_disco` is installed as a wheel
or run from a checkout.
"""
