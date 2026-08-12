# Usage: stack-organizr-sync
# Adds an Organizr tab for any service in the canonical table
# (control-panel/services/organizr/tabs.py) that doesn't have one yet.
# Additive only - never edits or deletes an existing tab, so anything
# hand-tweaked in Organizr's UI survives. Run this after adding a service
# to the stack.
function stack-organizr-sync --description 'Add any missing stack service as an Organizr tab'
    __stack_api POST /api/organizr/tabs/sync
end
