# Usage: stack-notifiarr-test
# Sends a real test message through this stack's Discord webhook, to
# sanity-check the notification path without waiting for a real event.
function stack-notifiarr-test --description 'Send a test Discord notification'
    __stack_api POST /api/notifiarr/test
end
