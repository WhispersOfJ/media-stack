# Usage: stack-tautulli-newsletters
# Configured Tautulli newsletter definitions, if any.
function stack-tautulli-newsletters --description 'List configured Tautulli newsletters'
    __stack_api GET /api/tautulli/newsletters
end
