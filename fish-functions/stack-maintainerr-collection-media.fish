# Usage: stack-maintainerr-collection-media <collection_id>
# Media items inside one tracked collection (see stack-maintainerr-collections).
function stack-maintainerr-collection-media --description 'Show media in one Maintainerr collection'
    if test (count $argv) -ne 1
        echo "Usage: stack-maintainerr-collection-media <collection_id>" >&2
        return 1
    end
    __stack_api GET "/api/maintainerr/collection-media?collection_id=$argv[1]"
end
