# Usage: stack-scrutiny-disk [uuid|device-name|serial]
# Per-disk SMART detail. The argument is optional on a single-disk host -
# omitting it picks the only registered disk.
function stack-scrutiny-disk --description 'Per-disk SMART detail (omit arg for the only disk)'
    if test (count $argv) -ge 1
        __stack_api GET "/api/scrutiny/disk?disk_id=$argv[1]"
    else
        __stack_api GET /api/scrutiny/disk
    end
end
