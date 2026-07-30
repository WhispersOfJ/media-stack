# Usage: stack-kometa-config
# Which libraries/collections Kometa's config.yml is set to touch.
function stack-kometa-config --description 'Show Kometa configured libraries'
    __stack_api GET /api/kometa/config
end
