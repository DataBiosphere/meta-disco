"""Package-data home for the slot maps: which of a source's tables and columns speak to
which slot (claims contract 2.4). `anvil_slot_map.yaml` is AnVIL's submitter tables
(#369) and `anvil_published_slot_map.yaml` its published `anvil_file` columns (#497);
`slot_map.py` loads either. Kept beside the runtime that reads them for the reason the
rules and the schema are (#164, #166): available whether `meta_disco` is installed as a
wheel or run from a checkout.
"""
