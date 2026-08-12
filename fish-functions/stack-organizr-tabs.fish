# Usage: stack-organizr-tabs
# Every tab Organizr currently has, plus which of this stack's services are
# missing one. Includes Organizr's own two built-in type-0 pages (Settings,
# Homepage), which this stack does not manage.
function stack-organizr-tabs --description "List Organizr's configured dashboard tabs"
    __stack_api GET /api/organizr/tabs
end
