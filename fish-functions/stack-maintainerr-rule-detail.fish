# Usage: stack-maintainerr-rule-detail <rule_id>
# Full definition of a single Maintainerr rule (see stack-maintainerr-rules).
function stack-maintainerr-rule-detail --description 'Show one Maintainerr rule in full'
    if test (count $argv) -ne 1
        echo "Usage: stack-maintainerr-rule-detail <rule_id>" >&2
        return 1
    end
    __stack_api GET "/api/maintainerr/rule-detail?rule_id=$argv[1]"
end
